# -*- coding: utf-8 -*-
"""Parsing tests for the lightweight fetchers (no network / DB)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_secban
import fetch_fii_dii
import fetch_short_selling


# --------------------------------------------------------------------------- #
# fetch_secban.parse_secban
# --------------------------------------------------------------------------- #
def test_secban_nil_day():
    assert fetch_secban.parse_secban("Securities in Ban For Trade Date 31-JUL-2026: NIL") == []


def test_secban_populated():
    text = "Securities in Ban For Trade Date 05-FEB-2024:\n1,HINDCOPPER\n2,INDIACEM\n3,SAIL\n"
    assert fetch_secban.parse_secban(text) == ["HINDCOPPER", "INDIACEM", "SAIL"]


def test_secban_empty_text():
    assert fetch_secban.parse_secban("") == []


# --------------------------------------------------------------------------- #
# fetch_fii_dii.parse
# --------------------------------------------------------------------------- #
def test_fiidii_parse():
    js = ('[{"buyValue":"19885.8","category":"DII","date":"31-Jul-2026",'
          '"netValue":"2260.37","sellValue":"17625.43"},'
          '{"buyValue":"19045.51","category":"FII/FPI","date":"31-Jul-2026",'
          '"netValue":"277.48","sellValue":"18768.03"}]')
    rows = list(fetch_fii_dii.parse(js))
    assert rows[0] == ("2026-07-31", "DII", 19885.8, 17625.43, 2260.37)
    assert rows[1][1] == "FII/FPI"
    assert abs(rows[1][4] - 277.48) < 1e-9


# --------------------------------------------------------------------------- #
# fetch_short_selling.parse
# --------------------------------------------------------------------------- #
def test_short_selling_parse():
    csv_text = ('"Date ","Symbol ","Security Name ","Quantity "\n'
                '"01-FEB-2024","METROPOLIS","METROPOLIS HEALTHCARE LIMITED","4,800"\n'
                '"02-FEB-2024","IBULHSGFIN","INDIABULLS HOUSING","12,34,567"\n')
    rows = list(fetch_short_selling.parse(csv_text))
    assert rows[0] == ("2024-02-01", "METROPOLIS", 4800)
    assert rows[1] == ("2024-02-02", "IBULHSGFIN", 1234567)   # Indian-comma qty parsed


def test_short_selling_no_records():
    assert list(fetch_short_selling.parse('"Date ","Symbol ","Name ","Quantity "\nNO RECORDS,,,\n')) == []
