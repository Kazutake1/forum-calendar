import unittest
from types import SimpleNamespace
from unittest.mock import patch

from event_integrity import source_rank
from jr_walking_web import SEARCH_API, parse_jr_inazawa_walks


class JrWalkingWebTests(unittest.TestCase):
    def test_only_exact_inazawa_start_station_is_returned(self):
        rows = [
            {
                "station_name": "稲沢",
                "open_year": "2026",
                "open_month": "10",
                "open_day": "18",
                "detail_page": "/course/detail/123",
                "title": "歴史を歩く稲沢コース",
            },
            {
                "station_name": "稲沢駅",
                "open_year": "2026",
                "open_month": "10",
                "open_day": "19",
                "detail_page": "/course/detail/should-not-match",
                "title": "表記違い",
            },
            {
                "station_name": "尾張一宮",
                "open_year": "2026",
                "open_month": "10",
                "open_day": "20",
                "detail_page": "/course/detail/other-station",
                "title": "他駅コース",
            },
        ]
        search = SimpleNamespace(json=lambda: {"result_list": rows})
        detail = SimpleNamespace(text="<html><body>スタート受付時間 08:30～11:00</body></html>")

        def fake_get(url):
            if url.startswith(SEARCH_API + "?stname="):
                return search
            if url == "https://walking.jr-central.co.jp/course/detail/123":
                return detail
            self.fail(f"Unexpected JR URL: {url}")

        with patch("jr_walking_web._get", side_effect=fake_get):
            events, source = parse_jr_inazawa_walks()

        self.assertEqual(source, SEARCH_API)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["date"], "2026-10-18")
        self.assertEqual(event["hall"], "JR稲沢駅")
        self.assertEqual(event["venues"], ["JR稲沢駅"])
        self.assertEqual(event["time"], "08:30〜11:00")
        self.assertEqual(event["title"], "JR東海 さわやかウォーキング「歴史を歩く稲沢コース」")
        self.assertEqual(event["source"], "jr_walking")
        self.assertEqual(event["official_url"], "https://walking.jr-central.co.jp/course/detail/123")
        self.assertEqual(event["source_type"], "event_official")
        self.assertEqual(event["source_url"], event["official_url"])
        self.assertTrue(event["source_verified"])
        self.assertTrue(event["event_specific"])
        self.assertEqual(event["verified_fields"], ["date", "title", "hall", "time"])
        self.assertEqual(source_rank(event, "date"), 3)
        self.assertEqual(source_rank(event, "title"), 3)
        self.assertEqual(source_rank(event, "hall"), 3)
        self.assertEqual(source_rank(event, "time"), 3)
        self.assertEqual(source_rank(event, "price"), 0)

    def test_invalid_detail_path_is_not_accepted(self):
        rows = [{
            "station_name": "稲沢",
            "open_year": "2026",
            "open_month": "10",
            "open_day": "18",
            "detail_page": "/course/list/123",
            "title": "不正な詳細URL",
        }]
        search = SimpleNamespace(json=lambda: {"result_list": rows})
        with patch("jr_walking_web._get", return_value=search):
            with self.assertRaisesRegex(RuntimeError, "既存JRデータ維持"):
                parse_jr_inazawa_walks()

    def test_no_inazawa_course_fails_closed(self):
        search = SimpleNamespace(json=lambda: {"result_list": [{
            "station_name": "尾張一宮",
            "open_year": "2026",
            "open_month": "10",
            "open_day": "18",
            "detail_page": "/course/detail/999",
            "title": "他駅コース",
        }]})
        with patch("jr_walking_web._get", return_value=search):
            with self.assertRaisesRegex(RuntimeError, "既存JRデータ維持"):
                parse_jr_inazawa_walks()

    def test_unexpected_api_shape_is_rejected(self):
        search = SimpleNamespace(json=lambda: {"unexpected": []})
        with patch("jr_walking_web._get", return_value=search):
            with self.assertRaisesRegex(RuntimeError, "形式が想定外"):
                parse_jr_inazawa_walks()


if __name__ == "__main__":
    unittest.main()
