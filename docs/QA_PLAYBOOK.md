# Autonomous QA Playbook — CSS Information System
**Purpose:** a self-contained runbook for an *unattended* QA run that tests the build,
fixes what it safely can, and leaves a clear trail — designed for a more capable model
to execute end-to-end with no human in the loop. Carries forward the standing directive:
**fix everything found (incl. architectural), code + data fixes allowed, every change
backed up + regression-guarded, the delivered `css_is.db` never edited in place.**

This version is rewritten around the two hard lessons of the first pass.

---

## 0. The three lessons that reshape everything

**Lesson 1 — the working folder is an unreliable, eventually-consistent mount.**
- Large files get **silently truncated on write** (overflow dropped). This produced the
  P0 outages (app.py, activities.html) and recurred on a *newer* codebase between QA turns.
- The folder also **re-syncs from the Windows host**, which can overwrite in-session edits
  and can present files **mid-stream / truncated** for several seconds.
- The in-folder `.git` is an **empty skeleton** — there is no real rollback there.

**Lesson 2 — the execution sandbox has hard limits.**
- Shell calls are killed at **~45 seconds**; **background processes do not survive** a call.
- Bytecode caching on the mount is unreliable (set `PYTHONPYCACHEPREFIX` to a tmp dir).

**Lesson 3 — the Linux sandbox can hand Python *corrupted copies* of large files (the
blocker that stopped the 2026-06-11 run).** Files above ~20 KB (e.g. `app.py`, `storage.py`,
`dashboard_export.py`, `harmonize.py`) and the 15 MB `css_is.db` came through the bash mount
**truncated / internally inconsistent**, while the **file-reader tool (a different access path)
showed the same files complete and well-formed.** Tell-tales: identical byte size across reads
but different content/line-counts; `PRAGMA integrity_check` = "malformed" on a DB that is fine
on disk; small files read perfectly while large ones don't; re-reading never converges.
**This is an environment fault, not a code defect — and it is invisible unless you test for it.**
Consequences baked into this plan:
- **Run QA where files read faithfully.** For a codebase this size, prefer **native execution
  (Claude Code on Windows / the host)** over the Cowork Linux sandbox. The sandbox is only
  trustworthy for small files.
- **Never repair or sync a file whose "corruption" you've only seen in the sandbox.** Confirm
  on-disk truth via the faithful reader first; if the reader shows it intact, the sandbox is
  lying — change nothing.

Everything below is built so a run cannot be silently defeated by any of the three.

---

## 1. Operating principles (non-negotiable)

> **Execution contract.** When the user says "execute," active coding STOPS — the codebase is
> **frozen**. There is no work-in-progress. The frozen snapshot is the authoritative build and
> **every feature is expected to work.** Anything that is broken, truncated, non-importable, or
> functionally wrong is therefore a **defect to fix**, not WIP to scope around. The run does not
> finish until every feature works and the user can run it locally (§7.1, §8).

1. **Never edit files in the live mount.** Snapshot the folder to a stable working copy on
   the native FS (`outputs/qa_work/`), do ALL editing/testing there, and sync back only at
   the very end, after the preflight gate passes on the working copy.
2. **Gate before and after.** Run `qa_preflight.py` *first* (abort functional QA if RED) and
   *again* on the working copy *before* syncing back. A build that fails preflight is never
   shipped.
3. **Edit large files via shell only** (heredoc / Python rewrite). Never use overflow-prone
   in-app file editors on files > ~200 lines.
4. **Snapshot-and-settle.** On start, read each key file twice ~3s apart; if size/mtime is
   still changing, a host sync is in flight — wait and re-read until stable before trusting it.
5. **Chunk every long job.** No single shell call may rely on >40s. Use the resumable journal
   (§5) and the fast-subset env knobs so each step finishes inside the budget.
6. **Backup before every mutation.** Timestamped copy into `_backups/qa_<TS>/` (code) and a
   DB copy into `outputs/_qa_backups/` (data). `css_is.db` is touched only on a copy.
7. **Decide, don't ask.** Use the fix-policy decision tree (§6). Log the decision; keep going.

---

## 2. Run protocol (top to bottom)

