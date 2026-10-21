"""Bound document-service workers without cancelling an ambiguous external effect.

Admission has no waiting queue. A slot belongs to the actual worker future, so
request cancellation or timeout cannot admit another call while it still runs.
This is process-local capacity control, not a durable background-job scheduler.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from html import escape
import threading

from fastapi.responses import HTMLResponse, JSONResponse

MAX_WORKERS = 2
WAIT_SECONDS = 120


class Busy(Exception):
    pass


class Unconfirmed(Exception):
    pass


class Runner:
    def __init__(self, workers=MAX_WORKERS, wait_seconds=WAIT_SECONDS):
        self.wait_seconds = wait_seconds
        self._slots = threading.BoundedSemaphore(workers)
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='document-service')

    async def run(self, function, *args):
        if not self._slots.acquire(blocking=False):
            raise Busy()
        try:
            future = self._pool.submit(copy_context().run, function, *args)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda finished: self._slots.release())
        waiting = asyncio.wrap_future(future)

        def consume(finished):
            if not finished.cancelled():
                finished.exception()

        waiting.add_done_callback(consume)
        # asyncio.wait neither cancels the worker on timeout nor propagates
        # request cancellation into it. Completion still settles its receipt.
        done, _ = await asyncio.wait({waiting}, timeout=self.wait_seconds)
        if not done:
            raise Unconfirmed()
        return waiting.result()


RUNNER = Runner()


async def run(function, *args):
    return await RUNNER.run(function, *args)


def failure_response(request, location, error):
    busy = isinstance(error, Busy)
    message = ('Document services are busy. This request has not started. Wait briefly, then submit again.'
               if busy else 'The result is not yet confirmed. Processing may still finish. '
               'Check the record before submitting again.')
    status = 503 if busy else 504
    headers = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
    if busy:
        headers['Retry-After'] = '3'
    if ('application/json' in request.headers.get('accept', '')
            or request.headers.get('content-type', '').startswith('application/json')):
        return JSONResponse({'state': 'not_started' if busy else 'unconfirmed',
                             'error': message, 'url': location}, status_code=status, headers=headers)
    return HTMLResponse(f'<p>{escape(message)}</p><p><a href="{escape(location, quote=True)}">'
                        'Return to Documents</a></p>', status_code=status, headers=headers)
