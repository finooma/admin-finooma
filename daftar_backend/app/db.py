import os
import sqlite3

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """Returns a request-scoped SQLite connection (one per Flask request context)."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,  # autocommit; lets routes that need atomic multi-statement
                                   # writes (e.g. secure_profit) issue explicit BEGIN/COMMIT/ROLLBACK
        )
        g.db.execute("PRAGMA journal_mode=WAL")  # lets reads and writes from different
                                                  # connections/processes coexist safely —
                                                  # matters once this runs behind gunicorn
                                                  # with more than one worker process
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    """Creates tables on first run (safe every startup — CREATE TABLE IF NOT EXISTS), seeds
    the 7 default categories, then upgrades an existing (pre-v2) database file in place if
    needed (see migrations.py) — never drops or empties anything.

    IMPORTANT ORDERING: schema.sql's CREATE TABLE statements run first (harmless no-ops on
    tables that already exist, since they don't touch existing columns). Its CREATE INDEX
    statements are run LAST, after migrate_legacy_schema() has had a chance to ADD the columns
    those indexes reference (account_id, category_id, ...) — otherwise, on an old database
    that predates those columns, "CREATE INDEX ... ON transactions(account_id)" itself would
    fail with "no such column: account_id" before migration ever got a chance to run.
    """
    db_path = app.config["DATABASE_PATH"]
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_lines = f.readlines()
    index_lines = [ln for ln in schema_lines if ln.lstrip().startswith("CREATE INDEX")]
    table_lines = [ln for ln in schema_lines if not ln.lstrip().startswith("CREATE INDEX")]

    with sqlite3.connect(db_path) as conn:
        conn.executescript("".join(table_lines))
        _seed_default_categories(conn)
        conn.commit()

    from .migrations import migrate_legacy_schema
    migrate_legacy_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.executescript("".join(index_lines))
        conn.commit()


def _seed_default_categories(conn: sqlite3.Connection):
    from .business import BASE_CATEGORIES  # local import: avoids a hard dependency at module load
    from .utils import new_id
    import datetime

    existing = {row[0] for row in conn.execute("SELECT name FROM categories").fetchall()}
    today = datetime.date.today().isoformat()
    for name in BASE_CATEGORIES:
        if name not in existing:
            conn.execute(
                "INSERT INTO categories (id, name, is_default, created_at) VALUES (?, ?, 1, ?)",
                (new_id(), name, today),
            )


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur
