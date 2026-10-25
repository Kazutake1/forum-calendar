"""Read-only tests for the daily writer's conditional GitHub Pages refresh.

No network, real writer invocation, production data mutation, or Pages deployment.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DAILY = WORKFLOWS / "update-events.yml"
MONTHLY = WORKFLOWS / "monthly-manual-events.yml"


def get_step(source, name):
    marker = "      - name: " + name + "\n"
    if source.count(marker) != 1:
        raise AssertionError(f"Expected exactly one step: {name}")
    after = source.split(marker, 1)[1]
    return after.split("\n      - name: ", 1)[0]


class DailyPagesRefreshTests(unittest.TestCase):
    def test_rebuild_is_gated_on_successful_changed_push(self):
        source = DAILY.read_text(encoding="utf-8")
        commit = get_step(source, "Commit updated data")
        rebuild = get_step(source, "Explicitly request Pages rebuild after bot commit")
        self.assertIn("id: persist", commit)
        self.assertIn('echo "changed=false" >> "$GITHUB_OUTPUT"', commit)
        self.assertIn('echo "changed=true" >> "$GITHUB_OUTPUT"', commit)
        self.assertLess(commit.index("git push"), commit.index('echo "changed=true"'))
        self.assertIn("if: steps.persist.outputs.changed == 'true'", rebuild)
        self.assertLess(source.index("name: Validate generated event files"), source.index("name: Commit updated data"))
        self.assertLess(source.index("name: Commit updated data"), source.index("name: Explicitly request Pages rebuild"))
        self.assertIn("pages/builds", rebuild)
        self.assertIn('if [[ "$response" != "201" ]]', rebuild)
        self.assertIn("exit 1", rebuild)
        self.assertNotIn("continue-on-error: true", source)

    def test_scoped_writer_permissions_and_existing_trigger(self):
        source = DAILY.read_text(encoding="utf-8")
        monthly = MONTHLY.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: write\n  pages: write\n", source)
        self.assertIn("permissions:\n  contents: write\n  pages: write\n", monthly)
        self.assertNotIn("permissions: write-all", source)
        self.assertIn("cron: '20 22 * * *'", source)
        self.assertIn("run: python update_events_no_ocr.py", source)
        self.assertIn("group: forum-calendar-main-write", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("git add events.json update-meta.json", source)
        self.assertNotIn("actions/deploy-pages", source)

    def test_commit_step_no_change_vs_successful_push_with_fake_git(self):
        source = DAILY.read_text(encoding="utf-8")
        commit = get_step(source, "Commit updated data")
        self.assertIn("        run: |", commit)
        script = textwrap.dedent(commit.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            git = root / "git"
            git.write_text(
                "#!/bin/sh\n"
                'echo "$*" >> "$FAKE_GIT_LOG"\n'
                'if [ "$1" = "diff" ]; then\n'
                '  if [ "$GIT_CHANGED" = "0" ]; then exit 0; fi\n'
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            git.chmod(0o755)
            for changed in ("0", "1"):
                with self.subTest(changed=changed):
                    output = root / "outputs"
                    calls = root / "calls"
                    output.write_text("", encoding="utf-8")
                    calls.write_text("", encoding="utf-8")
                    env = dict(
                        os.environ,
                        PATH=str(root) + os.pathsep + os.environ.get("PATH", ""),
                        GIT_CHANGED=changed,
                        FAKE_GIT_LOG=str(calls),
                        GITHUB_OUTPUT=str(output),
                    )
                    result = subprocess.run(
                        ["bash", "-e", "-c", script],
                        cwd=root, env=env,
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        output.read_text(encoding="utf-8").strip(),
                        "changed=" + ("true" if changed == "1" else "false"),
                    )
                    called = calls.read_text(encoding="utf-8").splitlines()
                    if changed == "0":
                        self.assertFalse(any(s.startswith("push") for s in called))
                    else:
                        self.assertTrue(any(s.startswith("commit") for s in called))
                        self.assertTrue(any(s.startswith("push") for s in called))


if __name__ == "__main__":
    unittest.main()
