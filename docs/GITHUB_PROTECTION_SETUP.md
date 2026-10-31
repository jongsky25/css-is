# Main branch protection — setup step 3

## Latest observation — 2026-10-31 at 14:35 UTC

Ruleset [26274179](https://github.com/jongsky25/css-is/rules/26274179) is now
active for main, with no bypasses. PRs, the correct GitHub Actions check, resolved
review threads, deletion protection and force-push blocking are verified.
**One setting remains off:** require branches to be up to date before merging
(`strict_required_status_checks_policy: false`). Enable it and save; step 3
remains pending that final verification. The observations below describe the
initial state before the user created the rule.

## Verified state on 2026-10-31 at 14:15 UTC

**Enforcement is missing. Step 3 is pending an administrator action.**

Read-only checks against `jongsky25/css-is` returned:

| Check | Observed result |
| --- | --- |
| `GET /repos/jongsky25/css-is/branches/main` | `protected: false`; required status enforcement `off`; no required contexts |
| `GET /repos/jongsky25/css-is/rulesets` | Empty list |
| `GET /repos/jongsky25/css-is/rules/branches/main` through gh | Empty list |
| Classic branch-protection details | HTTP 403: Resource not accessible by integration |
| Required PR check identity | `verification / Required checks`, GitHub Actions app ID `15368` |

The empty active-rule listing and unprotected branch establish the gap; a 403
alone would only establish missing access. Both connector and terminal requests
use an integration without branch-administration access. Do not request or paste
personal tokens in chat to work around this.

Main was `aaef9d3da0ac5289ca79b1e458c249a404292ddf` (merged PR #570).
The latest five returned workflow runs all concluded success. Specifically:

- [PR CI run 41201937781](https://github.com/jongsky25/css-is/actions/runs/41201937781),
  attempt 2, head `657a668d9aa59a9cdcc0d83ad65c2e047ce3344f`: metadata,
  dependency audit, normal/shuffled suites, and aggregate Required checks succeeded.
- [Main deployment run 41206532759](https://github.com/jongsky25/css-is/actions/runs/41206532759),
  attempt 2, main commit above: the same verification jobs, deploy, and Telegram
  diagnostics succeeded. These are observed existing runs; no run was triggered
  during this setup step. Success on attempt 2 does not mean the first attempt passed.

This is evidence of working CI, not proof that failing PRs cannot be merged.

## Enable from your phone

Open [repository rulesets](https://github.com/jongsky25/css-is/settings/rules).
You must be signed in as an administrator. GitHub's mobile web page may require
your browser's **Desktop site** option to show all controls.

Use **New ruleset → New branch ruleset** and set:

1. Name: **Office Connect main release gate**. Enforcement: **Active**.
2. Target branch: **main**. Leave the bypass list empty.
3. Enable **Restrict deletions** and **Block force pushes**.
4. Enable **Require a pull request before merging**. Zero required approvals is
   intentional for a solo maintainer; checks remain mandatory. Enable resolution
   of review conversations. Do not require your own approval.
5. Enable **Require status checks to pass** and **Require branches to be up to date**.
   Select **verification / Required checks**, with **GitHub Actions** as its source.
6. Save the rule.

Alternatively, if GitHub offers **Import a ruleset**, import
[the prepared JSON](../.github/rulesets/main.json). It sets the same policy.
Merely committing this file does **not** apply it. Review imported settings and save.
There are no routine administrator bypasses in the prepared policy.

The rule prevents direct updates to main without a PR and passing current checks,
and blocks force pushes/deletion. It does not stop an administrator from changing
the rule itself or using separate production credentials outside GitHub.

## Verify after saving

Tell the agent **office connect** (with the setup repository/branch available).
It should re-read these live endpoints through the connector or `gh api`:

```bash
gh api repos/jongsky25/css-is/branches/main
gh api repos/jongsky25/css-is/rulesets
gh api repos/jongsky25/css-is/rules/branches/main
```

Read the saved ruleset's detail endpoint as well. Confirm active enforcement,
main targeting, empty bypass list, PR requirement, correct check/source, strict
up-to-date policy, deletion restriction and force-push blocking. Record the actual
ruleset ID and observation time in the status. If details remain inaccessible,
report the verification limitation instead of marking every setting verified.
Do not test the rule by pushing broken code to main or merging a PR.

Keep step 3 pending until observed settings match. This setup branch has no version
bump; the release gate will require a valid synchronized release version before
it can merge. Do not disable protection or weaken checks to merge setup files.
