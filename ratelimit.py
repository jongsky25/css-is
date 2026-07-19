"""Tiny in-process rate limiter for the public, unauthenticated endpoints.

No dependencies, no external store — a thread-safe sliding-window counter keyed by
(bucket, client-ip). It exists to blunt *scripted* abuse (email enumeration on
/check, bot-driven registration floods), NOT to police humans.

IMPORTANT — venue NAT: at a physical event, dozens of attendees share one public
IP (the venue WiFi). So the defaults are deliberately GENEROUS: high enough that a
crowd registering/typing at once is never blocked, low enough that a scripted
sweep of thousands of requests is. Tune via env vars if a deployment needs to.
"""
from __future__ import annotations
import os
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_HITS: dict[tuple[str, str], deque] = defaultdict(deque)
_LAST_PRUNE = [0.0]


def _limits(bucket):
    """(max_requests, window_seconds) for a bucket, env-overridable.
    CSS_RL_<BUCKET>="<max>/<window_seconds>", e.g. CSS_RL_CHECK="120/60"."""
    defaults = {
        "check": (300, 60),      # email duplicate-check probe (cheap GET, on keystroke)
        "register": (120, 60),   # POST registration — generous for a busy venue NAT
        "telemetry": (600, 60),  # UX telemetry batches — high-volume, low-value-per-request
        "ai": (20, 60),          # AI calls (ai_core.ask) — abuse throttle, NOT the spend
                                 # budget (that's DB-backed in ai_budget so it survives restarts)
    }
    raw = os.environ.get(f"CSS_RL_{bucket.upper()}")
    if raw and "/" in raw:
        try:
            n, w = raw.split("/", 1)
            return int(n), int(w)
        except ValueError:
            pass
    return defaults.get(bucket, (120, 60))


def allow(bucket, ip, now=None):
    """Return True if this (bucket, ip) is under its limit and record the hit.
    A blank/unknown ip is never limited (we can't attribute it fairly)."""
    if not ip:
        return True
    now = time.time() if now is None else now
    max_n, window = _limits(bucket)
    key = (bucket, ip)
    with _LOCK:
        _maybe_prune(now, window)
        dq = _HITS[key]
        cutoff = now - window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= max_n:
            return False
        dq.append(now)
        return True


def _maybe_prune(now, window):
    """Drop stale keys occasionally so the dict can't grow unbounded. Caller holds
    the lock. Cheap: at most once every 5 minutes."""
    if now - _LAST_PRUNE[0] < 300:
        return
    _LAST_PRUNE[0] = now
    horizon = now - max(window, 3600)
    for key in [k for k, dq in _HITS.items() if not dq or dq[-1] < horizon]:
        del _HITS[key]


def reset():
    """Test hook — clear all recorded hits."""
    with _LOCK:
        _HITS.clear()
        _LAST_PRUNE[0] = 0.0
