"""auth.py — the off-loop password-hash wrappers.

PBKDF2 (_ITERATIONS) is deliberately CPU-heavy, so calling it directly from an
`async def` handler freezes the single uvicorn worker's event loop for the whole
hash (~100-150ms) — a burst of sign-ins then fails the load balancer's health
check and produces an edge 5xx storm. hash_password_async / verify_password_async
run the hash off the loop; these tests pin their parity with the sync versions
and that they execute on a worker thread, not the event loop.
"""
import asyncio
import threading

import auth


def test_hash_password_async_matches_sync_and_verifies():
    h, salt = auth.hash_password("correct horse battery staple")
    # async verify against a sync-produced hash
    assert asyncio.run(
        auth.verify_password_async("correct horse battery staple", h, salt)) is True
    assert asyncio.run(auth.verify_password_async("wrong", h, salt)) is False


def test_hash_password_async_roundtrips_with_sync_verify():
    h, salt = asyncio.run(auth.hash_password_async("s3cret-pw"))
    # a hash produced off-loop verifies with the plain sync path
    assert auth.verify_password("s3cret-pw", h, salt) is True
    assert auth.verify_password("nope", h, salt) is False


def test_verify_password_async_runs_off_the_event_loop():
    h, salt = auth.hash_password("pw")
    seen = {}

    async def _main():
        # capture the thread the blocking hash actually runs on
        orig = auth.hash_password

        def _spy(password, s=None):
            seen["thread"] = threading.current_thread().name
            return orig(password, s)

        auth.hash_password = _spy
        try:
            return await auth.verify_password_async("pw", h, salt)
        finally:
            auth.hash_password = orig

    assert asyncio.run(_main()) is True
    assert seen["thread"] != threading.main_thread().name
