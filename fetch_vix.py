# -*- coding: utf-8 -*-
"""
fetch_vix.py — daily India VIX (market volatility index) from NSE's index-close
file (ind_close_all_DDMMYYYY.csv). Incremental via ingest_log dataset='vix'.
Holiday-aware, resume-safe. Safe to re-run.
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


def parse_vix(text):
    """Return (open, high, low, close, chg_pct) for the India VIX row, or None."""
    for parts in csv.reader(io.StringIO(text)):
        if parts and parts[0].strip().upper() == "INDIA VIX":
            def f(i):
                try:
                    return float(parts[i])
                except (ValueError, IndexError):
                    return None
            return f(2), f(3), f(4), f(5), f(7)     # open, high, low, close, %chg
    return None


def ingest_vix_day(conn, d):
    dmy = d.strftime("%d%m%Y")
    iso = d.strftime("%Y-%m-%d")
    resp = _get(URL.format(dmy=dmy))
    if resp is None:
        return "holiday", 0
    row = parse_vix(resp.text)
    if row is None:
        return "holiday", 0
    conn.execute("INSERT OR REPLACE INTO vix(date,open,high,low,close,chg_pct) "
                 "VALUES (?,?,?,?,?,?)", (iso, *row))
    conn.commit()
    return "ok", 1


def run(end=None):
    db.init_db()
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end = end or date.today()
    done = db.done_dates("vix")
    todo = [d for d in daterange(start, end) if d.strftime("%Y-%m-%d") not in done]
    if not todo:
        print("VIX up to date. Nothing to do.")
        return

    print(f"VIX ingest: {len(todo)} day(s) pending ({start} -> {end})")
    conn = db.connect()
    ok = hol = pend = err = 0
    try:
        for d in todo:
            iso = d.strftime("%Y-%m-%d")
            if d.weekday() >= 5 or holidays.is_holiday(iso):
                db.log_ingest("vix", iso, 0, "holiday")
                hol += 1
                continue
            try:
                status, n = ingest_vix_day(conn, d)
                if status == "holiday":              # 404 on trading day = not published yet
                    status = "pending"
                db.log_ingest("vix", iso, n, status)
                if status == "ok":
                    ok += 1
                elif status == "pending":
                    pend += 1
            except Exception as e:
                err += 1
                db.log_ingest("vix", iso, 0, "error")
                print(f"  {iso}  ERROR: {repr(e)[:100]}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
    finally:
        conn.close()
    print(f"Done. ok={ok}  holiday={hol}  pending={pend}  errors={err}")


if __name__ == "__main__":
    run()
