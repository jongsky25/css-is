"""Reproducible, offline A25 capacity rehearsal. Never opens a production DB.

Run from the repository root: python scripts/assess_capacity.py --responses 1000
The tool owns a new temporary directory and emits only aggregate JSON.
"""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import sys
import tempfile
import time

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = int(position)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low)


def distribution(values: list[float]) -> dict:
    return {"samples": len(values), "p50_ms": round(percentile(values, .50), 2),
            "p95_ms": round(percentile(values, .95), 2),
            "p99_ms": round(percentile(values, .99), 2),
            "max_ms": round(max(values), 2) if values else 0.0}


def seed(path: Path, responses: int) -> tuple[int, int]:
    import auth
    import storage as st
    conn = st.connect(str(path))
    try:
        st.init_db(conn)
        hashed, salt = auth.hash_password("SyntheticOnly123!")
        user_id = st.create_admin_user(conn, "a25@example.invalid", hashed, salt,
                                       "admin", created_by="synthetic-a25", active=True)
        st.mark_onboarded(conn, user_id)
        fid = st.create_form_instance(conn, 1, "F1", "2026-10-20",
                                      topic="Synthetic capacity exercise", venue="Synthetic site")
        # Batched transactions keep fixture creation out of the measured window.
        for batch_start in range(0, responses, 500):
            for n in range(batch_start, min(responses, batch_start + 500)):
                rid = conn.execute("INSERT INTO response(form_instance_id,submitted_at) VALUES (?,?)",
                                   (fid, "2026-10-20T09:00:00")).lastrowid
                conn.executemany("INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,0)",
                                 [(rid, f"SQD{i}", float((n + i) % 5 + 1)) for i in range(9)])
            conn.commit()
        return fid, user_id
    finally:
        conn.close()


def insert_response(path: Path, form_id: int) -> tuple[float, bool]:
    import storage as st
    start = time.perf_counter()
    conn = st.connect(str(path))
    try:
        st.record_response(conn, form_id, [(f"SQD{i}", 4) for i in range(9)],
                           submitted_at="2026-10-20T09:00:00")
        return (time.perf_counter() - start) * 1000, False
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        return (time.perf_counter() - start) * 1000, True
    finally:
        conn.close()


async def measure_http(app_module, path: Path, form_id: int, user_id: int, *, concurrency: int,
                       requests_per_worker: int) -> dict:
    """Run HTTP reads and committed writes on one ASGI loop against the same DB."""
    samples: dict[str, list[float]] = {"health": [], "dashboard": [], "write": []}
    errors: dict[str, int] = {key: 0 for key in samples}
    loop_lag: list[float] = []
    stop = asyncio.Event()
    transport = httpx.ASGITransport(app=app_module.app, raise_app_exceptions=True)

    async def heartbeat():
        target = asyncio.get_running_loop().time() + .02
        while not stop.is_set():
            await asyncio.sleep(max(0, target - asyncio.get_running_loop().time()))
            now = asyncio.get_running_loop().time()
            loop_lag.append(max(0, (now - target) * 1000))
            target = now + .02

    async def reader(client: httpx.AsyncClient, worker: int):
        for n in range(requests_per_worker):
            name = "dashboard" if (n + worker) % 2 else "health"
            url = "/dashboard" if name == "dashboard" else "/health"
            start = time.perf_counter()
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    errors[name] += 1
            except Exception:
                errors[name] += 1
            samples[name].append((time.perf_counter() - start) * 1000)

    async def writer():
        for _ in range(max(4, requests_per_worker)):
            ms, locked = await asyncio.to_thread(insert_response, path, form_id)
            samples["write"].append(ms)
            errors["write"] += int(locked)

    async with httpx.AsyncClient(transport=transport, base_url="http://local.test",
                                 timeout=30) as client:
        import auth
        token = app_module._issue_session({"id": user_id, "username": "a25@example.invalid", "role": "admin"})
        if not token:
            raise RuntimeError("synthetic account could not receive a session")
        client.cookies.set(auth.COOKIE_NAME, token)
        # Warm the shared atoms frame before measuring steady-state reads.
        warm_start = time.perf_counter()
        warm = await client.get("/dashboard")
        cold_dashboard_ms = (time.perf_counter() - warm_start) * 1000
        if warm.status_code != 200:
            raise RuntimeError(f"dashboard warm-up returned {warm.status_code}")
        beat = asyncio.create_task(heartbeat())
        start = time.perf_counter()
        await asyncio.gather(*(reader(client, i) for i in range(concurrency)), writer())
        elapsed = time.perf_counter() - start
        stop.set()
        await beat
        rss_before_export_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        start = time.perf_counter()
        export = await client.get("/reports/export?type=1&fmt=docx")
        export_result = {"status": export.status_code,
                         "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                         "bytes": len(export.content)}
        if export.status_code != 200:
            raise RuntimeError(f"report export returned {export.status_code}: {export.text[:300]}")
    return {"concurrency": concurrency, "reads_per_worker": requests_per_worker,
            "cold_dashboard_ms": round(cold_dashboard_ms, 2),
            "elapsed_s": round(elapsed, 3), "throughput_ops_s": round(sum(map(len, samples.values())) / elapsed, 2),
            "latency": {key: distribution(value) for key, value in samples.items()},
            "errors": errors, "event_loop_lag": distribution(loop_lag),
            "report_export": export_result, "peak_rss_before_export_kib": rss_before_export_kib}


def measure_sql(path: Path, *, repeats: int) -> dict:
    import storage as st
    times = []
    rows = 0
    for _ in range(repeats):
        conn = st.connect(str(path))
        try:
            start = time.perf_counter()
            frame = st.load_atoms(conn)
            times.append((time.perf_counter() - start) * 1000)
            rows = len(frame)
        finally:
            conn.close()
    return {"answer_rows": rows, "full_atoms_refresh": distribution(times)}


def measure_first_use(path: Path, workers: int) -> dict:
    """Concurrent first schema check on a fresh copy, without touching the measured DB."""
    import app
    import storage as st
    first_path = path.with_name("first-use.db")
    with sqlite3.connect(str(path)) as src, sqlite3.connect(str(first_path)) as dst:
        src.backup(dst)
    previous = app.DB
    app.DB = str(first_path)
    times = []
    errors = []

    def call():
        start = time.perf_counter()
        try:
            conn = app.get_conn()
            conn.execute("SELECT 1").fetchone()
            conn.close()
        except Exception as exc:
            errors.append(type(exc).__name__)
        times.append((time.perf_counter() - start) * 1000)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda _: call(), range(workers)))
    finally:
        app.DB = previous
        app._schema_ready_for.discard(str(first_path))
    return {"workers": workers, "latency": distribution(times), "errors": errors}


