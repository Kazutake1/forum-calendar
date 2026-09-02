#!/usr/bin/env python3
"""Non-destructive network diagnostics for forum-calendar sources.

This script only performs GET requests and prints response metadata.
It does not modify events.json, update-meta.json, or any repository file.
"""
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

URLS = [
    ("schedule", "https://www.city.inazawa.aichi.jp/ica/0000004875.html"),
    ("events", "https://www.city.inazawa.aichi.jp/ica/0000002507.html"),
    ("ica_home", "https://www.city.inazawa.aichi.jp/ica/index.html"),
    ("sitemap", "https://www.city.inazawa.aichi.jp/sitemap.html"),
    ("jr_walking", "https://walking.jr-central.co.jp/index.html"),
]

UA = "forum-calendar-auto-updater/2.0 (+GitHub Actions; diagnostics)"
MAX_READ = 2 * 1024 * 1024


def clean(value, limit=300):
    return " ".join(str(value or "").replace("\u3000", " ").split())[:limit]


def diagnose(name, url):
    print(f"\n=== DIAG {name} ===")
    print(f"request_url={url}")
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"},
            timeout=30,
            stream=True,
        )
        print(f"status={r.status_code}")
        print(f"final_url={r.url}")
        print(f"redirects={len(r.history)}")
        if r.history:
            print("redirect_chain=" + " -> ".join(f"{x.status_code}:{x.url}" for x in r.history))
        print(f"content_type={r.headers.get('Content-Type','')}")
        print(f"content_length_header={r.headers.get('Content-Length','')}")
        print(f"server={r.headers.get('Server','')}")
        print(f"via={r.headers.get('Via','')}")
        print(f"cf_ray={r.headers.get('CF-RAY','')}")

        data = bytearray()
        for chunk in r.iter_content(65536):
            if chunk:
                data.extend(chunk)
                if len(data) >= MAX_READ:
                    break
        print(f"bytes_read={len(data)}")

        ctype = (r.headers.get("Content-Type") or "").lower()
        if "html" in ctype or data[:50].lstrip().lower().startswith((b"<!doctype html", b"<html")):
            encoding = r.encoding or "utf-8"
            text = bytes(data).decode(encoding, errors="replace")
            soup = BeautifulSoup(text, "html.parser")
            title = clean(soup.title.get_text(" ", strip=True) if soup.title else "")
            h1 = clean(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
            body = clean(soup.get_text(" ", strip=True), 500)
            print(f"title={title}")
            print(f"h1={h1}")
            print(f"contains_schedule={'ホール催事予定表' in text}")
            print(f"contains_event_word={'イベント' in text}")
            print(f"body_preview={body}")
        else:
            print(f"first_bytes={bytes(data[:32]).hex()}")

        final = urlparse(r.url)
        print(f"final_scheme={final.scheme}")
        print(f"final_host={final.hostname}")
    except Exception as e:
        print(f"exception_type={type(e).__name__}")
        print(f"exception={clean(e,500)}")


if __name__ == "__main__":
    for name, url in URLS:
        diagnose(name, url)
