#!/usr/bin/env python3
"""Archive expired manual events and write a non-destructive monthly review report.

The public app reads only manual_events.json. Archive files are never loaded by it.
This program never edits events.json, the updater, or existing event fields.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from html import escape
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

DAYS_TO_KEEP = 90
ARCHIVE_PATTERN = "manual_events_*.json"


def read_events(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"必要なデータファイルがありません: {path}")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or any(not isinstance(e, dict) for e in records):
        raise ValueError(f"イベント配列ではありません: {path}")
    return records


def parse_date(value: object) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"イベントの日付が不正です: {value!r}")
    return date.fromisoformat(value)


def validate_manual(records: list[dict], source: Path, seen: set[str]) -> None:
    for record in records:
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(f"手動イベントIDが不正です: {source}")
        if identifier in seen:
            raise ValueError(f"手動イベントIDが重複しています: {identifier}")
        seen.add(identifier)
        parse_date(record.get("date"))
        for field in ("title", "hall"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"手動イベントの{field}が不正です: {identifier}")


def venue_set(event: dict) -> set[str]:
    values = event.get("venues")
    if isinstance(values, list) and values:
        return {str(v).strip() for v in values if str(v).strip()}
    hall = str(event.get("hall") or "").strip()
    return {hall} if hall else set()


def normalized_title(value: object) -> str:
    title = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[\s\u3000「」『』【】（）()・.,。,:：!?！？\"'“”‘’]+", "", title)


def review_reason(a: dict, b: dict) -> str | None:
    a_date, b_date = parse_date(a.get("date")), parse_date(b.get("date"))
    same_title = normalized_title(a.get("title")) == normalized_title(b.get("title"))
    shared_venue = bool(venue_set(a) & venue_set(b))
    if a_date == b_date and same_title:
        return "同日・名称一致（会場・時間を照合）"
    if a_date == b_date and shared_venue:
        return "同日・同会場（別イベントの可能性もあり）"
    if same_title and abs((a_date - b_date).days) <= 7:
        return "名称一致・日付違い（延期や別公演を照合）"
    return None


def duplicate_candidates(active: list[dict], automatic: list[dict]) -> list[tuple]:
    candidates = []
    for i, manual in enumerate(active):
        for other in automatic:
            reason = review_reason(manual, other)
            if reason:
                candidates.append((manual, other, "自動取得", reason))
        for other in active[i + 1:]:
            reason = review_reason(manual, other)
            if reason:
                candidates.append((manual, other, "手動登録", reason))
    return sorted(candidates, key=lambda row: (row[0]["date"], row[0]["title"], row[2], str(row[1].get("title"))))


def cell(value: object) -> str:
    return escape(str(value if value is not None else "")).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def brief(event: dict) -> str:
    return f"{event.get('date', '')} / {event.get('title', '')} / {','.join(sorted(venue_set(event)))} / {event.get('time', '')}"


def report(today: date, active: list[dict], archives: dict[Path, list[dict]], moved: list[dict], automatic: list[dict]) -> str:
    candidates = duplicate_candidates(active, automatic)
    old_auto = [e for e in automatic if parse_date(e.get("date")) + timedelta(days=DAYS_TO_KEEP) < today]
    lines = [
        "# 手動イベント月次管理レポート", "",
        f"- 判定基準日（日本時間）: {today.isoformat()}",
        f"- 保管条件: 開催日 + {DAYS_TO_KEEP}日を過ぎた手動イベント",
        f"- 公開用の手動イベント: {len(active)}件",
        f"- 今回アーカイブへ移動: {len(moved)}件",
        f"- 年別アーカイブの合計: {sum(map(len, archives.values()))}件",
        f"- 重複・食い違いの確認候補: {len(candidates)}組",
        f"- 自動取得側に残っている開催後90日超のイベント: {len(old_auto)}件（今回の整理対象外）",
        "", "## 重複・食い違いの確認候補", "",
        "この表は自動削除・自動統合を行いません。実際に同じイベントか、稲沢市公式サイト等で確認してください。", "",
    ]
    if candidates:
        lines += ["| 手動イベント | 相手の種別 | 照合先 | 理由 |", "| --- | --- | --- | --- |"]
        for manual, other, kind, reason in candidates:
            lines.append(f"| {cell(brief(manual))} | {cell(kind)} | {cell(brief(other))} | {cell(reason)} |")
    else:
        lines.append("該当候補なし。名称・日付・会場の異なる重複は検出できないため、登録時の確認も継続してください。")
    lines += ["", "## 今回アーカイブしたイベント", ""]
    if moved:
        for e in sorted(moved, key=lambda item: (item["date"], item["id"])):
            lines.append(f"- {cell(e['date'])} — {cell(e['title'])}（ID: {cell(e['id'])}）")
    else:
        lines.append("該当なし。")
    lines += ["", "## 運用上の注意", "",
              "- 保存先は `archive/manual_events_YYYY.json`。元の項目・出典情報はすべて維持します。",
              "- アプリは `manual_events.json` のみを読み込むため、アーカイブ済みの手動イベントは表示されません。",
              "- `events.json` と自動更新プログラムは変更しません。自動取得側に残る過去イベントは別途検討が必要です。",
              "- 稲沢市公式サイトの確認済み情報を優先します。X由来の会場・時間等を市公式確認済みとみなしません。",
              "- 月次処理が失敗した場合、GitHub Actionsのログを確認し、データを手作業で削除しないでください。", ""]
    return "\n".join(lines)


def manage(root: Path, today: date, dry_run: bool = False) -> dict:
    active_path = root / "manual_events.json"
    automatic = read_events(root / "events.json")
    active = read_events(active_path)
    archive_dir = root / "archive"
    archives = {p: read_events(p) for p in sorted(archive_dir.glob(ARCHIVE_PATTERN))}

    ids: set[str] = set()
    validate_manual(active, active_path, ids)
    for path, records in archives.items():
        if not re.fullmatch(r"manual_events_\d{4}\.json", path.name):
            raise ValueError(f"アーカイブ名が不正です: {path}")
        validate_manual(records, path, ids)
        year = int(path.stem.removeprefix("manual_events_"))
        if any(parse_date(e["date"]).year != year for e in records):
            raise ValueError(f"アーカイブ年が一致しません: {path}")
    for e in automatic:
        parse_date(e.get("date"))
        if not isinstance(e.get("title"), str) or not e["title"].strip():
            raise ValueError("自動取得データのイベント名が不正です")

    kept: list[dict] = []
    moved: list[dict] = []
    for event in active:
        if parse_date(event["date"]) + timedelta(days=DAYS_TO_KEEP) < today:
            path = archive_dir / f"manual_events_{event['date'][:4]}.json"
            archives.setdefault(path, []).append(event)
            moved.append(event)
        else:
            kept.append(event)
    text = report(today, kept, archives, moved, automatic)
    report_path = root / "reports" / "manual-event-review.md"
    if not dry_run:
        # All data are fully validated before any writes. Git commits the changed
        # paths together; a failed workflow never pushes a partial archive.
        archive_dir.mkdir(exist_ok=True)
        for path, records in archives.items():
            new_text = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
            if not path.exists() or path.read_text(encoding="utf-8") != new_text:
                path.write_text(new_text, encoding="utf-8")
        if moved:
            active_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_path.parent.mkdir(exist_ok=True)
        if not report_path.exists() or report_path.read_text(encoding="utf-8") != text:
            report_path.write_text(text, encoding="utf-8")
    return {"active": len(kept), "moved": len(moved), "candidates": len(duplicate_candidates(kept, automatic)), "report": text}


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive manual events after 90 days and review duplicates monthly")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--today", type=parse_date, default=None, help="Test override YYYY-MM-DD; normal runs use JST")
    parser.add_argument("--dry-run", action="store_true", help="Calculate without changing files")
    args = parser.parse_args()
    today = args.today or datetime.now(ZoneInfo("Asia/Tokyo")).date()
    result = manage(args.root, today, args.dry_run)
    print(f"基準日={today} 公開用={result['active']}件 アーカイブ={result['moved']}件 確認候補={result['candidates']}組")
    if args.dry_run:
        print(result["report"])


if __name__ == "__main__":
    main()
