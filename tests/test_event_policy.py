import unittest

from event_integrity import (
    CITY_HOST,
    CITY_SOURCE_TYPES,
    EVENT_POLICY,
    FIELDS,
    MANUAL_SOURCE_TYPES,
    manual_source_valid,
    source_rank,
    combine_performance,
)


class EventPolicyContractTests(unittest.TestCase):
    def event(self, source_type, url, *, verified=True, event_specific=False):
        return {
            "date": "2026-10-31",
            "title": "演奏会",
            "hall": "中ホール",
            "time": "開演18:00",
            "source_type": source_type,
            "source_url": url,
            "source_verified": verified,
            "event_specific": event_specific,
            "verified_fields": ["time"],
        }

    def test_policy_shape_and_shared_constants(self):
        self.assertEqual(EVENT_POLICY["schema_version"], 1)
        self.assertEqual(CITY_HOST, "www.city.inazawa.aichi.jp")
        self.assertEqual(
            FIELDS,
            ("date", "title", "hall", "time", "price", "official_url"),
        )
        self.assertEqual(
            MANUAL_SOURCE_TYPES,
            frozenset({
                "x", "city_official", "city_schedule", "city_event_guide",
                "city_event_calendar", "event_official", "organizer",
                "promoter", "other",
            }),
        )

        self.assertEqual(
            CITY_SOURCE_TYPES,
            frozenset({
                "city_schedule", "city_official", "city_event_guide",
                "event_guide", "city_event_calendar",
            }),
        )

    def test_rank_matrix_is_policy_driven(self):
        city_url = "https://www.city.inazawa.aichi.jp/ica/0000002507.html"
        x_url = "https://x.com/example/status/1"
        official_url = "https://example.org/event/1"

        for source_type in (
            "city_schedule", "city_official", "city_event_guide",
            "event_guide", "city_event_calendar",
        ):
            with self.subTest(source_type=source_type):
                self.assertEqual(source_rank(self.event(source_type, city_url), "time"),
                                 3 if source_type in ("city_event_guide", "event_guide") else 2)

        for source_type in ("event_official", "organizer", "promoter"):
            with self.subTest(source_type=source_type):
                self.assertEqual(
                    source_rank(self.event(source_type, official_url, event_specific=True), "time"),
                    4,
                )
                self.assertEqual(
                    source_rank(self.event(source_type, official_url, event_specific=False), "time"),
                    0,
                )

        self.assertEqual(source_rank(self.event("x", x_url), "time"), 1)
        self.assertEqual(source_rank(self.event("x", city_url), "time"), 0)
        self.assertEqual(source_rank(self.event("city_schedule", official_url), "time"), 0)
        self.assertEqual(
            source_rank(self.event("event_official", x_url, event_specific=True), "time"),
            0,
        )
        self.assertEqual(
            source_rank(self.event("city_schedule", city_url, verified=False), "time"),
            0,
        )

    def test_manual_city_sources_require_verified_city_host(self):
        city_url = "https://www.city.inazawa.aichi.jp/ica/0000002507.html"
        external_url = "https://example.org/city-looking-page"
        manual_city_types = (
            "city_official", "city_schedule", "city_event_guide", "city_event_calendar",
        )
        for source_type in manual_city_types:
            with self.subTest(source_type=source_type):
                self.assertTrue(manual_source_valid({
                    "source_type": source_type,
                    "source_url": city_url,
                    "source_verified": True,
                }))
                self.assertFalse(manual_source_valid({
                    "source_type": source_type,
                    "source_url": external_url,
                    "source_verified": True,
                }))
                self.assertFalse(manual_source_valid({
                    "source_type": source_type,
                    "source_url": city_url,
                    "source_verified": False,
                }))
        self.assertFalse(manual_source_valid({
            "source_type": "event_guide",
            "source_url": city_url,
            "source_verified": True,
        }))

    def test_source_types_are_not_duplicated_across_rank_groups(self):
        seen = set()
        for group in EVENT_POLICY["source_groups"]:
            for source_type in group["source_types"]:
                self.assertNotIn(source_type, seen)
                seen.add(source_type)

    def test_official_guide_wins_in_both_orders_with_provenance_and_history(self):
        city = "https://www.city.inazawa.aichi.jp/ica/0000002507.html"
        schedule = self.event("city_schedule", city)
        guide = dict(self.event("city_event_guide", city), time="開演19:00",
                     checked_at="2026-11-08T00:00:00Z")
        first = combine_performance(schedule, guide)
        second = combine_performance(guide, schedule)
        self.assertEqual(first["time"], guide["time"])
        self.assertEqual(second["time"], guide["time"])
        self.assertEqual(first["field_sources"]["time"]["source_type"], "city_event_guide")
        self.assertEqual(first["official_change_history"][0]["previous"], schedule["time"])
        self.assertEqual(first["official_change_history"][0]["source_url"], city)
        self.assertEqual(first["official_change_history"][0]["checked_at"], guide["checked_at"])
        again = combine_performance(first, guide)
        self.assertEqual(again["official_change_history"], first["official_change_history"])

    def test_official_label_does_not_certify_unverified_or_weaker_fields(self):
        city = "https://www.city.inazawa.aichi.jp/ica/0000002507.html"
        schedule = self.event("city_schedule", city)
        guide = dict(self.event("city_event_guide", city), time="開演19:00")
        for extras in ({"verified_fields": ["title"]}, {"field_sources": {"time": {
            "source_type": "x", "source_url": "https://x.com/example/status/1", "verified": True}}}):
            self.assertEqual(combine_performance(schedule, dict(guide, **extras))["time"], schedule["time"])
        official = dict(self.event("organizer", "https://example.org/show", event_specific=True), time="開演20:00")
        self.assertEqual(combine_performance(official, guide)["time"], official["time"])
        self.assertEqual(combine_performance(guide, official)["time"], official["time"])


if __name__ == "__main__":
    unittest.main()
