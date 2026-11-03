# Native avatar acceptance crash — November 3, 2026

Investigated the recurring failure on [PR #572](https://github.com/jongsky25/css-is/pull/572).
[Run 41600573915](https://github.com/jongsky25/css-is/actions/runs/41600573915)
on `c14c20526139ce02a27abecf7aa953ce9e1d6e3e` finished with 131 passes
and one failure: `test_native_visibility_and_touch`, line 56, reports
`Page.evaluate: Target crashed` querying profile animations after navigation to
`/me`. Earlier heads `df55759` and `3dc7600` record the same symptom in the PR.
The latest run is completed/failed, not queued.

The avatar JS, templates and avatar tests are unchanged between current main
`25fe812` and this PR head. The acceptance workflow changed from Debian Chromium
to the browser revision selected by the hashed Playwright lock. A renderer crash
is not a JavaScript exception; the expression's location does not establish that
the expression caused it.

The native test starts Chromium directly and discards stderr. Unlike normal
Playwright launch, it supplies only headless, no-sandbox, debugging-port and
profile arguments. Container shared-memory exhaustion is a hypothesis, not an
established cause. This workspace has 8.8 GiB shared memory; CI capacity was not
recorded. Artifact download returned HTTP 403. No OOM, signal or browser-native
failure diagnostic has yet been observed.

Unchanged native test on isolated Python 3.11/system Chromium 154.0.8037.57:
**1 passed in 69.78 seconds**, no skips; strict JUnit gate passed. The first
wrapper invocation skipped because it strips opt-in variables and is not pass
evidence. The rerun injected only test opt-ins into the wrapper's sanitized child
environment, preserving temporary databases and disabled schedulers.

With diagnostic capture and the CI-locked Google Chrome for Testing
151.0.7922.34, the same native test also passed: **1 passed in 68.74 seconds**,
no skips; strict JUnit gate passed. This narrows the problem to conditions not
reproduced locally, such as container resources or preceding suite activity;
it does not establish which condition causes it. Diagnostics were written and
browser stderr preserved successfully. Both local runs used the main avatar
source, which matches the failing PR; they did not execute its full preceding
131-test sequence or its Python 3.12 container.

The investigation branch adds native Chromium version, `/dev/shm` and `/tmp`
capacity, and stderr to the existing avatar artifact directory. It changes no
assertion, timeout, visibility emulation, browser flag, application code or gate.
Next: run acceptance on the failing PR head with these diagnostics, distinguish
resource exhaustion from a Chromium regression, then verify any proposed remedy
with the complete avatar gate. Local success is not hosted acceptance. No merge,
deployment or production data access is authorized by this investigation.

## Hosted diagnostic comparison

On candidate `c31fc95`, diagnostic head `58c82da` reproduced the same failure
after 131 passes in [run 41606656187](https://github.com/jongsky25/css-is/actions/runs/41606656187).
Chromium was 151.0.7922.34. The container had 67,108,864 bytes (64 MiB) of
shared memory, initially empty; `/tmp` had 88,688,689,152 bytes available.
Cgroup memory events reported zero `oom` and `oom_kill`, with a peak of
2,894,008,320 bytes and no cgroup memory limit. Stderr captured Crashpad activity
at the failure, but no explicit cause. This rules out a recorded cgroup OOM kill,
not every possible memory failure.

Comparison head `e7bea14` changes only the job container's shared-memory size
to 1 GiB, leaving the exact image, browser, tests, timing and native tab flags
unchanged. Diagnostics remain in the existing artifact and workflow log.

## Verified resolution

[Run 41607212977](https://github.com/jongsky25/css-is/actions/runs/41607212977)
passed on exact head `e7bea14f9f23919ed1ac39ca3b5aa6b17d3a2d84`:

- 137 interaction/frame tests passed in 278.15 seconds; strict JUnit gate
  confirmed no failures or skips, including the native visibility/touch test.
- 432 real rig/stage/mood/theme cases passed.
- Six themed contact sheets rendered, containing 1,170 cards.
- Captured shared-memory capacity was 1,073,741,824 bytes; no cgroup OOM kills.

The one-variable hosted comparison supports insufficient container shared-memory
capacity as the operational cause and verifies provisioning 1 GiB as the remedy.
The precise native Chromium allocation/signal was not captured; no stronger
browser-internal diagnosis is claimed. No test assertion, browser flag, timeout,
rendered content, application code or acceptance gate was weakened.

The verified head was fast-forwarded into PR #572's feature branch after checking
that it still pointed at `c31fc95`; the remote accepted the fast-forward.
PR head was independently read back as `e7bea14`. Its usual full release CI
is separate from this completed exact-head avatar workflow; do not infer that
the entire release is ready from avatar acceptance. No main merge or deployment.
This final evidence is saved on `docs/avatar-crash-resolution` so it does not
change the tested PR source merely to record its result.
