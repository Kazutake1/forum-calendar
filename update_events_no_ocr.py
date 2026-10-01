#!/usr/bin/env python3
"""Canonical production updater entrypoint.

The updater has no OCR execution path. JR Central Sawayaka Walking data is
provided by the official web/API parser imported by update_events.py.
"""
from update_events import main


if __name__ == "__main__":
    main()
