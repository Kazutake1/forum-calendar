#!/usr/bin/env python3
"""Safe updater entrypoint.

Disables schedule OCR replacement while preserving the current event data and
uses JR Central's official web/API source for Sawayaka Walking courses.
The existing updater remains the single source of truth for all other sources.
"""
import update_events as updater
from jr_walking_web import parse_jr_inazawa_walks


def disabled_ocr(_pdf_bytes):
    # Returning no OCR text makes parse_schedule_ocr produce zero events.
    # The existing confidence threshold then keeps the saved hall events.
    return ""


updater.ocr_pdf = disabled_ocr
updater.parse_jr_inazawa_walks = parse_jr_inazawa_walks

if __name__ == "__main__":
    updater.main()
