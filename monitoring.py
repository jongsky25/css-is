"""
Office Connect monitoring
=================

In-process performance monitoring — the four golden signals (latency, traffic,
errors, saturation) for the live app, plus a structured per-request log and a
liveness probe. Stdlib only; everything is kept in memory (a rolling window)
except the request log, which is appended to requests.log (size-rotated).

  * record()   — called by the metrics middleware once per request.
  * snapshot() — the numbers the /ops admin dashboard renders.
  * health()   — the cheap liveness/readiness payload for /health.

Path bucketing collapses ids/tokens (/r/<tok>, /directory/person/<id>/edit) so
the per-route table stays low-cardinality.
"""

from __future__ import annotations
import json
import os
import re
import threading
import time
from collections import deque
from contextlib import contextmanager

WINDOW = 2000             # recent requests kept for percentiles/rates
SLOW_MS = 1000.0          # a request slower than this is "slow" (saturation hint)
LOG_PATH = "requests.log"
LOG_MAX_BYTES = 5 * 1024 * 1024

_LOCK = threading.Lock()
_STATE = {
    "started": time.time(),
    "total": 0,
    "inflight": 0,
    "max_inflight": 0,
    "status": {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0},
    "slow": 0,
    "recent": deque(maxlen=WINDOW),   # (ts, dur_ms, status, method, bucket)
    "start_db_bytes": None,
}
_log_writes = 0

# Only fixed operation names and framework route templates enter these buffers.
# No URLs, query strings, actors, exception messages or record IDs are retained.
PHASES = {
    "auth_session": "Session lookup",
    "signed_in_context": "Signed-in navigation and permissions",
    "ops_connection": "Health page: database connection",
    "ops_backups": "Health page: backup listing",
    "ops_audit": "Health page: audit verification",
    "ops_inventory": "Health page: inventory counts",
    "ops_usage": "Health page: usage counts",
    "ops_telegram": "Health page: Telegram queue status",
}
_PHASE_RECENT = deque(maxlen=WINDOW)
_ROUTE_RECENT = deque(maxlen=WINDOW)


def route_template(scope):
    """Use framework patterns only; never interpolate client path parameters."""
    path = getattr(scope.get("route"), "path", None)
    # The API is a mounted FastAPI application; its route patterns are relative.
    if path and scope.get("root_path") == "/api/v1":
        return "/api/v1" + path
    return path


@contextmanager
def measure(phase):
    """Time a fixed operation, including failures, without retaining its data."""
    if phase not in PHASES:
        raise ValueError("Unknown monitoring phase")
    started = time.perf_counter()
    failed = True
    try:
        yield
        failed = False
    finally:
        elapsed = (time.perf_counter() - started) * 1000.0
        with _LOCK:
            _PHASE_RECENT.append((time.time(), phase, elapsed, failed))


def timed_call(phase, fn, *args, **kwargs):
    with measure(phase):
        return fn(*args, **kwargs)


def _diagnostics(routes, phases, now):
    def stats(values):
        ds = sorted(values)
        return {"n": len(ds), "p50": round(_percentile(ds, .5)),
                "p95": round(_percentile(ds, .95)), "max": round(max(ds)),
                "slow": sum(d >= SLOW_MS for d in ds)}

    grouped = {}
    for ts, method, route, dur, status in routes:
        if ts >= now - 300:
            grouped.setdefault((method, route), []).append((dur, status))
    rows = []
    for (method, route), samples in grouped.items():
        rows.append({"method": method, "path": route,
                     "errs": sum(status >= 500 for _, status in samples),
                     **stats([dur for dur, _ in samples])})
    rows.sort(key=lambda r: (-r["slow"], -r["p95"], -r["n"], r["path"], r["method"]))
    phase_rows = []
    for key, label in PHASES.items():
        samples = [(dur, failed) for ts, phase, dur, failed in phases
                   if ts >= now - 300 and phase == key]
        if samples:
            phase_rows.append({"phase": key, "label": label,
                               "failed": sum(failed for _, failed in samples),
                               **stats([dur for dur, _ in samples])})
    return {"routes": rows[:20], "phases": phase_rows}


