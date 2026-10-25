"""Guard GitHub Pages Jekyll 3 publishing exclusions without changing event data.

The actual Pages Jekyll build/deployment artifact must still be checked before
merging: these tests audit tracked source inputs and explicit Jekyll exclusions.
"""

import fnmatch
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "_config.yml"
PUBLIC_ASSETS = frozenset({
    "index.html", "sw.js", "manifest.json",
    "icon-180.png", "icon-192.png", "icon-512.png",
    "manual-events.js", "verified-schedule.js",
    "events.json", "manual_events.json", "verified_schedule.json",
    "event-policy.json", "update-meta.json",
})
JEKYLL_3_DEFAULT_EXCLUDES = frozenset({
    ".sass-cache/", ".jekyll-cache/", "gemfiles/",
    "Gemfile", "Gemfile.lock", "node_modules/",
    "vendor/bundle/", "vendor/cache/", "vendor/gems/", "vendor/ruby/",
})
# All 22 unwanted files independently observed inside the successful
# 2026-10-25 GitHub Pages deployment artifact.
PRIOR_UNWANTED_OUTPUT = frozenset({
    "CHANGELOG.html", "CHANGELOG.md", "README.md",
    "event_integrity.py", "jr_walking_web.py", "manage_manual_events.py",
    "reports/manual-event-review.html", "reports/manual-event-review.md",
    "requirements.txt", "tests/event_merge_contract.json",
    "tests/test_auto_offline.cjs", "tests/test_event_integrity.py",
    "tests/test_event_policy.py", "tests/test_jr_walking_web.py",
    "tests/test_manage_manual_events.py", "tests/test_manual_merge.cjs",
    "tests/test_no_ocr_policy.py", "tests/test_update_guard.py",
    "tests/test_verified_offline.cjs", "tests/test_verified_schedule.cjs",
    "update_events.py", "update_events_no_ocr.py",
})
GENERATED_HTML_SOURCES = {
    "CHANGELOG.html": "CHANGELOG.md",
    "reports/manual-event-review.html": "reports/manual-event-review.md",
}


def excludes_from_yaml_subset():
    """Parse only a strict JSON-quoted YAML exclude list; no YAML dependency."""
    entries = []
    non_comments = [line for line in CONFIG.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    if not non_comments or non_comments[0] != "exclude:":
        raise AssertionError("Jekyll _config.yml must set only exclude")
    for line in non_comments[1:]:
        if not line.startswith("  - "):
            raise AssertionError("Unexpected Jekyll setting; manual review required")
        item = json.loads(line[4:])
        if not isinstance(item, str) or not item or item.startswith("/"):
            raise AssertionError("Exclusion path must be relative and non-empty")
        entries.append(item)
    if len(entries) != len(set(entries)):
        raise AssertionError("Duplicate exclusions")
    return frozenset(entries)


def excluded_by_jekyll(path, entries):
    """Mirror the default hidden/underscore skip and explicit root excludes."""
    posix = Path(path).as_posix()
    if any(part.startswith((".", "_", "#")) for part in Path(posix).parts):
        return True
    if posix.endswith("~"):
        return True
    for entry in entries:
        base = entry.rstrip("/")
        if posix == base or posix.startswith(base + "/"):
            return True
        if fnmatch.fnmatchcase(posix, entry):
            return True
    return False


def tracked_paths():
    data = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return {name.decode("utf-8", "surrogateescape")
            for name in data.split(b"\0") if name}


class PagesPublicationBoundaryTests(unittest.TestCase):
    def test_only_jekyll_excludes_are_configured_and_defaults_preserved(self):
        entries = excludes_from_yaml_subset()
        self.assertFalse(JEKYLL_3_DEFAULT_EXCLUDES - entries)

    def test_pwa_assets_are_present_and_not_excluded(self):
        entries = excludes_from_yaml_subset()
        tracked = tracked_paths()
        self.assertFalse(PUBLIC_ASSETS - tracked)
        blocked = sorted(p for p in PUBLIC_ASSETS if excluded_by_jekyll(p, entries))
        self.assertEqual(blocked, [], "Jekyll exclusions block required PWA assets")

    def test_all_previous_unwanted_output_sources_are_excluded(self):
        entries = excludes_from_yaml_subset()
        uncovered = []
        for output in sorted(PRIOR_UNWANTED_OUTPUT):
            source = GENERATED_HTML_SOURCES.get(output, output)
            if not excluded_by_jekyll(source, entries):
                uncovered.append(output)
        self.assertEqual(uncovered, [], "Previously published non-PWA sources remain exposed")

    def test_new_tracked_files_cannot_silently_become_public(self):
        entries = excludes_from_yaml_subset()
        tracked = tracked_paths()
        accidental = sorted(
            path for path in tracked
            if path not in PUBLIC_ASSETS and not excluded_by_jekyll(path, entries)
        )
        self.assertEqual(accidental, [], "Unexpected tracked files may be published")

    def test_rejects_illustrative_future_unknown_sources(self):
        entries = excludes_from_yaml_subset()
        # Any such file must be explicitly reviewed and excluded if added to git.
        for candidate in ("internal-notes.txt", "backup-data.json",
                          "tmp/credentials.txt", "scratch/sample.csv"):
            with self.subTest(path=candidate):
                self.assertFalse(excluded_by_jekyll(candidate, entries))


if __name__ == "__main__":
    unittest.main()
