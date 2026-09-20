"""Conservative identity/provenance rules for automatic event updates.

A calendar event (title/date) can contain several independently ticketed
performances. Unknown time or a door-opening time is NOT proof of identity.
Corrections to conflicting performances require reviewed IDs/evidence.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

CITY_HOST = "www.city.inazawa.aichi.jp"
CITY_SOURCES = {"event_guide", "city_event_calendar", "schedule_ocr"}
FIELDS = ("date", "title", "hall", "time", "price", "official_url")


def normalize_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r'[\s\u3000「」『』【】（）()・.,。,:：!?！？"\'“”‘’]+', "", text)


def time_parts(value: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (start times, door times); do not mistake doors for starts."""
    text = unicodedata.normalize("NFKC", str(value or "")).replace("：", ":")
    clock = r"(\d{1,2}):(\d{2})"
    def extract(pattern: str) -> tuple[str, ...]:
        result = []
        for match in re.finditer(pattern, text):
            h, m = int(match.group(1)), int(match.group(2))
            if h < 24 and m < 60:
                value = f"{h:02d}:{m:02d}"
                if value not in result:
                    result.append(value)
        return tuple(result)
    starts = extract(r"(?:開演|開始)\s*" + clock)
    doors = extract(r"開場\s*" + clock)
    if not starts and not doors:
        leading = re.match(r"^\s*" + clock, text)
        if leading:
            h, m = map(int, leading.groups())
            if h < 24 and m < 60:
                starts = (f"{h:02d}:{m:02d}",)
                # Slash-delimited two showtimes, unlike a start/end range.
                if "/" in text:
                    starts = extract(clock)
    return starts, doors


def venue_names(e: dict) -> set[str]:
    places = e.get("venues")
    if isinstance(places, list) and places:
        return {v.strip() for v in places if isinstance(v, str) and v.strip()}
    place = e.get("hall")
    return {place.strip()} if isinstance(place, str) and place.strip() else set()


def same_performance(a: dict, b: dict) -> bool:
    if a.get("date") != b.get("date") or normalize_title(a.get("title")) != normalize_title(b.get("title")):
        return False
    if not (venue_names(a) & venue_names(b)):
        return False
    id_a, id_b = a.get("performance_id"), b.get("performance_id")
    if id_a and id_b:
        return id_a == id_b  # Reviewed stable IDs can identify corrected times.
    starts_a, doors_a = time_parts(a.get("time"))
    starts_b, doors_b = time_parts(b.get("time"))
    if len(starts_a) == len(starts_b) == 1:
        return starts_a == starts_b
    if starts_a or starts_b:
        return bool(a.get("time")) and a.get("time") == b.get("time")
    if doors_a and doors_b:
        return doors_a == doors_b
    # Even two missing times are not proof, unless they refer to one exact URL.
    if not a.get("time") and not b.get("time"):
        return bool(a.get("official_url")) and a.get("official_url") == b.get("official_url")
    return False


def field_provenance(e: dict, field: str) -> dict:
    stored = e.get("field_sources")
    if isinstance(stored, dict) and isinstance(stored.get(field), dict):
        return dict(stored[field])
    source_type = e.get(f"{field}_source_type") or e.get("source_type") or e.get("source") or "other"
    url = e.get(f"{field}_source_url") or e.get("source_url") or e.get("official_url") or ""
    verified = e.get(f"{field}_source_verified", e.get("source_verified", False)) is True
    allowed = e.get("verified_fields")
    if isinstance(allowed, list) and field not in allowed:
        verified = False
    return {"source_type": source_type, "source_url": url, "verified": verified}


def city_verified(e: dict, field: str) -> bool:
    info = field_provenance(e, field)
    url = info.get("source_url")
    try:
        parsed = urlparse(url)
        municipal = parsed.scheme == "https" and parsed.hostname == CITY_HOST
    except (TypeError, ValueError):
        municipal = False
    sources = str(info.get("source_type") or "").split("+")
    return municipal and info.get("verified") is True and any(
        source in CITY_SOURCES or source == "city_official" for source in sources
    )


def combine_performance(current: dict, incoming: dict) -> dict:
    """Keep existing fields unless the incoming specific field is city-verified."""
    merged = dict(current)
    field_sources = dict(current.get("field_sources") or {})
    for field in FIELDS:
        old, new = current.get(field), incoming.get(field)
        if (new and city_verified(incoming, field) and not city_verified(current, field)) or (not old and new):
            merged[field] = new
            field_sources[field] = field_provenance(incoming, field)
        elif old and field not in field_sources:
            field_sources[field] = field_provenance(current, field)
    if field_sources:
        merged["field_sources"] = field_sources
    combined_sources = []
    for record in (current, incoming):
        for token in str(record.get("source") or "").split("+"):
            if token and token not in combined_sources:
                combined_sources.append(token)
    if combined_sources:
        merged["source"] = "+".join(combined_sources)
    # Never overwrite a municipal URL merely because a later source has a URL.
    if current.get("official_url") and incoming.get("official_url") and not city_verified(incoming, "official_url"):
        merged["official_url"] = current["official_url"]
    return merged