# ---------------------------------------------------------------------
# Path bucketing (keep route cardinality low)
# ---------------------------------------------------------------------

_BUCKETS = [
    (re.compile(r"^/r/[0-9a-f]{6,}$"), "/r/{token}"),
    (re.compile(r"^/e/[0-9a-f]{6,}$"), "/e/{token}"),
    (re.compile(r"^/encode/[0-9a-f]{6,}$"), "/encode/{token}"),
    (re.compile(r"^/photo/\d+$"), "/photo/{id}"),
    (re.compile(r"^/directory/person/\d+/(\w+)$"), r"/directory/person/{id}/\1"),
    (re.compile(r"^/directory/unit/\d+/(\w+)$"), r"/directory/unit/{id}/\1"),
    (re.compile(r"^/admin/users/\d+/(\w+)$"), r"/admin/users/{id}/\1"),
    (re.compile(r"^/dashboard/people/[^/]+$"), "/dashboard/people/{name}"),
    (re.compile(r"^/reports/activities/\d+/(\w+)$"), r"/reports/activities/{id}/\1"),
    (re.compile(r"^/reports/activities/\d+$"), "/reports/activities/{id}"),
    (re.compile(r"^/dashboard/activities/\d+$"), "/dashboard/activities/{id}"),
]


def bucket_path(path):
    for rx, repl in _BUCKETS:
        if rx.match(path):
            return rx.sub(repl, path)
    return path


def _class(status):
    return f"{status // 100}xx" if 100 <= status < 600 else "5xx"


# ---------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------

def inc_inflight():
    with _LOCK:
        _STATE["inflight"] += 1
        _STATE["max_inflight"] = max(_STATE["max_inflight"], _STATE["inflight"])


def dec_inflight():
    with _LOCK:
        _STATE["inflight"] = max(0, _STATE["inflight"] - 1)


def record(method, path, status, dur_ms, *, ip=None, user=None, now=None, route_template=None):
    now = now or time.time()
    bucket = bucket_path(path)
    cls = _class(status)
    with _LOCK:
        # route_template must come from the matched framework route, never path.
        route = route_template or "(unmatched or denied before routing)"
        method_label = method if method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} else "OTHER"
        _ROUTE_RECENT.append((now, method_label, route, dur_ms, status))
        _STATE["total"] += 1
        _STATE["status"][cls] = _STATE["status"].get(cls, 0) + 1
        if dur_ms >= SLOW_MS:
            _STATE["slow"] += 1
        _STATE["recent"].append((now, dur_ms, status, method, bucket))
    _write_log({"ts": _iso(now), "method": method, "path": bucket, "status": status,
                "ms": round(dur_ms, 1), "ip": ip, "user": user})


