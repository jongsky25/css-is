# Standard hosted runner diagnostic — mobile workflow

The user has accepted evaluating a standard GitHub Linux x64 runner. This explicitly
supersedes the prior claim that only a physically reserved runner can be the next
environment. The data supports investigating contention; physical reservation is
not proven necessary. This is a new runner condition, not an assertion of isolation.

Use standard ubuntu-24.04 and the exact pinned Python trixie container; record actual
CPU topology/quota and GitHub run/ref provenance. Same exact Python/Playwright/Frida/
Chromium ELF and all original synthetic fixtures. No original-versus-candidate app
comparison, native probe calibration, 2B acceptance, deployment or paid runner setup.

Install pinned Debian Chromium packages and hash-locked dependencies. Reject missing
versions/build IDs rather than substituting. Failure logs remain downloadable.
Do not use actions/setup-python floating patches or Playwright browser downloads.
The existing collector executable path points by symlink to the installed ELF;
no source paths or fixture/census/query/phase semantics change.

Exactly four fresh uninjected controls with the frozen phase/CPU diagnostic. No
load-admission gate, extra warming, automatic retries, favorable replacement,
wall-time correction or relaxed gates. Context/identity traces and all failures
retained. A complete diagnostic only characterizes this runner. It cannot reverse
v12 or automatically qualify a later app comparison. Artifact upload runs on
failure; a plain job summary is available from a phone browser.

Because GitHub requires workflow_dispatch on the default branch, propose a small
registration PR containing only this workflow and phone instructions, checked out
from main. It checks out a fixed diagnostic commit on the verification branch;
it does not merge that branch's product/history into main. A path-restricted PR
trigger validates the workflow once before merge; subsequent manual runs require
default-branch registration. No automatic merge or deployment is part of this task.