```
STEP 0  ENV-FITNESS CHECK      -> can THIS environment read the codebase + DB faithfully?
                                  cross-check bash reads vs the file-reader on the largest
                                  files; sqlite integrity_check the DB; import app. MISMATCH =>
                                  sandbox is corrupting files: STOP, do not test/fix here, hand
                                  off to native (Windows) execution. (See §2.0.)
STEP A  SCOPE + update-detect  -> inventory modules/routes/schema; diff vs last QA manifest;
                                  classify WIP vs defect; snapshot to outputs/qa_work/ + settle
STEP B  Preflight GATE         -> qa_preflight.py   (RED => first ask: corruption or defect?
                                  cross-check via reader (§2.0); fix ONLY confirmed on-disk defects)
STEP C  Static analysis        -> compile, lint, dead-import, secret scan
STEP D  Unit/contract tests    -> engine scoring, storage CRUD, auth token logic
STEP E  HTTP/route + render    -> every route, authorized + unauthorized
STEP F  Auth & RBAC matrix     -> 4 roles x every gated route; sessions; reset/invite tokens
STEP G  Input/abuse + security -> hostile POSTs, XSS, CSRF, injection, cookie flags, rate
STEP H  Data integrity         -> orphans, FKs, unique tokens, audit hash-chain, counts
STEP I  Exports + fidelity     -> all 6 formats; content sanity, not just "no exception"
STEP J  Concurrency + perf     -> threaded requests, SQLite locking/WAL, full-volume timings
STEP K  Subsystem deep-dives   -> migrate idempotency, harmonize undo round-trip,
                                  backups.py backup/restore, monitoring.py, retention.py
STEP L  Synthetic-data pass    -> seed the missing scenarios (§4) and re-run E–I against them
STEP M  Triage + fix           -> apply per §6, regression-guard after EACH change
STEP N  Re-gate + sync back    -> preflight GREEN on working copy => copy code back to folder
STEP O  Deliver                -> findings report, updated logs, green test run, journal
STEP P  LOCAL-RUN handoff      -> boot the app on a copy, confirm it serves; write LOCAL_RUN.md
                                  so the user can launch and try it on their own machine
```

Each step writes its result to the journal (§5) the instant it finishes, so an interrupted
run resumes at the next unfinished step instead of restarting.

---

## 2.0  STEP 0 — Environment-fitness check (DO THIS BEFORE ANYTHING ELSE)

The 2026-06-11 run was defeated because it scoped, gated, and tried to fix a build the sandbox
**could not read correctly.** Never again: the very first action proves the environment can see
the code faithfully, and refuses to proceed (or fix) if it can't.

1. **Pick the largest 3–4 source files + the DB** as canaries (e.g. `app.py`, `storage.py`,
   `dashboard_insights.py`, `dashboard_export.py`, `css_is.db`).
2. **Faithful-read cross-check.** Read each canary two ways: (a) via the shell/Python where tests
   run, and (b) via the **file-reader tool** (the authoritative on-disk view). Compare line count,
   last line, and a hash of a late slice. They must **agree**.
