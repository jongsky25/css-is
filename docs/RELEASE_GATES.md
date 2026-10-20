# Release gates — A10 step 4

## Checks implemented in code

`ci.yml` calls the shared `release-checks.yml` workflow for every pull request
and merge group. It uses read-only repository permissions and no production
secrets. It does not use `pull_request_target`.

The shared workflow checks:

- Python 3.11, with complete test dependencies, Node.js 24, and Chromium.
- The complete suite in normal order and shuffled order (seed 311).
- A nonempty JUnit report with no failures, errors, or skipped tests.
- A version greater than the base commit's version.
- Agreement between `APP_VERSION`, the first in-app changelog entry, the first
  Markdown changelog release, and the service-worker cache version.

The final **Required checks** job runs even when prerequisites fail or are skipped
and succeeds only when both metadata validation and the entire test matrix
succeed. Cancelled workflows cannot produce a successful gate.
JUnit results and resolved dependencies are retained as workflow artifacts
for 14 days, including after test failure.

`deploy-hf.yml` runs the same verification on the exact main commit before
the deployment job. Failed verification prevents the deployment job from
receiving production secrets or running the deployment script. Manual workflow
dispatch uses the same gates, is restricted to main, and compares versions to
the first parent. Push runs compare to the previous main commit.

The pre-deploy database backup, strict live-version guard, and post-deploy
live-version check remain enabled. The manual workflow's backup-bypass input
has been removed. The existing command-line deployment script is not a GitHub
authorization boundary; access to its production credentials must remain
restricted.

## Repository enforcement requires administrator configuration

Workflow files alone cannot prohibit a user from merging a failing pull request.
The current GitHub connector cannot administer branch protection; its protection
read returned HTTP 403, and its ruleset listing was empty. The local GitHub CLI
credential was also unavailable. **Required checks before merge are not yet
enforced by this implementation.**

After this PR's checks have run, a repository administrator must configure
Settings → Rules → Rulesets (or branch protection) for `main`:

1. Require a pull request before merging.
2. Require the check **verification / Required checks** from GitHub Actions.
   Use the exact context displayed on this PR if GitHub presents a different
   reusable-workflow prefix.
3. Require the branch to be up to date before merging, or use a merge queue.
4. Keep the rule active, with no routine bypass, and block force pushes and
   deletion of main.

Do not remove this limitation from the progress record until the repository
rule is confirmed active. Workflow edits can change the deployment gates, so
they must receive the same review as application code.

## Local commands

```bash
python scripts/check_release.py release --base origin/main
python -m pytest tests/test_release_checks.py
python -m pytest --junitxml=results.xml
python scripts/check_release.py junit results.xml
```

The base ref must identify the previous release, not the release being checked.
The JUnit command intentionally fails if Chromium or Node is absent and tests
skip. The metadata checker parses version assignments without executing either
the base or candidate Python file.
