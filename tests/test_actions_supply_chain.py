"""Static regression guard for GitHub Actions supply-chain policy (no external services).

This test is intentionally local-only: it does not execute the scheduled
writer workflows or access production event data.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
PYTHON = "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"
NODE = "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1"
JEKYLL_PREVIEW = "actions/jekyll-build-pages@44a6e6beabd48582f863aeeb6cb2151cc1716697"
EXPECTED = {
    "app-smoke-test.yml": ["actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510"],
    "monthly-manual-events.yml": [CHECKOUT, PYTHON, "actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510"],
    "test-integrity.yml": [CHECKOUT, PYTHON, NODE, JEKYLL_PREVIEW],
    "update-events.yml": [CHECKOUT, PYTHON, "actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510"],
}


class WorkflowSupplyChainTests(unittest.TestCase):
    def test_actions_are_pinned_to_verified_full_shas(self):
        for filename, expected in EXPECTED.items():
            with self.subTest(workflow=filename):
                content = (ROOT / filename).read_text(encoding="utf-8")
                actual = re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", content, re.M)
                self.assertEqual(actual, expected, "Unexpected or unpinned action reference")
                for action in actual:
                    self.assertRegex(action, r"^[a-z-]+/[a-z-]+@[0-9a-f]{40}$")

    def test_integrity_checks_all_main_pushes_and_pull_requests(self):
        verify = (ROOT / "test-integrity.yml").read_text(encoding="utf-8")
        self.assertIn(
            "on:\n  push:\n    branches: [main]\n  pull_request:\n"
            "    branches: [main]\n",
            verify,
        )
        self.assertNotIn("    paths:", verify, "Main pushes must not bypass publication scan")

    def test_writer_permissions_remain_explicit_and_limited(self):
        monthly = (ROOT / "monthly-manual-events.yml").read_text(encoding="utf-8")
        update = (ROOT / "update-events.yml").read_text(encoding="utf-8")
        verify = (ROOT / "test-integrity.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n  actions: read", monthly)
        self.assertIn("permissions:\n  contents: read\n  actions: read", update)
        self.assertNotIn("pages: write", update)
        self.assertIn("permissions:\n  contents: read\n", verify)
        self.assertNotIn("permissions: write-all", monthly + update + verify)
        self.assertNotIn("pages: write", verify)
        self.assertIn("persist-credentials: false", verify)
        self.assertIn("persist-credentials: false", monthly)
        self.assertIn("persist-credentials: false", update)

    def test_scheduled_commands_and_ocr_policy_are_preserved(self):
        monthly = (ROOT / "monthly-manual-events.yml").read_text(encoding="utf-8")
        update = (ROOT / "update-events.yml").read_text(encoding="utf-8")
        verify = (ROOT / "test-integrity.yml").read_text(encoding="utf-8")
        self.assertIn("python manage_manual_events.py", monthly)
        self.assertIn("git add -- manual_events.json", monthly)
        self.assertIn("run: python monthly_auto_merge.py", monthly)
        self.assertNotIn("git push origin HEAD:main", monthly)
        self.assertNotIn("pages/builds", monthly)
        self.assertNotIn("pages/builds", monthly)
        self.assertIn("python update_events_no_ocr.py", update)
        self.assertIn("git add -- events.json update-meta.json", update)
        self.assertIn("-F draft=false", update)
        self.assertIn("run: python daily_auto_merge.py", update)
        self.assertNotIn("-F draft=true", update)
        self.assertNotIn("git push", update)
        self.assertNotIn("pages/builds", update)
        self.assertIn("python -m unittest discover -s tests -v", verify)


if __name__ == "__main__":
    unittest.main()
