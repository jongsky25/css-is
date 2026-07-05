# CSS·IS — Performance Assessment (Phase 5)

**Method:** hands-on measurement against a **copy** of the live `css_is.db` (`css_is_perf.db`, 15.6 MB) — the live DB was never touched. Timings via in-process benchmarks + FastAPI `TestClient`. Environment: Python 3.14.5, SQLite 3.50.4, Windows 10.

> **Headline:** Steady-state performance is fine (sub-500 ms). **One thing dominates everything: the ~8 s `load_atoms()` rebuild, which balloons to ~12 s under a request and fires on every server restart AND every new survey submission.** Two proven fixes (incremental rebuild + background refresh) turn that 12 s stall into ~0.4 s. Nothing else is urgent.

---

## 1. Data scale (the copy)

| Table | Rows |
|---|---|
| **answer** (the atoms) | **392,712** |
| response | 35,808 |
| form_instance | 3,898 |
| audit_log | 2,428 |
| resource_person | 45 |
| org_unit | 10 |
| event | 1 |
| event_form | 2 |
| attendee | 0 |

`load_atoms()` materializes 392,195 rows (after the `archived` filter) into a pandas DataFrame on each rebuild. The `event`/link-tree feature is effectively unused (1 event, 0 attendees) — relevant for prioritizing Phase 6.

---

## 2. Measured latencies

### Page latency (FastAPI TestClient, authed admin)
| Scenario | Latency |
|---|---|
| **Cold first hit** (`/dashboard`, builds atoms) | **12,710 ms** |
| Warm `/` (home) | 14 ms |
| Warm `/dashboard` (pulse) | 434 ms |
| Warm `/dashboard/people` | 187 ms |
| Warm `/dashboard/teams` | 244 ms |
| Warm `/dashboard/trends` | 195 ms |
| Warm `/dashboard/participation` | 190 ms |
| Warm `/reports?type=1` | 288 ms |
| Warm `/reports/verbatims` | 389 ms |
| **After a new response invalidates the cache** | **~11,630 ms** |

**Steady-state is healthy.** The only red numbers are cold-start and post-invalidation — both are the atoms rebuild.

### `load_atoms()` cost breakdown (isolated, ~7.6–8.5 s total)
| Stage | Time |
|---|---|
| `pd.read_sql_query(_LOAD_SQL)` (SQL exec + DataFrame build) | ~4,500 ms |
| `assign_periods()` (pandas datetime work) | ~1,300 ms |
| `value`/`is_na`/`event_date` coercions | ~7 ms (negligible) |

### Per-request overhead in `get_conn()` (paid on every page)
| Piece | Time |
|---|---|
| `_data_key()` cache-check query (9 COUNT/MAX subqueries) | ~14 ms |
| `init_db()` (schema re-check) | ~2–3 ms |
| `seed_directory_if_empty()` | ~0.2 ms |
| fresh `connect()` | ~0.3 ms |

