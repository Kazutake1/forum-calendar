"""Static policy tests for manual GitHub App synthetic PR smoke workflow.

Never execute the workflow, read secrets, call GitHub, or modify event data.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "app-smoke-test.yml"

def workflow():
    return WORKFLOW.read_text(encoding="utf-8")

class AppSmokeWorkflowTests(unittest.TestCase):
    def test_only_manual_dispatch_with_explicit_confirmation_and_main_gate(self):
        s = workflow()
        self.assertIn("on:\n  workflow_dispatch:\n    inputs:\n", s)
        self.assertNotIn("\n  schedule:", s)
        self.assertNotIn("\n  push:", s)
        self.assertNotIn("\n  pull_request:", s)
        self.assertIn("if: github.ref == 'refs/heads/main'", s)
        self.assertIn("SYNTHETIC_DRAFT_PR_ONLY", s)
        self.assertIn("if [[ \"$CONFIRMATION\" != 'SYNTHETIC_DRAFT_PR_ONLY' ]]", s)

    def test_repo_scoped_token_and_no_default_writer_token_escalation(self):
        s = workflow()
        self.assertIn("permissions:\n  contents: read\n", s)
        self.assertNotIn("permissions: write-all", s)
        self.assertIn("actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510", s)
        self.assertIn("client-id: ${{ vars.FORUM_CALENDAR_APP_CLIENT_ID }}", s)
        self.assertIn("private-key: ${{ secrets.FORUM_CALENDAR_APP_PRIVATE_KEY }}", s)
        self.assertIn("permission-contents: write", s)
        self.assertIn("permission-pull-requests: write", s)
        self.assertNotIn("skip-token-revoke:", s)
        self.assertNotIn("owner: ${{ github.repository_owner }}", s)
        self.assertNotIn("repositories:", s)
        self.assertIn("GH_TOKEN: ${{ steps.app-token.outputs.token }}", s)
        self.assertNotIn("echo \"${{ steps.app-token.outputs.token }}\"", s)

    def test_only_synthetic_fixture_draft_pr_never_main_push(self):
        s = workflow()
        self.assertIn("REPOSITORY\" != 'Kazutake1/forum-calendar'", s)
        self.assertIn('branch="automation/app-smoke/${RUN_ID}-${RUN_ATTEMPT}"', s)
        self.assertIn('path="tests/fixtures/app-smoke-${RUN_ID}-${RUN_ATTEMPT}.json"', s)
        self.assertIn('current=$(gh api "repos/${REPOSITORY}/git/ref/heads/main"', s)
        self.assertIn('if [[ "$current" != "$BASE_SHA" ]]', s)
        self.assertIn('-f branch="$branch" -f content="$encoded"', s)
        self.assertIn('-F draft=true --jq \'.html_url\'', s)
        self.assertIn("do not merge", s)
        self.assertNotIn("git push", s)
        for forbidden in ("events.json", "manual_events.json", "verified_schedule.json",
                          "update-meta.json", "archive/manual_events_"):
            self.assertNotIn(forbidden, s)

    def test_synthetic_payload_cannot_embed_source_secrets(self):
        s = workflow()
        self.assertIn('"fictional":true', s)
        self.assertIn("base64 | tr -d", s)
        self.assertIn("id: app-token", s)
        self.assertIn("timeout-minutes: 10", s)
        self.assertIn("set -euo pipefail", s)
        self.assertNotIn("set -x", s)
        self.assertNotIn("pull_request_target", s)

    def _exercise_api_shell_with_fake_gh(self, current_sha, fail_put=False):
        """Execute the real workflow shell fragment with mocked GitHub CLI."""
        import os
        import subprocess
        import tempfile
        import textwrap
        source = workflow()
        step = source.split("      - name: Open synthetic draft PR (never merge)\n", 1)[1]
        code = textwrap.dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / "gh"
            fake.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_GH_CALLS\"\n"
                "case \"$2\" in\n"
                "  */git/ref/heads/main) printf '%s\\n' \"$FAKE_MAIN_SHA\" ;;\n"
                "  */contents/tests/fixtures/*)\n"
                "    if [ \"$FAKE_FAIL_PUT\" = '1' ]; then exit 19; fi ;;\n"
                "  */pulls) printf '%s\\n' 'https://github.com/Kazutake1/forum-calendar/pull/999999' ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            calls = root / "calls"
            summary = root / "summary"
            env = dict(os.environ,
                       PATH=str(root) + os.pathsep + os.environ.get("PATH", ""),
                       REPOSITORY="Kazutake1/forum-calendar",
                       BASE_SHA="a" * 40,
                       RUN_ID="999001",
                       RUN_ATTEMPT="1",
                       FAKE_MAIN_SHA=current_sha,
                       FAKE_FAIL_PUT="1" if fail_put else "0",
                       FAKE_GH_CALLS=str(calls),
                       GITHUB_STEP_SUMMARY=str(summary),
                       GH_TOKEN="TEST_ONLY_NOT_A_REAL_TOKEN")
            result = subprocess.run(
                ["bash", "-e", "-c", code], cwd=root,
                env=env, capture_output=True, text=True, check=False,
            )
            return (result.returncode,
                    calls.read_text(encoding="utf-8").splitlines() if calls.exists() else [],
                    summary.read_text(encoding="utf-8") if summary.exists() else "")

    def test_app_smoke_shell_api_sequence_with_fake_gh(self):
        status, calls, summary = self._exercise_api_shell_with_fake_gh("a" * 40)
        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 4)
        self.assertIn("/git/ref/heads/main", calls[0])
        self.assertIn("/git/refs -X POST", calls[1])
        self.assertIn("automation/app-smoke/999001-1", calls[1])
        self.assertIn("/contents/tests/fixtures/app-smoke-999001-1.json", calls[2])
        self.assertIn("-f branch=automation/app-smoke/999001-1", calls[2])
        self.assertIn("/pulls -X POST", calls[3])
        self.assertIn("-F draft=true", calls[3])
        self.assertIn("pull/999999", summary)

    def test_app_smoke_shell_fails_closed_before_pr_on_conflict_or_api_error(self):
        mismatch, calls, summary = self._exercise_api_shell_with_fake_gh("b" * 40)
        self.assertNotEqual(mismatch, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(summary, "")

        error, calls, summary = self._exercise_api_shell_with_fake_gh(
            "a" * 40, fail_put=True)
        self.assertNotEqual(error, 0)
        self.assertEqual(len(calls), 3)
        self.assertFalse(any("/pulls" in c for c in calls))
        self.assertEqual(summary, "")

if __name__ == "__main__":
    unittest.main()
