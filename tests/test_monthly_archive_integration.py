"""Fake git history: exercise the monthly guard against real local git blobs.

Never reads a user's real archives, writes main, or connects to GitHub.
"""
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from manage_manual_events import manage
from monthly_archive_guard import validate_local


def row(identity, when):
    return {"id": identity, "date": when, "title": "架空のイベント",
            "hall": "小ホール", "source_type": "other",
            "source_url": "https://example.org/fictional"}


class MonthlyHistoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.old_cwd)
        self.root = Path(".")
        self.day = date(2026, 10, 25)
        self.expired = row("expired", "2026-01-01")
        self.current = row("current", "2026-12-31")
        self.existing = row("historical", "2025-06-10")
        self.write("manual_events.json", [self.expired, self.current])
        self.write("events.json", [])
        self.write("archive/manual_events_2025.json", [self.existing])
        self.git("init", "-q")
        self.git("add", "--", "manual_events.json", "events.json", "archive")
        self.git("-c", "user.name=Synthetic", "-c",
                 "user.email=synthetic@example.org", "commit", "-qm", "fixture")

    def write(self, name, rows):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    def git(self, *args):
        return subprocess.run(("git", *args), check=True, capture_output=True,
                              text=True, timeout=15)

    def test_exact_valid_archive_move_and_report_are_accepted(self):
        result = manage(self.root, self.day)
        self.assertEqual(result["moved"], 1)
        active, moved, files = validate_local(self.root, self.day)
        self.assertEqual((active, moved), (1, 1))
        self.assertIn("manual_events.json", files)
        self.assertIn("archive/manual_events_2026.json", files)
        self.assertIn("reports/manual-event-review.md", files)
        self.assertEqual(json.loads(Path("archive/manual_events_2025.json").read_text()),
                         [self.existing])

    def test_corrupted_historical_record_is_rejected(self):
        manage(self.root, self.day)
        self.write("archive/manual_events_2025.json",
                   [dict(self.existing, title="意図しない書き換え")])
        with self.assertRaisesRegex(ValueError, "Archive"):
            validate_local(self.root, self.day)

    def test_deleted_archived_record_is_rejected(self):
        manage(self.root, self.day)
        self.write("archive/manual_events_2026.json", [])
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_local(self.root, self.day)

    def test_unrelated_file_change_is_rejected(self):
        manage(self.root, self.day)
        Path("sw.js").write_text("unapproved script", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unexpected monthly worktree"):
            validate_local(self.root, self.day)

    def test_report_tampering_is_rejected(self):
        manage(self.root, self.day)
        report = Path("reports/manual-event-review.md")
        report.write_text("wrong report\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "report does not match"):
            validate_local(self.root, self.day)


if __name__ == "__main__":
    unittest.main()
