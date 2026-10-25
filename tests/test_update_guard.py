"""Regression cases for auto-update safety and source precedence; no network calls."""
import json
import tempfile
import unittest
import update_events
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from event_integrity import combine_performance, same_performance, source_rank
from update_events import (
    dedupe, is_non_event_guide_notice, is_stale_event_guide_notice, load_required_events,
    parse_event_guide, park_event_from_page,
)


class UpdateSafetyTests(unittest.TestCase):
    def _collect_park_fixture(self, city_events, city_checked, tourism_events=None, tourism_checked=0):
        """Run the real updater with only fictional sources and disposable files."""
        old_city = {
            "date": "2027-02-05", "title": "既存の市公式公園催事",
            "hall": "文化の丘公園", "venues": ["文化の丘公園"],
            "time": "10:00〜", "price": "無料", "source": "city_event_calendar",
            "official_url": "https://www.city.inazawa.aichi.jp/0000009991.html",
        }
        old_tourism = {
            "date": "2027-02-06", "title": "既存の観光協会公園催事",
            "hall": "文化の丘公園", "venues": ["文化の丘公園"],
            "time": "11:00〜", "price": "", "source": "tourism",
            "official_url": "https://www.inazawa-kankou.jp/archives/9991",
        }
        old_hall = {
            "date": "2027-02-07", "title": "既存のホール演奏会",
            "hall": "大ホール", "time": "14:00〜", "price": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events.json"
            meta = root / "update-meta.json"
            events.write_text(json.dumps([old_city, old_tourism, old_hall],
                                         ensure_ascii=False), encoding="utf-8")
            meta.write_text("{}", encoding="utf-8")
            with (
                patch.object(update_events, "EVENTS_FILE", events),
                patch.object(update_events, "META_FILE", meta),
                patch("update_events.discover_page",
                      side_effect=RuntimeError("fictional source unavailable")),
                patch("update_events.parse_event_guide", return_value=[]),
                patch("update_events.find_schedule_pdf",
                      side_effect=RuntimeError("fictional PDF unavailable")),
                patch("update_events.parse_city_park_events",
                      return_value=(city_events, city_checked)),
                patch("update_events.parse_tourism_park_events",
                      return_value=(tourism_events or [], tourism_checked)),
                patch("update_events.parse_jr_inazawa_walks",
                      side_effect=RuntimeError("fictional JR unavailable")),
            ):
                update_events.main()
            rows = json.loads(events.read_text(encoding="utf-8"))
            written_meta = json.loads(meta.read_text(encoding="utf-8"))
        return rows, written_meta, [old_city, old_tourism, old_hall]

    def test_empty_successful_city_calendar_cannot_delete_saved_park_events(self):
        rows, meta, original = self._collect_park_fixture([], 13)
        self.assertEqual(len(rows), 3)
        self.assertEqual({(e["date"], e["title"]) for e in rows},
                         {(e["date"], e["title"]) for e in original})
        self.assertTrue(any("既存イベントは保持" in note for note in meta["notes"]))

    def test_partial_city_calendar_adds_new_without_deleting_unseen_old_events(self):
        new = {
            "date": "2027-02-08", "title": "新しい市公式公園催事",
            "hall": "文化の丘公園", "venues": ["文化の丘公園"],
            "time": "13:00〜", "price": "", "source": "city_event_calendar",
            "official_url": "https://www.city.inazawa.aichi.jp/0000009992.html",
        }
        for pages_checked in (1, 13, 65):
            with self.subTest(pages_checked=pages_checked):
                rows, _, old = self._collect_park_fixture([new], pages_checked)
                pairs = {(e["date"], e["title"]) for e in rows}
                self.assertEqual(len(rows), 4)
                self.assertTrue({(e["date"], e["title"]) for e in old}.issubset(pairs))
                self.assertIn((new["date"], new["title"]), pairs)

    def test_tourism_results_cannot_remove_other_saved_park_events(self):
        new = {
            "date": "2027-02-09", "title": "新しい観光協会公園催事",
            "hall": "文化の丘公園", "venues": ["文化の丘公園"],
            "time": "15:00〜", "price": "", "source": "tourism",
            "official_url": "https://www.inazawa-kankou.jp/archives/9992",
        }
        rows, _, old = self._collect_park_fixture([], 13, [new], 1)
        pairs = {(e["date"], e["title"]) for e in rows}
        self.assertEqual(len(rows), 4)
        self.assertTrue({(e["date"], e["title"]) for e in old}.issubset(pairs))
        self.assertIn((new["date"], new["title"]), pairs)

    def test_park_source_failure_keeps_saved_records(self):
        rows, _, old = self._collect_park_fixture([], 0)
        self.assertEqual({(e["date"], e["title"]) for e in rows},
                         {(e["date"], e["title"]) for e in old})

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


    def test_event_guide_has_distinct_city_source_type(self):
        html = """
        <html><body>
          <h2>テストコンサート</h2>
          <p>開催日 令和9年3月22日</p>
          <p>会場 大ホール</p>
          <p>開催時間 14時00分</p>
        </body></html>
        """
        response = type("Response", (), {"text": html})()
        with patch("update_events.get", return_value=response):
            rows = parse_event_guide("https://www.city.inazawa.aichi.jp/ica/0000002507.html")
        self.assertEqual(len(rows), 1)
        event = rows[0]
        self.assertEqual(event["source"], "event_guide")
        self.assertEqual(event["source_type"], "city_event_guide")
        self.assertEqual(event["source_url"], "https://www.city.inazawa.aichi.jp/ica/0000002507.html")
        self.assertEqual(source_rank(event, "date"), 2)
        self.assertEqual(source_rank(event, "title"), 2)
        self.assertEqual(source_rank(event, "hall"), 2)
        self.assertEqual(source_rank(event, "time"), 2)

    def test_city_event_calendar_uses_city_rank_not_event_official_rank(self):
        event_date = date.today() + timedelta(days=30)
        html = f"""
        <html><body>
          <h1>稲沢まつり</h1>
          <p>開催日 {event_date.year}年{event_date.month}月{event_date.day}日</p>
          <p>開催時間 10時00分〜16時00分</p>
          <p>開催場所 文化の丘公園ほか</p>
        </body></html>
        """
        response = type("Response", (), {"text": html})()
        url = "https://www.city.inazawa.aichi.jp/0000000913.html"
        with patch("update_events.get", return_value=response):
            rows = park_event_from_page(url, "city_event_calendar")
        self.assertEqual(len(rows), 1)
        event = rows[0]
        self.assertEqual(event["source"], "city_event_calendar")
        self.assertEqual(event["source_type"], "city_event_calendar")
        self.assertEqual(event["source_url"], url)
        self.assertTrue(event["source_verified"])
        self.assertEqual(source_rank(event, "date"), 2)
        self.assertEqual(source_rank(event, "title"), 2)
        self.assertEqual(source_rank(event, "time"), 2)
        self.assertEqual(source_rank(event, "hall"), 0)


    def test_recruitment_notices_are_not_calendar_events(self):
        for title in (
            "出演者募集",
            "出演者募集中",
            "参加者を募集します",
            "参加者を募集しています",
            "参加者募集受付中",
            "ボランティア募集要項",
            "「音楽三昧」合唱団員募集（申込受付中）",
            "出演者募集のお知らせ",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_non_event_guide_notice(title))
        for title in (
            "ワンコインコンサートスペシャル 音楽三昧「ドイツ編」",
            "募集作品展",
            "合唱団演奏会",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_non_event_guide_notice(title))

        stale = {
            "date": "2027-03-22", "title": "出演者募集", "hall": "その他",
            "source": "event_guide",
        }
        self.assertTrue(is_stale_event_guide_notice(stale))
        self.assertFalse(is_stale_event_guide_notice(dict(stale, source="manual")))

    def test_same_source_unknown_time_dedupes_without_merging_other_records(self):
        base = {
            "date": "2027-03-22", "title": "テストイベント", "hall": "その他",
            "venues": ["その他"], "time": "", "price": "", "source": "event_guide",
            "official_url": "https://www.city.inazawa.aichi.jp/ica/0000002507.html",
        }
        richer = dict(
            base,
            source_type="city_schedule",
            source_url="https://www.city.inazawa.aichi.jp/ica/0000002507.html",
            source_verified=True,
            verified_fields=["date", "title"],
        )
        self.assertEqual(len(dedupe([base, richer])), 1)

        early = dict(base, title="同日同名公演", time="13:00〜")
        late = dict(base, title="同日同名公演", time="17:00〜")
        self.assertEqual(len(dedupe([early, late])), 2)

        other_url = dict(base, official_url="https://example.org/event")
        self.assertEqual(len(dedupe([base, other_url])), 2)

    def test_x_cannot_silently_overwrite_unverified_legacy(self):
        base = {"date": "2026-10-31", "title": "演奏会", "hall": "中ホール", "time": "開演18:00", "price": "旧データ"}
        x = dict(base, price="X価格", source_type="x", source_url="https://x.com/sample/status/123",
                 source_verified=True, verified_fields=["price"])
        self.assertEqual(combine_performance(base, x)["price"], "旧データ")


if __name__ == "__main__":
    unittest.main()
