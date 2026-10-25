#!/usr/bin/env python3
"""Fail closed on suspicious mass loss of daily calendar events.

Read the old canonical dataset from the checked-out Git commit, compare it to
the newly generated local dataset and do not modify either one. An unusually
large reduction is safer to investigate than to publish automatically.
"""
import json
import subprocess
import sys
from pathlib import Path

# This is a *stop threshold*, not a claim that smaller changes are correct.
# 40% is deliberately conservative for a public calendar with rolling events.
MAX_DROP_FRACTION = 0.40
MIN_BASELINE = 10


def event_count(raw, origin):
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"{origin}: invalid event JSON") from exc
    if not isinstance(rows, list) or not rows or any(not isinstance(e, dict) for e in rows):
        raise RuntimeError(f"{origin}: expected non-empty event array")
    return len(rows)


def validate_change(old_raw, new_raw):
    previous = event_count(old_raw, "Previous saved events")
    current = event_count(new_raw, "New generated events")
    if previous >= MIN_BASELINE and current < previous * (1 - MAX_DROP_FRACTION):
        raise RuntimeError(
            f"Event count dropped abnormally ({previous} to {current}); "
            "refusing automatic publication. Review the source/collector."
        )
    return previous, current


def main():
    try:
        saved = subprocess.run(
            ["git", "show", "HEAD:events.json"], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
        ).stdout
        generated = Path("events.json").read_bytes()
        old_count, new_count = validate_change(saved, generated)
    except (OSError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"Daily update safety check failed: {exc}") from None
    print(f"Daily event count safety check passed ({old_count} to {new_count}).")


if __name__ == "__main__":
    main()
