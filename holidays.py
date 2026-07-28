# -*- coding: utf-8 -*-
"""
holidays.py — NSE trading-holiday calendar (CM / equity segment).

Used so the fetchers can tell apart:
  - a REAL NSE holiday  -> mark 'holiday' once, never re-fetch
  - a trading day whose files NSE hasn't published yet (404) -> mark 'pending'
    and retry every run until the data appears (no permanent gaps).

If the NSE API is unreachable, returns an empty set; callers then fall back to
treating weekday 404s as 'pending' (retried), which is still safe.
"""
from datetime import datetime

import requests

from config import HEADERS

HOLIDAY_API = "https://www.nseindia.com/api/holiday-master?type=trading"
_cache = {"days": None}


def trading_holidays(force=False):
    """Set of NSE CM trading-holiday dates as 'YYYY-MM-DD'. Cached per process."""
    if _cache["days"] is not None and not force:
        return _cache["days"]
    days = set()
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.get("https://www.nseindia.com", timeout=15)          # prime cookies
        r = s.get(HOLIDAY_API, timeout=20)
        if r.status_code == 200:
            data = r.json()
            for h in data.get("CM", []):                        # CM = equity segment
                td = h.get("tradingDate")                       # e.g. "26-Jan-2026"
                try:
                    days.add(datetime.strptime(td, "%d-%b-%Y").strftime("%Y-%m-%d"))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    _cache["days"] = days
    return days


def is_holiday(iso_date):
    """True if `iso_date` (YYYY-MM-DD) is a known NSE trading holiday."""
    return iso_date in trading_holidays()


if __name__ == "__main__":
    h = sorted(trading_holidays())
    print(f"{len(h)} NSE trading holidays fetched")
    for d in h:
        print(" ", d)
