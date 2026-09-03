#!/usr/bin/env python3
"""Safe updater entrypoint.

Disables schedule OCR replacement while preserving the current event data and
all other source update logic in update_events.py. This is intentionally small
so the existing updater remains the single source of truth.
"""
import update_events as updater


def disabled_ocr(_pdf_bytes):
    # Returning no OCR text makes parse_schedule_ocr produce zero events.
    # The existing confidence threshold then keeps the saved hall events.
    return ""


updater.ocr_pdf = disabled_ocr

if __name__ == "__main__":
    updater.main()
