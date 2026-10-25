"""Offline regression tests for the prospective GitHub App writer-PR gate.

All event and archive records are synthetic. Never call GitHub or run a writer.
"""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from manage_manual_events import manage
from update_events import load_required_events
from writer_pr_policy import UnsafeWriterProposal, validate_writer_pr


HEAD = "a" * 40
GOOD_CHECK = {"name": "test", "head_sha": HEAD,
              "status": "completed", "conclusion": "success"}


def proposal(kind="daily", paths=None, checks=None, **overrides):
    args = {
        "kind": kind,
        "base_branch": "main",
        "head_branch": "automation/" + kind + "/20991001",
        "head_sha": HEAD,
        "changed_paths": (["events.json", "update-meta.json"] if paths is None else paths),
        "checks": ([dict(GOOD_CHECK)] if checks is None else checks),
    }
    args.update(overrides)
    return validate_writer_pr(**args)


def fake_event(event_id, event_date):
    return {
        "id": event_id, "date": event_date, "title": "架空コンサート",
        "hall": "中ホール", "source_type": "other",
        "source_url": "https://example.org/fictional-event",
    }


class WriterPrPolicyTests(unittest.TestCase):
    def test_valid_daily_is_review_only_never_auto_merge(self):
        verdict = proposal()
        self.assertTrue(verdict.ready_for_human_review)
        self.assertFalse(verdict.automated_merge_authorized)
        with self.assertRaises(Exception):
            replace(verdict, automated_merge_authorized="no", non_existing_field=True)

    def test_proposed_daily_change_uses_only_allowed_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events = [fake_event("fake-1", "2099-10-01"),
                      fake_event("fake-2", "2099-10-02")]
            (root / "events.json").write_text(
                json.dumps(events, ensure_ascii=False), encoding="utf-8"
            )
            (root / "update-meta.json").write_text(
                json.dumps({"event_count": 2}), encoding="utf-8"
            )
            validated = load_required_events(root / "events.json")
            metadata = json.loads((root / "update-meta.json").read_text(encoding="utf-8"))
            self.assertEqual(len(validated), metadata["event_count"])
            self.assertTrue(proposal().ready_for_human_review)
            self.assertFalse((root / ".git").exists())

    def test_monthly_archival_flow_with_synthetic_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "events.json").write_text("[]", encoding="utf-8")
            (root / "manual_events.json").write_text(
                json.dumps([fake_event("fake-old", "2099-01-01"),
                            fake_event("fake-new", "2099-11-30")],
                           ensure_ascii=False), encoding="utf-8"
            )
            result = manage(root, date(2099, 5, 1))
            self.assertEqual(result["moved"], 1)
            self.assertEqual(result["active"], 1)
            archived = json.loads(
                (root / "archive" / "manual_events_2099.json").read_text(encoding="utf-8")
            )
            self.assertEqual(archived[0]["id"], "fake-old")
            paths = ["manual_events.json", "archive/manual_events_2099.json",
                     "reports/manual-event-review.md"]
            self.assertTrue(proposal(kind="monthly", paths=paths).ready_for_human_review)
            self.assertEqual(manage(root, date(2099, 5, 1), dry_run=True)["moved"], 0)
            self.assertFalse((root / ".git").exists())

    def test_safely_rejects_wrong_writer_and_target(self):
        for args in (
            {"kind": "other"},
            {"base_branch": "develop"},
            {"head_branch": "main"},
            {"head_branch": "automation/monthly/fake"},
            {"head_branch": "automation/daily/../escape"},
            {"head_sha": HEAD[:-1]},
            {"head_sha": "Z" * 40},
        ):
            with self.subTest(args=args), self.assertRaises(UnsafeWriterProposal):
                proposal(**args)

    def test_change_allowlists_reject_sensitive_or_unrelated_sources(self):
        cases = [
            ["index.html"], [".env"], [".github/workflows/update-events.yml"],
            ["tests/test_writer_pr_policy.py"], ["archive/manual_events_2099.json"],
            ["reports/manual-event-review.md"], ["/tmp/secrets.txt"],
            ["events.json", "secrets.json"], ["foo\\..\\secret.txt"],
            ["events.json", "../main.json"], ["events.json", "events.json"],
            [], [""], [None],
        ]
        for paths in cases:
            with self.subTest(paths=paths), self.assertRaises(UnsafeWriterProposal):
                proposal(paths=paths)

    def test_monthly_rejects_wrong_archive_patterns_and_cross_writer_files(self):
        for paths in (
            ["events.json"], ["update-meta.json"], ["archive/credentials.json"],
            ["archive/manual_events_2026.json.bak"],
            ["archive/manual_events_99.json"],
            ["archive/subdir/manual_events_2026.json"],
            ["archive/../reports/manual-event-review.md"],
        ):
            with self.subTest(paths=paths), self.assertRaises(UnsafeWriterProposal):
                proposal(kind="monthly", paths=paths)

    def test_pr_ci_must_match_exact_head_revision_and_be_successful(self):
        cases = [
            [],
            [{"name": "other", "head_sha": HEAD,
              "status": "completed", "conclusion": "success"}],
            [dict(GOOD_CHECK, head_sha="b" * 40)],
            [dict(GOOD_CHECK, status="queued", conclusion=None)],
            [dict(GOOD_CHECK, status="in_progress", conclusion=None)],
            [dict(GOOD_CHECK, conclusion="failure")],
            [dict(GOOD_CHECK, conclusion="cancelled")],
            [dict(GOOD_CHECK), dict(GOOD_CHECK)],
        ]
        for checks in cases:
            with self.subTest(checks=checks), self.assertRaises(UnsafeWriterProposal):
                proposal(checks=checks)

    def test_unrelated_success_cannot_override_required_failure(self):
        checks = [
            dict(GOOD_CHECK, conclusion="failure"),
            {"name": "lint", "head_sha": HEAD, "status": "completed", "conclusion": "success"},
        ]
        with self.assertRaises(UnsafeWriterProposal):
            proposal(checks=checks)

    def test_unrelated_checks_cannot_replace_required_check(self):
        self.assertTrue(proposal(checks=[dict(GOOD_CHECK),
            {"name": "lint", "head_sha": HEAD,
             "status": "completed", "conclusion": "success"}]).ready_for_human_review)


if __name__ == "__main__":
    unittest.main()
