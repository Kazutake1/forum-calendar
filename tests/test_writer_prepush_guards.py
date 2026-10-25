"""Static safety checks for scheduled writers before commits reach main.

Read workflow definitions only. Never run update or archive commands.
"""
from pathlib import Path
import unittest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PREPUSH = "run: python -m unittest discover -s tests -v"

def workflow(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")

class ScheduledWriterPrepushTests(unittest.TestCase):
    def test_auto_update_validated_after_mutation_before_commit(self):
        source = workflow("update-events.yml")
        first = source.index("run: python update_events_no_ocr.py")
        data_check = source.index("name: Validate generated event files (read-only)")
        self.assertIn("load_required_events(Path(\"events.json\"))", source)
        self.assertIn('meta["event_count"] != len(events)', source)
        validation = source.index("name: Verify updated data before committing to main")
        call = source.index(PREPUSH, validation)
        commit = source.index("name: Commit updated data")
        push = source.index("git push", commit)
        self.assertTrue(first < data_check < validation < call < commit < push)
        self.assertEqual(source.count(PREPUSH), 1)
        self.assertIn("git add events.json update-meta.json", source)
        self.assertNotIn("continue-on-error: true", source)

    def test_monthly_validated_after_archive_before_commit(self):
        source = workflow("monthly-manual-events.yml")
        archive = source.index("python manage_manual_events.py")
        data_check = source.index("name: Validate archived records (read-only)")
        self.assertIn("from manage_manual_events import manage", source)
        self.assertIn("dry_run=True", source)
        self.assertIn('result["moved"] != 0', source)
        validation = source.index("name: Verify archived data before committing to main")
        call = source.index(PREPUSH, validation)
        commit = source.index("name: Commit only manual data, archives, and the report")
        push = source.index("git push origin HEAD:main", commit)
        self.assertTrue(archive < data_check < validation < call < commit < push)
        self.assertEqual(source.count(PREPUSH), 2)
        self.assertIn("git add -- manual_events.json", source)
        self.assertNotIn("continue-on-error: true", source)

    def test_writer_schedule_and_concurrency_remain_intact(self):
        auto = workflow("update-events.yml")
        monthly = workflow("monthly-manual-events.yml")
        self.assertIn("cron: '20 22 * * *'", auto)
        self.assertIn("cron: '10 1 1 * *'", monthly)
        for source in (auto, monthly):
            self.assertIn("group: forum-calendar-main-write", source)
            self.assertIn("cancel-in-progress: false", source)
            self.assertIn("permissions:\n  contents: write", source)
        self.assertIn("run: python update_events_no_ocr.py", auto)
        self.assertIn("run: python -m unittest discover -s tests -v", monthly)

if __name__ == "__main__":
    unittest.main()
