# -*- coding: utf-8 -*-
"""
nse_utils.py — small shared helpers used by the fetchers (date parsing,
number parsing, monthly chunking). Single source of truth so the same logic
isn't copy-pasted across fetch_deals / fetch_corp_actions / fetch_short_selling
/ fetch_fii_dii.
"""
from datetime import date, datetime


def iso_date(dmy):
    """'01-FEB-2024' / '01-Feb-2024' -> '2024-02-01', or None if unparseable.
    (strptime's %b is case-insensitive, so upper/mixed-case months both work.)"""
    try:
        return datetime.strptime(str(dmy).strip(), "%d-%b-%Y").strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def parse_int(s):
    """Int from a possibly comma-grouped string ('2,62,628' -> 262628), or None."""
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def parse_float(s):
    """Float from a possibly comma-grouped string, or None."""
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def month_chunks(start, end):
    """Yield (first_day, last_day) date pairs, one per month, clipped to [start, end]."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
        yield max(cur, start), min(date.fromordinal(nxt.toordinal() - 1), end)
        cur = nxt