3. **DB check.** `PRAGMA integrity_check` on a copy of `css_is.db` must return `ok`.
4. **Import check.** `import app` must succeed.
5. **Verdict:**
   - **All agree + DB ok + import ok →** environment is fit; proceed to STEP A.
   - **Reader shows a file intact but the test environment shows it broken (or DB "malformed") →**
     the **sandbox is corrupting files in transit.** Do **NOT** scope, test, "repair", or sync
     anything. Emit a short status note (what's corrupted, proof, that the code is intact) and
     **hand off to native execution** (run the same `qa_preflight.py` + suite on Windows/Claude
     Code, where there is no mount in between). Re-attempt in-sandbox only after a clean
     ENV-CHECK (e.g. user reconnects the folder).
   - **Reader AND test env agree a file is broken →** that's a *real* defect; treat it per the
     normal flow once the build is otherwise readable.

This check is cheap (seconds) and is the single highest-value addition to the plan: it converts
"silently test garbage / risk overwriting good code" into "detect, stop, route to where it works."

## 2.1  STEP A in detail — Scope the system & check for updates (ALWAYS FIRST)

Development on this codebase is **ongoing**, so a run must never assume it is looking at the
same system the last run saw. Before any testing, build a fresh picture and diff it against
history:

1. **Inventory.** Enumerate every `*.py` and template; record line counts, mtimes, and a hash
   of each. Extract the live **route table** (`for r in app.app.routes`), the **DB schema**
   (`sqlite_master` + `PRAGMA table_info`), and the **module import graph** (which is the only
   reliable way to discover new modules — e.g. `import backups as bk` revealed `backups.py`).
2. **Diff against the last manifest.** Persist the inventory as `outputs/qa_manifest.json` each
   run. On the next run, compute: **new** modules/routes/tables, **removed** ones, and
   **changed** ones (hash differs). New surface (e.g. `backups.py`, `monitoring.py`,
   `retention.py`, `import_csm_blhsd.py`) gets its own dedicated test step — untested code is
   the highest-risk code.
3. **Confirm the freeze, then treat everything broken as a defect.** Coding has stopped, so the
   snapshot is final. Do a one-time **settle check** at kickoff only to be sure no stray sync is
   still landing: re-read the key files twice ~3s apart; if anything is still changing, wait until
   it stops, take the snapshot, and proceed. After that:
   - The snapshot is **authoritative and frozen** — there is no "leave it alone, it's WIP."
   - Any file that does not compile/import, any route that 500s, any feature that doesn't work →
     **DEFECT → fix it** (per the §6 policy), back it up, regression-guard, and continue.
   - Truncation/corruption is repaired from the most complete available source (snapshot/backup),
     then re-gated. A frozen build that won't import is the run's **first** fix, not a pause.
4. **Make the frozen build green, then test it.** The target is the frozen snapshot. If it
   doesn't import, **fixing it to a coherent, importable state is step one of the work** (not a
   reason to defer). Only once it imports cleanly and preflight is GREEN does functional testing
   begin — but reaching that GREEN state is in-scope and expected.
5. **Record the scope** in the journal: system summary, module/route/table counts, the
   new-since-last-run list, and which target snapshot was chosen. Everything downstream is scoped
   to what was actually found, not to assumptions.

**Coordination note:** the run begins only after the user says "execute," at which point coding has
stopped and the build is frozen. The run therefore owns making that frozen build fully working —
scoping is to *understand and inventory* the system (and catch new modules), not to excuse leaving
any broken feature in place.

---

## 3. Test layers — what to ADD beyond the first pass

The first pass covered routes, RBAC, input-abuse, integrity, and one perf check. A
*comprehensive* run adds:

- **Static & hygiene:** `python -m py_compile` all modules; `ruff`/`pyflakes` if available;
  detect imports of modules that don't exist (this would have flagged `backups`/`monitoring`
  early); scan for hard-coded secrets/keys; confirm every `import X` resolves.
- **Security (beyond input-abuse):**
  - **Template XSS** — confirm Jinja autoescape is on and that user-supplied strings
    (remarks, names, topics, verbatims) render escaped on every page that shows them.
  - **CSRF** — state-changing POSTs rely only on a signed cookie; assess whether a
    same-site/origin check or token is needed for the LAN threat model; recommend or add.
  - **Auth edges** — login throttling/lockout, session fixation, `httponly`/`samesite`/
    `Secure` cookie flags, logout invalidation, action-token replay.
  - **Injection** — parametrized-query audit across `storage.py` (no f-string SQL with user
    data); path traversal on `/photo/{id}` and any file route; SSRF on QR/base-url handling.
- **Concurrency & durability:** fire N concurrent requests (incl. writes) to surface SQLite
  `database is locked`; evaluate WAL mode; verify the in-process atoms cache + `_view_memo`
  invalidation is correct under interleaved reads/writes.
- **Audit-log integrity:** verify the hash-chain (`prev_hash`/`row_hash`) is unbroken and
  tamper-evident end-to-end.
- **Backup/restore (new `backups.py`):** create → list → restore → delete round-trip on a
  copy; confirm restore yields a byte/row-identical DB and that delete is gated by `wipe`.
