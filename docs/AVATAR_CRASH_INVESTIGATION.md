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
