PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('admin','user')),
    allowed_tabs  TEXT,               -- JSON array, NULL means "all tabs" (only meaningful for role='user')
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id           TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ts           INTEGER NOT NULL,
    type         TEXT NOT NULL CHECK(type IN ('buy','sell','dividend')),
    date         TEXT NOT NULL,        -- normalized Jalali "YYYY/MM/DD"
    asset        TEXT NOT NULL,
    category     TEXT NOT NULL,
    qty          REAL NOT NULL DEFAULT 0,
    price        REAL NOT NULL DEFAULT 0,
    amount       REAL NOT NULL DEFAULT 0,
    location     TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_txn_portfolio ON transactions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_txn_asset ON transactions(asset, portfolio_id);

CREATE TABLE IF NOT EXISTS withdrawals (
    id             TEXT PRIMARY KEY,
    portfolio_id   TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ts             INTEGER NOT NULL,
    category       TEXT NOT NULL,
    date           TEXT NOT NULL,
    amount         REAL NOT NULL DEFAULT 0,
    dest           TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    level          INTEGER,                 -- which ladder rung (0-based), NULL = free withdrawal
    source_txn_id  TEXT REFERENCES transactions(id) ON DELETE SET NULL
        -- set only when this withdrawal was created by the "سیو سود" flow, linking it to
        -- the sell transaction that produced it; deleting that transaction cascades here
        -- via application logic (not a DB cascade) so we can un-mark the ladder rung.
);
CREATE INDEX IF NOT EXISTS idx_wd_portfolio_cat ON withdrawals(portfolio_id, category);

CREATE TABLE IF NOT EXISTS prices (
    asset      TEXT PRIMARY KEY,   -- shared across every portfolio, exactly like the frontend
    price      REAL NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id                 TEXT PRIMARY KEY,
    portfolio_id       TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    date               TEXT NOT NULL,
    total_value        REAL NOT NULL DEFAULT 0,
    total_investment   REAL NOT NULL DEFAULT 0,
    total_unrealized   REAL NOT NULL DEFAULT 0,
    total_realized     REAL NOT NULL DEFAULT 0,
    category_breakdown TEXT,               -- JSON: {category: {investment, value}} — matches
                                            -- the frontend's per-category trend chart data
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_portfolio ON snapshots(portfolio_id, date);

-- One row per (portfolio, category, rung). Only rows that differ from DEFAULT_LADDERS need to
-- be stored; ensure_portfolio_ladders() in business.py fills in the rest on read.
CREATE TABLE IF NOT EXISTS ladders (
    portfolio_id   TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    category       TEXT NOT NULL,
    idx            INTEGER NOT NULL,
    threshold_pct  REAL NOT NULL,
    withdraw_pct   REAL NOT NULL,
    PRIMARY KEY (portfolio_id, category, idx)
);
