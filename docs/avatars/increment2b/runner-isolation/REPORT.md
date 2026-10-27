# Runner isolation: infrastructure blocker confirmed

**No supported isolation intervention is available from this session.** We have
completed the current runtime/control inventory and prepared a concrete
[runner handoff](RUNNER_REQUIREMENTS.md). Continuing requires an externally
configured reserved runner or a supported environment capacity/isolation action.
No new benchmark or qualification sample was collected. **2B remains blocked.**

## Observed capability

Frozen read-only inventory **ccb4365**, with
[runtime results](runtime-inventory.json) and
[provider/tool capabilities](provider-capabilities.json):

| Observation | Result | Meaning/limit |
| --- | --- | --- |
| CPU virtualization | KVM full virtualization; five visible CPUs | Guest topology does not attest host reservation |
| Current affinity / effective cpuset | 0–4 | Selection within guest, not exclusive physical CPUs |
| CPU quota | 400000 per 100000 microseconds | Four CPU seconds per second |
| Exclusive cpuset / partition | Empty / member | No exclusive guest cpuset is reported |
| CPU/cpuset controls | Not writable by current uid 1000 | Observed permissions; no write attempted |
| Cgroup mount | cgroup2, mount reports rw | Mount flag does not override per-file permissions |
| Connected runtime status | Current, running, provider cloud; capabilities empty | Connectivity/readiness only; no reservation details |
| Connected runtime actions | Status and network diagnostics only | No capacity, reservation, migration or environment configuration action |
| Existing avatar workflow labels | ubuntu-24.04; completed workflows disabled | Neither a label nor disabled workflow proves reserved capacity |
| GitHub runner inventory | Read-only request denied: Forbidden | Runner alternatives unknown, not established absent |

[Capability assessment](capability-assessment.json) preserves exact workflow source
hashes and runner labels, installed versions, frozen commit identity and the denied
GET request. No network-policy workaround, unrelated hosting service, paid resource,
process affinity change or privilege escalation was attempted.

The runtime's cumulative quota counters have advanced since the previous task;
this inventory is not a time-bracketed workload, so it does **not** attribute those
changes to prior control measurements. The prior phase diagnostic continues to
show no throttle increments in its recorded operation brackets. No new CPU-steal
sampling or favorable-window admission test was performed here.

## What is and is not established

The earlier control timing diagnostic observes navigation/serialization stalls
with 31.03/38.74% aggregate CPU steal in its slowest first document. This supports
investigating virtual-host contention. The current inventory adds concrete evidence
that this user cannot change the relevant local controls and that the available
provider tools cannot request a host-level intervention. It cannot identify the
physical-host scheduling policy, prove exclusive causation, or provision isolation.

A fresh container or `taskset` could not establish physical-host reservation, even
if available. Increasing guest quota would be a different resource condition and
would not itself remove hypervisor steal. We did not silently substitute either
for the intended intervention.

There is **no further local diagnostic prerequisite to repeat unchanged**. The
missing input is actual runner capacity/access with documented isolation scope.
[RUNNER_REQUIREMENTS.md](RUNNER_REQUIREMENTS.md) specifies exact browser/toolchain,
resource provenance, permissions, paths, and resume order. A supported environment
configuration workflow may require its own review, but none is callable here;
this is a capability blocker rather than an unanswered approval request.

## Validation and status

The read-only inventory command completed successfully. Its SHA256 matches the
script frozen in ccb4365; the evidence manifest covers raw inventories and source.
The prior **97 focused tests** remain the latest test run; no workload/test changes
requiring another run were made in this inventory task. Product files remain
byte-identical to cf363bf. No measurement, environment mutation, CI dispatch,
application comparison, merge, deployment or later increment was started.

C recorder v12 retains passing cost/reclamation probes and its failed **20.7568%
control variation >20%**. Instrument/application qualification and 2B acceptance
stay false. Do not retry until a quiet period occurs, exclude slow samples,
subtract scheduling time or loosen budgets. Resume only after a concrete new
runner condition is documented and its complete capture protocol is frozen.
