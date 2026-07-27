# -*- coding: utf-8 -*-
"""
run_daily.py — one command that keeps everything up to date.

Steps (in order):
  1. Equity + delivery  (fetch_data.run)
  2. F&O futures + options (fetch_fno.run)
  3. Math stats           (analysis.run)

First run  = full backfill from 1-Jan-2024 to today (resume-safe, may take a while).
Later runs = incremental — only the missing days — so it's fast.

Meant to be scheduled daily (see task_scheduler_setup.txt). Also fine to run by hand:
    python run_daily.py
Everything it prints is also appended to run_daily.log.
"""
import sys
import time
import logging
from datetime import datetime

import fetch_data
import fetch_fno
import fetch_participant
import analysis
from config import BASE_DIR

# Windows consoles default to cp1252 and choke on box-drawing / ✓ chars.
# Force UTF-8 so stdout logging never errors (the file handler is already utf-8).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

LOG_FILE = BASE_DIR / "run_daily.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("run_daily")


def _step(name, fn):
    log.info(f"── {name} ─────────────────────────────")
    t0 = time.time()
    try:
        fn()
        log.info(f"✓ {name} done in {time.time() - t0:.0f}s")
        return True
    except Exception as e:
        log.exception(f"✗ {name} FAILED: {e}")
        return False


def main():
    log.info("=" * 60)
    log.info(f"run_daily START  {datetime.now():%Y-%m-%d %H:%M:%S}")
    t0 = time.time()

    ok_eq = _step("1/4 Equity + delivery", fetch_data.run)
    ok_fo = _step("2/4 F&O futures + options", fetch_fno.run)
    ok_pt = _step("3/4 Participant OI/Vol (FII/DII/Pro/Client)", fetch_participant.run)
    # Stats only make sense if we have price data; run even if F&O partially failed.
    ok_an = _step("4/4 Math stats", analysis.run)

    dur = time.time() - t0
    ok_all = ok_eq and ok_fo and ok_pt and ok_an
    status = "OK" if ok_all else "COMPLETED WITH ERRORS"
    log.info(f"run_daily END  [{status}]  total {dur/60:.1f} min")
    log.info("=" * 60)
    # Non-zero exit if anything failed (useful for Task Scheduler result codes)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
