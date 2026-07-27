# -*- coding: utf-8 -*-
"""
universe.py — derive the tradable F&O stock universe from NSE's F&O bhavcopy.

The set of stocks in F&O changes over time, so instead of a hard-coded list we
read the most recent F&O bhavcopy and take every stock-futures (STF) symbol.
Self-contained (no extra data files), and always current.
"""
import io
import csv
import zipfile
from datetime import date, timedelta

import requests

from config import HEADERS, REQUEST_TIMEOUT

FO_URL = ("https://nsearchives.nseindia.com/content/fo/"
          "BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip")

_cache = {"symbols": None}


def fno_universe(days_back=12, force=False):
    """Return the set of F&O stock symbols (STF) from the latest available
    F&O bhavcopy. Result is cached for the process. Empty set if unreachable."""
    if _cache["symbols"] is not None and not force:
        return _cache["symbols"]

    d = date.today()
    for _ in range(days_back):
        if d.weekday() < 5:                       # skip weekends
            try:
                r = requests.get(FO_URL.format(ymd=d.strftime("%Y%m%d")),
                                 headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    z = zipfile.ZipFile(io.BytesIO(r.content))
                    raw = z.open(z.namelist()[0]).read().decode("utf-8", "replace")
                    syms = {row["TckrSymb"].strip()
                            for row in csv.DictReader(io.StringIO(raw))
                            if row.get("FinInstrmTp", "").strip() == "STF"}
                    if syms:
                        _cache["symbols"] = syms
                        return syms
            except Exception:
                pass
        d -= timedelta(days=1)
    _cache["symbols"] = set()
    return _cache["symbols"]


if __name__ == "__main__":
    u = fno_universe()
    print(f"F&O universe: {len(u)} stocks")
    print(sorted(u))
