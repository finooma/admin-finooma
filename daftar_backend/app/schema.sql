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

-- Categories are now a managed, first-class entity (Microsoft-Money-style) instead of free
-- text: they can be created, renamed, and deleted from one place, and every transaction /
-- ladder rung references the same category_id, so a rename instantly applies everywhere.
CREATE TABLE IF NOT EXISTS categories (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    is_default INTEGER NOT NULL DEFAULT 0,   -- 1 for the 7 seeded categories (still deletable
                                              -- once unused, just flagged for the UI to show
                                              -- them first / mark them as "built-in")
    created_at TEXT NOT NULL
);

-- Cash accounts (Microsoft-Money-style) — GLOBAL, shared across every portfolio, exactly like
-- a real bank account isn't "owned" by one of this app's logical portfolios. Buying an asset
-- in ANY portfolio can debit the same account; selling (or a dividend) credits it back.
-- Deposits and withdrawals of real-world cash are logged directly against an account via
-- cash_movements. The balance itself is never stored — it's always computed from
-- opening_balance + every movement + every transaction (from any portfolio) that references
-- this account (see business.py, compute_account_balance) — same "replay the ledger"
-- philosophy as holdings.
CREATE TABLE IF NOT EXISTS accounts (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    opening_balance  REAL NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

-- Deposits, withdrawals, and transfers of real cash — anything that moves money into or out
-- of an account WITHOUT an underlying buy/sell/dividend (those already move cash implicitly
-- via transactions.account_id, see below). A transfer between two accounts is stored as two
-- rows sharing the same transfer_group_id (one 'transfer_out', one 'transfer_in') so it can
-- be displayed/undone as a single logical operation.
CREATE TABLE IF NOT EXISTS cash_movements (
    id                TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    ts                INTEGER NOT NULL,
    type              TEXT NOT NULL CHECK(type IN ('deposit','withdraw','transfer_in','transfer_out')),
    date              TEXT NOT NULL,
    amount            REAL NOT NULL DEFAULT 0,   -- always stored positive; sign is implied by type
    note              TEXT NOT NULL DEFAULT '',
    transfer_group_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_cash_mov_account ON cash_movements(account_id);

CREATE TABLE IF NOT EXISTS transactions (
    id           TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ts           INTEGER NOT NULL,
    type         TEXT NOT NULL CHECK(type IN ('buy','sell','dividend')),
    date         TEXT NOT NULL,        -- normalized Jalali "YYYY/MM/DD"
    asset        TEXT NOT NULL,
    category_id  TEXT NOT NULL REFERENCES categories(id),
    account_id   TEXT REFERENCES accounts(id) ON DELETE SET NULL,
        -- which cash account this trade's money moved through. Nullable: some people don't
        -- want cash tracked for every single transaction (e.g. an old backfilled trade), in
        -- which case it simply doesn't touch any account's balance.
    qty          REAL NOT NULL DEFAULT 0,
    price        REAL NOT NULL DEFAULT 0,
    amount       REAL NOT NULL DEFAULT 0,   -- gross trade amount, BEFORE fee
    fee          REAL NOT NULL DEFAULT 0,   -- broker/exchange fee — added to cost on a buy,
                                            -- subtracted from proceeds on a sell (see business.py)
    location     TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_txn_portfolio ON transactions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_txn_asset ON transactions(asset, portfolio_id);
CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions(account_id);

CREATE TABLE IF NOT EXISTS withdrawals (
    id             TEXT PRIMARY KEY,
    portfolio_id   TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ts             INTEGER NOT NULL,
    category_id    TEXT NOT NULL REFERENCES categories(id),
    date           TEXT NOT NULL,
    amount         REAL NOT NULL DEFAULT 0,
    dest           TEXT NOT NULL DEFAULT '',   -- free text: this is money leaving the whole
                                                -- portfolio (e.g. "بانک ملی"), not an internal
                                                -- transfer between two of this app's own accounts
    note           TEXT NOT NULL DEFAULT '',
    level          INTEGER,                 -- which ladder rung (0-based), NULL = free withdrawal
    source_txn_id  TEXT REFERENCES transactions(id) ON DELETE SET NULL
        -- set only when this withdrawal was created by the "سیو سود" flow, linking it to
        -- the sell transaction that produced it; deleting that transaction cascades here
        -- via application logic (not a DB cascade) so we can un-mark the ladder rung.
);
CREATE INDEX IF NOT EXISTS idx_wd_portfolio_cat ON withdrawals(portfolio_id, category_id);

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
    category_breakdown TEXT,               -- JSON: {category_id: {investment, value}} — matches
                                            -- the frontend's per-category trend chart data
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_portfolio ON snapshots(portfolio_id, date);

-- One row per (portfolio, category, rung). Only rows that differ from DEFAULT_LADDERS need to
-- be stored; ladder_levels_with_defaults() in business.py fills in the rest on read.
CREATE TABLE IF NOT EXISTS ladders (
    portfolio_id   TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    category_id    TEXT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    idx            INTEGER NOT NULL,
    threshold_pct  REAL NOT NULL,
    withdraw_pct   REAL NOT NULL,
    PRIMARY KEY (portfolio_id, category_id, idx)
);
