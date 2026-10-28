# Offline acceptance audit

Run from the repository root with the locked test virtual environment. This
rechecks retained evidence; it starts no browser, profiler, GC or native probe.
Use separate extraction roots so each phase keeps its own artifact manifest.

```bash
mkdir -p /tmp/avatar-review-functional /tmp/avatar-review-runtime /tmp/avatar-review-matrix
unzip -q docs/avatars/completion/hosted-functional.zip -d /tmp/avatar-review-functional
tar -xzf docs/avatars/completion/hosted-runtime/avatar-review-runtime-1.tar.gz -C /tmp/avatar-review-runtime
unzip -q docs/avatars/completion/hosted-matrix.zip -d /tmp/avatar-review-matrix
.venv/bin/python docs/avatars/completion/audit_completion.py /tmp/avatar-review-functional completion-functional --out /tmp/functional-audit.json
.venv/bin/python docs/avatars/completion/audit_completion.py /tmp/avatar-review-runtime runtime --out /tmp/runtime-audit.json
.venv/bin/python docs/avatars/completion/audit_completion.py /tmp/avatar-review-matrix matrix --out /tmp/matrix-audit.json
```

Compare archive SHA-256 values against hosted-provenance.json before extraction.
The functional ZIP digest is also in hosted-functional-manifest.json. Runtime
trace bytes remain in the original hosted artifact until its stated expiry;
portable runtime evidence retains all 40 trace hashes and 20 numeric/visual files.
The audit explicitly reports that limitation. Matrix inputs retain all five
samples per source/group/scenario and all navigation checkpoints. No sample is
filtered or budget relaxed by this audit. Git history must include both sources.
