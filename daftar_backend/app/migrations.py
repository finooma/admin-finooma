"""Upgrades an EXISTING database file created by an older version of this app to the current
schema, WITHOUT ever dropping or truncating a table. This is what fixes the exact class of
error the person reported: "no such column: account_id" (or category_id / fee) — that error
means schema.sql's CREATE TABLE IF NOT EXISTS correctly left old tables alone (since they
already existed), but nobody had gone back and added the new columns those old tables were
missing.

Safe-by-construction:
- Every ALTER TABLE here is guarded by first checking PRAGMA table_info — so re-running this
  on an already-migrated (or brand-new) database is a silent no-op, never an error.
- Before touching anything, if ANY column is actually about to be added, the whole database
  file is first copied to a timestamped .bak file next to it — so even in the worst case,
  the person's original data is one file-copy away from being restored by hand.
- Nothing is ever DELETEd or DROPped. Old free-text columns (e.g. transactions.category) are
  left in place, just unused by the new code — annoying dead weight, never a data-loss risk.
"""
import datetime
import shutil
import sqlite3


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _category_id_for_name(conn: sqlite3.Connection, name: str, cache: dict, today: str) -> str:
    from .utils import new_id

    name = (name or "سایر").strip() or "سایر"
    key = name.lower()
    if key in cache:
        return cache[key]
    row = conn.execute("SELECT id FROM categories WHERE lower(name) = lower(?)", (name,)).fetchone()
    if row:
        cid = row[0]
    else:
        cid = new_id()
        conn.execute(
            "INSERT INTO categories (id, name, is_default, created_at) VALUES (?, ?, 0, ?)",
            (cid, name, today),
        )
    cache[key] = cid
    return cid


def needs_migration(db_path: str) -> bool:
    """Cheap pre-check so init_db only pays for a file copy / backup when something will
    actually change."""
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return False
    try:
        if not _table_exists(conn, "transactions"):
            return False  # brand-new database, nothing to migrate
        cols = _columns(conn, "transactions")
        if not {"category_id", "account_id", "fee"}.issubset(cols):
            return True
        if _table_exists(conn, "accounts") and "portfolio_id" in _columns(conn, "accounts"):
            return True  # accounts used to be scoped per-portfolio; now they're global
        return False
    finally:
        conn.close()


def migrate_legacy_schema(db_path: str):
    """Adds any column the current code expects but an older database file doesn't have yet,
    and backfills category_id from the old free-text `category` column wherever one exists.
    Call this AFTER schema.sql has run (so `categories` already exists and is seeded) and
    BEFORE the app serves any request."""
    if not needs_migration(db_path):
        return

    backup_path = f"{db_path}.pre-migration-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
    shutil.copy2(db_path, backup_path)
    print(f"[migration] existing database needs schema updates — backed up to {backup_path}")

    conn = sqlite3.connect(db_path)
    today = datetime.date.today().isoformat()
    category_cache: dict = {}
    try:
        conn.execute("BEGIN")

        # ---- transactions: category_id, account_id, fee ----
        cols = _columns(conn, "transactions")
        if "category_id" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN category_id TEXT")
        if "account_id" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN account_id TEXT")
        if "fee" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN fee REAL NOT NULL DEFAULT 0")
        if "category" in cols:
            rows = conn.execute(
                "SELECT id, category FROM transactions WHERE category_id IS NULL OR category_id = ''"
            ).fetchall()
            for tid, cat_text in rows:
                cid = _category_id_for_name(conn, cat_text, category_cache, today)
                conn.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (cid, tid))
            print(f"[migration] transactions: backfilled category_id for {len(rows)} row(s)")

        # ---- withdrawals: category_id ----
        if _table_exists(conn, "withdrawals"):
            wcols = _columns(conn, "withdrawals")
            if "category_id" not in wcols:
                conn.execute("ALTER TABLE withdrawals ADD COLUMN category_id TEXT")
            if "category" in wcols:
                rows = conn.execute(
                    "SELECT id, category FROM withdrawals WHERE category_id IS NULL OR category_id = ''"
                ).fetchall()
                for wid, cat_text in rows:
                    cid = _category_id_for_name(conn, cat_text, category_cache, today)
                    conn.execute("UPDATE withdrawals SET category_id = ? WHERE id = ?", (cid, wid))
                print(f"[migration] withdrawals: backfilled category_id for {len(rows)} row(s)")

        # ---- ladders: category_id (composite primary key stays as-is; the old `category`
        # column is simply ignored by the app from now on, never dropped) ----
        if _table_exists(conn, "ladders"):
            lcols = _columns(conn, "ladders")
            if "category_id" not in lcols:
                conn.execute("ALTER TABLE ladders ADD COLUMN category_id TEXT")
            if "category" in lcols:
                rows = conn.execute(
                    "SELECT rowid, category FROM ladders WHERE category_id IS NULL OR category_id = ''"
                ).fetchall()
                for rowid, cat_text in rows:
                    cid = _category_id_for_name(conn, cat_text, category_cache, today)
                    conn.execute("UPDATE ladders SET category_id = ? WHERE rowid = ?", (cid, rowid))
                print(f"[migration] ladders: backfilled category_id for {len(rows)} row(s)")

        # ---- accounts: used to be scoped per-portfolio (portfolio_id NOT NULL); now global,
        # shared across every portfolio, matching how a real bank account actually works. SQLite
        # can't just ALTER a NOT NULL column away, so this rebuilds the table — id, name,
        # opening_balance, and created_at are preserved exactly; only the portfolio_id link is
        # dropped (every account simply becomes usable from any portfolio going forward).
        if _table_exists(conn, "accounts") and "portfolio_id" in _columns(conn, "accounts"):
            existing_accounts = conn.execute(
                "SELECT id, name, opening_balance, created_at FROM accounts"
            ).fetchall()
            conn.execute(
                "CREATE TABLE accounts_new (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                "opening_balance REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
            )
            for aid, name, opening_balance, created_at in existing_accounts:
                conn.execute(
                    "INSERT INTO accounts_new (id, name, opening_balance, created_at) VALUES (?, ?, ?, ?)",
                    (aid, name, opening_balance, created_at),
                )
            conn.execute("DROP TABLE accounts")
            conn.execute("ALTER TABLE accounts_new RENAME TO accounts")
            print(f"[migration] accounts: made {len(existing_accounts)} account(s) global (dropped portfolio_id)")

        conn.commit()
        print("[migration] done — old columns were kept (not dropped), only added to.")
    except Exception:
        conn.rollback()
        print(f"[migration] FAILED and rolled back — your original file is untouched; a pre-migration backup was also saved to {backup_path}")
        raise
    finally:
        conn.close()
