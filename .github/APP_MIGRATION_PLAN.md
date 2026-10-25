# GitHub Appでの安全な自動イベントPR移行計画

**Status: design only. Do not enable or execute.**  
Project: Kazutake1/forum-calendar  
Tracking: GitHub Issue #27  
Reference main: c5283ad63bddcfaccb4e81cf3803eca22c09ad5d (re-fetch before execution)

## 1. Goals and invariants

The public GitHub Pages site should receive updates only from changes reviewed in a pull request with passing required CI. Preserve the current no-OCR parser, event identity/provenance contract, JSON formats, scheduled runs, monthly archival history, and unchanged UI/Service Worker.

**Do not activate a PR-required main Ruleset while either current writer still pushes directly to main.** The existing writers must remain operational until a reviewed, working alternative replaces both of them.

Current state:
- Daily writer: update-events.yml, cron 20 22 * * * (07:20 JST). Directly pushes ONLY events.json and update-meta.json. It validates new content and explicitly requests a Pages rebuild after a changed push.
- Monthly writer: monthly-manual-events.yml, cron 10 1 1 * * (first day 10:10 JST). Directly pushes manual_events.json, reports/manual-event-review.md, and archive/manual_events_YYYY.json. It runs pre/post-validation and a conditional Pages rebuild.
- Both writers use the forum-calendar-main-write concurrency group. Main currently has no protection or Ruleset.
- Current CI job name is **test** in the Calendar Integrity Tests workflow. Its PR checks include Python, JS/offline behavior and the official Jekyll 14-file manifest.
- GitHub repository itself is **public**: excluding archive from Pages does NOT conceal archive JSON committed to GitHub. Assess any private archival requirement separately.

## 2. App installation, permission boundary and credential ownership

Create a NEW app installed on **only Kazutake1/forum-calendar**, not on All repositories.

Repository permissions:
- Metadata: Read (automatic required baseline).
- Contents: Read and write (create only dedicated update branches and commits).
- Pull requests: Read and write (create/update PRs).
- Actions, Checks, Secrets, Administration, Workflows, Pages, Deployments: **No access** initially.
- Organization permissions: none. User authorization / personal access tokens: none.

App permissions alone do not stop direct main pushes. **Never add this App to a bypass list.** The main Ruleset must ultimately enforce PR review and CI. Do not grant Workflows write permission merely to enable the PR authoring.

Only the repository owner should configure:
1. Register the GitHub App using GitHub Developer Settings; enable the minimum repository permissions, then install into this single repository.
2. Store the App Client ID in an Actions **Variable** named FORUM_CALENDAR_APP_CLIENT_ID.
3. Store the private key exclusively in an Actions **Secret** named FORUM_CALENDAR_APP_PRIVATE_KEY.
4. Confirm the installation target and listed permissions using the GitHub settings UI. Share only whether configuration succeeded, never the key or token.

Never send the private key into an issue, PR, chat, commit, Pages output, Actions artifact or logs. Do not generate a key inside the codebase or keep plaintext keys in Downloads longer than necessary. Do not add a PAT, .env, or secret-bearing configuration file to the repository.

Implementation phase (NOT in this PR):
- Use audited actions/create-github-app-token pinned to a **verified full 40-character commit SHA**, never to a mutable tag.
- Pass Client ID through repository variables and private key through repository secrets; explicitly scope the installation token to the **current repository only** and to Contents write / Pull requests write.
- Installation tokens normally expire after one hour; keep default token revocation at job end. Do not set skip-token-revoke. Do not reuse token across jobs.
- For Git checkout, disable credential persistence; avoid token-bearing URLs, shell traces, echoed secrets, or dangerous workflow interpolation.
- Only mint a token from trusted scheduled/explicitly initiated default-branch writer jobs; never from fork pull_request jobs or arbitrary branch code.
- Reject missing/invalid secret configuration cleanly without modifying active event data.

References:
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app
- https://github.com/actions/create-github-app-token
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow

## 3. Proposed writer PR flow (not yet deployed)

1. Enter through existing trusted schedule or approved manual dispatch. Refresh main, acquire concurrency lock and evaluate previous run/PR state.
2. Obtain a short-lived one-repository App installation token. Create or safely reuse a non-main dedicated branch:
   - automation/daily/DATE-RUN-ID
   - automation/monthly/DATE-RUN-ID
