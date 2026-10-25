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

if __name__ == "__main__":
    unittest.main()
