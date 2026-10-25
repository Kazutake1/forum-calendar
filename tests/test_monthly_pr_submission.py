"""Execute the monthly proposal shell step against fake gh/git, never GitHub.

Checks GitHub Contents API version requirements for modified vs newly added
archive files and fail-closed behavior on main races, pending PRs, or API errors.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

MONTHLY = Path(__file__).resolve().parents[1] / ".github/workflows/monthly-manual-events.yml"


def proposal_shell():
    content = MONTHLY.read_text(encoding="utf-8")
    marker = "      - name: Open monthly archive PR for verified automatic publication\n"
    if content.count(marker) != 1:
        raise AssertionError("Monthly PR proposal step missing or duplicated")
    step = content.split(marker, 1)[1].split("\n      - name: ", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


class MonthlyProposalSyntheticTests(unittest.TestCase):
    def execute(self, *, main_sha=None, pending="", fail_put=False,
                wrong_blob=False):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            for relative, value in (
                ("manual_events.json", "[]\n"),
                ("reports/manual-event-review.md", "fictional report\n"),
                ("archive/manual_events_2026.json", "[]\n"),
            ):
                p = root / relative
                p.parent.mkdir(exist_ok=True, parents=True)
                p.write_text(value, encoding="utf-8")
            gh = root / "gh"
            gh.write_text(r"""#!/bin/bash
printf '%s\n' "$*" >> "$FAKE_GH_CALLS"
if [[ "$*" == *'/pulls?state=open'* ]]; then
  printf '%s\n' "$FAKE_PENDING"
  exit 0
fi
if [[ "$*" == *'/git/ref/heads/main'* ]]; then
  printf '%s\n' "$FAKE_MAIN_SHA"
  exit 0
fi
if [[ "$*" == *'/contents/'* ]]; then
  python -c 'import json,re,sys; d=json.load(sys.stdin); p=sys.argv[1]; assert d["branch"] == "automation/monthly-manual/12345-1"; assert d["content"]; assert ("sha" not in d) if "archive/" in p else bool(re.fullmatch(r"[0-9a-f]{40}", d.get("sha", "")))' "$*" || exit 41
  if [[ "$FAKE_FAIL_PUT" == 1 ]]; then
    exit 42
  fi
  exit 0
fi
if [[ "$*" == *'/pulls -X POST'* ]]; then
  printf '%s\n' '999'
fi
""", encoding="utf-8")
            gh.chmod(0o755)
            git = root / "git"
            git.write_text(r"""#!/bin/bash
if [[ "$*" == 'diff --cached --name-only' ]]; then
  printf '%s\n' manual_events.json reports/manual-event-review.md archive/manual_events_2026.json
  exit 0
fi
if [[ "$*" == 'cat-file -e HEAD:archive/manual_events_2026.json' ]]; then
  exit 1
fi
if [[ "$1" == 'cat-file' ]]; then
  exit 0
fi
if [[ "$1" == 'rev-parse' ]]; then
  if [[ "$FAKE_BAD_BLOB" == 1 ]]; then
    printf '%s\n' 'bad'
  else
    printf '%040d\n' 7
  fi
  exit 0
fi
exit 99
""", encoding="utf-8")
            git.chmod(0o755)
            log = root / "calls"
            summary = root / "summary"
            env = dict(os.environ,
                       PATH=str(root) + os.pathsep + os.environ["PATH"],
                       REPOSITORY="Kazutake1/forum-calendar",
                       BASE_SHA="a" * 40,
                       RUN_ID="12345", RUN_ATTEMPT="1",
                       FAKE_MAIN_SHA=main_sha or ("a" * 40),
                       FAKE_PENDING=pending,
                       FAKE_FAIL_PUT="1" if fail_put else "0",
                       FAKE_BAD_BLOB="1" if wrong_blob else "0",
                       FAKE_GH_CALLS=str(log),
                       GITHUB_STEP_SUMMARY=str(summary),
                       GITHUB_OUTPUT=str(root / "output"),
                       GH_TOKEN="SYNTHETIC_NOT_SECRET")
            run = subprocess.run(["bash", "-e", "-c", proposal_shell()],
                                 cwd=root, env=env, text=True,
                                 capture_output=True, timeout=20, check=False)
            calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            output = (root / "output").read_text(encoding="utf-8") if (root / "output").exists() else ""
            return run.returncode, calls, output

    def test_modified_files_use_base_blob_sha_and_new_archive_has_no_sha(self):
        code, calls, output = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(len([c for c in calls if "/contents/" in c]), 3)
        self.assertIn("/contents/manual_events.json", " ".join(calls))
        self.assertIn("/contents/reports/manual-event-review.md", " ".join(calls))
        self.assertIn("/contents/archive/manual_events_2026.json", " ".join(calls))
        self.assertIn("number=999", output)
        self.assertIn("branch=automation/monthly-manual/12345-1", output)

    def test_stale_main_blocks_branch_and_pr_creation(self):
        code, calls, output = self.execute(main_sha="b" * 40)
        self.assertNotEqual(code, 0)
        self.assertFalse(any("/git/refs" in c or "/contents/" in c or "/pulls -X POST" in c
                             for c in calls))
        self.assertEqual(output, "")

    def test_pending_monthly_pr_blocks_new_proposal(self):
        code, calls, output = self.execute(pending="88")
        self.assertNotEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(output, "")

    def test_invalid_original_blob_sha_prevents_any_file_updates(self):
        code, calls, output = self.execute(wrong_blob=True)
        self.assertNotEqual(code, 0)
        self.assertFalse(any("/contents/" in c or "/pulls -X POST" in c for c in calls))
        self.assertEqual(output, "")

    def test_api_file_update_failure_prevents_pr_creation(self):
        code, calls, output = self.execute(fail_put=True)
        self.assertNotEqual(code, 0)
        self.assertTrue(any("/contents/" in c for c in calls))
        self.assertFalse(any("/pulls -X POST" in c for c in calls))
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
