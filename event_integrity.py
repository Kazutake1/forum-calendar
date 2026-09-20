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
    if not starts:
        leading = re.match(r"^\s*" + clock + r"(?!\s*開場)", text)
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
        return bool(id_a and id_b and id_a == id_b)
    return False


def field_provenance(e: dict, field: str) -> dict:
    stored = e.get("field_sources")
    if isinstance(stored, dict) and isinstance(stored.get(field), dict):
        return dict(stored[field])
    kind = e.get(f"{field}_source_type") or e.get("source_type") or e.get("source") or "other"
    url = e.get(f"{field}_source_url") or e.get("source_url") or e.get("official_url") or ""
    verified = e.get(f"{field}_source_verified", e.get("source_verified", False)) is True
    allowed = e.get("verified_fields")
    if isinstance(allowed, list) and field not in allowed: verified = False
    specific = e.get(f"{field}_event_specific", e.get("event_specific", False)) is True
    return {"source_type": kind, "source_url": url, "verified": verified, "event_specific": specific}

def source_rank(e: dict, field: str) -> int:
    """Verified field: event-specific official 3 > city schedule 2 > X 1."""
    info = field_provenance(e, field)
    if info.get("verified") is not True: return 0
    try:
        parsed = urlparse(info.get("source_url") or "")
        if parsed.scheme != "https" or not parsed.hostname: return 0
    except (TypeError, ValueError): return 0
    kind = str(info.get("source_type") or "")
    if (kind in {"event_official", "promoter", "organizer"} and info.get("event_specific") is True
            and parsed.hostname not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}):
        return 3
    if parsed.hostname == CITY_HOST and kind in {"city_schedule", "city_official", *CITY_SOURCES}:
        return 2
    if kind == "x" and parsed.hostname in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return 1
    return 0

def city_verified(e: dict, field: str) -> bool:
    info = field_provenance(e, field)
    try: host = urlparse(info.get("source_url") or "").hostname
    except (TypeError, ValueError): return False
    return host == CITY_HOST and source_rank(e, field) >= 2

def combine_performance(current: dict, incoming: dict) -> dict:
    """Merge a *proven* single performance; keep conflicts for review."""
    merged = dict(current)
    evidence = dict(current.get("field_sources") or {})
    conflicts = list(current.get("review_conflicts") or [])
    for field in FIELDS:
        old,new=current.get(field),incoming.get(field)
        old_rank,new_rank=source_rank(current,field),source_rank(incoming,field)
        if new and (not old or (new_rank > old_rank and not (old_rank == 0 and new_rank == 1))):
            merged[field]=new
            evidence[field]=field_provenance(incoming,field)
        elif old == new and new_rank > old_rank:
            evidence[field]=field_provenance(incoming,field)
        elif old and new and old != new and old_rank == new_rank and old_rank > 0:
            conflict={"field":field,"existing":old,"incoming":new,"source_url":field_provenance(incoming,field).get("source_url","")}
            if conflict not in conflicts: conflicts.append(conflict)
        elif old and field not in evidence:
            evidence[field]=field_provenance(current,field)
    # Door-opening time is distinct from the start time: retain both.
    starts_a,doors_a=time_parts(current.get("time"))
    starts_b,doors_b=time_parts(incoming.get("time"))
    if len(starts_a)==len(starts_b)==1 and starts_a==starts_b and (doors_a or doors_b):
        chosen=doors_a or doors_b
        if doors_a and doors_b and doors_a != doors_b:
            chosen=doors_b if source_rank(incoming,"time")>source_rank(current,"time") else doors_a
            if source_rank(incoming,"time")==source_rank(current,"time"):
                conflict={"field":"opening_time","existing":doors_a,"incoming":doors_b}
                if conflict not in conflicts: conflicts.append(conflict)
        if len(chosen)==1:
            merged["time"]=f"開場{chosen[0]}／開演{starts_a[0]}"
            merged["opening_time_sources"]=[field_provenance(e,"time") for e in (current,incoming) if time_parts(e.get("time"))[1]]
    if merged.get("hall") != current.get("hall"):
        merged["venues"]=incoming.get("venues") or [incoming["hall"]]
    if evidence: merged["field_sources"]=evidence
    if conflicts: merged["review_conflicts"]=conflicts
    for key in ("event_id","performance_id"):
        if not merged.get(key) and incoming.get(key): merged[key]=incoming[key]
    sources=[]
    for record in (current,incoming):
        for token in str(record.get("source") or "").split("+"):
            if token and token not in sources: sources.append(token)
    if sources: merged["source"]="+".join(sources)
    return merged
