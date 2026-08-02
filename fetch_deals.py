# -*- coding: utf-8 -*-
"""
fetch_deals.py — BULK & BLOCK deals (large disclosed trades) from NSE.

Institutional-activity signal: who bought/sold a big chunk of a stock, and at
what price. Two deal types share one schema.

Source: NSE historical CSV export (uncapped — the plain JSON API caps at 70 rows):
    api/historicalOR/bulk-block-short-deals?optionType={bulk_deals|block_deals}
        &from=DD-MM-YYYY&to=DD-MM-YYYY&csv=true

Backfills in MONTHLY chunks (fast: ~1 request/month/type). Incremental runs
re-fetch from the last stored month to catch late disclosures. Idempotent:
each chunk deletes its date-range for that deal_type before inserting.
"""
import io
import sys
import csv
import time
from datetime import date, datetime

import db
from config import START_DATE, REQUEST_DELAY
from fetch_data import _get

URL = ("https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
       "?optionType={opt}&from={a}&to={b}&csv=true")
TYPES = {"bulk": "bulk_deals", "block": "block_deals"}


def _iso(dmy):
    """'01-FEB-2024' -> '2024-02-01' (fallback: return as-is)."""
    try:
        return datetime.strptime(dmy.strip(), "%d-%b-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return dmy.strip()


def _int(s):
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def parse(text):
    """Yield (iso_date, symbol, client, buy_sell, qty, price) from a deals CSV."""
    txt = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(txt))
    for i, row in enumerate(reader):
        if i == 0 or len(row) < 7:                 # header / short/blank rows
            continue
        if row[0].strip().upper().startswith("NO RECORD"):
            continue
        d = _iso(row[0])
        sym = row[1].strip()
        if not sym:
            continue
        yield d, sym, row[3].strip(), row[4].strip(), _int(row[5]), _float(row[6])


def _month_chunks(start, end):
    """Yield (first_day, last_day) date pairs, one per month, clipped to range."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
        a = max(cur, start)
        b = min(nxt.fromordinal(nxt.toordinal() - 1), end)   # last day of month
        yield a, b
        cur = nxt


def fetch_chunk(conn, deal_type, a, b):
    opt = TYPES[deal_type]
    url = URL.format(opt=opt, a=a.strftime("%d-%m-%Y"), b=b.strftime("%d-%m-%Y"))
    resp = _get(url)
    if resp is None:
        return None                                # signal failure (don't wipe range)
    rows = [(d, deal_type, sym, cl, bs, q, p)
            for (d, sym, cl, bs, q, p) in parse(resp.text)]
    conn.execute("DELETE FROM deals WHERE deal_type=? AND date BETWEEN ? AND ?",
                 (deal_type, a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")))
    if rows:
        conn.executemany(
            "INSERT INTO deals(date,deal_type,symbol,client,buy_sell,qty,price) "
            "VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def run(end=None):
    db.init_db()
    end = end or date.today()
    conn = db.connect()
    try:
        last = conn.execute("SELECT MAX(date) FROM deals").fetchone()[0]
        if last:                                   # re-fetch from last stored month
            start = datetime.strptime(last, "%Y-%m-%d").date().replace(day=1)
        else:
            start = datetime.strptime(START_DATE, "%Y-%m-%d").date()

        chunks = list(_month_chunks(start, end))
        print(f"Deals ingest: {len(chunks)} month(s) × 2 types ({start} -> {end})")
        tot = {"bulk": 0, "block": 0}
        for a, b in chunks:
            for deal_type in TYPES:
                n = fetch_chunk(conn, deal_type, a, b)
                if n is None:
                    print(f"  {a:%Y-%m}  {deal_type}: fetch failed (skipped)", file=sys.stderr)
                else:
                    tot[deal_type] += n
                time.sleep(REQUEST_DELAY)
        latest = conn.execute("SELECT MAX(date) FROM deals").fetchone()[0]
        db.log_ingest("deals", latest or end.strftime("%Y-%m-%d"),
                      tot["bulk"] + tot["block"], "ok")
        print(f"Done. bulk={tot['bulk']}  block={tot['block']}  latest={latest}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
