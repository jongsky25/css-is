"""In-process pub/sub for SSE live-count pushes.

Only correct with --workers 1 (single uvicorn worker), which is the
project's required run mode anyway (WAL + single SQLite writer).
"""
from __future__ import annotations
import asyncio

# event_id -> set of per-subscriber queues
_subs: dict[int, set[asyncio.Queue]] = {}


def subscribe(event_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subs.setdefault(event_id, set()).add(q)
    return q


def unsubscribe(event_id: int, q: asyncio.Queue) -> None:
    s = _subs.get(event_id)
    if s:
        s.discard(q)
        if not s:
            del _subs[event_id]


async def broadcast(event_id: int, count: int) -> None:
    for q in list(_subs.get(event_id, [])):
        await q.put(count)
