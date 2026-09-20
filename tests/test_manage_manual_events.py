import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from manage_manual_events import manage, review_reason


def event(identity, date_string, title="公演", hall="中ホール", **extras):
    return {"id": identity, "date": date_string, "title": title, "hall": hall,
            "source_type": "other", "source_url": "https://example.org/event", **extras}


class HousekeepingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(contents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def read(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def test_ninety_day_boundary_and_preservation(self):
        old = event("old", "2026-01-01", title="古い公演", source_note="出典の注記")
        boundary = event("boundary", "2026-01-02")
        future = event("future", "2026-10-31")
        self.write("manual_events.json", [old, boundary, future])
        self.write("events.json", [{"date": "2026-01-01", "title": "既存の自動", "hall": "中ホール"}])
        original_auto = (self.root / "events.json").read_bytes()
        result = manage(self.root, date(2026, 4, 2))
        self.assertEqual(result["moved"], 1)
        self.assertEqual([e["id"] for e in self.read("manual_events.json")], ["boundary", "future"])
        self.assertEqual(self.read("archive/manual_events_2026.json"), [old])
        self.assertEqual(self.read("archive/manual_events_2026.json")[0]["source_note"], "出典の注記")
        self.assertEqual((self.root / "events.json").read_bytes(), original_auto)
        self.assertIn("自動取得側に残っている開催後90日超", result["report"])

    def test_rerun_is_idempotent_and_archive_append(self):
        first = event("first", "2026-01-01")
        second = event("second", "2026-02-01")
        self.write("manual_events.json", [first, second])
        self.write("events.json", [])
        self.write("archive/manual_events_2026.json", [event("earlier", "2025-12-31")])
        # Invalid archive year must fail, never overwrite or silently fix.
        with self.assertRaisesRegex(ValueError, "アーカイブ年"):
            manage(self.root, date(2026, 5, 1))
        self.write("archive/manual_events_2026.json", [event("earlier", "2026-01-02")])
        manage(self.root, date(2026, 5, 5))
        snapshot = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*.json")}
        manage(self.root, date(2026, 5, 5))
        self.assertEqual(snapshot, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*.json")})
        self.assertEqual(len(self.read("archive/manual_events_2026.json")), 3)

    def test_cross_year_archive_and_monthly_report(self):
        self.write("manual_events.json", [event("dec", "2026-12-31")])
        self.write("events.json", [])
        result = manage(self.root, date(2027, 4, 2))
        self.assertEqual(result["moved"], 1)
        self.assertEqual(self.read("manual_events.json"), [])
        self.assertEqual(len(self.read("archive/manual_events_2026.json")), 1)
        self.assertIn("2027-04-02", (self.root / "reports/manual-event-review.md").read_text())

    def test_duplicate_candidates_only_reported_not_changed(self):
        manual = event("candidate", "2026-10-31", "ザッハトルテ", "中ホール")
        self.write("manual_events.json", [manual])
        self.write("events.json", [{"date": "2026-10-31", "title": "別名の催事", "hall": "中ホール"}])
        result = manage(self.root, date(2026, 9, 20))
        self.assertEqual(result["candidates"], 1)
        self.assertIn("同日・同会場", result["report"])
        self.assertEqual(self.read("manual_events.json"), [manual])

    def test_title_identical_date_changed_is_reviewed(self):
        self.assertIn("日付違い", review_reason(
            event("a", "2026-11-14", "講演会"),
            {"date": "2026-11-15", "title": "講演会", "hall": "大ホール"}))

    def test_invalid_or_repeated_id_aborts_without_writes(self):
        records = [event("same", "2026-01-01"), event("same", "2026-02-01")]
        self.write("manual_events.json", records)
        self.write("events.json", [])
        with self.assertRaisesRegex(ValueError, "重複"):
            manage(self.root, date(2026, 5, 1))
        self.assertFalse((self.root / "archive").exists())
        self.assertFalse((self.root / "reports").exists())
        self.assertEqual(self.read("manual_events.json"), records)

    def test_dry_run_never_changes_files(self):
        self.write("manual_events.json", [event("old", "2026-01-01")])
        self.write("events.json", [])
        result = manage(self.root, date(2026, 5, 1), dry_run=True)
        self.assertEqual(result["moved"], 1)
        self.assertFalse((self.root / "archive").exists())
        self.assertFalse((self.root / "reports").exists())
        self.assertEqual(len(self.read("manual_events.json")), 1)


if __name__ == "__main__":
    unittest.main()
