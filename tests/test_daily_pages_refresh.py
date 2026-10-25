"""Offline guards for daily GitHub App Draft PR writer.

No network, no production updater, no Pages deployment, no real GitHub token.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "update-events.yml"
MONTHLY = ROOT / ".github" / "workflows" / "monthly-manual-events.yml"


def get_step(source, name):
    marker = "      - name: " + name + "\n"
    if source.count(marker) != 1:
        raise AssertionError(f"Expected exactly one step: {name}")
    after = source.split(marker, 1)[1]
    return after.split("\n      - name: ", 1)[0]


def shell_step(source, name):
    step = get_step(source, name)
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


class DailyAppPrTests(unittest.TestCase):
    def test_daily_writer_is_review_only_with_no_main_push_or_pages_rebuild(self):
        source = DAILY.read_text(encoding="utf-8")
        self.assertIn("cron: '20 22 * * *'", source)
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("if: github.ref == 'refs/heads/main'", source)
        self.assertIn("group: forum-calendar-main-write", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("permissions:\n  contents: read\n", source)
        self.assertIn("persist-credentials: false", source)
        self.assertNotIn("git push", source)
        self.assertNotIn("pages/builds", source)
        self.assertNotIn("continue-on-error: true", source)
        self.assertIn("run: python update_events_no_ocr.py", source)
        self.assertLess(source.index("name: Validate generated event files"),
                        source.index("name: Verify updated data before proposing PR"))
        self.assertLess(source.index("name: Verify updated data before proposing PR"),
                        source.index("name: Check exact daily output files"))
        self.assertLess(source.index("name: Check exact daily output files"),
                        source.index("name: Issue short-lived repository-scoped GitHub App token"))
        self.assertLess(source.index("name: Issue short-lived repository-scoped GitHub App token"),
                        source.index("name: Open review-only daily event Draft PR"))

    def test_app_token_only_if_changed_and_publish_exact_allowlist(self):
        source = DAILY.read_text(encoding="utf-8")
        self.assertEqual(source.count("if: steps.changes.outputs.changed == 'true'"), 2)
        self.assertIn("client-id: ${{ vars.FORUM_CALENDAR_APP_CLIENT_ID }}", source)
        self.assertIn("private-key: ${{ secrets.FORUM_CALENDAR_APP_PRIVATE_KEY }}", source)
        self.assertIn("permission-contents: write", source)
        self.assertIn("permission-pull-requests: write", source)
        self.assertIn("GH_TOKEN: ${{ steps.app-token.outputs.token }}", source)
        self.assertIn("git add -- events.json update-meta.json", source)
        self.assertIn("Unexpected changed file; refusing to publish", source)
        self.assertIn("git status --porcelain --untracked-files=all", source)
        self.assertIn("git diff --cached --quiet --", source)
        self.assertIn("automation/daily-events/", source)
        self.assertIn("-F draft=true", source)
        self.assertIn("git/ref/heads/main", source)
        self.assertIn('if [[ "$current" != "$BASE_SHA" ]]', source)
        self.assertIn("--paginate", source)
        self.assertIn("human approval", source)

    def test_monthly_writer_is_unchanged(self):
        monthly = MONTHLY.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: write\n  pages: write", monthly)
        self.assertIn("git push origin HEAD:main", monthly)
        self.assertIn("cron: '10 1 1 * *'", monthly)

    def _exercise_submit(self, latest_sha, pending="", fail_put=False, changed=("events.json", "update-meta.json")):
        script = shell_step(DAILY.read_text(encoding="utf-8"),
                            "Open review-only daily event Draft PR")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "events.json").write_text("[]\n", encoding="utf-8")
            (root / "update-meta.json").write_text('{"event_count":0}\n', encoding="utf-8")
            gh = root / "gh"
            gh.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_GH_CALLS\"\n"
                "if [[ \"$*\" == *'/pulls?state=open'* ]]; then\n"
                "  printf '%s\\n' \"$FAKE_PENDING\"; exit 0\n"
                "fi\n"
                "if [[ \"$*\" == *'/git/ref/heads/main'* ]]; then\n"
                "  printf '%s\\n' \"$FAKE_MAIN_SHA\"; exit 0\n"
                "fi\n"
                "if [[ \"$*\" == *'/contents/'* ]]; then\n"
                "  cat >/dev/null  # consume piped JSON, preventing broken pipe\n"
                "  if [[ \"$FAKE_FAIL_PUT\" == 1 ]]; then exit 19; fi\n"
                "fi\n"
                "if [[ \"$*\" == *'/pulls -X POST'* ]]; then\n"
                "  printf '%s\\n' 'https://github.com/Kazutake1/forum-calendar/pull/99999'\n"
                "fi\n",
                encoding="utf-8",
            )
            gh.chmod(0o755)
            git = root / "git"
            git.write_text(
                "#!/bin/bash\n"
                "if [[ \"$*\" == *'events.json'* ]]; then\n"
                "  [[ \"$FAKE_CHANGED\" != *events.json* ]]; exit $?\n"
                "elif [[ \"$*\" == *'update-meta.json'* ]]; then\n"
                "  [[ \"$FAKE_CHANGED\" != *update-meta.json* ]]; exit $?\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            git.chmod(0o755)
            calls, summary = root / "calls", root / "summary"
            env = dict(os.environ,
                       PATH=str(root) + os.pathsep + os.environ.get("PATH", ""),
                       REPOSITORY="Kazutake1/forum-calendar",
                       BASE_SHA="a" * 40,
                       RUN_ID="12345", RUN_ATTEMPT="1",
                       FAKE_MAIN_SHA=latest_sha, FAKE_PENDING=pending,
                       FAKE_FAIL_PUT="1" if fail_put else "0",
                       FAKE_CHANGED=",".join(changed),
                       FAKE_GH_CALLS=str(calls),
                       GITHUB_STEP_SUMMARY=str(summary),
                       GH_TOKEN="SYNTHETIC_TEST_ONLY")
            p = subprocess.run(["bash", "-e", "-c", script], cwd=root,
                               env=env, text=True, capture_output=True, check=False)
            return (p.returncode, calls.read_text(encoding="utf-8").splitlines()
                    if calls.exists() else [],
                    summary.read_text(encoding="utf-8") if summary.exists() else "")

    def test_fake_github_creates_two_outputs_and_draft_pr_only(self):
        code, calls, summary = self._exercise_submit("a" * 40)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 6, calls)
        self.assertIn("/pulls?state=open", calls[0])
        self.assertIn("/git/ref/heads/main", calls[1])
        self.assertIn("/git/refs -X POST", calls[2])
        self.assertIn("automation/daily-events/12345-1", calls[2])
        self.assertIn("/contents/events.json -X PUT", calls[3])
        self.assertIn("/contents/update-meta.json -X PUT", calls[4])
        self.assertIn("/pulls -X POST", calls[5])
        self.assertIn("-F draft=true", calls[5])
        self.assertIn("pull/99999", summary)

    def test_fake_github_does_not_create_pr_if_review_pending_or_main_changed(self):
        code, calls, summary = self._exercise_submit("a" * 40, pending="34")
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("awaiting review", summary)
        code, calls, summary = self._exercise_submit("b" * 40)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(summary, "")

    def test_fake_github_fail_closed_on_put_error(self):
        code, calls, summary = self._exercise_submit("a" * 40, fail_put=True)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(calls), 4)
        self.assertFalse(any("/pulls -X POST" in call for call in calls))
        self.assertEqual(summary, "")

    def test_fake_github_only_writes_changed_output_file(self):
        code, calls, summary = self._exercise_submit("a" * 40, changed=("events.json",))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 5)
        self.assertEqual(len([c for c in calls if "/contents/" in c]), 1)
        self.assertIn("/contents/events.json", " ".join(calls))
        self.assertIn("pull/99999", summary)


if __name__ == "__main__":
    unittest.main()