Per-request overhead totals ~17 ms — **minor**. (This corrects a pre-measurement assumption that per-request `init_db` was a hotspot; it isn't.)

---

## 3. Root-cause analysis (what is and isn't the problem)

**The query is already optimal.** `EXPLAIN QUERY PLAN` on `_LOAD_SQL`:
```
SCAN a
SEARCH r  USING INTEGER PRIMARY KEY (rowid=?)
SEARCH fi USING INTEGER PRIMARY KEY (rowid=?)
SEARCH rp/sb/ostaff/osb/olead/orp/xo USING INTEGER PRIMARY KEY (rowid=?) LEFT-JOIN
```
Every join uses integer-primary-key (rowid) lookups — the fastest possible. The single `SCAN a` is **unavoidable**: the function deliberately loads *all* answers, then filters in pandas (`eng.scope()`).

**Therefore — assumptions corrected by measurement:**
- ❌ **"Add indexes to speed up the dashboard."** Indexes won't help `load_atoms` — the joins are already rowid lookups and it must scan all rows by design. *(Indexes would only help narrowly-filtered direct queries, none of which are currently hot.)*
- ❌ **"The 8 LEFT JOINs are the bottleneck."** Stripping them to a minimal 3-table join saved only ~270 ms (4,046 → 3,773 ms). The cost is **moving 392K rows through the sqlite→pandas bridge**, not join complexity.
- ❌ **"Per-request `init_db()` is a hotspot."** It's ~2–3 ms.
- ✅ **The real cost is rebuilding the whole atoms frame**, and the real *pain* is **how often** that rebuild fires: the cache key (`_data_key`) includes `COUNT/MAX` of `answer` and `response`, so **every new submission invalidates it** → the next dashboard view eats ~12 s. During an active event with ratings streaming in, this repeats.

**Concurrency note:** the rebuild holds `_atoms_lock`, so *all* concurrent requests block for the full ~8 s while one rebuilds.

**Single-process constraint (important for deployment):** the atoms cache and view memo are **in-process** (`_atoms_state`, `_view_memo`). Running multiple uvicorn **workers** would give each its own cache → rebuilds and ~150 MB memory **multiplied per worker**, with no shared invalidation. **This app must run single-process** (concurrency via threads/async, not worker processes) unless a shared cache is introduced later.

---

## 4. Fixes — measured impact, ranked

| # | Fix | Effort | Measured / expected impact | Risk |
|---|---|---|---|---|
| **F1** | **Incremental atoms rebuild** — keep the cached frame; when only new answers were appended, load just `answer.id > last_max`, transform, and `concat`. | M | **101 ms (50 new) / 110 ms (500 new)** vs ~8,000 ms full → **~75× faster**. Post-response page ≈ 100 ms (atoms) + ~300 ms (view rebuild) ≈ **0.4 s vs 12 s**. | Med |
| **F2** | **Background refresh (stale-while-revalidate)** — when the cache is stale, serve the existing frame immediately and rebuild in a daemon thread, swap when ready. Covers the structural invalidations F1 can't (archive/retag/rename/hide). | M | Users **never** block on a rebuild; worst case data is a few seconds stale. Converts every remaining 8 s stall into ~400 ms. | Med |
| **F3** | **Pickle cold-start cache** — persist the built frame to `_atoms_cache.pkl` keyed on the data-key; hydrate on startup instead of rebuilding. | S | **914 ms read** vs ~8,000 ms rebuild → **9× faster** restart. (95 MB file; dependency-free — `df.to_pickle`/`read_pickle`.) | Low |
| **F4** | **WAL + pragmas** — `PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000` (set WAL once; pragmas per connection). | S | Readers don't block the single writer during a rebuild/new submission; better multi-user concurrency. **Backup-safe — verified** (`backups.py` uses the SQLite online backup API, not a file copy, so it captures WAL pages correctly). | Low |
| **F5** | **`assign_periods` tune** — `pd.to_datetime(..., format="%Y-%m-%d")`, drop the redundant `.copy()`. | S | 1,371 → 1,166 ms (~15%). Minor; nice-to-have alongside F1/F3. | Low |
| **F6** | **Move `init_db()`/`seed_directory_if_empty()` to startup** — run once on boot, not per request. | S | ~2–3 ms/request + removes per-request schema churn; cleaner. | Low |
| **F7** | **`_data_key` micro-tune** (optional) — it's ~14 ms; fine as-is. | XS | Marginal. Skip unless profiling later flags it. | Low |

**Combined expected result:** cold-start ~0.9 s (F3), per-response refresh ~0.1–0.4 s (F1/F2), no user ever blocked (F2), better concurrency (F4) — i.e. the ~12 s stalls disappear and the app stays sub-second across the board.

---

## 5. Recommended tech stack & ops

- **Server (prod):** `python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1` (no `--reload`). **Keep `--workers 1`** (single-process — see §3). For resilience on Windows, run it under a service supervisor (NSSM, or a Task Scheduler "at startup" task) so it restarts on crash/reboot.
- **Concurrency:** rely on async + the sync threadpool within the single process; WAL (F4) removes read/write contention. Sufficient for an office-LAN tool. Only consider a shared cache (e.g. a small Redis or an on-disk memoization) if you ever need multiple worker processes.
- **No Redis/Celery/ORM needed** at this scale — SQLite + the in-process cache is the right architecture; the fixes above make it fast.
- **Profiling tools (dev-only, do NOT add to `requirements.txt`):** `scalene` or `py-spy` for line-level profiling, `locust` for load testing — useful if you optimize further. This assessment got clear answers with stdlib timing alone, so they're optional.
- **Housekeeping:** add `_atoms_cache.pkl`, `css_is_perf.db`, and any `*.db-wal`/`*.db-shm` to `.gitignore`.

---

## 6. Suggested execution order (low-risk → high-value)

1. **F4 (WAL + pragmas)** — one-time, trivial, immediate concurrency benefit, backup-safe. *Run the full `pytest` + `qa_smoke` + a backup/restore round-trip to confirm.*
2. **F6 (init_db/seed to startup)** — small cleanup, removes per-request work.
3. **F1 + F2 (incremental + background refresh)** — the headline fix; build together since F2 is the safety net for cases F1 can't do incrementally. Most care + tests here (verify: new-response path takes the incremental branch; archive/retag/rename/hide trigger a full background rebuild and eventually reflect correctly; concurrent requests during a rebuild get the old frame, not a half-built one).
4. **F3 (pickle cold-start)** — independent; add after F1/F2 so the persisted frame already benefits from them.
5. **F5 (assign_periods tune)** — fold in opportunistically.

**Regression gate after each step:** `python -m pytest`, `python qa_preflight.py` (RESULT: GREEN), `python qa_smoke.py` (ALL PASSED), and for F4 specifically a manual backup → restore to confirm WAL safety end-to-end.

---

## 7. Evidence appendix (key raw numbers)

- `load_atoms()` cold: 8,500 / 7,653 / 7,565 ms (3 runs). Raw SQL only: 5,158 / 3,452 / 3,528 ms.
- Page cold first hit: 12,710 ms. Post-invalidation rebuild: 11,682 / 11,628 ms.
- Minimal 3-table SQL 3,773 ms vs full 11-table 4,046 ms (joins add ~270 ms).
- Pickle: write 1,885 ms, read 914 ms, 95,698 KB, 392,195 rows.
- Incremental: 50 new = 101 ms, 500 new = 110 ms (→ 392,245 / 392,695 rows).
- `assign_periods`: 1,371 ms → 1,166 ms with explicit format.
- Indexes present: only `sqlite_autoindex_*` (PK/UNIQUE) + `ux_admin_user_rp`. No index on `answer.response_id`, `answer.item_id`, `response.form_instance_id` — and none needed for the hot path (rowid joins).
- `journal_mode`: `delete` (WAL not enabled).
