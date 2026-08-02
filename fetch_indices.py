# -*- coding: utf-8 -*-
"""
fetch_indices.py — daily broad + sectoral index levels from NSE's index-close
file (ind_close_all_DDMMYYYY.csv) — the SAME file used for India VIX.

Stores every index row (Nifty 50, Nifty Bank, Nifty IT, ... ~160 indices) so we
have real benchmarks: beta vs Nifty 50, sector comparison, correlation, etc.
India VIX is skipped here (it lives in its own `vix` table).

Incremental via ingest_log dataset='indices'. Holiday-aware, resume-safe.
"""
import io
import sys
import csv
import time
from datetime import date, datetime

import db
import holidays
from config import START_DATE, REQUEST_DELAY
from fetch_data import _get, daterange

URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{dmy}.csv"


def parse_indices(text):
    """Yield (name, open, high, low, close, chg_pct) for every index row.

    Columns: Index Name(0), Index Date(1), Open(2), High(3), Low(4),
    Closing Value(5), Points Change(6), Change%(7), ...
    """
    reader = csv.reader(io.StringIO(text))
    header_seen = False
    for parts in reader:
        if not parts or len(parts) < 8:
            continue
        name = parts[0].strip()
        if not header_seen and name.lower() == "index name":
            header_seen = True
            continue
        if name.upper() == "INDIA VIX":         # lives in the vix table
            continue

        def f(i):
            try:
                return float(parts[i])
            except (ValueError, IndexError):
                return None

        close = f(5)
        if close is None:                       # skip non-data / malformed rows
            continue
        yield name, f(2), f(3), f(4), close, f(7)


def ingest_indices_day(conn, d):
    dmy = d.strftime("%d%m%Y")
    iso = d.strftime("%Y-%m-%d")
    resp = _get(URL.format(dmy=dmy))
    if resp is None:
        return "holiday", 0
    rows = list(parse_indices(resp.text))
    if not rows:
        return "holiday", 0
    conn.executemany(
        "INSERT OR REPLACE INTO indices(date,name,open,high,low,close,chg_pct) "
        "VALUES (?,?,?,?,?,?,?)",
        [(iso, name, o, h, l, c, chg) for (name, o, h, l, c, chg) in rows],
    )
    conn.commit()
    return "ok", len(rows)


def run(end=None):
    db.init_db()
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end = end or date.today()
    done = db.done_dates("indices")
    todo = [d for d in daterange(start, end) if d.strftime("%Y-%m-%d") not in done]
    if not todo:
        print("Indices up to date. Nothing to do.")
        return

    print(f"Indices ingest: {len(todo)} day(s) pending ({start} -> {end})")
    conn = db.connect()
    ok = hol = pend = err = 0
    try:
        for d in todo:
            iso = d.strftime("%Y-%m-%d")
            if d.weekday() >= 5 or holidays.is_holiday(iso):
                db.log_ingest("indices", iso, 0, "holiday")
                hol += 1
                continue
            try:
                status, n = ingest_indices_day(conn, d)
                if status == "holiday":          # 404 on trading day = not published yet
                    status = "pending"
                db.log_ingest("indices", iso, n, status)
                if status == "ok":
                    ok += 1
                elif status == "pending":
                    pend += 1
            except Exception as e:
                err += 1
                db.log_ingest("indices", iso, 0, "error")
                print(f"  {iso}  ERROR: {repr(e)[:100]}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
    finally:
        conn.close()
    print(f"Done. ok={ok}  holiday={hol}  pending={pend}  errors={err}")


if __name__ == "__main__":
    run()
