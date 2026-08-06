# -*- coding: utf-8 -*-
"""
fetch_short_selling.py — securities-wise daily SHORT SELLING quantity from NSE.

How much of each security was sold short that day (NSE disclosure). A small,
sparse dataset (only securities with disclosed short selling appear).

Source: same NSE historical CSV export as bulk/block deals (uncapped):
    api/historicalOR/bulk-block-short-deals?optionType=short_selling
        &from=DD-MM-YYYY&to=DD-MM-YYYY&csv=true
Columns: Date, Symbol, Security Name, Quantity.

Backfills in monthly chunks; incremental runs re-fetch from the last stored
month. Idempotent: each chunk deletes its date-range before inserting.
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
       "?optionType=short_selling&from={a}&to={b}&csv=true")


def _iso(dmy):
    try:
        return datetime.strptime(dmy.strip(), "%d-%b-%Y").strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return dmy.strip()


def _int(s):
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def parse(text):
    """Yield (iso_date, symbol, qty) rows from a short-selling CSV."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    for i, row in enumerate(reader):
        if i == 0 or len(row) < 4:                 # header / short rows
            continue
        if row[0].strip().upper().startswith("NO RECORD"):
            continue
        sym = row[1].strip()
        if not sym:
            continue
        yield _iso(row[0]), sym, _int(row[3])


def _month_chunks(start, end):
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
        a = max(cur, start)
        b = min(date.fromordinal(nxt.toordinal() - 1), end)
        yield a, b
        cur = nxt


def fetch_chunk(conn, a, b):
    resp = _get(URL.format(a=a.strftime("%d-%m-%Y"), b=b.strftime("%d-%m-%Y")))
    if resp is None:
        return None
    rows = list(parse(resp.text))
    conn.execute("DELETE FROM short_selling WHERE date BETWEEN ? AND ?",
                 (a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")))
    if rows:
        conn.executemany(
            "INSERT INTO short_selling(date,symbol,qty) VALUES (?,?,?)", rows)
    conn.commit()
    return len(rows)


def run(end=None):
    db.init_db()
    end = end or date.today()
    conn = db.connect()
    try:
        last = conn.execute("SELECT MAX(date) FROM short_selling").fetchone()[0]
        if last:
            start = datetime.strptime(last, "%Y-%m-%d").date().replace(day=1)
        else:
            start = datetime.strptime(START_DATE, "%Y-%m-%d").date()

        chunks = list(_month_chunks(start, end))
        print(f"Short selling: {len(chunks)} month(s) ({start} -> {end})")
        tot = 0
        for a, b in chunks:
            n = fetch_chunk(conn, a, b)
            if n is None:
                print(f"  {a:%Y-%m}: fetch failed (skipped)", file=sys.stderr)
            else:
                tot += n
            time.sleep(REQUEST_DELAY)
        latest = conn.execute("SELECT MAX(date) FROM short_selling").fetchone()[0]
        db.log_ingest("short_selling", latest or end.strftime("%Y-%m-%d"), tot, "ok")
        print(f"Done. rows touched={tot}  latest={latest}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
