# -*- coding: utf-8 -*-
"""
export_db.py — split the single nse.db into a tidy per-stock folder tree.

    database/
      RELIANCE/RELIANCE.db   (tables: prices, futures, options, deals,
                              corp_actions, secban, stats  — only this stock)
      TCS/TCS.db
      ...
      _market/market.db      (vix, indices, participant, fii_dii — market-wide)

nse.db is NOT modified — this is an export you can re-run any time (e.g. after
run_daily.py). Each stock's DB is rebuilt fresh so re-runs stay clean.

    python export_db.py
"""
import os
import sys
import time
import sqlite3

from config import DB_PATH, BASE_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

DB_PATH = str(DB_PATH)                    # sqlite param binding needs a str, not Path
OUT_DIR = os.path.join(str(BASE_DIR), "database")
PER_STOCK = ["prices", "futures", "options", "deals", "corp_actions", "secban", "stats"]
MARKET = ["vix", "indices", "participant", "fii_dii"]


def _safe(name):
    """Make a symbol safe as a Windows folder/file name."""
    out = name
    for ch in '<>:"/\\|?*':
        out = out.replace(ch, "_")
    return out.strip().rstrip(".")


def _schemas(src):
    """{table: CREATE TABLE sql} from the source DB."""
    rows = src.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
    ).fetchall()
    return {name: sql for name, sql in rows}


def _build_db(path, schemas, tables, where_sym=None):
    """Create a fresh SQLite DB at `path` with `tables` copied from src (attached).
    If where_sym is given, only that symbol's rows are copied. Returns total rows."""
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    total = 0
    try:
        conn.execute("ATTACH ? AS src", (DB_PATH,))
        for t in tables:
            if t not in schemas:
                continue
            conn.execute(schemas[t])                       # same schema (PK, types)
            if where_sym is not None:
                conn.execute(f"INSERT INTO {t} SELECT * FROM src.{t} WHERE symbol=?",
                             (where_sym,))
            else:
                conn.execute(f"INSERT INTO {t} SELECT * FROM src.{t}")
            total += conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        conn.commit()
        conn.execute("DETACH src")
    finally:
        conn.close()
    return total


def run():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        return
    src = sqlite3.connect(DB_PATH)
    try:
        schemas = _schemas(src)
        symbols = [r[0] for r in src.execute(
            "SELECT DISTINCT symbol FROM prices ORDER BY symbol")]
    finally:
        src.close()

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Exporting {len(symbols)} stocks -> {OUT_DIR}")
    t0 = time.time()

    for i, sym in enumerate(symbols, 1):
        folder = os.path.join(OUT_DIR, _safe(sym))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{_safe(sym)}.db")
        rows = _build_db(path, schemas, PER_STOCK, where_sym=sym)
        if i % 25 == 0 or i == len(symbols):
            print(f"  [{i}/{len(symbols)}] {sym} ({rows:,} rows)  "
                  f"elapsed {time.time()-t0:.0f}s")

    # market-wide
    mkt_dir = os.path.join(OUT_DIR, "_market")
    os.makedirs(mkt_dir, exist_ok=True)
    mrows = _build_db(os.path.join(mkt_dir, "market.db"), schemas, MARKET)
    print(f"  _market/market.db  ({mrows:,} rows)")

    print(f"Done. {len(symbols)} stock DBs + 1 market DB in {time.time()-t0:.0f}s.")


if __name__ == "__main__":
    run()
