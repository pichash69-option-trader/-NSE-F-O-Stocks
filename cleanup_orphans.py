# -*- coding: utf-8 -*-
"""
cleanup_orphans.py — remove orphaned F&O data and shrink the DB.

Over time, stocks enter and exit the NSE F&O list. Equity (prices) is fetched
only for the CURRENT F&O universe, but futures/options bhavcopies are kept for
every stock they contained on each day. So stocks that later EXIT F&O leave
behind futures/options rows that no longer have any equity data — "orphans".
They are never shown in the dashboard (the stock dropdown = symbols in `prices`),
they just take up space.

This script deletes any futures/options rows whose symbol is NOT in `prices`
(i.e. not a current F&O stock) and then VACUUMs to reclaim disk space.

Safe:
  - Only touches `futures` and `options`. `prices`, `stats`, `participant`
    are never modified.
  - Never deletes a symbol that exists in `prices` (active stock).
  - Incremental daily updates do NOT re-create orphans (fetch is forward-only),
    so this only needs running occasionally (e.g. after F&O list revisions).

Usage:
    python cleanup_orphans.py            # clean + shrink
    python cleanup_orphans.py --dry-run  # only report, delete nothing

NOTE: stop the dashboard first (VACUUM needs an exclusive lock to shrink the
file). If VACUUM can't get the lock, the delete still succeeds — just re-run to
reclaim space when the dashboard is closed.
"""
import os
import sys
import time
import sqlite3

from config import DB_PATH

# Windows consoles default to cp1252 and choke on emoji/✓ — force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _mb(n):
    return f"{n / 1e6:,.0f} MB"


def orphan_symbols(conn):
    """Symbols present in futures/options but absent from prices (exited F&O)."""
    prices = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM prices")}
    fut = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM futures")}
    opt = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM options")}
    return sorted((fut | opt) - prices), len(prices)


def main():
    dry_run = "--dry-run" in sys.argv
    size_before = os.path.getsize(DB_PATH)
    print(f"DB: {DB_PATH}")
    print(f"Size before: {_mb(size_before)}\n")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=30000")           # wait up to 30s for locks
    try:
        orphans, n_prices = orphan_symbols(conn)
        print(f"Active (prices) symbols : {n_prices}")
        print(f"Orphan symbols (exited F&O): {len(orphans)}")
        if not orphans:
            print("\nNothing to clean — no orphans. ✅")
            return
        print("  " + ", ".join(orphans))

        ph = ",".join("?" * len(orphans))
        fut_n = conn.execute(
            f"SELECT COUNT(*) FROM futures WHERE symbol IN ({ph})", orphans).fetchone()[0]
        print(f"\nRows to delete -> futures: {fut_n:,}   options: (counting…)", flush=True)
        opt_n = conn.execute(
            f"SELECT COUNT(*) FROM options WHERE symbol IN ({ph})", orphans).fetchone()[0]
        print(f"Rows to delete -> futures: {fut_n:,}   options: {opt_n:,}")

        # Safety: never delete an active symbol.
        prices = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM prices")}
        assert not (set(orphans) & prices), "orphan overlaps active symbols — aborting!"

        if dry_run:
            print("\n--dry-run: nothing deleted. Run without --dry-run to apply.")
            return

        print("\nDeleting…", flush=True)
        conn.execute(f"DELETE FROM futures WHERE symbol IN ({ph})", orphans)
        conn.execute(f"DELETE FROM options WHERE symbol IN ({ph})", orphans)
        conn.commit()
        print("Deleted. Reclaiming space (VACUUM)…", flush=True)

        # Reclaim disk: fold any WAL into the main file, leave WAL mode so VACUUM
        # rewrites a single compact file (VACUUM in WAL mode bloats the -wal file
        # instead of shrinking the db), then restore WAL for the app.
        t = time.time()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("VACUUM")
            conn.execute("PRAGMA journal_mode=WAL")
            print(f"VACUUM done in {time.time() - t:.0f}s")
        except sqlite3.OperationalError as e:
            print(f"⚠️  Could not VACUUM ({e}). Delete is saved; close the dashboard "
                  f"and re-run to reclaim space.")
    finally:
        conn.close()

    size_after = os.path.getsize(DB_PATH)
    print(f"\nSize after : {_mb(size_after)}  "
          f"(freed {_mb(max(0, size_before - size_after))})")
    print("Done. ✅")


if __name__ == "__main__":
    main()