- **Migration & harmonize:** re-run `verify_migration.py`; prove `harmonize` apply+undo is an
  exact round-trip with zero responses lost (regression-guard the destructive paths).
- **Export fidelity:** open each xlsx/pptx/pdf/csv and assert it contains the expected
  sheets/slides/headers and non-empty data — not merely that export didn't throw.
- **HTML/markup validity & error paths:** every 4xx/5xx path renders a proper page (no raw
  tracebacks leaked); 404/403/closed-window pages are correct.

---

## 4. Synthetic-data fixtures (close the coverage gaps)

Real `css_is.db` has only survey types 2 & 3, no external events, and no walk-in-only /
"both" people — so those code paths ship untested. The run must build a small **synthetic
DB** (a seeded copy, never the real one) containing at least: one Type-1 walk-in form with
responses; one external (outside) event; one person who is *both* a speaker and a walk-in
server; one person who is walk-in-only; an empty-scope (no data) case; and a unicode/RTL/
very-long-string stress record. Re-run the HTTP, export, and integrity layers against this
DB so every type-specific branch is exercised at least once.

---

## 5. Resumable journal (survives the 45s/no-background limits)

Maintain `outputs/qa_work/QA_JOURNAL.jsonl` — one line per step: `{step, status, started,
finished, findings:[...], fixes:[...], guard:"smoke=pass"}`. Rules:
- Append the result **the moment a step finishes** (calls die at 45s; never hold state in RAM
  across calls).
- On (re)start, read the journal and **resume at the first step not marked done**.
- Long suites run as **fast subsets first** (`QA_SAMPLE=1 QA_FORMATS=png,csv`) as the
  per-change guard; the **full** matrix runs once at the end (it has no 45s limit on the
  user's own machine, so note "full run: user-side" if it can't finish in-session).
- Split any suite that won't fit: run pytest **per file** with `timeout 40`, record each.

---

## 6. Autonomous fix policy (decision tree — no human needed)

For each finding, classify and act:

- **AUTO-FIX (apply immediately, then regression-guard):** syntax/truncation repair; missing
  import or helper; a route/template that 500s; off-by-one/validation bug; a test-provable
  logic error; a clearly-safe perf rewrite that is *proven numerically identical*.
- **FIX-WITH-GUARD (apply, but isolate + prove):** anything touching scoring math, the DB
  schema, or destructive ops — make a backup, apply, and prove exact-equivalence / round-trip
  before keeping it; otherwise revert and downgrade to FLAG.
- **FLAG-ONLY (do not change; document with severity + repro + suggested patch):** product/
  policy decisions (e.g. enabling `Secure` cookies, adding CSRF tokens, WAL mode), anything
  that changes user-visible behavior or external contracts, or any fix that can't be proven
  safe unattended.
- **NEVER reconstruct/overwrite from a corrupted read.** Before repairing any "truncated" file,
  confirm it is broken **on disk** via the faithful reader (§2.0). If the reader shows it intact,
  the breakage is an environment artifact — **change nothing, sync nothing**; a write-back would
  overwrite good code with a guess.
- **Always:** after every applied change, run the fast guard (preflight + subset pytest +
  subset smoke). If a guard regresses, **revert that change** and reclassify to FLAG.

---

## 7. Rollback & safety

- Code originals: `_backups/qa_<TS>/` (mirror the tree; keep `.orig` copies).
- Data: pre-QA `css_is.db` copy in `outputs/_qa_backups/`; the delivered DB is never edited
  in place — work on a copy and sync back only a DB that passes integrity + smoke.
- Sync-back is the **last** action and only if preflight is GREEN on the working copy. After
  sync, **re-read from the folder and re-run preflight** to confirm the mount didn't truncate
  on write (it has before). If it did, rewrite via shell and re-verify; loop until clean.
- Recommend (for the user, host-side): `git init` + commit a known-good baseline so there is a
  real rollback point outside the mount.

---

## 7.1  STEP P — Local-run handoff (the run MUST end here)

The goal line is not "tests pass" — it is **the user can start the system on their own local
hosting and click around.** Every run ends by guaranteeing and documenting that.

