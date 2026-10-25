"""Read-only, fabricated event-count scenarios for safe automatic publishing."""
import json
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

    def test_tiny_source_count_does_not_false_alarm(self):
        self.assertEqual(validate_change(rows(2), rows(1)), (2, 1))


if __name__ == "__main__":
    unittest.main()
