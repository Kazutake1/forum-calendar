"""Offline-only safety cases for the production daily auto-merge gate.

All remote GitHub responses are synthetic; no real Actions, secrets, events or
merges are used. Assertions cover exact PR identity, event-file bytes, exact
check SHA and refusal to publish on any unexpected or failed state.
"""
import base64
from datetime import datetime, timedelta, timezone
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
        self.pages_run = {
            "id": 4567, "event": "dynamic",
            "name": "pages build and deployment",
            "path": mod.PAGES_WORKFLOW,
            "head_sha": self.after, "head_branch": "main",
            "repository": {"full_name": mod.REPO},
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
        if "/actions/runs?head_sha=" in endpoint:
            self.assertTrue(read_actions)
            self.assertIn("head_sha=" + self.after, endpoint)
            return {"workflow_runs": [self.pages_run]}
        if endpoint.endswith(f"/git/commits/{self.after}"):
            self.assertFalse(read_actions)
            return {"parents": [{"sha": self.base}]}
        if endpoint.endswith(f"/pulls/{self.number}/merge"):
            self.assertEqual(method, "PUT")
            self.assertIn("sha=" + self.head, fields)
            self.assertIn("merge_method=squash", fields)
            return {"merged": True, "sha": self.after}
        raise AssertionError("Unexpected API endpoint: " + endpoint)


    def test_old_verified_app_pr_is_closed_to_unblock_next_daily_update(self):
        old = json.loads(json.dumps(self.pr))
        old["created_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=26)
        ).isoformat()
        calls = []
        def fake(endpoint, *, method=None, fields=(), **kwargs):
            calls.append((endpoint, method))
            if endpoint.endswith("/git/ref/heads/main"):
                return {"object": {"sha": self.base}}
            if endpoint.endswith("/pulls?state=open&base=main&per_page=100"):
                return [{"number": self.number, "head": {"ref": self.branch}}]
            if endpoint.endswith(f"/pulls/{self.number}") and not method:
                return old
            if endpoint.endswith(f"/pulls/{self.number}") and method == "PATCH":
                self.assertEqual(fields, ("state=closed",))
                return {"number": self.number, "state": "closed"}
            raise AssertionError(endpoint)
        with patch.object(mod, "api", side_effect=fake):
            mod.cleanup_stale_daily_prs()
        self.assertIn((f"repos/{mod.REPO}/pulls/{self.number}", "PATCH"), calls)

    def test_recent_or_untrusted_stale_daily_pr_is_never_closed(self):
        for case in ("recent", "wrong-author", "fork", "invalid-branch"):
            with self.subTest(case=case):
                old = json.loads(json.dumps(self.pr))
                old["created_at"] = (
                    datetime.now(timezone.utc) - timedelta(hours=26)
                ).isoformat()
                if case == "recent":
                    old["created_at"] = datetime.now(timezone.utc).isoformat()
                elif case == "wrong-author":
                    old["user"]["login"] = "untrusted-user"
                elif case == "fork":
                    old["head"]["repo"]["full_name"] = "untrusted/fork"
                elif case == "invalid-branch":
                    old["head"]["ref"] = "automation/daily-events/handmade"
                calls = []
                def fake(endpoint, *, method=None, **kwargs):
                    calls.append((endpoint, method))
                    if endpoint.endswith("/git/ref/heads/main"):
                        return {"object": {"sha": self.base}}
                    if endpoint.endswith("/pulls?state=open&base=main&per_page=100"):
                        return [{"number": self.number, "head": {"ref": self.branch}}]
                    if endpoint.endswith(f"/pulls/{self.number}") and not method:
                        return old
                    raise AssertionError("Unexpected mutation: " + endpoint)
                with patch.object(mod, "api", side_effect=fake):
                    with self.assertRaises(mod.UnsafeToPublish):
                        mod.cleanup_stale_daily_prs()
                self.assertFalse(any(method for _, method in calls))

    def test_cleanup_refuses_ambiguous_list_or_moved_main(self):
        with patch.object(mod, "current_main", return_value="e" * 40), \
             patch.object(mod, "api") as mocked:
            with self.assertRaises(mod.UnsafeToPublish):
                mod.cleanup_stale_daily_prs()
            mocked.assert_not_called()
        with patch.object(mod, "current_main", return_value=self.base), \
             patch.object(mod, "api", return_value=[
                 {"number": 1, "head": {"ref": self.branch}},
                 {"number": 2, "head": {"ref": "automation/daily-events/2-1"}},
             ]):
            with self.assertRaises(mod.UnsafeToPublish):
                mod.cleanup_stale_daily_prs()


    def test_healthy_pr_and_exact_head_ci_allow_publication(self):
        with patch.object(mod, "api", side_effect=self.fake_api), patch.object(
                mod, "current_main", side_effect=[self.base, self.base, self.after]):
            mod.publish()
        self.assertIn("GitHub Pages deployment succeeded", Path("summary").read_text())




    def test_merged_commit_contains_exact_validated_local_json(self):
        with patch.object(mod, "api", side_effect=self.fake_api):
            mod.verify_merged_payload(self.after)

    def test_merged_commit_payload_tamper_is_detected_after_merge(self):
        calls = []
        def modified_merged_content(endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint.endswith(f"/contents/events.json?ref={self.after}"):
                return {"type": "file", "encoding": "base64",
                        "content": base64.b64encode(b'{"fake":true}').decode()}
            return self.fake_api(endpoint, **kwargs)
        with patch.object(mod, "api", side_effect=modified_merged_content), patch.object(
                mod, "current_main", side_effect=[self.base, self.base, self.after]):
            with self.assertRaisesRegex(mod.UnsafeToPublish, "differs from validated"):
                mod.publish()
        self.assertTrue(any(x.endswith("/merge") for x in calls))
        self.assertFalse(any("/actions/runs?head_sha=" in x for x in calls))

    def test_merged_commit_bad_encoding_or_missing_file_is_rejected(self):
        for payload in (
            {"type": "file", "encoding": "base64", "content": "$invalid"},
            {"type": "file", "encoding": "raw", "content": "not base64"},
            {"type": "dir", "encoding": "base64", "content": "AA=="},
        ):
            with self.subTest(payload=payload):
                def bad_file(endpoint, **kwargs):
                    if endpoint.endswith(f"/contents/events.json?ref={self.after}"):
                        return payload
                    return self.fake_api(endpoint, **kwargs)
                with patch.object(mod, "api", side_effect=bad_file):
                    with self.assertRaises(mod.UnsafeToPublish):
                        mod.verify_merged_payload(self.after)


    def test_squash_parent_must_be_original_main_before_reporting_deployment(self):
        with patch.object(mod, "api", side_effect=self.fake_api):
            self.assertTrue(mod.verify_merged_commit_parent(self.base, self.after))
        for parents in (
            [{"sha": "d" * 40}],
            [], [{"sha": self.base}, {"sha": self.base}],
            None,
        ):
            with self.subTest(parents=parents):
                def changed_parent(endpoint, **kwargs):
                    if endpoint.endswith(f"/git/commits/{self.after}"):
                        return {"parents": parents}
                    return self.fake_api(endpoint, **kwargs)
                with patch.object(mod, "api", side_effect=changed_parent):
                    with self.assertRaisesRegex(mod.UnsafeToPublish, "across PR merge"):
                        mod.verify_merged_commit_parent(self.base, self.after)

    def test_merge_race_is_detected_after_real_merge_result_without_undo(self):
        calls = []
        def concurrent_main(endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint.endswith(f"/git/commits/{self.after}"):
                return {"parents": [{"sha": "d" * 40}]}
            return self.fake_api(endpoint, **kwargs)
        with patch.object(mod, "api", side_effect=concurrent_main), patch.object(
                mod, "current_main", side_effect=[self.base, self.base, self.after]):
            with self.assertRaisesRegex(mod.UnsafeToPublish, "across PR merge"):
                mod.publish()
        self.assertTrue(any(x.endswith("/merge") for x in calls))
        self.assertFalse(any("/actions/runs?head_sha=" in x for x in calls))


    def test_pages_success_matches_real_dynamic_pages_workflow_only(self):
        with patch.object(mod, "api", side_effect=self.fake_api):
            self.assertEqual(mod.pages_status(self.after), "success")
        for field, wrong in (
            ("head_sha", "d" * 40),
            ("head_branch", "automation/old"),
            ("event", "push"),
            ("name", "Calendar Integrity Tests"),
            ("path", ".github/workflows/test-integrity.yml"),
        ):
            with self.subTest(field=field):
                before = self.pages_run[field]
                self.pages_run[field] = wrong
                with patch.object(mod, "api", side_effect=self.fake_api):
                    self.assertEqual(mod.pages_status(self.after), "pending")
                self.pages_run[field] = before

    def test_pages_failure_and_ambiguous_runs_rejected_after_merge(self):
        original = self.pages_run["conclusion"]
        self.pages_run["conclusion"] = "failure"
        with patch.object(mod, "api", side_effect=self.fake_api):
            with self.assertRaisesRegex(mod.UnsafeToPublish, "after merge"):
                mod.pages_status(self.after)
        self.pages_run["conclusion"] = original
        def duplicate(endpoint, **kwargs):
            if "/actions/runs?head_sha=" in endpoint:
                return {"workflow_runs": [self.pages_run, self.pages_run]}
            return self.fake_api(endpoint, **kwargs)
        with patch.object(mod, "api", side_effect=duplicate):
            with self.assertRaisesRegex(mod.UnsafeToPublish, "Ambiguous"):
                mod.pages_status(self.after)

    def test_no_pages_run_times_out_after_merge_without_claiming_success(self):
        call_sequence = []
        def missing_pages(endpoint, **kwargs):
            call_sequence.append(endpoint)
            if "/actions/runs?head_sha=" in endpoint:
                return {"workflow_runs": []}
            return self.fake_api(endpoint, **kwargs)
        with patch.object(mod, "api", side_effect=missing_pages), patch.object(
                mod, "current_main", side_effect=[self.base, self.base, self.after]), patch.object(
                mod.time, "sleep", return_value=None), patch.object(
                mod.time, "monotonic", side_effect=[0, 0, 999]):
            with self.assertRaisesRegex(mod.UnsafeToPublish, "not confirmed after merge"):
                mod.publish()
        self.assertTrue(any(x.endswith("/merge") for x in call_sequence))
        self.assertNotIn("deployment succeeded", Path("summary").read_text())


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
