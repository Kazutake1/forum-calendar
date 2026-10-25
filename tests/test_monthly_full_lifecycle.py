"""Synthetic full monthly PR gate: actual CI and Pages policy, no network.

Exercises the unmodified production gate functions with an in-memory
simulation of the GitHub REST API and time-bound post-merge verification.
"""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monthly_auto_merge as month


class FakeGitHub:
    def __init__(self, case="normal"):
        self.case = case
        self.repo = month.REPO
        self.base, self.head, self.merged = "a" * 40, "b" * 40, "c" * 40
        self.branch = "automation/monthly-manual/999-1"
        self.number = 444
        self.did_merge = False
        self.merge_calls = 0
        self.requests = []
        self.paths = (
            "manual_events.json", "reports/manual-event-review.md",
            "archive/manual_events_2026.json",
        )
        self.pr = {
            "number": self.number, "state": "open", "draft": False,
            "merged": False, "user": {"login": month.BOT},
            "head": {"ref": self.branch, "sha": self.head,
                     "repo": {"full_name": self.repo}},
            "base": {"ref": "main", "sha": self.base},
        }
        self.ci = {
            "id": 322, "event": "pull_request", "path": month.shared.WORKFLOW,
            "head_sha": self.head, "head_branch": self.branch,
            "actor": {"login": month.BOT},
            "pull_requests": [{
                "number": self.number, "head": {"sha": self.head},
            }],
            "status": "completed", "conclusion": "success",
        }
        self.pages = {
            "id": 433, "event": "dynamic",
            "name": "pages build and deployment",
            "head_branch": "main", "head_sha": self.merged,
            "path": month.shared.PAGES_WORKFLOW,
            "repository": {"full_name": self.repo},
            "status": "completed", "conclusion": "success",
        }

    def api(self, endpoint, *, read_actions=False, method=None, fields=()):
        self.requests.append((endpoint, method))
        if endpoint.endswith("/git/ref/heads/main"):
            if self.case == "premerge_race" and len([
                req for req, _ in self.requests
                if req.endswith("/git/ref/heads/main")
            ]) >= 2:
                return {"object": {"sha": "d" * 40}}
            return {"object": {"sha": self.merged if self.did_merge else self.base}}
        if endpoint.endswith(f"/pulls/{self.number}") and method is None:
            return self.pr
        if endpoint.endswith(f"/pulls/{self.number}/files?per_page=100"):
            return [{"filename": x, "status": "added" if x.startswith("archive/")
                     else "modified"} for x in self.paths]
        if "/contents/" in endpoint:
            filename = endpoint.split("/contents/", 1)[1].split("?", 1)[0]
            if self.case == "bad_postmerge_bytes" and f"ref={self.merged}" in endpoint:
                contents = b"incorrect post-merge bytes"
            else:
                contents = Path(filename).read_bytes()
            return {"type": "file", "encoding": "base64",
                    "content": base64.b64encode(contents).decode("ascii")}
        if "/actions/workflows/test-integrity.yml/runs?" in endpoint:
            if not read_actions:
                raise AssertionError("CI must be fetched with read-only token")
            if self.case == "ci_failure":
                return {"workflow_runs": [{**self.ci, "conclusion": "failure"}]}
            if self.case == "wrong_ci_actor":
                return {"workflow_runs": [{
                    **self.ci, "actor": {"login": "untrusted"},
                }]}
            return {"workflow_runs": [self.ci]}
        if endpoint.endswith(f"/pulls/{self.number}/merge"):
            if method != "PUT" or f"sha={self.head}" not in fields:
                raise AssertionError("Wrong merge preconditions")
            self.merge_calls += 1
            self.did_merge = True
            return {"merged": True, "sha": self.merged}
        if endpoint.endswith(f"/git/commits/{self.merged}"):
            if self.case == "postmerge_parent_race":
                return {"parents": [{"sha": "d" * 40}]}
            return {"parents": [{"sha": self.base}]}
        if "/actions/runs?head_sha=" in endpoint:
            if not read_actions:
                raise AssertionError("Pages must be fetched with read-only token")
            if self.case == "pages_failure":
                return {"workflow_runs": [{
                    **self.pages, "conclusion": "failure"}]}
            if self.case == "pages_missing":
                return {"workflow_runs": []}
            return {"workflow_runs": [self.pages]}
        raise AssertionError("Unexpected GitHub API call: " + endpoint)


class MonthlyLifecycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        old = os.getcwd()
        os.chdir(temp.name)
        self.addCleanup(os.chdir, old)
        self.data = FakeGitHub()
        for p, data in (
            ("manual_events.json", b"[]\n"),
            ("reports/manual-event-review.md", b"# fictional review\n"),
            ("archive/manual_events_2026.json", b"[]\n"),
        ):
            file = Path(p)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        self.summary = Path(temp.name, "summary")
        self.environ = patch.dict(os.environ, {
            "REPOSITORY": month.REPO,
            "BASE_SHA": self.data.base,
            "PR_BRANCH": self.data.branch,
            "PR_NUMBER": str(self.data.number),
            "GH_TOKEN": "SYNTHETIC_APP_TOKEN",
            "GH_CI_READ_TOKEN": "SYNTHETIC_ACTIONS_TOKEN",
            "GITHUB_STEP_SUMMARY": str(self.summary),
        })
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def exercise(self, case):
        fake = FakeGitHub(case)
        with patch.object(month.shared, "api", side_effect=fake.api):
            if case in ("pages_missing", "wrong_ci_actor"):
                with patch.object(month.time, "sleep", return_value=None), \
                     patch.object(month.time, "monotonic",
                                  side_effect=[0, 0, 999, 1000]):
                    month.publish()
            else:
                month.publish()
        return fake

    def test_complete_app_ci_squash_payload_and_pages_lifecycle(self):
        fake = self.exercise("normal")
        self.assertEqual(fake.merge_calls, 1)
        self.assertTrue(fake.did_merge)
        self.assertIn(f"Monthly PR #{fake.number} merged at {fake.merged}", self.summary.read_text())
        self.assertIn("Monthly Pages deployment succeeded", self.summary.read_text())
        self.assertTrue(any("/actions/runs?head_sha=" in x for x, _ in fake.requests))

    def test_failed_ci_prohibits_merge_and_pages(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "CI did not pass"):
            self.exercise("ci_failure")
        self.assertFalse(self.summary.exists())

    def test_daily_main_change_during_ci_blocks_monthly_merge(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "main moved during CI"):
            self.exercise("premerge_race")
        self.assertFalse(self.summary.exists())

    def test_parent_change_after_merge_is_detected_not_rolled_back(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "across PR merge"):
            self.exercise("postmerge_parent_race")
        self.assertIn("merged at", self.summary.read_text())
        self.assertNotIn("deployment succeeded", self.summary.read_text())

    def test_malformed_monthly_merged_payload_is_detected(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "differs"):
            self.exercise("bad_postmerge_bytes")
        self.assertIn("merged at", self.summary.read_text())
        self.assertNotIn("deployment succeeded", self.summary.read_text())

    def test_failed_pages_prohibits_reporting_success_after_merge(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "Pages deployment failed"):
            self.exercise("pages_failure")
        self.assertIn("merged at", self.summary.read_text())
        self.assertNotIn("deployment succeeded", self.summary.read_text())

    def test_missing_pages_times_out_after_merge_without_false_success(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "not confirmed"):
            self.exercise("pages_missing")
        self.assertIn("merged at", self.summary.read_text())
        self.assertNotIn("deployment succeeded", self.summary.read_text())

    def test_unverified_ci_actor_never_reaches_merge(self):
        with self.assertRaisesRegex(month.UnsafeToPublish, "did not finish"):
            self.exercise("wrong_ci_actor")
        self.assertFalse(self.summary.exists())


if __name__ == "__main__":
    unittest.main()
