#!/usr/bin/env python3
"""Canonical production updater entrypoint.

The base updater has no OCR execution path. This wrapper also replaces the
legacy JR brochure parser with JR Central's official web/API source.
"""
import update_events as updater
from jr_walking_web import parse_jr_inazawa_walks


updater.parse_jr_inazawa_walks = parse_jr_inazawa_walks

if __name__ == "__main__":
    updater.main()
