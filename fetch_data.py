# -*- coding: utf-8 -*-
"""
fetch_data.py — download NSE equity bhavcopy + delivery (MTO) and store in SQLite.

Phase 1: EQUITY + DELIVERY only (F&O comes in Phase 2).

Logic:
  - Figure out resume date (last ingested + 1, else START_DATE).
  - For each calendar day up to today: download equity bhavcopy + MTO,
    filter to NIFTY 50 EQ rows, merge delivery, INSERT OR REPLACE into `prices`.
  - Weekends / holidays return HTTP 404 -> logged as 'holiday', skipped.
Safe to re-run anytime; it only fetches missing days.
"""
import io
import sys
import time
import zipfile
from datetime import date, datetime, timedelta

import requests

import db
import universe
import holidays
from config import (HEADERS, NIFTY50_SET, UNIVERSE, REQUEST_DELAY,
                    REQUEST_TIMEOUT, MAX_RETRIES, START_DATE)

# Which symbols to keep. Overridden in run() with the active universe so the
# whole run uses one consistent set. Defaults to NIFTY 50 for direct calls/tests.
SYMBOLS = NIFTY50_SET


def active_symbols():
    """The symbol set to fetch: full F&O universe or the NIFTY 50."""
    if UNIVERSE == "FNO":
        s = universe.fno_universe()
        return s if s else NIFTY50_SET           # fall back if NSE unreachable
    return NIFTY50_SET

CM_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
MTO_URL = "https://nsearchives.nseindia.com/archives/equities/mto/MTO_{dmy}.DAT"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _get(url):
    """GET with retries. Returns Response, or None on a clean 404 (holiday)."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r
            last_exc = RuntimeError(f"HTTP {r.status_code}")
        except requests.RequestException as e:
            last_exc = e
        time.sleep(1.0 + attempt)
    raise RuntimeError(f"Failed after {MAX_RETRIES} tries: {url} ({last_exc})")


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
def parse_equity(content):
    """Return {symbol: row-dict} for NIFTY50 EQ rows from a bhavcopy zip."""
    import csv
    z = zipfile.ZipFile(io.BytesIO(content))
    raw = z.open(z.namelist()[0]).read().decode("utf-8", errors="replace")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("SctySrs", "").strip() != "EQ":
            continue
        sym = row.get("TckrSymb", "").strip()
        if sym not in SYMBOLS:
            continue

        def num(key):
            v = (row.get(key) or "").strip()
            try:
                return float(v)
            except ValueError:
                return None

        out[sym] = {
            "open": num("OpnPric"), "high": num("HghPric"),
            "low": num("LwPric"), "close": num("ClsPric"),
            "prev_close": num("PrvsClsgPric"), "settle": num("SttlmPric"),
            "volume": num("TtlTradgVol"), "turnover": num("TtlTrfVal"),
            "num_trades": num("TtlNbOfTxsExctd"),
        }
    return out


def parse_delivery(text):
    """Return {symbol: (deliv_qty, deliv_pct)} from an MTO .DAT file (EQ series)."""
    out = {}
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 7 or parts[0].strip() != "20":
            continue
        series = parts[3].strip()
        if series != "EQ":
            continue
        sym = parts[2].strip()
        if sym not in SYMBOLS:
            continue
        try:
            deliv_qty = int(parts[5])
            deliv_pct = float(parts[6])
        except ValueError:
            continue
        out[sym] = (deliv_qty, deliv_pct)
    return out


# --------------------------------------------------------------------------- #
# Ingest one day
# --------------------------------------------------------------------------- #
def ingest_equity_day(conn, d):
    """Fetch + store one day. Returns (status, n_rows)."""
    ymd = d.strftime("%Y%m%d")
    dmy = d.strftime("%d%m%Y")
    iso = d.strftime("%Y-%m-%d")

    eq_resp = _get(CM_URL.format(ymd=ymd))
    if eq_resp is None:
        return "holiday", 0                      # no trading that day

    equity = parse_equity(eq_resp.content)
    if not equity:
        return "holiday", 0

    mto_resp = _get(MTO_URL.format(dmy=dmy))
    delivery = parse_delivery(mto_resp.text) if mto_resp is not None else {}

    rows = []
    for sym, e in equity.items():
        dq, dp = delivery.get(sym, (None, None))
        rows.append((
            sym, iso, e["open"], e["high"], e["low"], e["close"],
            e["prev_close"], e["settle"], e["volume"], e["turnover"],
            e["num_trades"], dq, dp,
        ))

    conn.executemany(
        """INSERT OR REPLACE INTO prices
           (symbol,date,open,high,low,close,prev_close,settle,
            volume,turnover,num_trades,deliv_qty,deliv_pct)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    return "ok", len(rows)


# --------------------------------------------------------------------------- #
# Backfill / incremental driver
# --------------------------------------------------------------------------- #
def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def run(end=None):
    db.init_db()
    global SYMBOLS
    SYMBOLS = active_symbols()
    print(f"Universe: {UNIVERSE} ({len(SYMBOLS)} symbols)")
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end = end or date.today()
    done = db.done_dates("equity")               # skip completed, retry errors/gaps

    todo = [d for d in daterange(start, end)
            if d.strftime("%Y-%m-%d") not in done]
    if not todo:
        print("Equity up to date. Nothing to do.")
        return

    print(f"Equity ingest: {len(todo)} day(s) pending ({start} -> {end})")
    conn = db.connect()
    ok = hol = pend = err = 0
    try:
        for d in todo:
            iso = d.strftime("%Y-%m-%d")
            if d.weekday() >= 5 or holidays.is_holiday(iso):    # real holiday
                db.log_ingest("equity", iso, 0, "holiday")
                hol += 1
                continue
            try:
                status, n = ingest_equity_day(conn, d)
                # trading day but NSE returned 404 => data not published yet
                if status == "holiday":
                    status = "pending"
                db.log_ingest("equity", iso, n, status)
                if status == "ok":
                    ok += 1
                    print(f"  {iso}  {n:2d} stocks")
                elif status == "pending":
                    pend += 1
                    print(f"  {iso}  pending (NSE data not published yet)")
                else:
                    hol += 1
            except Exception as e:
                err += 1
                db.log_ingest("equity", iso, 0, "error")
                print(f"  {iso}  ERROR: {repr(e)[:120]}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
    finally:
        conn.close()
    print(f"Done. ok={ok}  holiday={hol}  pending={pend}  errors={err}")


if __name__ == "__main__":
    run()
