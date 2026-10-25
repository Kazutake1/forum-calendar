"""Static regression guard for GitHub Actions supply-chain policy (no external services).

This test is intentionally local-only: it does not execute the scheduled
writer workflows or access production event data.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CHECKOUT = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
NODE = "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020"
EXPECTED = {
    "monthly-manual-events.yml": [CHECKOUT, PYTHON],
    "test-integrity.yml": [CHECKOUT, PYTHON, NODE],
    "update-events.yml": [CHECKOUT, PYTHON],
}


class WorkflowSupplyChainTests(unittest.TestCase):
    def test_actions_are_pinned_to_verified_full_shas(self):
        for filename, expected in EXPECTED.items():
            with self.subTest(workflow=filename):
                content = (ROOT / filename).read_text(encoding="utf-8")
                actual = re.findall(r"^\\s*(?:-\\s*)?uses:\\s*([^\\s#]+)", content, re.M)
                self.assertEqual(actual, expected, "Unexpected or unpinned action reference")
                for action in actual:
                    self.assertRegex(action, r"^[a-z-]+/[a-z-]+@[0-9a-f]{40}$")

    def test_writer_permissions_remain_explicit_and_limited(self):
        monthly = (ROOT / "monthly-manual-events.yml").read_text(encoding="utf-8")
        update = (ROOT / "update-events.yml").read_text(encoding="utf-8")
        verify = (ROOT / "test-integrity.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\\n  contents: write\\n  pages: write", monthly)
        self.assertIn("permissions:\\n  contents: write\\n", update)
        self.assertIn("permissions:\\n  contents: read\\n", verify)
        self.assertNotIn("permissions: write-all", monthly + update + verify)
        self.assertNotIn("pages: write", update + verify)
        self.assertIn("persist-credentials: false", verify)
        self.assertIn("persist-credentials: true", monthly)
        self.assertIn("persist-credentials: true", update)

    def test_scheduled_commands_and_ocr_policy_are_preserved(self):
        monthly = (ROOT / "monthly-manual-events.yml").read_text(encoding="utf-8")
        update = (ROOT / "update-events.yml").read_text(encoding="utf-8")
        verify = (ROOT / "test-integrity.yml").read_text(encoding="utf-8")
        self.assertIn("python manage_manual_events.py", monthly)
        self.assertIn("git add -- manual_events.json", monthly)
        self.assertIn("git push origin HEAD:main", monthly)
        self.assertIn("https://api.github.com/repos/${REPOSITORY}/pages/builds", monthly)
        self.assertIn("python update_events_no_ocr.py", update)
        self.assertIn("git add events.json update-meta.json", update)
        self.assertIn("git push", update)
        self.assertIn("python -m unittest discover -s tests -v", verify)


if __name__ == "__main__":
    unittest.main()
