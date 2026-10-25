"""Offline policy checks for a proposed scheduled-writer pull request.

Pure validation only: no GitHub API, credentials, branch writes, or merge.
The repository ruleset and required GitHub checks must independently enforce
protection before this can be used for any automated production workflow.
"""

from dataclasses import dataclass
from collections.abc import Iterable
import re

REQUIRED_CI = "test"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_BRANCH_SUFFIX = re.compile(r"[a-z0-9][a-z0-9/_-]*\Z")
_ARCHIVE = re.compile(r"archive/manual_events_[0-9]{4}\.json\Z")
_ALLOWED = {
    "daily": frozenset(("events.json", "update-meta.json")),
    "monthly": frozenset(("manual_events.json", "reports/manual-event-review.md")),
}


class UnsafeWriterProposal(ValueError):
    """Fail closed when a proposed bot PR does not meet the known contract."""


@dataclass(frozen=True)
class ReviewDecision:
    ready_for_human_review: bool
    automated_merge_authorized: bool = False


def validate_writer_pr(
    *,
    kind: str,
    base_branch: str,
    head_branch: str,
    head_sha: str,
    changed_paths: Iterable[str],
    checks: Iterable[dict],
) -> ReviewDecision:
    """Evaluate fictional/real metadata without performing a network action.

    This can only signal that a PR is ready for human review. It is NOT a
    substitute for verified GitHub branch protection, actual CI/PR review,
    token permissions, or validation of the contents of changed JSON files.
    """
    if kind not in _ALLOWED:
        raise UnsafeWriterProposal("unknown writer type")
    if base_branch != "main":
        raise UnsafeWriterProposal("writer PR must target main")
    prefix = f"automation/{kind}/"
    if not isinstance(head_branch, str) or not head_branch.startswith(prefix):
        raise UnsafeWriterProposal("writer PR branch namespace is invalid")
    suffix = head_branch[len(prefix):]
    if not _BRANCH_SUFFIX.fullmatch(suffix) or ".." in suffix or "//" in suffix:
        raise UnsafeWriterProposal("unsafe writer branch")
    if not isinstance(head_sha, str) or _SHA.fullmatch(head_sha) is None:
        raise UnsafeWriterProposal("invalid PR head SHA")

    paths = list(changed_paths)
    if not paths:
        raise UnsafeWriterProposal("empty PR has no changes to review")
    if any(not isinstance(p, str) or not p for p in paths):
        raise UnsafeWriterProposal("malformed changed path")
    if len(paths) != len(set(paths)):
        raise UnsafeWriterProposal("duplicate changed path")

    for path in paths:
        if (path.startswith("/") or "\\" in path
                or any(part in ("", ".", "..") for part in path.split("/"))):
            raise UnsafeWriterProposal("unsafe path")
        if path in _ALLOWED[kind]:
            continue
        if kind == "monthly" and _ARCHIVE.fullmatch(path):
            continue
        raise UnsafeWriterProposal("unauthorized changed file")

    check_rows = list(checks)
    matching = [
        row for row in check_rows
        if isinstance(row, dict) and row.get("name") == REQUIRED_CI
    ]
    if len(matching) != 1:
        raise UnsafeWriterProposal("missing or ambiguous required check")
    check = matching[0]
    if check.get("head_sha") != head_sha:
        raise UnsafeWriterProposal("check result belongs to another revision")
    if check.get("status") != "completed" or check.get("conclusion") != "success":
        raise UnsafeWriterProposal("required check has not passed")

    # Never authorize a merge on the basis of client-side metadata alone.
    # In production, GitHub Ruleset, checks and review requirements decide.
    return ReviewDecision(ready_for_human_review=True)
