"""
Manual test script for LogCleaner.

Creates a controlled set of fake log files, error snapshot dirs, and screenshot
files with dates spread across the past, then runs the cleaner and reports
exactly what was deleted and what survived.

Usage:
    .\\toolkit\\python.exe dev_tools\\test_log_cleaner.py

Options (edit the constants below):
    KEEP_DAYS    -- retention window passed to clean_logs()
    SHOW_TREE    -- print directory tree before/after cleanup
"""

import os
import shutil
import sys
import time
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KEEP_DAYS = 7  # days to retain
SHOW_TREE = True  # print dir tree before / after

# ---------------------------------------------------------------------------
# Bootstrap: make sure project root is importable
# ---------------------------------------------------------------------------
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from module.logger import logger
import module.log_cleaner as lc_module
from module.log_cleaner import LogCleaner

# ---------------------------------------------------------------------------
# Fake directory layout (isolated from real data)
# ---------------------------------------------------------------------------
TEST_BASE = "./_test_log_cleaner"
TEST_LOG_DIR = os.path.join(TEST_BASE, "log")
TEST_ERROR_DIR = os.path.join(TEST_BASE, "log", "error")
TEST_SS_DIR = os.path.join(TEST_BASE, "screenshots")

# Age buckets for test fixtures (days ago)
AGES = {
    "old": KEEP_DAYS + 3,  # definitely outside retention window
    "edge": KEEP_DAYS,  # exactly at the boundary (should be deleted,
    # cutoff = today - KEEP_DAYS, file_date < cutoff)
    "recent": KEEP_DAYS - 1,  # inside retention window
    "today": 0,  # today
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_timestamp(days_ago):
    """Return a millisecond timestamp for midnight N days ago."""
    d = datetime.now() - timedelta(days=days_ago)
    d = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp() * 1000)


