# -*- coding: utf-8 -*-
"""
fetch_participant.py — daily participant-wise OI & Volume (FII/DII/Pro/Client)
in equity derivatives, from NSE's nsccl reports.

Two files per day:
  fao_participant_oi_DDMMYYYY.csv   -> Open Interest (contracts)
  fao_participant_vol_DDMMYYYY.csv  -> Trading Volume (contracts)

Each has 5 rows (Client, DII, FII, Pro, TOTAL) x 14 category columns.
Incremental via ingest_log dataset='participant'. Safe to re-run.
"""
import io
import sys
import csv
import time
from datetime import date, datetime, timedelta

import db
from config import START_DATE, REQUEST_DELAY
from fetch_data import _get, daterange

URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_{metric}_{dmy}.csv"

# 14 value columns, in the file's order
COLS = ["fut_idx_long", "fut_idx_short", "fut_stk_long", "fut_stk_short",
        "opt_idx_call_long", "opt_idx_put_long", "opt_idx_call_short",
        "opt_idx_put_short", "opt_stk_call_long", "opt_stk_put_long",
        "opt_stk_call_short", "opt_stk_put_short", "total_long", "total_short"]
CLIENTS = {"Client", "DII", "FII", "Pro", "TOTAL"}


def parse(text, metric, iso):
    """Return rows for the participant table from one report's CSV text."""
    rows = []
    for parts in csv.reader(io.StringIO(text)):
        if not parts:
            continue
        ct = parts[0].strip()
        if ct not in CLIENTS or len(parts) < 15:
            continue
        vals = []
        for v in parts[1:15]:
            v = v.strip()
            try:
                vals.append(int(float(v)))
            except ValueError:
                vals.append(None)
        rows.append((iso, metric, ct, *vals))
    return rows


def ingest_participant_day(conn, d):
    iso = d.strftime("%Y-%m-%d")
    dmy = d.strftime("%d%m%Y")
    total = 0
    for metric in ("oi", "vol"):
        resp = _get(URL.format(metric=metric, dmy=dmy))
        if resp is None:
            continue
        rows = parse(resp.text, metric, iso)
        if rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO participant "
                f"(date,metric,client_type,{','.join(COLS)}) "
                f"VALUES ({','.join('?' * (3 + len(COLS)))})", rows)
            total += len(rows)
    conn.commit()
    return ("ok", total) if total else ("holiday", 0)


def run(end=None):
    db.init_db()
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end = end or date.today()
    done = db.done_dates("participant")

    todo = [d for d in daterange(start, end)
            if d.strftime("%Y-%m-%d") not in done]
    if not todo:
        print("Participant data up to date. Nothing to do.")
        return

    print(f"Participant ingest: {len(todo)} day(s) pending ({start} -> {end})")
    conn = db.connect()
    ok = hol = err = 0
    try:
        for d in todo:
            iso = d.strftime("%Y-%m-%d")
            if d.weekday() >= 5:
                db.log_ingest("participant", iso, 0, "holiday")
                hol += 1
                continue
            try:
                status, n = ingest_participant_day(conn, d)
                db.log_ingest("participant", iso, n, status)
                if status == "ok":
                    ok += 1
                else:
                    hol += 1
            except Exception as e:
                err += 1
                db.log_ingest("participant", iso, 0, "error")
                print(f"  {iso}  ERROR: {repr(e)[:120]}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
    finally:
        conn.close()
    print(f"Done. trading-days={ok}  skipped={hol}  errors={err}")


if __name__ == "__main__":
    run()
