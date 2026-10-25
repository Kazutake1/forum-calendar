#!/usr/bin/env python3
"""Read-only guard against lost, mutated, or duplicated monthly manual events.

This tool validates local monthly housekeeping output against the checked-out
main commit. No live data is written and no network requests are performed.
"""
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

from manage_manual_events import (
    DAYS_TO_KEEP, parse_date, read_events, report, validate_manual,
)

ARCHIVE_RE = re.compile(r"archive/manual_events_(\d{4})\.json\Z")
FIXED = frozenset(("manual_events.json", "reports/manual-event-review.md"))


def permitted(path):
    return path in FIXED or ARCHIVE_RE.fullmatch(path) is not None


def validate_transition(previous_manual, current_manual, previous_archives,
                        current_archives, today):
    """Exact records in active+archive must survive, with only 90-day moves."""
    if not isinstance(previous_manual, list) or not isinstance(current_manual, list):
        raise ValueError("Monthly manual event array missing")
    previous_archives = dict(previous_archives)
    current_archives = dict(current_archives)
    before_ids = set()
    for name, records in [("manual_events.json", previous_manual),
                          *sorted(previous_archives.items())]:
        validate_manual(records, Path(name), before_ids)
    after_ids = set()
    for name, records in [("manual_events.json", current_manual),
                          *sorted(current_archives.items())]:
        validate_manual(records, Path(name), after_ids)
        if name != "manual_events.json":
            match = ARCHIVE_RE.fullmatch(name)
            if not match or any(parse_date(row["date"]).year != int(match[1])
                                for row in records):
                raise ValueError("Monthly archive year mismatch")
    if before_ids != after_ids:
        raise ValueError("Monthly event identity lost or unexpectedly added")
    kept = []
    expected = {name: list(rows) for name, rows in previous_archives.items()}
    moved = []
    for row in previous_manual:
        if parse_date(row["date"]) + timedelta(days=DAYS_TO_KEEP) < today:
            name = f'archive/manual_events_{row["date"][:4]}.json'
            expected.setdefault(name, []).append(row)
            moved.append(row)
        else:
            kept.append(row)
    if current_manual != kept:
        raise ValueError("Active manual records were modified, lost, or reordered")
    if current_archives != expected:
        raise ValueError("Archive was modified, omitted, or unexpectedly extended")
    return kept, moved


def git(*args):
    return subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=20).stdout


def validate_local(root=Path("."), today=None):
    root = Path(root)
    today = today or datetime.now(ZoneInfo("Asia/Tokyo")).date()
    changed = set(git("diff", "--name-only", "HEAD", "--").decode().splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard").decode().splitlines())
    if not changed or any(not permitted(p) for p in changed):
        if changed:
            raise ValueError("Unexpected monthly worktree path; refusing publication")
    for name in changed:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing, non-regular, or symlink monthly output")
    before = json.loads(git("show", "HEAD:manual_events.json"))
    existing_paths = git("ls-tree", "-r", "--name-only", "HEAD", "--", "archive").decode().splitlines()
    old_archives = {}
    for name in existing_paths:
        if ARCHIVE_RE.fullmatch(name):
            old_archives[name] = json.loads(git("show", f"HEAD:{name}"))
    new_archives = {}
    for path in (root / "archive").glob("manual_events_*.json"):
        name = path.relative_to(root).as_posix()
        if not ARCHIVE_RE.fullmatch(name) or path.is_symlink() or not path.is_file():
            raise ValueError("Invalid monthly archive path or type")
        new_archives[name] = read_events(path)
    current = read_events(root / "manual_events.json")
    kept, moved = validate_transition(
        before, current, old_archives, new_archives, today)
    current_report = root / "reports/manual-event-review.md"
    if current_report.is_symlink() or not current_report.is_file():
        raise ValueError("Monthly report missing or invalid")
    automatic = read_events(root / "events.json")
    expected_text = report(
        today, kept,
        {root / name: rows for name, rows in new_archives.items()},
        moved, automatic)
    if current_report.read_text(encoding="utf-8") != expected_text:
        raise ValueError("Monthly report does not match validated archive")
    return len(kept), len(moved), sorted(changed)


if __name__ == "__main__":
    try:
        active, moved, changed = validate_local()
        print(f"Monthly archive preserved: active={active}, moved={moved}, files={len(changed)}")
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"Monthly archive verification failed: {exc}") from None