1. **Boot verification (in-session, on a copy).** Launch the real server against a *copy* of the
   DB and confirm it actually serves:
   `PYTHONPYCACHEPREFIX=/tmp/pc python -m uvicorn app:app --port 8011` (in the background for a
   few seconds), then GET `/login` and 2–3 core pages and assert HTTP 200. This proves the build
   boots, not just that it imports.
   - **Environment caveat (known):** inside the Cowork mount the live app **cannot** keep its
     SQLite DB in the mounted folder (the mount blocks the journal delete every write needs). So
     boot-test against a DB copy on the native FS. **On the user's Windows host this restriction
     does not exist** — the app runs normally with `css_is.db` in place. State this explicitly.
2. **Dependency manifest.** Emit/refresh `requirements.txt` (fastapi, starlette, jinja2, qrcode,
   pandas, matplotlib, openpyxl, python-pptx, uvicorn, + anything new modules pull in) so the
   user can `pip install -r requirements.txt` cleanly.
3. **Write `LOCAL_RUN.md`** — copy-paste instructions for their machine:
   - install deps;
   - launch: `python -m uvicorn app:app --reload --port 8000`;
   - open `http://localhost:8000`;
   - **first-run:** the DB ships with 0 admin users, so the first login screen creates the first
     admin (enter the email + a password ≥ 8 chars) — document this;
   - how to point at their real `css_is.db`, and how to roll back (the `_backups/qa_<TS>/` copies);
   - the LAN/QR note: respondents scan a QR that encodes `http://<LAN-IP>:8000/r/<token>`, so the
     host must be reachable on the office Wi-Fi (set `CSS_BASE_URL` if needed).
4. **Final gate.** Re-run `qa_preflight.py` against the folder after sync-back; only declare done
   when it is GREEN and the boot test served 200s. If the mount truncated on write-back, rewrite
   via shell and repeat.

---

## 8. Definition of done

- `qa_preflight.py` GREEN on the folder (re-read after sync-back).
- Full pytest suite green (or green in per-file chunks); full export smoke green
  (in-session subset + a note that the unrestricted full run is user-side if needed).
- `css_is.db` integrity ok, 0 orphans, unique tokens, audit chain intact, counts plausible.
- **Every feature works.** Each route/feature (incl. new modules like backups/monitoring/
  retention/import) was exercised and behaves correctly — not just "imports" or "returns 200".
  Defects found are **fixed-and-guarded**; only genuine product/policy choices are flagged.
- Deliverables present: dated findings report, updated `CHANGELOG`/`IMPROVEMENT_LOG`/
  `RUN_SUMMARY`, the `QA_JOURNAL.jsonl`, and a one-paragraph "read this first" summary.
- **The user can run it locally:** the app boot-served HTTP 200 on a copy in-session, a fresh
  `requirements.txt` exists, and `LOCAL_RUN.md` gives copy-paste launch + first-run + rollback
  steps. This is the terminal acceptance criterion — the run is not done until it is met.

---

## 9. First actions for the next run (concrete)

1. **ENV-FITNESS CHECK first (§2.0).** Cross-check the largest files + the DB between the test
   environment and the file-reader. If they disagree, the sandbox is corrupting files — **stop and
   run on native Windows / Claude Code** (no mount in between), where `qa_preflight.py` and the
   suite read the real code. Do not test or fix anything in a sandbox that fails this check.
2. **Prefer native execution for this codebase.** It's large enough that the Cowork Linux sandbox
   is unreliable; the Windows host reads it faithfully. Run the QA where ENV-CHECK is clean.
3. **Then get the frozen build green.** `python qa_preflight.py` → if RED, decide *corruption vs
   defect* (§2.0); repair only confirmed on-disk defects from the most complete source, re-gate,
   *then* functional-test. Account for the larger codebase (`backups.py`, `monitoring.py`,
   `retention.py`, `import_csm_blhsd.py`, `/admin/backups`, delete-activity) — new, untested
   surface gets its own steps (K).
4. Proceed through the run protocol (§2), journaling each step.

_Last updated: 2026-06-11, after the Linux sandbox corrupted large-file reads and blocked the run._
_Top change: STEP 0 environment-fitness check + prefer native (Windows) execution; never repair_
_a file whose corruption is only seen in the sandbox._
