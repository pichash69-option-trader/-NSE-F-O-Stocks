# -*- coding: utf-8 -*-
"""
fetch_fno.py — download NSE F&O bhavcopy and store futures + options in SQLite.

Phase 2. Keeps EVERYTHING for the 50 NIFTY stocks: all expiries, all strikes, CE & PE.
Instrument types kept: STF (stock futures), STO (stock options).
(Index F&O — IDF/IDO — skipped; project scope is the 50 stocks.)

Incremental via ingest_log dataset='fno'. Safe to re-run; only fetches missing days.
"""
import io
import sys
import time
import csv
import zipfile
from datetime import date, datetime, timedelta

import db
from config import (NIFTY50_SET, UNIVERSE, REQUEST_DELAY, START_DATE)
from fetch_data import _get, daterange   # reuse HTTP + date helpers

FO_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"


def _num(v):
    v = (v or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def parse_fno(content):
    """Return (futures_rows, options_rows) as lists of tuples for our 50 stocks."""
    z = zipfile.ZipFile(io.BytesIO(content))
    raw = z.open(z.namelist()[0]).read().decode("utf-8", errors="replace")
    fut, opt = [], []
    for row in csv.DictReader(io.StringIO(raw)):
        sym = row.get("TckrSymb", "").strip()
        # NIFTY50 mode: only the 50. FNO mode: keep every stock (STF/STO) — the
        # bhavcopy's own symbols ARE that day's F&O universe (self-contained).
        if UNIVERSE == "NIFTY50" and sym not in NIFTY50_SET:
            continue
        tp = row.get("FinInstrmTp", "").strip()
        iso = row.get("TradDt", "").strip()
        expiry = row.get("XpryDt", "").strip()
        o, h, l, c = _num(row["OpnPric"]), _num(row["HghPric"]), _num(row["LwPric"]), _num(row["ClsPric"])
        settle = _num(row["SttlmPric"])
        oi, chg_oi = _num(row["OpnIntrst"]), _num(row["ChngInOpnIntrst"])
        vol, val = _num(row["TtlTradgVol"]), _num(row["TtlTrfVal"])

        if tp == "STF":                      # stock future
            fut.append((sym, iso, expiry, o, h, l, c, settle,
                        int(vol) if vol is not None else None, val,
                        int(oi) if oi is not None else None,
                        int(chg_oi) if chg_oi is not None else None))
        elif tp == "STO":                    # stock option
            strike = _num(row["StrkPric"])
            otype = row.get("OptnTp", "").strip()   # CE / PE
            opt.append((sym, iso, expiry, strike, otype, o, h, l, c, settle,
                        int(vol) if vol is not None else None,
                        int(vol) if vol is not None else None, val,
                        int(oi) if oi is not None else None,
                        int(chg_oi) if chg_oi is not None else None))
    return fut, opt


def ingest_fno_day(conn, d):
    ymd = d.strftime("%Y%m%d")
    resp = _get(FO_URL.format(ymd=ymd))
    if resp is None:
        return "holiday", 0
    fut, opt = parse_fno(resp.content)
    if not fut and not opt:
        return "holiday", 0

    conn.executemany(
        """INSERT OR REPLACE INTO futures
           (symbol,date,expiry,open,high,low,close,settle,contracts,value_lakh,oi,chg_oi)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", fut)
    conn.executemany(
        """INSERT OR REPLACE INTO options
           (symbol,date,expiry,strike,opt_type,open,high,low,close,settle,
            contracts,volume,value_lakh,oi,chg_oi)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", opt)
    conn.commit()
    return "ok", len(fut) + len(opt)


def run(end=None):
    db.init_db()
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end = end or date.today()
    done = db.done_dates("fno")                  # skip completed, retry errors/gaps

    todo = [d for d in daterange(start, end)
            if d.strftime("%Y-%m-%d") not in done]
    if not todo:
        print("F&O up to date. Nothing to do.")
        return

    print(f"F&O ingest: {len(todo)} day(s) pending ({start} -> {end})")
    conn = db.connect()
    ok = hol = err = 0
    try:
        for d in todo:
            iso = d.strftime("%Y-%m-%d")
            if d.weekday() >= 5:
                db.log_ingest("fno", iso, 0, "holiday")
                hol += 1
                continue
            try:
                status, n = ingest_fno_day(conn, d)
                db.log_ingest("fno", iso, n, status)
                if status == "ok":
                    ok += 1
                    print(f"  {iso}  {n:5d} F&O rows")
                else:
                    hol += 1
            except Exception as e:
                err += 1
                db.log_ingest("fno", iso, 0, "error")
                print(f"  {iso}  ERROR: {repr(e)[:120]}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
    finally:
        conn.close()
    print(f"Done. trading-days={ok}  skipped={hol}  errors={err}")


if __name__ == "__main__":
    run()
