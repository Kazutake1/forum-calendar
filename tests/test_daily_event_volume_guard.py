"""Read-only, fabricated event-count scenarios for safe automatic publishing."""
import json
from datetime import date
import unittest

from daily_event_volume_guard import validate_change


def rows(count):
    return json.dumps([
        {"date": "2099-01-01", "title": f"fictional-{i}", "hall": "test"}
        for i in range(count)
    ]).encode("utf-8")


class DailyVolumeGuardTests(unittest.TestCase):
    def test_same_count_or_normal_small_variation_passes(self):
        self.assertEqual(validate_change(rows(79), rows(79)), (79, 79))
        self.assertEqual(validate_change(rows(79), rows(70)), (79, 70))
        self.assertEqual(validate_change(rows(79), rows(48)), (79, 48))

    def test_suspicious_mass_loss_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "dropped abnormally"):
            validate_change(rows(79), rows(47))
        with self.assertRaisesRegex(RuntimeError, "dropped abnormally"):
            validate_change(rows(50), rows(15))

    def test_missing_or_malformed_data_refuses_publication(self):
        for previous, generated in (
            (b"not-json", rows(10)),
            (rows(10), b"not-json"),
            (rows(10), b"[]"),
            (rows(10), b'{"events":[]}'),
            (rows(10), json.dumps([0, 1]).encode()),
        ):
            with self.subTest(generated=generated[:30]):
                with self.assertRaises(RuntimeError):
                    validate_change(previous, generated)

    def test_same_total_count_with_mass_replacement_is_rejected(self):
        previous = rows(12)
        changed = json.dumps([
            *json.loads(rows(4)),
            *[{"date": "2099-01-01", "title": f"unrecognized-{i}",
               "hall": "test"} for i in range(8)]
        ]).encode("utf-8")
        with self.assertRaisesRegex(RuntimeError, "identities vanished abnormally"):
            validate_change(previous, changed, reference_date=date(2098, 12, 1))

    def test_normal_title_corrections_do_not_block_daily_updates(self):
        previous = rows(12)
        changed = json.dumps([
            *json.loads(rows(7)),
            *[{"date": "2099-01-01", "title": f"corrected-{i}",
               "hall": "test"} for i in range(5)]
        ]).encode("utf-8")
        self.assertEqual(validate_change(previous, changed,
                         reference_date=date(2098, 12, 1)), (12, 12))

    def test_elapsed_events_do_not_trigger_upcoming_loss_guard(self):
        previous = rows(12)
        changed = json.dumps([
            {"date": "2099-01-01", "title": f"new-{i}", "hall": "test"}
            for i in range(12)
        ]).encode("utf-8")
        self.assertEqual(validate_change(previous, changed,
                         reference_date=date(2099, 2, 1)), (12, 12))

    def test_invalid_event_date_is_rejected(self):
        corrupt = json.dumps([
            {"date": "2099-14-50", "title": "synthetic", "hall": "test"},
            *json.loads(rows(11)),
        ]).encode("utf-8")
        with self.assertRaisesRegex(RuntimeError, "invalid event date"):
            validate_change(rows(12), corrupt, reference_date=date(2098, 12, 1))

    def test_tiny_source_count_does_not_false_alarm(self):
        self.assertEqual(validate_change(rows(2), rows(1)), (2, 1))


if __name__ == "__main__":
    unittest.main()
