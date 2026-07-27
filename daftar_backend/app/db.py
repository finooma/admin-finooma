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
    """Creates tables on first run. Safe to call every startup (CREATE TABLE IF NOT EXISTS)."""
    db_path = app.config["DATABASE_PATH"]
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with sqlite3.connect(db_path) as conn:
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur
