#!/usr/bin/env python3
"""JR Central Sawayaka Walking web-source parser.

Uses JR Central's official course search API and official detail pages.
Only courses whose start station is exactly 稲沢 are returned.
If no Inazawa course is published, raise an exception so the caller keeps any
existing JR-derived data instead of deleting it on an uncertain/empty result.
"""
from datetime import date
import re
from urllib.parse import quote_from_bytes, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://walking.jr-central.co.jp/"
SEARCH_API = urljoin(BASE, "common/_api/course_search")
TARGET_STATION = "稲沢"
UA = "forum-calendar-auto-updater/2.0 (+GitHub Actions)"
ALLOWED_HOST = "walking.jr-central.co.jp"


def _get(url):
    u = urlparse(url)
    if u.scheme != "https" or u.hostname != ALLOWED_HOST:
        raise RuntimeError("JR東海の許可されたHTTPS URLではありません")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
    r.raise_for_status()
    final = urlparse(r.url)
    if final.scheme != "https" or final.hostname != ALLOWED_HOST:
        raise RuntimeError("JR東海以外へリダイレクトされました")
    if len(r.content) > 10 * 1024 * 1024:
        raise RuntimeError("JR東海レスポンスが大きすぎます")
    ctype = r.headers.get("Content-Type", "").lower()
    if "text" in ctype or "json" in ctype or "javascript" in ctype:
        r.encoding = r.apparent_encoding or r.encoding
    return r


def _clean(value, limit=300):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _detail_time(detail_url):
    text = BeautifulSoup(_get(detail_url).text, "html.parser").get_text(" ", strip=True)
    m = re.search(r"スタート受付時間\s*(\d{1,2}:\d{2})\s*[～〜~\-－]\s*(\d{1,2}:\d{2})", text)
    if not m:
        return ""
    return f"{m.group(1)}〜{m.group(2)}"


def parse_jr_inazawa_walks():
    station_q = quote_from_bytes(TARGET_STATION.encode("shift_jis"))
    r = _get(f"{SEARCH_API}?stname={station_q}")
    try:
        payload = r.json()
    except Exception as e:
        raise RuntimeError("JR東海コース検索APIのJSON解析に失敗しました") from e

    rows = payload.get("result_list") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("JR東海コース検索APIの形式が想定外です")

    verified = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _clean(row.get("station_name"), 50) != TARGET_STATION:
            continue
        try:
            y = int(row.get("open_year"))
            m = int(row.get("open_month"))
            d = int(row.get("open_day"))
            event_date = date(y, m, d).isoformat()
        except Exception:
            continue

        detail_path = str(row.get("detail_page") or "")
        detail_url = urljoin(BASE, detail_path)
        parsed = urlparse(detail_url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or not parsed.path.startswith("/course/detail/"):
            continue

        title = _clean(row.get("title"), 240)
        if not title:
            continue

        verified.append({
            "date": event_date,
            "hall": "JR稲沢駅",
            "venues": ["JR稲沢駅"],
            "time": _detail_time(detail_url),
            "title": f"JR東海 さわやかウォーキング「{title}」",
            "price": "参加費無料・予約不要",
            "source": "jr_walking",
            "official_url": detail_url,
        })

    if not verified:
        raise RuntimeError("JR東海公式Webに稲沢駅スタートの公開コースなし（既存JRデータ維持）")

    deduped = {}
    for e in verified:
        deduped[(e["date"], e["title"], e["official_url"])] = e
    return list(deduped.values()), SEARCH_API
