# -*- coding: utf-8 -*-
"""
db.py — SQLite schema setup and small helpers.
One file DB (nse.db). Safe to call init_db() repeatedly.
"""
import sqlite3
from config import DB_PATH


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")     # faster concurrent-ish writes
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


SCHEMA = """
-- EQUITY: raw daily cash-segment data
CREATE TABLE IF NOT EXISTS prices (
    symbol     TEXT NOT NULL,
    date       TEXT NOT NULL,
    open       REAL, high REAL, low REAL, close REAL,
    prev_close REAL, settle REAL,
    volume     INTEGER, turnover REAL, num_trades INTEGER,
    deliv_qty  INTEGER, deliv_pct REAL,
    PRIMARY KEY (symbol, date)
);

-- F&O FUTURES: all expiries
CREATE TABLE IF NOT EXISTS futures (
    symbol   TEXT NOT NULL,
    date     TEXT NOT NULL,
    expiry   TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, settle REAL,
    contracts INTEGER, value_lakh REAL,
    oi INTEGER, chg_oi INTEGER,
    PRIMARY KEY (symbol, date, expiry)
);

-- F&O OPTIONS: all strikes + all expiries + CE & PE
CREATE TABLE IF NOT EXISTS options (
    symbol   TEXT NOT NULL,
    date     TEXT NOT NULL,
    expiry   TEXT NOT NULL,
    strike   REAL NOT NULL,
    opt_type TEXT NOT NULL,            -- CE / PE
    open REAL, high REAL, low REAL, close REAL, settle REAL,
    contracts INTEGER, volume INTEGER, value_lakh REAL,
    oi INTEGER, chg_oi INTEGER,
    PRIMARY KEY (symbol, date, expiry, strike, opt_type)
);

-- Computed math stats (latest per symbol; recomputed each run)
CREATE TABLE IF NOT EXISTS stats (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    daily_return REAL, cum_return REAL, mean_return REAL,
    volatility REAL, ann_volatility REAL,
    sharpe REAL, max_drawdown REAL, beta REAL,
    correlation REAL, avg_deliv_pct REAL,
    zscore REAL, pct_rank_52w REAL, cagr REAL,
    skew REAL, kurtosis REAL,
    put_call_ratio REAL, total_oi INTEGER, oi_change REAL,
    futures_premium REAL, futures_premium_pct REAL,
    PRIMARY KEY (symbol, date)
);

-- Track ingest progress so incremental fetch knows where to resume.
CREATE TABLE IF NOT EXISTS ingest_log (
    dataset TEXT NOT NULL,             -- 'equity' / 'fno'
    date    TEXT NOT NULL,
    rows    INTEGER,
    status  TEXT,                      -- 'ok' / 'holiday' / 'error'
    PRIMARY KEY (dataset, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date   ON prices(date);
CREATE INDEX IF NOT EXISTS idx_futures_date  ON futures(date);
CREATE INDEX IF NOT EXISTS idx_options_date  ON options(date);
CREATE INDEX IF NOT EXISTS idx_options_chain ON options(symbol, date, expiry);

-- PARTICIPANT-wise OI & Volume (FII / DII / Pro / Client) in equity derivatives
CREATE TABLE IF NOT EXISTS participant (
    date TEXT NOT NULL,
    metric TEXT NOT NULL,          -- 'oi' or 'vol'
    client_type TEXT NOT NULL,     -- Client / DII / FII / Pro / TOTAL
    fut_idx_long INTEGER, fut_idx_short INTEGER,
    fut_stk_long INTEGER, fut_stk_short INTEGER,
    opt_idx_call_long INTEGER, opt_idx_put_long INTEGER,
    opt_idx_call_short INTEGER, opt_idx_put_short INTEGER,
    opt_stk_call_long INTEGER, opt_stk_put_long INTEGER,
    opt_stk_call_short INTEGER, opt_stk_put_short INTEGER,
    total_long INTEGER, total_short INTEGER,
    PRIMARY KEY (date, metric, client_type)
);
CREATE INDEX IF NOT EXISTS idx_participant_date ON participant(date);

-- INDIA VIX — market volatility index (daily, from NSE index-close file)
CREATE TABLE IF NOT EXISTS vix (
    date TEXT PRIMARY KEY,
    open REAL, high REAL, low REAL, close REAL, chg_pct REAL
);

-- INDICES — broad + sectoral index levels (daily, from the same NSE index-close
-- file as VIX). Used as real benchmarks: beta vs Nifty 50, sector comparison, etc.
CREATE TABLE IF NOT EXISTS indices (
    date TEXT NOT NULL,
    name TEXT NOT NULL,               -- e.g. 'Nifty 50', 'Nifty Bank', 'Nifty IT'
    open REAL, high REAL, low REAL, close REAL, chg_pct REAL,
    PRIMARY KEY (date, name)
);
CREATE INDEX IF NOT EXISTS idx_indices_name ON indices(name);

-- FII / DII CASH-segment provisional daily flows (₹ crore). NSE only publishes
-- the latest day (no dated archive), so this table accumulates going forward.
CREATE TABLE IF NOT EXISTS fii_dii (
    date     TEXT NOT NULL,
    category TEXT NOT NULL,            -- 'FII/FPI' or 'DII'
    buy      REAL, sell REAL, net REAL,
    PRIMARY KEY (date, category)
);
CREATE INDEX IF NOT EXISTS idx_fiidii_date ON fii_dii(date);

-- F&O SECURITIES-IN-BAN: symbols that crossed 95% MWPL (no fresh F&O positions
-- allowed that day). One row per (date, symbol). A trading day with no bans is
-- still logged 'ok' (0 rows) in ingest_log so we know it was checked.
CREATE TABLE IF NOT EXISTS secban (
    date   TEXT NOT NULL,
    symbol TEXT NOT NULL,
    PRIMARY KEY (date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_secban_date ON secban(date);

-- BULK & BLOCK DEALS: large disclosed trades (institutional activity signal).
-- No PK — idempotency comes from delete-by-date-range before re-inserting a chunk.
CREATE TABLE IF NOT EXISTS deals (
    date      TEXT NOT NULL,
    deal_type TEXT NOT NULL,           -- 'bulk' / 'block'
    symbol    TEXT NOT NULL,
    client    TEXT,
    buy_sell  TEXT,                    -- BUY / SELL
    qty       INTEGER,
    price     REAL
);
CREATE INDEX IF NOT EXISTS idx_deals_date   ON deals(date);
CREATE INDEX IF NOT EXISTS idx_deals_symbol ON deals(symbol);

-- SHORT SELLING: securities-wise daily short-sold quantity (NSE disclosure).
-- No PK — idempotency via delete-by-date-range before re-inserting a chunk.
CREATE TABLE IF NOT EXISTS short_selling (
    date   TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_shortsell_date   ON short_selling(date);
CREATE INDEX IF NOT EXISTS idx_shortsell_symbol ON short_selling(symbol);

-- CORPORATE ACTIONS: dividends / splits / bonus / rights / buyback (by ex-date).
-- action_type is parsed from the free-text `subject`. Includes upcoming ex-dates.
CREATE TABLE IF NOT EXISTS corp_actions (
    symbol      TEXT NOT NULL,
    ex_date     TEXT NOT NULL,
    action_type TEXT,                  -- Dividend/Split/Bonus/Rights/Buyback/Other
    subject     TEXT,
    face_value  TEXT,
    series      TEXT,
    PRIMARY KEY (symbol, ex_date, subject)
);
CREATE INDEX IF NOT EXISTS idx_corp_symbol ON corp_actions(symbol);
CREATE INDEX IF NOT EXISTS idx_corp_exdate ON corp_actions(ex_date);
"""


# Columns added to `stats` after its first release — added to existing DBs via
# ALTER (CREATE IF NOT EXISTS won't add columns to an already-created table).
_STATS_ADDED = {"correlation": "REAL", "avg_deliv_pct": "REAL",
                "futures_premium_pct": "REAL"}


def init_db():
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        have = {r[1] for r in conn.execute("PRAGMA table_info(stats)")}
        for col, typ in _STATS_ADDED.items():
            if col not in have:
                conn.execute(f"ALTER TABLE stats ADD COLUMN {col} {typ}")
        conn.commit()
    finally:
        conn.close()


def done_dates(dataset):
    """Set of dates already completed ('ok' data or a real 'holiday').

    'pending' (a trading day whose NSE files weren't published yet) and 'error'
    days are NOT included, so every run retries them until the data appears —
    no permanent gaps from late-published data. Real holidays are decided from
    the NSE calendar (see holidays.py) before fetching, so they never get stuck
    as 'pending'."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT date FROM ingest_log WHERE dataset=? AND status IN ('ok','holiday')",
            (dataset,),
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def log_ingest(dataset, date, rows, status):
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_log(dataset, date, rows, status) VALUES (?,?,?,?)",
            (dataset, date, rows, status),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB ready at {DB_PATH}")
