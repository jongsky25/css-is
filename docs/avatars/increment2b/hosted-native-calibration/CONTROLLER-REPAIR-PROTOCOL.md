# Isolate one-shot native workflow before measurement

Initial setup branch commit 32c5797 incorrectly placed container options at job
level. GitHub did not launch a native job. Initial YAML is retained as
workflow-initial-invalid.yml; no native prerequisite or calibration sample exists
from that invalid definition. Correct options belong in container.image/options.

That push also retriggered the existing PR #511 control diagnostic because GitHub
PR path filters use the cumulative PR diff, not just the latest commit. Run
40508311821 is incidental and must be retained, never substituted for prior controls
or used to qualify the native instrument. No native calibration ran concurrently
in the same job; these are distinct VM jobs. The connected GitHub tools expose no
cancellation endpoint. No network-policy bypass or artificial failure was used to
suppress the incidental run.

Correction: PR #511 retains its completed control workflow but guards automatic
PR execution to its original validated SHA; manual dispatch remains available after
registration. Remove the invalid native workflow from that PR. Create a separate
main-based native setup PR with only the native workflow and phone guide. Its PR
trigger is opened-only, preventing later pushes from repeating native measurements.
Keep the original immutable native harness 0af68b8 and all proof/measurement gates.

The corrected native YAML has a container mapping with SYS_PTRACE scoped to the job;
read-only repository permission, no privileged/host-PID mode or app secrets. Validate
nested schema, opened-only trigger, exact checkout, failure-upload conditions and
all bash blocks before opening the new PR. Archive this correction and workflow
bytes before starting the single native attempt; all later results/failures remain.
