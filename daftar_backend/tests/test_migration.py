import os
import sys
import sqlite3
import time
import uuid
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def _uid():
    return uuid.uuid4().hex[:16]


def _make_legacy_db(path):
    """Builds a database matching the OLD (pre-v2) schema: transactions/withdrawals/ladders
    keyed by free-text `category`, no account_id, no fee column — exactly what a database
    created before the categories/accounts/fee redesign looks like."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL, role TEXT NOT NULL, allowed_tabs TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE portfolios (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE transactions (
            id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, ts INTEGER NOT NULL, type TEXT NOT NULL,
            date TEXT NOT NULL, asset TEXT NOT NULL, category TEXT NOT NULL, qty REAL NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0, amount REAL NOT NULL DEFAULT 0, location TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE withdrawals (
            id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, ts INTEGER NOT NULL, category TEXT NOT NULL,
            date TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0, dest TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '', level INTEGER, source_txn_id TEXT
        );
        CREATE TABLE prices (asset TEXT PRIMARY KEY, price REAL NOT NULL DEFAULT 0, updated_at TEXT);
        CREATE TABLE snapshots (
            id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, date TEXT NOT NULL,
            total_value REAL NOT NULL DEFAULT 0, total_investment REAL NOT NULL DEFAULT 0,
            total_unrealized REAL NOT NULL DEFAULT 0, total_realized REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE ladders (
            portfolio_id TEXT NOT NULL, category TEXT NOT NULL, idx INTEGER NOT NULL,
            threshold_pct REAL NOT NULL, withdraw_pct REAL NOT NULL,
            PRIMARY KEY (portfolio_id, category, idx)
        );
    """)
    admin_id = _uid()
    conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)",
                 (admin_id, 'admin', 'placeholder-hash', 'Admin', 'admin', None, '2026-01-01'))
    pid = _uid()
    conn.execute("INSERT INTO portfolios VALUES (?,?,?)", (pid, 'Main', '2026-01-01'))
    tid = _uid()
    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (tid, pid, int(time.time() * 1000), 'buy', '1404/01/01', 'BTC', 'کریپتو', 1, 1000, 1000, '', ''))
    tid2 = _uid()
    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (tid2, pid, int(time.time() * 1000), 'buy', '1404/01/02', 'GOLDX', 'کتگوری سفارشی قدیمی', 1, 500, 500, '', ''))
    wid = _uid()
    conn.execute("INSERT INTO withdrawals VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (wid, pid, int(time.time() * 1000), 'کریپتو', '1404/02/01', 100, 'نقد', '', None, None))
    conn.execute("INSERT INTO ladders VALUES (?,?,?,?,?)", (pid, 'کریپتو', 0, 70, 50))
    conn.commit()
    conn.close()
    return pid


def test_legacy_database_migrates_without_data_loss(tmp_path=None):
    import tempfile
    db_path = os.path.join(tempfile.mkdtemp(), "legacy.sqlite3")
    for f in glob.glob(db_path + "*.bak"):
        os.remove(f)

    pid = _make_legacy_db(db_path)

    # Booting the app must not raise (this is exactly the bug report: "no such column: account_id")
    app = create_app({"DATABASE_PATH": db_path, "TESTING": True})

    # A backup file must have been created before anything was altered.
    backups = glob.glob(db_path + "*.bak")
    assert backups, "expected a pre-migration backup file to be created"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Old data is still there, untouched, AND now has category_id populated.
    txns = conn.execute("SELECT * FROM transactions ORDER BY date").fetchall()
    assert len(txns) == 2
    assert all(t["category_id"] for t in txns), "every old transaction should get a backfilled category_id"
    assert txns[0]["category"] == "کریپتو"  # old column preserved, not dropped
    assert txns[0]["fee"] == 0  # new column defaulted safely

    # The pre-existing "کریپتو" transaction must map to the SAME category row the app already
    # seeds by default — not a duplicate "کریپتو" category.
    crypto_rows = conn.execute("SELECT id FROM categories WHERE name = 'کریپتو'").fetchall()
    assert len(crypto_rows) == 1
    assert txns[0]["category_id"] == crypto_rows[0]["id"]

    # The old custom category got its own new row.
    custom_rows = conn.execute("SELECT id FROM categories WHERE name = 'کتگوری سفارشی قدیمی'").fetchall()
    assert len(custom_rows) == 1

    wd = conn.execute("SELECT * FROM withdrawals").fetchone()
    assert wd["category_id"] == crypto_rows[0]["id"]

    ladder = conn.execute("SELECT * FROM ladders").fetchone()
    assert ladder["category_id"] == crypto_rows[0]["id"]
    assert ladder["threshold_pct"] == 70  # the custom (non-default) rung value survived migration
    conn.close()

    # And the app actually works end-to-end against the migrated file (this is what the
    # person doing the migration ultimately cares about).
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET password_hash = ?", (generate_password_hash("pass1234"),))
    conn.commit()
    conn.close()

    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": "admin", "password": "pass1234"})
    assert r.status_code == 200
    token = r.get_json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = c.get(f"/api/portfolios/{pid}/holdings", headers=h)
    assert r.status_code == 200
    holdings = r.get_json()
    assert len(holdings) == 2
    assert {h["categoryId"] for h in holdings} == {crypto_rows[0]["id"], custom_rows[0]["id"]}

    print("LEGACY MIGRATION TEST PASSED")


def test_migration_is_idempotent():
    import tempfile
    db_path = os.path.join(tempfile.mkdtemp(), "legacy2.sqlite3")
    _make_legacy_db(db_path)

    create_app({"DATABASE_PATH": db_path, "TESTING": True})
    backups_after_first = glob.glob(db_path + "*.bak")
    assert len(backups_after_first) == 1

    # Booting again on the now-migrated file must not error, and must not create another backup
    # (needs_migration() should correctly see nothing left to do).
    create_app({"DATABASE_PATH": db_path, "TESTING": True})
    backups_after_second = glob.glob(db_path + "*.bak")
    assert len(backups_after_second) == 1, "should not re-migrate (or re-backup) an already-migrated database"

    print("IDEMPOTENCY TEST PASSED")


def test_portfolio_scoped_accounts_become_global():
    """Accounts used to belong to one portfolio (portfolio_id NOT NULL); they're global now
    (shared across every portfolio, like a real bank account). Booting against an old database
    with the previous accounts schema must migrate it in place without losing any account."""
    import tempfile
    db_path = os.path.join(tempfile.mkdtemp(), "legacy_accounts.sqlite3")

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL, role TEXT NOT NULL, allowed_tabs TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE portfolios (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE categories (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, name TEXT NOT NULL,
            opening_balance REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE cash_movements (
            id TEXT PRIMARY KEY, account_id TEXT NOT NULL, ts INTEGER NOT NULL, type TEXT NOT NULL,
            date TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', transfer_group_id TEXT
        );
        CREATE TABLE transactions (
            id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, ts INTEGER NOT NULL, type TEXT NOT NULL,
            date TEXT NOT NULL, asset TEXT NOT NULL, category_id TEXT, account_id TEXT, qty REAL NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0, amount REAL NOT NULL DEFAULT 0, fee REAL NOT NULL DEFAULT 0,
            location TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT ''
        );
    """)
    pid = _uid()
    conn.execute("INSERT INTO portfolios VALUES (?,?,?)", (pid, "Main", "2026-01-01"))
    aid = _uid()
    conn.execute("INSERT INTO accounts VALUES (?,?,?,?,?)", (aid, pid, "بانک ملی", 1000000, "2026-01-01"))
    conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)",
                 (_uid(), "admin", "placeholder-hash", "Admin", "admin", None, "2026-01-01"))
    conn.commit()
    conn.close()

    app = create_app({"DATABASE_PATH": db_path, "TESTING": True})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
    assert "portfolio_id" not in cols, "portfolio_id should have been dropped from accounts"
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (aid,)).fetchone()
    assert row["name"] == "بانک ملی"
    assert row["opening_balance"] == 1000000
    conn.close()

    # And it's actually usable through the global (non-portfolio-scoped) API now.
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET password_hash = ?", (generate_password_hash("pass1234"),))
    conn.commit()
    conn.close()
    c = app.test_client()
    token = c.post("/api/auth/login", json={"username": "admin", "password": "pass1234"}).get_json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = c.get("/api/accounts", headers=h)
    assert r.status_code == 200
    assert any(a["id"] == aid and a["name"] == "بانک ملی" for a in r.get_json())

    print("ACCOUNTS-GLOBALIZATION MIGRATION TEST PASSED")


if __name__ == "__main__":
    test_legacy_database_migrates_without_data_loss()
    test_migration_is_idempotent()
    test_portfolio_scoped_accounts_become_global()
