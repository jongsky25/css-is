# Correct cross-allocation qualification before any app workload

Attempt 1 (harness35f0d31/workflow6a4f391, run40516585623) passes setup/tests and
reproduces prior native qualification, but stops on an allocated CPU-model mismatch.
No fresh native proof or application workload starts. The complete failure artifact
and 78 internal manifest entries are retained. The initial helper rejected before
writing its current inventory: actual failed CPU model is unknown, not inferred.

The standard GitHub label does not guarantee the same CPU model for different
jobs. Do not retry until AMD EPYC7763 happens to appear or waive inherited cost
qualification for another model. Instead, qualify the actual allocated condition
in the SAME job before application calibration. Always save its inventory first.

Keep the retained prior-native artifact/source audit as provenance, and require
unchanged agent/toolchain. Then run the existing full hosted native qualification:
fresh selftest, fresh mixed receiver proof, fixed control/probe/probe/control, all
original gates and independent audit. If it fails, no application workload starts.
Verify this fresh qualification's CPU/inventory matches this job; then the frozen
real-app receiver proof and application four-slot schedule may proceed. Resource
models may differ from older jobs, but no app slot inherits timing qualification
from another allocation. There is no load-admission filter or favorable rerun.

Application source/workload/selection/observable/cost/stability/coverage/reclamation
rules from PROTOCOL.md remain unchanged. Preserve all raw native and app results.
This replaces only the cross-job CPU-equality prerequisite with stronger same-job
qualification, not a relaxed performance threshold. No app comparison/acceptance.

Close the superseded setup PR #515 and open a corrected workflow-only PR with an
opened-only trigger. Freeze the new source SHA first. Keep both attempt histories;
no Re-run jobs action or repeated unchanged sample is used. Bounded25-minute job,
scoped container SYS_PTRACE, read-only repo permissions and no app secrets remain.
