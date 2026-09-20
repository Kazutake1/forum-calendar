import unittest

from event_integrity import (
    city_verified, combine_performance, same_performance, time_parts,
)


def event(time, **extra):
    return {"date": "2026-10-31", "title": "演奏会", "hall": "中ホール", "time": time, **extra}


class IdentityAndEvidenceTests(unittest.TestCase):
    def test_two_explicit_performances_remain_distinct(self):
        self.assertFalse(same_performance(event("開演10:00"), event("開演18:00")))
        self.assertFalse(same_performance(event("10:00〜"), event("18:00〜")))
        self.assertFalse(same_performance(event("13:00〜 / 17:30〜"), event("13:00〜")))

    def test_doors_are_not_mistaken_for_start(self):
        self.assertEqual(time_parts("開場17:30／開演18:00"), (("18:00",), ("17:30",)))
        self.assertTrue(same_performance(event("開場17:30／開演18:00"), event("開演18:00")))
        self.assertFalse(same_performance(event("開場17:30"), event("開演18:00")))

    def test_unknown_time_requires_evidence(self):
        self.assertFalse(same_performance(event(""), event("18:00〜")))
        self.assertFalse(same_performance(event(""), event("")))
        self.assertTrue(same_performance(event("", official_url="https://example.org/event"),
                                         event("", official_url="https://example.org/event")))

    def test_reviewed_performance_identity_supports_correction(self):
        self.assertTrue(same_performance(event("10:00〜", performance_id="show-a"),
                                         event("10:30〜", performance_id="show-a")))
        self.assertFalse(same_performance(event("18:00〜", performance_id="show-b"),
                                          event("18:00〜", performance_id="show-a")))

    def test_field_specific_city_evidence(self):
        city = event("18:00〜", source_type="city_official", source_verified=True,
                     source_url="https://www.city.inazawa.aichi.jp/0000123456.html",
                     hall_source_type="x", hall_source_url="https://x.com/post/1")
        self.assertTrue(city_verified(city, "time"))
        self.assertFalse(city_verified(city, "hall"))
        auto = event("17:00〜", price="500円", hall="中ホール")
        result = combine_performance(auto, city)
        self.assertEqual(result["time"], "18:00〜")
        self.assertEqual(result["price"], "500円")
        self.assertFalse(city_verified(result, "hall"))

    def test_unverified_city_link_is_not_verification(self):
        item = event("18:00〜", source="event_guide",
                     official_url="https://www.city.inazawa.aichi.jp/ica/0000002507.html")
        self.assertFalse(city_verified(item, "time"))
        item.update(source_verified=True, verified_fields=["title", "date"])
        self.assertFalse(city_verified(item, "time"))
        self.assertTrue(city_verified(item, "title"))


if __name__ == "__main__":
    unittest.main()
