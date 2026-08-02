# -*- coding: utf-8 -*-
"""
fetch_secban.py — daily F&O "Securities in Ban" list from NSE.

A stock enters the ban when its open interest crosses 95% of the Market-Wide
Position Limit (MWPL); no fresh F&O positions are allowed that day. This is a
key risk flag for F&O traders.

Source (dated archive, so it backfills):
    archives/fo/sec_ban/fo_secban_DDMMYYYY.csv
Format:
    line 1: "Securities in Ban For Trade Date DD-MON-YYYY:"  (+ " NIL" if none)
    then  : "1,SYMBOL", "2,SYMBOL", ...

Incremental via ingest_log dataset='secban'. Holiday-aware, resume-safe.
A trading day with zero bans is still recorded 'ok' (0 rows).
"""
import sys
import time
from datetime import date, datetime

import db
import holidays
from config import START_DATE, REQUEST_DELAY
from fetch_data import _get, daterange

URL = "https://nsearchives.nseindia.com/archives/fo/sec_ban/fo_secban_{dmy}.csv"


def parse_secban(text):
    """Return list of banned symbols (empty list for a NIL / no-ban day)."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return []
    if "NIL" in lines[0].upper():
        return []
    syms = []
    for ln in lines[1:]:                 # skip the "Securities in Ban..." header
        parts = ln.split(",")
        if len(parts) >= 2 and parts[1].strip():
            syms.append(parts[1].strip().upper())
    return syms


def ingest_secban_day(conn, d):
    dmy = d.strftime("%d%m%Y")
    iso = d.strftime("%Y-%m-%d")
    resp = _get(URL.format(dmy=dmy))
    if resp is None:
        return "pending", 0              # 404 on a trading day = not published yet
    syms = parse_secban(resp.text)
    # clear any prior rows for this date, then insert (idempotent)
    conn.execute("DELETE FROM secban WHERE date=?", (iso,))
    if syms:
        conn.executemany("INSERT OR REPLACE INTO secban(date,symbol) VALUES (?,?)",
                         [(iso, s) for s in syms])
    conn.commit()
    return "ok", len(syms)               # ok even when 0 (NIL day)


def run(end=None):
    db.init_db()
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end = end or date.today()
    done = db.done_dates("secban")
    todo = [d for d in daterange(start, end) if d.strftime("%Y-%m-%d") not in done]
    if not todo:
        print("Sec-ban up to date. Nothing to do.")
        return

    print(f"Sec-ban ingest: {len(todo)} day(s) pending ({start} -> {end})")
    conn = db.connect()
    ok = hol = pend = err = 0
    try:
        for d in todo:
            iso = d.strftime("%Y-%m-%d")
            if d.weekday() >= 5 or holidays.is_holiday(iso):
                db.log_ingest("secban", iso, 0, "holiday")
                hol += 1
                continue
            try:
                status, n = ingest_secban_day(conn, d)
                db.log_ingest("secban", iso, n, status)
                if status == "ok":
                    ok += 1
                elif status == "pending":
                    pend += 1
            except Exception as e:
                err += 1
                db.log_ingest("secban", iso, 0, "error")
                print(f"  {iso}  ERROR: {repr(e)[:100]}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
    finally:
        conn.close()
    print(f"Done. ok={ok}  holiday={hol}  pending={pend}  errors={err}")


if __name__ == "__main__":
    run()
