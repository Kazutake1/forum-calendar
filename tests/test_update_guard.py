"""Regression cases for auto-update safety and source precedence; no network calls."""
import json
import tempfile
import unittest
from pathlib import Path

from event_integrity import combine_performance, same_performance, source_rank
from update_events import dedupe, load_required_events


class UpdateSafetyTests(unittest.TestCase):
    def test_saved_data_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            for value in (None, "{broken", "[]", "{}", '[{"date":"bad","title":"演奏会","hall":"中ホール"}]'):
                if value is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(value, encoding="utf-8")
                with self.subTest(value=value):
                    with self.assertRaises(RuntimeError):
                        load_required_events(path)
            valid = [{"date": "2026-10-31", "title": "演奏会", "hall": "中ホール", "time": "開演18:00"}]
            path.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_required_events(path), valid)

    def test_separate_performances_and_opening_time(self):
        a = {"date": "2026-10-31", "title": "演奏会", "hall": "中ホール", "time": "開演10:00"}
        b = dict(a, time="開演18:00")
        self.assertEqual(len(dedupe([a, b])), 2)
        with_opening = dict(b, time="開場17:30／開演18:00")
        self.assertTrue(same_performance(b, with_opening))
        self.assertEqual(len(dedupe([b, with_opening])), 1)
        self.assertEqual(dedupe([b, with_opening])[0]["time"], "開場17:30／開演18:00")

    def test_verified_event_official_over_city_over_x(self):
        base = {"date": "2026-10-31", "title": "演奏会", "hall": "中ホール", "time": "開演18:00"}
        x = dict(base, price="X価格", source_type="x", source_url="https://x.com/sample/status/123",
                 source_verified=True, verified_fields=["price"])
        city = dict(base, price="市価格", source_type="city_schedule",
                    source_url="https://www.city.inazawa.aichi.jp/ica/0000002507.html",
                    source_verified=True, verified_fields=["price"])
        official = dict(base, price="公式価格", source_type="event_official",
                        source_url="https://example.org/events/concert", source_verified=True,
                        event_specific=True, verified_fields=["price"])
        self.assertEqual([source_rank(item, "price") for item in (x, city, official)], [1, 2, 3])
        merged = combine_performance(x, city)
        self.assertEqual(merged["price"], "市価格")
        self.assertEqual(combine_performance(merged, official)["price"], "公式価格")
        self.assertEqual(combine_performance(official, x)["price"], "公式価格")
        self.assertEqual(source_rank(dict(official, event_specific=False), "price"), 0)

    def test_x_cannot_silently_overwrite_unverified_legacy(self):
        base = {"date": "2026-10-31", "title": "演奏会", "hall": "中ホール", "time": "開演18:00", "price": "旧データ"}
        x = dict(base, price="X価格", source_type="x", source_url="https://x.com/sample/status/123",
                 source_verified=True, verified_fields=["price"])
        self.assertEqual(combine_performance(base, x)["price"], "旧データ")


if __name__ == "__main__":
    unittest.main()
