# -*- coding: utf-8 -*-
"""
backup_db.py — safe timestamped backup of nse.db.

Uses SQLite's online-backup API, so the copy is consistent even if the
dashboard / run_daily is using the DB at the same time.

    python backup_db.py            # create a backup in backups/
    python backup_db.py --list     # list existing backups

Keeps the most recent KEEP backups; older ones are pruned automatically.
Restore: stop the app, then copy a chosen  backups/nse_*.db  over  nse.db.
"""
import os
import sys
import glob
import time
import sqlite3
from datetime import datetime

from config import DB_PATH

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")
KEEP = 5


def human(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def list_backups():
    return sorted(glob.glob(os.path.join(BACKUP_DIR, "nse_*.db")))


def backup():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found. Build it first (python run_daily.py).")
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, f"nse_{datetime.now():%Y%m%d_%H%M}.db")
    t0 = time.time()
    src = sqlite3.connect(DB_PATH)
    out = sqlite3.connect(dst)
    try:
        with out:
            src.backup(out)                       # consistent online copy
    finally:
        out.close()
        src.close()
    print(f"Backup created: {dst}  ({human(os.path.getsize(dst))}, {time.time()-t0:.0f}s)")

    # prune oldest, keep the most recent KEEP
    for f in list_backups()[:-KEEP]:
        os.remove(f)
        print(f"  pruned old backup: {os.path.basename(f)}")
    print(f"Backups kept: {len(list_backups())} (max {KEEP}) in {BACKUP_DIR}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        b = list_backups()
        print(f"{len(b)} backup(s) in {BACKUP_DIR}:")
        for f in b:
            print(f"  {os.path.basename(f)}  {human(os.path.getsize(f))}")
    else:
        backup()
