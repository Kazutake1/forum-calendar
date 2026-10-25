"""Synthetic only. No real manual events or GitHub API calls."""
from datetime import date
import unittest

from monthly_archive_guard import permitted, validate_transition


def event(identity, date_str="2026-12-20", **kwargs):
    return {"id": identity, "date": date_str, "title": "架空の公演",
            "hall": "小ホール", "source_type": "other",
            "source_url": "https://example.org/fixture", **kwargs}


class MonthlyArchiveGuardTests(unittest.TestCase):
    def setUp(self):
        self.old = [event("expired", "2026-01-10", source_note="原本維持"),
                    event("current", "2026-09-01")]
        self.old_archive = {
            "archive/manual_events_2025.json": [event("history", "2025-08-20")]
        }
        self.today = date(2026, 10, 25)

    def test_preserves_history_and_moves_exact_expired_record(self):
        self.assertEqual(validate_transition(
            self.old, self.old[1:], self.old_archive,
            {**self.old_archive,
             "archive/manual_events_2026.json": [self.old[0]]}, self.today
        ), (self.old[1:], [self.old[0]]))

    def test_no_expiry_never_rewrites_manual_data(self):
        old = [event("future")]
        self.assertEqual(validate_transition(
            old, old, {}, {}, self.today), (old, []))

    def test_archived_original_field_cannot_be_modified(self):
        overwritten = [dict(self.old_archive["archive/manual_events_2025.json"][0],
                            title="改ざん")]
        with self.assertRaisesRegex(ValueError, "Archive"):
            validate_transition(self.old, self.old[1:], self.old_archive,
                {"archive/manual_events_2025.json": overwritten,
                 "archive/manual_events_2026.json": [self.old[0]]}, self.today)

    def test_record_cannot_be_discarded_or_inserted(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_transition(self.old, self.old[1:], self.old_archive,
                self.old_archive, self.today)
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_transition(self.old, self.old[1:] + [event("invented")],
                self.old_archive,
                {**self.old_archive, "archive/manual_events_2026.json": [self.old[0]]},
                self.today)

    def test_90_day_boundary_is_strict(self):
        sample = [event("edge", "2026-01-02")]
        self.assertEqual(validate_transition(sample, sample, {}, {},
            date(2026, 4, 2)), (sample, []))
        self.assertEqual(validate_transition(sample, [],
            {}, {"archive/manual_events_2026.json": sample},
            date(2026, 4, 3)), ([], sample))

    def test_archives_cannot_be_reordered_or_cross_year(self):
        wrong_year = {"archive/manual_events_2025.json": [self.old[0]]}
        with self.assertRaisesRegex(ValueError, "year"):
            validate_transition(self.old, self.old[1:], {}, wrong_year, self.today)
        duplicate = {"archive/manual_events_2026.json": [self.old[0], self.old[0]]}
        with self.assertRaisesRegex(ValueError, "重複"):
            validate_transition(self.old, self.old[1:], {}, duplicate, self.today)

    def test_only_monthly_output_paths_are_allowed(self):
        for path in ("manual_events.json", "reports/manual-event-review.md",
                     "archive/manual_events_2025.json"):
            self.assertTrue(permitted(path))
        for path in ("events.json", "sw.js", ".env", "archive/../events.json",
                     "archive/manual_events_2026.json/extra",
                     "archive/manual_events_2026.json.bak"):
            self.assertFalse(permitted(path))


if __name__ == "__main__":
    unittest.main()