def _iso(epoch):
    # Render in local (PH) wall-clock, not the server clock (UTC on Hugging
    # Face), so the request log lines up with the rest of the time logs.
    import tzutil as tz
    from datetime import datetime
    return datetime.fromtimestamp(epoch, tz.LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S")


def _write_log(rec):
    """Append one JSON line to the request log; rotate by size. Best-effort —
    logging must never break a request."""
    global _log_writes
    try:
        _log_writes += 1
        if _log_writes % 200 == 1 and os.path.exists(LOG_PATH) \
                and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            try:
                os.replace(LOG_PATH, LOG_PATH + ".1")
            except OSError:
                pass
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------

def _percentile(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def set_start_db_bytes(db_path):
    with _LOCK:
        if _STATE["start_db_bytes"] is None and os.path.exists(db_path):
            _STATE["start_db_bytes"] = os.path.getsize(db_path)


def snapshot(db_path="css_is.db", now=None):
    """The four golden signals + a per-route breakdown for the /ops dashboard."""
    now = now or time.time()
    with _LOCK:
        recent = list(_STATE["recent"])
        total = _STATE["total"]
        status = dict(_STATE["status"])
        inflight = _STATE["inflight"]
        max_inflight = _STATE["max_inflight"]
        slow = _STATE["slow"]
        started = _STATE["started"]
        start_db = _STATE["start_db_bytes"]
        diagnostic_routes = list(_ROUTE_RECENT)
        phases = list(_PHASE_RECENT)

    def in_window(secs):
        return [r for r in recent if r[0] >= now - secs]

    last1m = in_window(60)
    last5m = in_window(300)
    durs = sorted(r[1] for r in last5m) or [0.0]
    err5 = sum(1 for r in last5m if r[2] >= 500)
    err4 = sum(1 for r in last5m if 400 <= r[2] < 500)

    # per-route table over the recent window
    routes = {}
    for ts, dur, st_code, method, bucket in last5m:
        d = routes.setdefault(bucket, {"n": 0, "errs": 0, "durs": []})
        d["n"] += 1
        d["durs"].append(dur)
        if st_code >= 500:
            d["errs"] += 1
    route_rows = []
    for bucket, d in routes.items():
        ds = sorted(d["durs"])
        route_rows.append({"path": bucket, "n": d["n"], "errs": d["errs"],
                           "p50": round(_percentile(ds, .5)), "p95": round(_percentile(ds, .95))})
    route_rows.sort(key=lambda r: r["n"], reverse=True)

    db_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    growth = (db_bytes - start_db) if start_db is not None else 0

    return {
        "uptime_s": int(now - started),
        "uptime_h": human_duration(now - started),
        # traffic
        "total": total,
        "rpm_1m": len(last1m),
        "rpm_5m_avg": round(len(last5m) / 5.0, 1),
        # latency (ms, over last 5 min)
        "p50": round(_percentile(durs, .50)),
        "p95": round(_percentile(durs, .95)),
        "p99": round(_percentile(durs, .99)),
        "max": round(max(durs)),
        # errors
        "status": status,
        "err5_5m": err5,
        "err4_5m": err4,
        "err_rate_5m": round(100.0 * err5 / len(last5m), 1) if last5m else 0.0,
        # saturation
        "inflight": inflight,
        "max_inflight": max_inflight,
        "slow_total": slow,
        "db_bytes": db_bytes,
        "db_human": human_size(db_bytes),
        "db_growth_human": ("+" if growth >= 0 else "") + human_size(growth),
        "sample_5m": len(last5m),
        "routes": route_rows[:20],
        "diagnostics": _diagnostics(diagnostic_routes, phases, now),
    }


def health(db_path="css_is.db", db_ok=None):
    with _LOCK:
        started = _STATE["started"]
        total = _STATE["total"]
    return {"status": "ok" if (db_ok is None or db_ok) else "degraded",
            "db": "ok" if (db_ok is None or db_ok) else "error",
            "uptime_s": int(time.time() - started),
            "requests": total}


def tail_log(n=50):
    """Last n structured request-log lines (most recent first), parsed."""
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in reversed(lines):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def human_size(n):
    neg = n < 0
    n = abs(float(n or 0))
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            s = f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            return ("-" + s) if neg else s
        n /= 1024


def human_duration(secs):
    secs = int(secs)
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m, _ = divmod(secs, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def reset():
    """Test helper — clear all in-memory state."""
    global _log_writes
    with _LOCK:
        _PHASE_RECENT.clear()
        _ROUTE_RECENT.clear()
        _STATE.update({"started": time.time(), "total": 0, "inflight": 0,
                       "max_inflight": 0, "status": {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0},
                       "slow": 0, "recent": deque(maxlen=WINDOW), "start_db_bytes": None})
    _log_writes = 0
