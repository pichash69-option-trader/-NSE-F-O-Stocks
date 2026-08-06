# -*- coding: utf-8 -*-
"""
fetch_fii_dii.py — FII/FPI & DII CASH-segment provisional daily flows (₹ crore).

Source: NSE's fiidiiTradeReact API. NSE only exposes the LATEST published day
here (there is no dated archive like the bhavcopies), so this can't be
backfilled — it accumulates going forward, one day per run. Idempotent:
re-running the same day just overwrites (INSERT OR REPLACE).

Stored per (date, category): buy / sell / net in ₹ crore.
"""
import sys
import json
import db
from fetch_data import _get
from nse_utils import iso_date, parse_float

URL = "https://www.nseindia.com/api/fiidiiTradeReact"


def parse(text):
    """Yield (iso_date, category, buy, sell, net) rows."""
    for row in json.loads(text):
        d = iso_date(row.get("date", ""))
        cat = (row.get("category") or "").strip()
        if not d or not cat:
            continue
        yield d, cat, parse_float(row.get("buyValue")), parse_float(row.get("sellValue")), parse_float(row.get("netValue"))


def run():
    db.init_db()
    resp = _get(URL)
    if resp is None:
        print("FII/DII: API not reachable (holiday or blocked). Nothing stored.")
        return
    try:
        rows = list(parse(resp.text))
    except (json.JSONDecodeError, ValueError) as e:
        print(f"FII/DII: could not parse response: {e}", file=sys.stderr)
        return
    if not rows:
        print("FII/DII: empty response. Nothing stored.")
        return

    conn = db.connect()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO fii_dii(date,category,buy,sell,net) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    latest = max(r[0] for r in rows)
    db.log_ingest("fiidii", latest, len(rows), "ok")
    for d, cat, buy, sell, net in rows:
        print(f"  {d}  {cat:8}  buy={buy}  sell={sell}  net={net}")
    print(f"FII/DII: stored {len(rows)} row(s), latest {latest}.")


if __name__ == "__main__":
    run()
