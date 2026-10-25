"""Monthly GitHub App PR CI safety tests. Purely fabricated responses."""
import base64
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monthly_auto_merge as gate


class MonthlyMergeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        original = os.getcwd()
        os.chdir(temp.name)
        self.addCleanup(os.chdir, original)
        self.base, self.head, self.merged = ("a" * 40, "b" * 40, "c" * 40)
        self.branch = "automation/monthly-manual/712-1"
        self.number = 77
        for name, data in (("manual_events.json", b"[]\n"),
                           ("reports/manual-event-review.md", b"fictional report\n"),
                           ("archive/manual_events_2026.json", b"[]\n")):
            path = Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.changed = [
            {"filename": "manual_events.json", "status": "modified"},
            {"filename": "reports/manual-event-review.md", "status": "modified"},
            {"filename": "archive/manual_events_2026.json", "status": "added"},
        ]
        self.pr = {
            "number": self.number, "state": "open", "draft": False,
            "merged": False, "user": {"login": gate.BOT},
            "head": {"ref": self.branch, "sha": self.head,
                     "repo": {"full_name": gate.REPO}},
            "base": {"ref": "main", "sha": self.base},
        }
        self.env = patch.dict(os.environ, {
            "REPOSITORY": gate.REPO, "BASE_SHA": self.base,
            "PR_BRANCH": self.branch, "PR_NUMBER": str(self.number),
            "GH_TOKEN": "FAKE_APP_TOKEN",
            "GH_CI_READ_TOKEN": "FAKE_CI_TOKEN",
            "GITHUB_STEP_SUMMARY": str(Path(temp.name) / "summary")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.endpoints = []

    def api(self, path, **kwargs):
        self.endpoints.append(path)
        if path.endswith(f"/pulls/{self.number}"):
            return self.pr
        if path.endswith(f"/pulls/{self.number}/files?per_page=100"):
            return self.changed
        if "/contents/" in path:
            name = path.split("/contents/", 1)[1].split("?", 1)[0]
            return {"type": "file", "encoding": "base64",
                    "content": base64.b64encode(Path(name).read_bytes()).decode()}
        if path.endswith(f"/pulls/{self.number}/merge"):
            self.assertEqual(kwargs.get("method"), "PUT")
            self.assertIn("sha=" + self.head, kwargs.get("fields"))
            return {"merged": True, "sha": self.merged}
        raise AssertionError(path)

    def test_cleanup_old_verified_bot_pr_allows_next_month_without_merging_old_data(self):
        old = {**self.pr, "created_at": (
            datetime.now(timezone.utc) - timedelta(days=32)).isoformat()}
        requests = []
        def api(path, *, method=None, fields=(), **kwargs):
            requests.append((path, method))
            if path.endswith("/pulls?state=open&base=main&per_page=100"):
                return [{"number": self.number, "head": {"ref": self.branch}}]
            if path.endswith(f"/pulls/{self.number}") and method == "PATCH":
                self.assertEqual(fields, ("state=closed",))
                return {"number": self.number, "state": "closed"}
            if path.endswith(f"/pulls/{self.number}"):
                return old
            raise AssertionError(path)
        with patch.object(gate.shared, "current_main",
                          side_effect=[self.base, self.base]), patch.object(
                gate.shared, "api", side_effect=api):
            gate.cleanup_stale_monthly_prs()
        self.assertIn((f"repos/{gate.REPO}/pulls/{self.number}", "PATCH"), requests)
        self.assertFalse(any("/merge" in p for p, _ in requests))
        summary = Path(os.environ["GITHUB_STEP_SUMMARY"]).read_text()
        self.assertIn(f"Closed stale App-owned monthly PR #{self.number}; no data removed.\\n",
                      summary)
        self.assertEqual(summary.count("\\n"), 1)

    def test_cleanup_rejects_recent_foreign_fork_or_invalid_monthly_pr(self):
        for problem in ("recent", "author", "fork", "branch", "missing-created"):
            old = {
                **self.pr,
                "head": {**self.pr["head"], "repo": dict(self.pr["head"]["repo"])},
                "user": dict(self.pr["user"]),
                "created_at": (
                    datetime.now(timezone.utc) - timedelta(days=32)).isoformat(),
            }
            if problem == "recent":
                old["created_at"] = datetime.now(timezone.utc).isoformat()
            elif problem == "author":
                old["user"]["login"] = "human"
            elif problem == "fork":
                old["head"]["repo"]["full_name"] = "untrusted/repo"
            elif problem == "branch":
                old["head"]["ref"] = "automation/monthly-manual/unsafe"
            elif problem == "missing-created":
                del old["created_at"]
            mutations = []
            def api(path, *, method=None, **kwargs):
                if method:
                    mutations.append(path)
                    raise AssertionError("Untrusted monthly PR cannot be closed")
                if path.endswith("/pulls?state=open&base=main&per_page=100"):
                    return [{"number": self.number, "head": {"ref": self.branch}}]
                if path.endswith(f"/pulls/{self.number}"):
                    return old
                raise AssertionError(path)
            with self.subTest(problem=problem), patch.object(
                    gate.shared, "current_main", return_value=self.base), patch.object(
                    gate.shared, "api", side_effect=api):
                with self.assertRaises(gate.UnsafeToPublish):
                    gate.cleanup_stale_monthly_prs()
            self.assertEqual(mutations, [])

    def test_cleanup_does_not_close_multiple_or_unreadable_pending_prs(self):
        for opened in (
            [{"number": 7, "head": {"ref": self.branch}},
             {"number": 8, "head": {"ref": "automation/monthly-manual/99-1"}}],
            [{}] * 100,
            {"unexpected": "API response"},
        ):
            def api(path, **kwargs):
                self.assertTrue(path.endswith("/pulls?state=open&base=main&per_page=100"))
                return opened
            with self.subTest(opened=str(opened)[:60]), patch.object(
                    gate.shared, "current_main", return_value=self.base), patch.object(
                    gate.shared, "api", side_effect=api):
                with self.assertRaises(gate.UnsafeToPublish):
                    gate.cleanup_stale_monthly_prs()

    def test_exact_bot_owned_pr_and_content_are_required(self):
        with patch.object(gate.shared, "api", side_effect=self.api):
            self.assertEqual(gate.inspect_pr(
                self.base, self.branch, self.number),
                (self.head, {x["filename"] for x in self.changed}))

    def test_wrong_actor_or_draft_or_fork_rejected(self):
        for key, field, value in (
            ("user", "login", "another-user"),
            ("head", "repo", {"full_name": "another/fork"}),
        ):
            before = self.pr[key][field]
            self.pr[key][field] = value
            try:
                with patch.object(gate.shared, "api", side_effect=self.api):
                    with self.assertRaises(gate.UnsafeToPublish):
                        gate.inspect_pr(self.base, self.branch, self.number)
            finally:
                self.pr[key][field] = before
        self.pr["draft"] = True
        with patch.object(gate.shared, "api", side_effect=self.api):
            with self.assertRaises(gate.UnsafeToPublish):
                gate.inspect_pr(self.base, self.branch, self.number)

    def test_bad_diff_rejected_without_merge(self):
        for filename, status in (
            ("events.json", "modified"),
            ("archive/manual_events_2026.json", "removed"),
            ("archive/../events.json", "added"),
        ):
            prior = self.changed[2]
            self.changed[2] = {"filename": filename, "status": status}
            try:
                with patch.object(gate.shared, "api", side_effect=self.api):
                    with self.assertRaises(gate.UnsafeToPublish):
                        gate.inspect_pr(self.base, self.branch, self.number)
            finally:
                self.changed[2] = prior

    def test_remote_tamper_or_bad_base64_rejected(self):
        def corrupted(path, **kwargs):
            if "/contents/manual_events.json?" in path:
                return {"type": "file", "encoding": "base64",
                        "content": base64.b64encode(b"wrong").decode()}
            return self.api(path, **kwargs)
        with patch.object(gate.shared, "api", side_effect=corrupted):
            with self.assertRaisesRegex(gate.UnsafeToPublish, "not equal"):
                gate.inspect_pr(self.base, self.branch, self.number)
        def bad_encoding(path, **kwargs):
            if "/contents/manual_events.json?" in path:
                return {"type": "file", "encoding": "base64", "content": "!bad"}
            return self.api(path, **kwargs)
        with patch.object(gate.shared, "api", side_effect=bad_encoding):
            with self.assertRaisesRegex(gate.UnsafeToPublish, "encoding"):
                gate.inspect_pr(self.base, self.branch, self.number)

    def test_complete_verified_monthly_lifecycle(self):
        with patch.object(gate.shared, "api", side_effect=self.api), patch.object(
                gate.shared, "current_main",
                side_effect=[self.base, self.base, self.merged]), patch.object(
                gate.shared, "ci_status", return_value="success"), patch.object(
                gate.shared, "verify_merged_commit_parent", return_value=True), patch.object(
                gate.shared, "wait_for_pages", return_value=None):
            gate.publish()
        self.assertTrue(any(x.endswith("/merge") for x in self.endpoints))
        self.assertIn("succeeded", Path("summary").read_text())

    def test_stale_main_or_failed_ci_never_merges(self):
        with patch.object(gate.shared, "current_main", return_value="f" * 40), patch.object(
                gate.shared, "api", side_effect=self.api):
            with self.assertRaises(gate.UnsafeToPublish):
                gate.publish()
        self.assertFalse(any(e.endswith("/merge") for e in self.endpoints))
        self.endpoints.clear()
        with patch.object(gate.shared, "api", side_effect=self.api), patch.object(
                gate.shared, "current_main", return_value=self.base), patch.object(
                gate.shared, "ci_status", side_effect=gate.UnsafeToPublish("CI failed")):
            with self.assertRaisesRegex(gate.UnsafeToPublish, "CI failed"):
                gate.publish()
        self.assertFalse(any(e.endswith("/merge") for e in self.endpoints))

    def test_pages_failure_after_merge_is_not_reported_as_success(self):
        with patch.object(gate.shared, "api", side_effect=self.api), patch.object(
                gate.shared, "current_main",
                side_effect=[self.base, self.base, self.merged]), patch.object(
                gate.shared, "ci_status", return_value="success"), patch.object(
                gate.shared, "verify_merged_commit_parent", return_value=True), patch.object(
                gate.shared, "wait_for_pages", side_effect=gate.UnsafeToPublish("Pages failed")):
            with self.assertRaisesRegex(gate.UnsafeToPublish, "Pages failed"):
                gate.publish()
        self.assertIn("merged", Path("summary").read_text())
        self.assertNotIn("succeeded", Path("summary").read_text())


if __name__ == "__main__":
    unittest.main()
