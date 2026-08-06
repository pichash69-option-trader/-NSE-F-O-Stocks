# -*- coding: utf-8 -*-
"""
fetch_corp_actions.py — corporate actions (dividend / split / bonus / rights /
buyback) from NSE, keyed by ex-date.

Replaces guessing: the equity view can show exactly why a price gapped
(1:1 bonus, 1:5 split, big dividend) instead of inferring it.

Source (uncapped JSON, supports date ranges):
    api/corporates-corporateActions?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY

Backfills in monthly chunks; incremental runs also look ~60 days AHEAD to catch
upcoming ex-dates. Idempotent: each chunk deletes its ex-date range before insert.
"""
import sys
import json
import time
from datetime import date, datetime, timedelta

import db
from config import START_DATE, REQUEST_DELAY
from fetch_data import _get
from nse_utils import iso_date, month_chunks

URL = ("https://www.nseindia.com/api/corporates-corporateActions"
       "?index=equities&from_date={a}&to_date={b}")


def classify(subject):
    """Bucket the free-text subject into an action_type."""
    s = (subject or "").upper()
    if "SPLIT" in s:
        return "Split"
    if "BONUS" in s:
        return "Bonus"
    if "RIGHTS" in s:
        return "Rights"
    if "BUY BACK" in s or "BUYBACK" in s:
        return "Buyback"
    if "DIVIDEND" in s:
        return "Dividend"
    return "Other"


def parse(text):
    """Yield (symbol, ex_date, action_type, subject, face_value, series)."""
    for x in json.loads(text):
        ex = iso_date(x.get("exDate", ""))
        sym = (x.get("symbol") or "").strip()
        if not ex or not sym:
            continue
        subject = (x.get("subject") or "").strip()
        yield sym, ex, classify(subject), subject, x.get("faceVal"), x.get("series")


def fetch_chunk(conn, a, b):
    resp = _get(URL.format(a=a.strftime("%d-%m-%Y"), b=b.strftime("%d-%m-%Y")))
    if resp is None:
        return None
    try:
        rows = list(parse(resp.text))
    except (json.JSONDecodeError, ValueError):
        return None
    conn.execute("DELETE FROM corp_actions WHERE ex_date BETWEEN ? AND ?",
                 (a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO corp_actions"
            "(symbol,ex_date,action_type,subject,face_value,series) VALUES (?,?,?,?,?,?)",
            rows)
    conn.commit()
    return len(rows)


def run(end=None):
    db.init_db()
    end = (end or date.today()) + timedelta(days=60)     # include upcoming ex-dates
    conn = db.connect()
    try:
        last = conn.execute("SELECT MAX(ex_date) FROM corp_actions "
                            "WHERE ex_date <= ?", (date.today().strftime("%Y-%m-%d"),)).fetchone()[0]
        if last:
            start = datetime.strptime(last, "%Y-%m-%d").date().replace(day=1)
        else:
            start = datetime.strptime(START_DATE, "%Y-%m-%d").date()

        chunks = list(month_chunks(start, end))
        print(f"Corp actions: {len(chunks)} month(s) ({start} -> {end})")
        tot = 0
        for a, b in chunks:
            n = fetch_chunk(conn, a, b)
            if n is None:
                print(f"  {a:%Y-%m}: fetch failed (skipped)", file=sys.stderr)
            else:
                tot += n
            time.sleep(REQUEST_DELAY)
        latest = conn.execute("SELECT MAX(ex_date) FROM corp_actions").fetchone()[0]
        db.log_ingest("corp_actions", latest or end.strftime("%Y-%m-%d"), tot, "ok")
        print(f"Done. rows touched={tot}  latest ex-date={latest}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
