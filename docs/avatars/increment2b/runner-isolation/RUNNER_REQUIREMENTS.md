# Concrete handoff for an isolated measurement runner

**Superseded runner choice:** the user has since accepted evaluating a standard
GitHub Linux x64 runner from a phone. Physical reservation was not proved necessary.
Use [mobile runner setup](../mobile-runner/README.md) and PR #511; this inventory
remains evidence about the original managed host, not an active reserved-only gate.

Current task is blocked on **runner access/capacity**, not another application
approval. This session cannot allocate, migrate or reserve its managed host. The
connected runtime API exposes only status/network diagnostics; repository runner
discovery was denied. Repeating this inventory or the failed v12 screen will not
remove that blocker.

Provide an existing reserved Linux x86-64 runner, or configure this task's host via
its supported environment configuration UI/workflow. The provider/operator must
supply evidence of the reservation/isolation scope and actual CPU scheduling
policy. An affinity mask, guest cpuset, larger runner label, fresh container or
unverified assertion of isolation is insufficient to establish host reservation.
Retain this evidence with the runner configuration; do not invent it in a script.

## Runner contract

1. Checkout `jongsky25/css-is`, branch `codex/avatar-2b-verification`, with full Git
   history. Use latest report HEAD; do not reset to old harness commits or promote
   candidate cd94bf3. Product sources stay byte-identical to cf363bf.
2. Record actual old/new CPU model/topology, guest-visible CPUs, cgroup quota,
   affinity, physical-host reservation scope and other permitted workloads. Current
   environment: KVM, five visible CPUs, four-CPU quota. Any differences are a new
   runner condition and limit comparisons to historical absolute timings. New
   within-run comparisons retain the original gates and complete fixed schedules.
3. Use Python 3.12.14; install the repository's hash-locked requirements-test.txt
   in `.venv`. Pinned Playwright is 1.62.0; diagnostic Frida is 17.5.1. No silent
   runtime/dependency upgrade. Preserve installed versions and package identities.
4. Supply Chromium **156.0.8078.47**, native ELF build ID
   **1c5dca8527a61d07372e489142bee26af1bcaf71**, with its matching runtime libraries.
   Existing collector expects executable at
   `/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium`. Preserve that
   path or explicitly freeze an audited path-only harness revision before use.
   Native proof offsets are specific to this build; a different browser is invalid.
5. Permit loopback HTTP and ordinary Chromium process launches; provide readable
   process stat/schedstat and cgroup counters. Frida must be able to attach to this
   task's own renderer when the separately authorized calibration reaches that
   step. No application account, DB, user data or production secrets are needed.
6. Run only the predeclared process schedule with no concurrent build/analysis jobs.
   Record CPU-steal/cgroup context and missing telemetry without turning it into a
   post-hoc filter, quiet-window retry loop or corrected-duration calculation.

## Resume after the external runner condition exists

First save the read-only configuration inventory:

```sh
.venv/bin/python -m scripts.avatar_baseline.runner_isolation_inventory \
  --out /tmp/runner-isolation-inventory.json
readelf -n /workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium
```

Review inventory alongside the provider/operator reservation evidence. The script
always reports `isolation_established:false` because guest observations cannot
attest physical-host reservation. Do not change that flag merely to pass a gate.
No new performance run is authorized by a low-steal snapshot alone.

Then freeze the intervention, exact resource comparison, full four-slot schedule
and contextual capture policy before running. Preserve original comparisons and
every failed slot. Begin with the separate control phase diagnostic to characterize
the **new condition**; require full recorder calibration before any application
memory comparisons. No acceptance thresholds, receiver counts or fixtures change.
Do not dispatch the existing disabled CI workflows or reuse standard ubuntu-24.04
labels as evidence that the necessary host isolation exists.