def measure_lock_wait(path: Path, form_id: int) -> dict:
    """A controlled 100 ms SQLite writer hold, separate from the normal workload."""
    import threading
    import storage as st
    acquired = threading.Event()

    def holder():
        conn = st.connect(str(path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            acquired.set()
            time.sleep(.1)
            conn.rollback()
        finally:
            conn.close()

    worker = threading.Thread(target=holder)
    worker.start()
    if not acquired.wait(5):
        worker.join()
        raise RuntimeError("writer hold was not acquired")
    try:
        waited_ms, locked = insert_response(path, form_id)
    finally:
        worker.join()
    if locked:
        raise RuntimeError("writer timed out during the controlled lock test")
    return {"hold_ms": 100, "write_completion_ms": round(waited_ms, 2),
            "sqlite_busy_timeout_ms": 5000}


def measure_recovery(path: Path, backup_dir: Path) -> dict:
    import backups as bk
    import storage as st
    previous = bk.SCHED_DIR
    bk.SCHED_DIR = str(backup_dir)
    try:
        start = time.perf_counter()
        saved = bk.make_backup(str(path), kind="manual")
        snapshot_ms = (time.perf_counter() - start) * 1000
        conn = st.connect(str(path))
        expected = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
        conn.execute("INSERT INTO response(form_instance_id,submitted_at) "
                     "SELECT id,'2026-10-20T10:00:00' FROM form_instance LIMIT 1")
        conn.commit()
        conn.close()
        # The isolated restore exercises the application path, including its
        # safety snapshot and session/integration invalidation behavior.
        start = time.perf_counter()
        bk.restore_backup(saved["name"], str(path))
        restore_ms = (time.perf_counter() - start) * 1000
        conn = st.connect(str(path))
        restored = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if restored != expected or integrity != "ok":
            raise RuntimeError("restore did not reconcile response count and integrity")
        return {"snapshot_ms": round(snapshot_ms, 2), "restore_ms": round(restore_ms, 2),
                "snapshot_bytes": saved["size"], "responses_reconciled": restored,
                "integrity": integrity, "simulated_unbacked_writes": 1}
    finally:
        bk.SCHED_DIR = previous


def queue_depth(path: Path) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute("SELECT state,COUNT(*) FROM document_job GROUP BY state").fetchall()
        return {state: count for state, count in rows}
    finally:
        conn.close()


def assess(responses: int, concurrency: int, requests_per_worker: int) -> dict:
    if not 10 <= responses <= 100_000 or not 1 <= concurrency <= 32 or not 2 <= requests_per_worker <= 100:
        raise ValueError("responses=10..100000, concurrency=1..32, requests-per-worker=2..100")
    with tempfile.TemporaryDirectory(prefix="css-a25-") as directory:
        root = Path(directory)
        path = root / "synthetic.db"
        os.environ["CSS_DB"] = str(path)
        os.environ["CSS_PERSIST_DIR"] = ""
        os.environ["CSS_SESSION_SECRET"] = "synthetic-a25-only-ephemeral-session-key"
        form_id, user_id = seed(path, responses)
        with redirect_stdout(io.StringIO()):
            import app
        import monitoring
        monitoring.LOG_PATH = str(root / "requests.log")
        cpu_start = time.process_time()
        first = measure_first_use(path, concurrency)
        sql = measure_sql(path, repeats=2)
        http = asyncio.run(measure_http(app, path, form_id, user_id, concurrency=concurrency,
                                        requests_per_worker=requests_per_worker))
        contention = measure_lock_wait(path, form_id)
        queue = queue_depth(path)
        recovery = measure_recovery(path, root / "backups")
        return {"schema": 1, "mode": "synthetic_local_in_process",
                "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                            "platform": platform.platform()},
                "responses_seeded": responses,
                "answers_seeded": responses * 9, "database_bytes": path.stat().st_size,
                "first_use": first, "sql": sql, "mixed_workload": http,
                "controlled_lock_wait": contention,
                "document_job_states": queue, "recovery": recovery,
                "process_cpu_s": round(time.process_time() - cpu_start, 3),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "limits": ["No production data or real provider calls", "Single in-process ASGI loop, not hosted network latency",
                           "Synthetic response-heavy mix; no real document jobs or queue-age sample",
                           "Temporary local disk is not the hosted snapshot bucket"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--requests-per-worker", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = assess(args.responses, args.concurrency, args.requests_per_worker)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