3. Run existing update/archival operation with present validations. Re-read produced JSON files and compare counts, dates, duplicates, origin fields, archive year/ID consistency. Fail closed on empty, invalid, duplicate, untrusted or partial data.
4. Determine the complete diff, including status (add/update/delete/rename/symlink), and enforce kind-specific allowlists:
   - daily: events.json, update-meta.json
   - monthly: manual_events.json, reports/manual-event-review.md, archive/manual_events_YYYY.json
   Reject scripts, workflows, icons, website HTML/JS, verified_schedule.json, secrets, path traversal, cross-writer files or any unapproved changes. Validate the **contents**, not merely the names, before committing.
5. No diff: finish successfully without PR. Valid diff: commit on dedicated branch and open a Draft PR to main. GitHub App-created pull_request events trigger the existing CI without the GITHUB_TOKEN approval wait.
6. The latest PR commit must pass required CI, with exact head SHA/source verified on GitHub. Re-read PR diff from GitHub. A pass only makes PR eligible for **human review**; automated merge is not authorized.
7. A human confirms diff, provenance and completeness, then marks ready and merges. GitHub rules must enforce PR-required and the GitHub Actions **test** check. Confirm that the actual status check name and provider selected in the UI are correct.
8. Confirm that Pages publishes 13 exact PWA assets and one generated theme CSS file, that no archive/source code leaks into Pages, and that event counts/metadata match.

**Never assume local policy checks equal GitHub enforcement.** Draft PR #31 only tests synthetic metadata and does NOT implement GitHub App API calls or protected-branch checks. GITHUB_TOKEN-created PRs can require manually approving CI; installation tokens avoid that limitation but must be tested.

## 4. Rollout gates (strict order)

- A. Review this document and Draft PR #31. Keep both unmerged pending review.
- B. Repository owner confirms whether PRs require human review (default recommended: YES); confirm current allowed Apps, Secrets permissions, Pages branch source and repo protection capabilities. Do not guess any unreadable settings.
- C. Owner creates/installs App and saves credentials in GitHub UI. No credential values passed to any assistant.
- D. Add a separate test-only workflow in a future **Draft PR**, running trusted code with purely synthetic data in a test branch. Confirm App token -> dedicated branch -> Draft PR -> GitHub CI success. Do NOT merge synthetic data or write active events.
- E. Design/implement **both** writer migrations in isolated Draft PRs. Validate no-OCR and archive preservation, all paths, no-change behavior, concurrency, retry, GitHub Pages output and error recovery. Do not switch just one writer while enabling main protection.
- F. Switch to PR-only writers only after owner review and proof that both writers can create PRs with passing CI. If there is a manual approval requirement, acknowledge that **data acquisition can be automatic but publication waits for approval**.
- G. Only then enable main protection using Settings > Rules > Rulesets: target main; Require a pull request; Require status check **test** with the expected GitHub Actions source; Block force pushes; Restrict deletions. Start with Disabled or Evaluate (if offered) to inspect before Active. No App bypass.
- H. Confirm blocked direct pushes, correct PR/CI merge behavior, successful normal daily and first monthly runs, correct Pages artifact, preserved archive and all event sources.

## 5. Fail-closed and rollback

Immediate stop conditions: key/token appears in logs or committed files; App installed on unintended repositories; CI is absent/pending/untrusted; base or head SHA drift; branch or path allowlist mismatch; unreviewed auto-merge; event loss or changed formats; a scheduled update fails; Pages publishes unexpected files.

Revoke/rotate compromised keys and uninstall/suspend the App as needed. Do not discard the current event/archived data. Record failing run IDs and retain recovery copies. Reverting to the old direct-main-push writer while Ruleset is Active will fail; changes to the Ruleset or rollback of writers must be consciously reviewed, coordinated and approved. No emergency force push or blanket bypass.

## 6. Verified versus not verified

Verified: existing main CI and 14-file Pages output, previous PR #31 synthetic policy tests, ordinary Draft PR CI trigger, and current cron/writer flow.

Not verified: App registration or key storage; App token generation; PR creation by App; approval workflow with protected main; Ruleset enforcement; automatic merging; a controlled failed-PR rollback; new deployment after rollout.

**This is a proposed operational design. It does not run, configure, or authorize an App, change Rulesets, or switch production writer workflows.**
