"""Offline-only safety cases for the production daily auto-merge gate.

All remote GitHub responses are synthetic; no real Actions, secrets, events or
merges are used. Assertions cover exact PR identity, event-file bytes, exact
check SHA and refusal to publish on any unexpected or failed state.
"""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import daily_auto_merge as mod


class DailyAutoMergePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(self.temp.cleanup)
        self.auto = b'[{"date":"2099-01-02","title":"fictional event","hall":"A"}]\n'
        self.meta = b'{"event_count":1}\n'
        Path("events.json").write_bytes(self.auto)
        Path("update-meta.json").write_bytes(self.meta)
        self.base = "a" * 40
        self.head = "b" * 40
        self.after = "c" * 40
        self.branch = "automation/daily-events/12345-1"
        self.number = 999
        self.pr = {
            "number": self.number, "state": "open", "draft": False,
            "merged": False, "user": {"login": mod.BOT},
            "head": {
                "ref": self.branch, "sha": self.head,
                "repo": {"full_name": mod.REPO},
            },
            "base": {"ref": "main", "sha": self.base},
        }
        self.files = [
            {"filename": "events.json", "status": "modified"},
            {"filename": "update-meta.json", "status": "modified"},
        ]
        self.run = {
            "id": 888, "event": "pull_request",
            "head_branch": self.branch, "head_sha": self.head,
            "path": mod.WORKFLOW,  # GitHub REST returns the bare workflow path
            "actor": {"login": mod.BOT},
            "pull_requests": [{
                "number": self.number,
                "head": {"sha": self.head},
            }],
            "status": "completed", "conclusion": "success",
        }
        self.env = patch.dict(os.environ, {
            "REPOSITORY": mod.REPO, "BASE_SHA": self.base,
            "PR_BRANCH": self.branch, "PR_NUMBER": str(self.number),
            "GH_TOKEN": "TEST_APP_TOKEN_NOT_REAL",
            "GH_CI_READ_TOKEN": "TEST_CI_READ_TOKEN_NOT_REAL",
            "GITHUB_STEP_SUMMARY": str(Path(self.temp.name) / "summary"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake_api(self, endpoint, *, read_actions=False, method=None, fields=()):
        if endpoint.endswith("/git/ref/heads/main"):
            self.assertFalse(read_actions)
            return {"object": {"sha": self.base}}
        if endpoint.endswith(f"/pulls/{self.number}"):
            self.assertFalse(read_actions)
            return self.pr
        if endpoint.endswith(f"/pulls/{self.number}/files?per_page=100"):
            return self.files
        if "/contents/" in endpoint:
            name = endpoint.split("/contents/", 1)[1].split("?", 1)[0]
            data = Path(name).read_bytes()
            return {"type": "file", "encoding": "base64",
                    "content": base64.b64encode(data).decode("ascii")}
        if "/actions/workflows/test-integrity.yml/runs?" in endpoint:
            self.assertTrue(read_actions)
            self.assertIn("event=pull_request", endpoint)
            self.assertIn("head_sha=" + self.head, endpoint)
            return {"workflow_runs": [self.run]}
        if endpoint.endswith(f"/pulls/{self.number}/merge"):
            self.assertEqual(method, "PUT")
            self.assertIn("sha=" + self.head, fields)
            self.assertIn("merge_method=squash", fields)
            return {"merged": True, "sha": self.after}
        raise AssertionError("Unexpected API endpoint: " + endpoint)

    def test_healthy_pr_and_exact_head_ci_allow_publication(self):
        with patch.object(mod, "api", side_effect=self.fake_api), patch.object(
                mod, "current_main", side_effect=[self.base, self.base, self.after]):
            mod.publish()
        self.assertIn("auto-merged daily events PR", Path("summary").read_text())

    def test_only_current_bot_and_non_draft_pr_can_publish(self):
        for field, value in (("bot", "untrusted-user"), ("draft", True),
                             ("base", "d" * 40), ("head", "e" * 40)):
            with self.subTest(field=field):
                previous = json.loads(json.dumps(self.pr))
                if field == "bot":
                    self.pr["user"]["login"] = value
                elif field == "draft":
                    self.pr["draft"] = value
                elif field == "head":
                    self.pr[field]["ref"] = "unapproved-branch"
                else:
                    self.pr[field]["sha"] = value
                with patch.object(mod, "api", side_effect=self.fake_api):
                    with self.assertRaises(mod.UnsafeToPublish):
                        mod.inspect_pr(self.base, self.branch, self.number)
                self.pr = previous

    def test_rejects_unknown_or_deleted_files(self):
        for files in ([{"filename": "secret.env", "status": "modified"}],
                      [{"filename": "events.json", "status": "removed"}],
                      [{"filename": "events.json", "status": "modified"},
                       {"filename": "events.json", "status": "modified"}],
                      self.files + [{"filename": ".github/workflows/evil.yml",
                                     "status": "added"}]):
            with self.subTest(files=files):
                self.files = files
                with patch.object(mod, "api", side_effect=self.fake_api):
                    with self.assertRaises(mod.UnsafeToPublish):
                        mod.inspect_pr(self.base, self.branch, self.number)

    def test_rejects_remote_data_not_matching_validated_bytes(self):
        def tampered(endpoint, **kwargs):
            if "/contents/events.json" in endpoint:
                return {"type": "file", "encoding": "base64",
                        "content": base64.b64encode(b"tampered").decode()}
            return self.fake_api(endpoint, **kwargs)
        with patch.object(mod, "api", side_effect=tampered):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.inspect_pr(self.base, self.branch, self.number)

    def test_ci_rejects_wrong_workflow_path(self):
        self.run["path"] = ".github/workflows/other.yml"
        with patch.object(mod, "api", side_effect=self.fake_api):
            self.assertEqual(mod.ci_status(self.branch, self.head, self.number), "pending")

    def test_ci_rejects_wrong_actor_sha_branch_or_pr(self):
        for field, value in (("head_sha", "d" * 40),
                             ("head_branch", "some-other-branch"),
                             ("event", "push")):
            with self.subTest(field=field):
                previous = self.run[field]
                self.run[field] = value
                with patch.object(mod, "api", side_effect=self.fake_api):
                    self.assertEqual(
                        mod.ci_status(self.branch, self.head, self.number), "pending")
                self.run[field] = previous

    def test_ci_rejects_wrong_pr_association_or_multiple_runs(self):
        original = self.run["pull_requests"]
        self.run["pull_requests"] = [{"number": 1000, "head": {"sha": self.head}}]
        with patch.object(mod, "api", side_effect=self.fake_api):
            self.assertEqual(mod.ci_status(self.branch, self.head, self.number), "pending")
        self.run["pull_requests"] = original
        with patch.object(mod, "api", side_effect=lambda endpoint, **kw: {
                "workflow_runs": [self.run, self.run]
            }):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.ci_status(self.branch, self.head, self.number)

    def test_ci_pending_and_failure_are_not_approved(self):
        self.run["status"] = "in_progress"
        self.run["conclusion"] = None
        with patch.object(mod, "api", side_effect=self.fake_api):
            self.assertEqual(mod.ci_status(self.branch, self.head, self.number), "pending")
        self.run["status"] = "completed"
        self.run["conclusion"] = "failure"
        with patch.object(mod, "api", side_effect=self.fake_api):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.ci_status(self.branch, self.head, self.number)

    def test_main_drift_stops_before_any_merge(self):
        with patch.object(mod, "current_main", return_value="d" * 40), \
             patch.object(mod, "api") as mocked:
            with self.assertRaises(mod.UnsafeToPublish):
                mod.publish()
            mocked.assert_not_called()

    def test_base_sha_and_branch_must_match_expected_policy(self):
        with patch.dict(os.environ, {"PR_BRANCH": "refs/heads/main"}):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.expected_environment()
        with patch.dict(os.environ, {"REPOSITORY": "other/project"}):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.expected_environment()

    def test_missing_ci_never_merges_even_when_pr_is_correct(self):
        def no_run(endpoint, **kwargs):
            if "/actions/workflows/" in endpoint:
                return {"workflow_runs": []}
            return self.fake_api(endpoint, **kwargs)
        with patch.object(mod, "api", side_effect=no_run), \
             patch.object(mod, "current_main", return_value=self.base), \
             patch.object(mod.time, "sleep", return_value=None), \
             patch.object(mod.time, "monotonic", side_effect=[0, 999]):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.publish()


if __name__ == "__main__":
    unittest.main()
