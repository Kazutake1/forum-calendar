#!/usr/bin/env python3
"""Gate automatic monthly PR merge by exact GitHub App identity and passing CI.

This script is called only by the trusted main scheduled workflow. No approval
is needed on healthy runs; a failed check leaves the existing main intact.
"""
import base64
import binascii
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

import daily_auto_merge as shared
from monthly_archive_guard import permitted

REPO = shared.REPO
BOT = shared.BOT
PREFIX = "automation/monthly-manual/"
UnsafeToPublish = shared.UnsafeToPublish


def environment():
    base = os.environ.get("BASE_SHA", "")
    branch = os.environ.get("PR_BRANCH", "")
    number = os.environ.get("PR_NUMBER", "")
    if os.environ.get("REPOSITORY") != REPO or not re.fullmatch(r"[a-f0-9]{40}", base):
        raise UnsafeToPublish("Invalid monthly repository or main SHA")
    if not re.fullmatch(r"automation/monthly-manual/[0-9]+-[0-9]+", branch):
        raise UnsafeToPublish("Invalid monthly PR branch")
    if not number.isdecimal() or int(number) < 1:
        raise UnsafeToPublish("Invalid monthly PR number")
    if not (os.environ.get("GH_TOKEN") and os.environ.get("GH_CI_READ_TOKEN")):
        raise UnsafeToPublish("Missing monthly GitHub permissions")
    return base, branch, int(number)


def remote_bytes(path, sha):
    if not permitted(path):
        raise UnsafeToPublish("Unexpected monthly file path")
    remote = shared.api(
        f"repos/{REPO}/contents/{path}?ref={quote(sha, safe='')}")
    if (remote.get("type") != "file"
            or remote.get("encoding") != "base64"
            or not isinstance(remote.get("content"), str)):
        raise UnsafeToPublish("Unreadable verified monthly output")
    try:
        return base64.b64decode(
            "".join(remote["content"].split()), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise UnsafeToPublish("Invalid monthly output encoding") from exc


def inspect_pr(base, branch, number):
    pr = shared.api(f"repos/{REPO}/pulls/{number}")
    head = pr.get("head") or {}
    if not (pr.get("number") == number
            and pr.get("state") == "open"
            and pr.get("draft") is False
            and pr.get("merged") is False
            and (pr.get("user") or {}).get("login") == BOT
            and head.get("ref") == branch
            and (head.get("repo") or {}).get("full_name") == REPO
            and (pr.get("base") or {}).get("ref") == "main"
            and (pr.get("base") or {}).get("sha") == base):
        raise UnsafeToPublish("Monthly PR owner, branch or base changed")
    sha = head.get("sha", "")
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise UnsafeToPublish("Invalid monthly head SHA")
    files = shared.api(f"repos/{REPO}/pulls/{number}/files?per_page=100")
    if not isinstance(files, list) or not 1 <= len(files) <= 20:
        raise UnsafeToPublish("Monthly PR has invalid file count")
    paths = set()
    for entry in files:
        path = entry.get("filename")
        status = entry.get("status")
        if (not isinstance(path, str) or not permitted(path)
                or path in paths
                or status not in ("modified", "added")
                or (status == "added" and path == "manual_events.json")):
            raise UnsafeToPublish("Unexpected monthly PR file or status")
        paths.add(path)
        local = Path(path)
        if local.is_symlink() or not local.is_file():
            raise UnsafeToPublish("Monthly PR output file missing or a symlink")
        if remote_bytes(path, sha) != local.read_bytes():
            raise UnsafeToPublish("Monthly PR remote output not equal to checked data")
    return sha, paths


def publish():
    base, branch, number = environment()
    if shared.current_main() != base:
        raise UnsafeToPublish("Monthly main moved before PR inspection")
    head, paths = inspect_pr(base, branch, number)
    end = time.monotonic() + shared.WAIT_SECONDS
    while shared.ci_status(branch, head, number) != "success":
        if time.monotonic() >= end:
            raise UnsafeToPublish("Monthly exact-HEAD CI did not finish in time")
        time.sleep(shared.POLL_SECONDS)
    if shared.current_main() != base:
        raise UnsafeToPublish("Monthly main moved during CI")
    if inspect_pr(base, branch, number) != (head, paths):
        raise UnsafeToPublish("Monthly PR changed during CI")
    if shared.ci_status(branch, head, number) != "success":
        raise UnsafeToPublish("Monthly CI no longer successful")
    result = shared.api(f"repos/{REPO}/pulls/{number}/merge", method="PUT",
                        fields=(f"sha={head}", "merge_method=squash"))
    if result.get("merged") is not True:
        raise UnsafeToPublish("Monthly merge not confirmed")
    merged = result.get("sha")
    if not isinstance(merged, str) or not re.fullmatch(r"[a-f0-9]{40}", merged):
        raise UnsafeToPublish("Invalid monthly squash result")
    summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as out:
            out.write(f"Monthly PR #{number} merged at {merged}; verifying deployment.\n")
    if shared.current_main() != merged:
        raise UnsafeToPublish("Monthly main SHA differs after merge")
    shared.verify_merged_commit_parent(base, merged)
    for path in sorted(paths):
        if remote_bytes(path, merged) != Path(path).read_bytes():
            raise UnsafeToPublish("Monthly merged file differs from verified content")
    shared.wait_for_pages(merged)
    if summary:
        with Path(summary).open("a", encoding="utf-8") as out:
            out.write(f"Monthly Pages deployment succeeded for main SHA {merged}.\n")
    print(f"Monthly archive PR #{number} and Pages deployment succeeded.")


if __name__ == "__main__":
    try:
        if sys.argv[1:]:
            raise UnsafeToPublish("Unexpected monthly merge argument")
        publish()
    except (UnsafeToPublish, KeyError, OSError, TypeError,
            ValueError) as exc:
        print(f"Monthly publication failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