def _date_str(days_ago):
    """Return YYYY-MM-DD string for N days ago."""
    return (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def touch(path, content="test\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def make_error_dir(ts_ms):
    """Create a fake ./log/error/<ts_ms>/ directory with a log.txt inside."""
    d = os.path.join(TEST_ERROR_DIR, str(ts_ms))
    os.makedirs(d, exist_ok=True)
    touch(os.path.join(d, "log.txt"), f"error snapshot ts={ts_ms}\n")
    touch(os.path.join(d, "2026-01-01_00-00-00-000.png"), "")


def tree(root, prefix=""):
    """Yield lines representing the directory tree under root."""
    if not os.path.exists(root):
        yield f"{prefix}(does not exist)"
        return
    entries = sorted(os.listdir(root))
    for i, name in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        path = os.path.join(root, name)
        yield prefix + connector + name
        if os.path.isdir(path):
            extension = "    " if i == len(entries) - 1 else "│   "
            yield from tree(path, prefix + extension)


def print_tree(label, root):
    print(f"\n[{label}]  {root}")
    for line in tree(root):
        print(line)


# ---------------------------------------------------------------------------
# Test fixture creation
# ---------------------------------------------------------------------------


def create_fixtures():
    """Create fake files/dirs spread across different age buckets."""
    shutil.rmtree(TEST_BASE, ignore_errors=True)
    os.makedirs(TEST_ERROR_DIR, exist_ok=True)
    os.makedirs(os.path.join(TEST_SS_DIR, "items"), exist_ok=True)
    os.makedirs(os.path.join(TEST_SS_DIR, "combat"), exist_ok=True)
    os.makedirs(os.path.join(TEST_SS_DIR, "research"), exist_ok=True)

    created = []

    # --- log files ---
    for label, days in AGES.items():
        fname = f"{_date_str(days)}_alas.txt"
        path = os.path.join(TEST_LOG_DIR, fname)
        touch(path, f"# fake log ({label}, {days}d ago)\n")
        created.append(("log", label, days, path))

    # Extra: file WITHOUT date prefix (should never be touched)
    no_date = os.path.join(TEST_LOG_DIR, "recent.txt")
    touch(no_date, "# no date prefix\n")
    created.append(("log-nodate", "n/a", 0, no_date))

    # --- error snapshot dirs ---
    for label, days in AGES.items():
        ts = _ms_timestamp(days)
        make_error_dir(ts)
        created.append(
            ("error-dir", label, days, os.path.join(TEST_ERROR_DIR, str(ts)))
        )

    # --- screenshots ---
    # items: mix of old and recent -> subdir should survive (has remaining files)
    for label, days in AGES.items():
        ts = _ms_timestamp(days)
        path = os.path.join(TEST_SS_DIR, "items", f"{ts}.png")
        touch(path, "")
        created.append(("screenshot", label, days, path))

    # combat: only old files -> subdir should be removed after cleanup
    for label in ("old", "edge"):
        days = AGES[label]
        ts = _ms_timestamp(days)
        path = os.path.join(TEST_SS_DIR, "combat", f"{ts}.png")
        touch(path, "")
        created.append(("screenshot", label, days, path))

    # research: only recent files -> subdir should survive untouched
    for label in ("recent", "today"):
        days = AGES[label]
        ts = _ms_timestamp(days)
        path = os.path.join(TEST_SS_DIR, "research", f"{ts}.png")
        touch(path, "")
        created.append(("screenshot", label, days, path))

    # only_old: ALL files are old -> subdir itself should be removed after cleanup
    os.makedirs(os.path.join(TEST_SS_DIR, "only_old"), exist_ok=True)
    for label in ("old",):
        days = AGES[label]
        ts = _ms_timestamp(days)
        path = os.path.join(TEST_SS_DIR, "only_old", f"{ts}.png")
        touch(path, "")
        created.append(("screenshot", label, days, path))

    return created


# ---------------------------------------------------------------------------
# Snapshot: record existence of every fixture before/after
# ---------------------------------------------------------------------------


def snapshot(fixtures):
    """Return dict mapping path -> exists."""
    result = {}
    for _, _, _, path in fixtures:
        result[path] = os.path.exists(path)
    # Track subdir existence separately for empty-dir removal checks
    for subdir in ("combat", "only_old"):
        d = os.path.join(TEST_SS_DIR, subdir)
        result[d] = os.path.exists(d)
    return result


# ---------------------------------------------------------------------------
# Expectations
# ---------------------------------------------------------------------------


def expected_deleted(kind, label, days):
    """
    Return True if this fixture should be deleted given KEEP_DAYS.
    cutoff = today - KEEP_DAYS; items with date < cutoff are deleted.
    """
    cutoff_days = KEEP_DAYS  # items older than this (strictly) are deleted
    if kind == "log-nodate":
        return False  # never touched
    return days > cutoff_days


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def report(fixtures, before, after):
    cutoff_date = date.today() - timedelta(days=KEEP_DAYS)
    print(f"\nKeep days : {KEEP_DAYS}")
    print(f"Cutoff    : {cutoff_date}  (files older than this date are deleted)")
    print()

    col = "{:<12} {:<10} {:<6} {:<8} {:<8} {:<8} {}"
    print(col.format("TYPE", "AGE-LABEL", "DAYS", "EXPECT", "RESULT", "STATUS", "PATH"))
    print("-" * 100)

    passed = 0
    failed = 0

    for kind, label, days, path in fixtures:
        was_there = before.get(path, False)
        is_there = after.get(path, False)
        got_deleted = was_there and not is_there
        exp_deleted = expected_deleted(kind, label, days)

        ok = got_deleted == exp_deleted
        status = "PASS" if ok else "FAIL"
        expect_str = "DELETE" if exp_deleted else "KEEP"
        result_str = "DELETED" if got_deleted else "KEPT"

        rel = os.path.relpath(path, TEST_BASE)
        print(
            col.format(
                kind, label, str(days) + "d", expect_str, result_str, status, rel
            )
        )

        if ok:
            passed += 1
        else:
            failed += 1

    # Check empty-dir removal for combat subdir.
    # combat has 'old' (deleted) and 'edge' (kept, days==KEEP_DAYS is NOT deleted).
    # So one file remains -> dir should NOT be removed.
    combat_dir = os.path.join(TEST_SS_DIR, "combat")
    was_there = before.get(combat_dir, False)
    is_there = after.get(combat_dir, False)
    got_removed = was_there and not is_there
    expect_removed = False  # edge file survives, so dir is non-empty
    ok = got_removed == expect_removed
    status = "PASS" if ok else "FAIL"
    result_str = "REMOVED" if got_removed else "STILL EXISTS"
    expect_str = "KEEP"
    rel = os.path.relpath(combat_dir, TEST_BASE)
    print(col.format("empty-dir", "combat", "-", expect_str, result_str, status, rel))
    if ok:
        passed += 1
    else:
        failed += 1

    # Also check that a dir becomes truly empty when ALL its files are deleted.
    # (This is validated implicitly by the 'combat' dir having one edge file kept.
    #  The full empty-dir removal path is exercised by the earlier e2e test.)
    # Check empty-dir removal for only_old subdir.
    # only_old has only 'old' files -> all deleted -> dir should be removed.
    only_old_dir = os.path.join(TEST_SS_DIR, "only_old")
    was_there = before.get(only_old_dir, False)
    is_there = after.get(only_old_dir, False)
    got_removed = was_there and not is_there
    expect_removed = True
    ok = got_removed == expect_removed
    status = "PASS" if ok else "FAIL"
    result_str = "REMOVED" if got_removed else "STILL EXISTS"
    expect_str = "REMOVE"
    rel = os.path.relpath(only_old_dir, TEST_BASE)
    print(col.format("empty-dir", "only_old", "-", expect_str, result_str, status, rel))
    if ok:
        passed += 1
    else:
        failed += 1

    print("-" * 100)
    print(f"Result: {passed} passed, {failed} failed")
    return failed == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logger.hr("LogCleaner Manual Test", level=0)

    # Patch module-level directory constants so the cleaner uses our test dirs
    original_log_dir = lc_module.LOG_DIR
    original_error_dir = lc_module.LOG_ERROR_DIR
    lc_module.LOG_DIR = TEST_LOG_DIR
    lc_module.LOG_ERROR_DIR = TEST_ERROR_DIR

    try:
        # 1. Create fixtures
        print("\n=== Creating test fixtures ===")
        fixtures = create_fixtures()
        print(f"Created {len(fixtures)} fixture entries under {TEST_BASE}/")

        if SHOW_TREE:
            print_tree("BEFORE cleanup", TEST_BASE)

        # 2. Snapshot before
        before = snapshot(fixtures)

        # 3. Build a minimal config mock
        class FakeConfig:
            LogCleaner_KeepDays = KEEP_DAYS
            LogCleaner_ScheduledTime = "00:00"
            DropRecord_SaveFolder = TEST_SS_DIR

        # 4. Run the cleaner
        print(f"\n=== Running LogCleaner (keep_days={KEEP_DAYS}) ===")
        cleaner = LogCleaner(FakeConfig())
        cleaner.clean_logs(keep_days=KEEP_DAYS)

        # 5. Snapshot after
        after = snapshot(fixtures)

        if SHOW_TREE:
            print_tree("AFTER cleanup", TEST_BASE)

        # 6. Report
        print("\n=== Test Results ===")
        success = report(fixtures, before, after)

    finally:
        # Restore patched constants
        lc_module.LOG_DIR = original_log_dir
        lc_module.LOG_ERROR_DIR = original_error_dir
        # Clean up test directory
        shutil.rmtree(TEST_BASE, ignore_errors=True)
        print(f"\nTest directory {TEST_BASE}/ removed.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
