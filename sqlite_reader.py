"""One thread-owned connection for short, materialized application reads.

Only synchronous callbacks belong here: never return cursors/generators or submit
another read from a callback. Writes keep their existing fresh connections.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading


class SQLiteReader:
    def __init__(self):
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlite-reader")
        self._conn = None
        self._key = None
        self._owner = None
        self._closed = False

    def read(self, path, connect, operation, *, refresh=False):
        if threading.get_ident() == self._owner:
            raise RuntimeError("Nested SQLiteReader callback")
        return self._worker.submit(self._read, path, connect, operation, refresh).result()

    def _close(self):
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        self._key = None

    def _read(self, path, connect, operation, refresh):
        self._owner = threading.get_ident()
        # Repointed test databases and replaced/restored files must not retain an
        # old handle. Missing files also invalidate before the factory creates one.
        disk = Path(path).resolve()
        stat = disk.stat() if disk.exists() else None
        key = (str(disk), (stat.st_dev, stat.st_ino) if stat else None)
        if refresh or key != self._key or str(path) == ":memory:":
            self._close()
        try:
            if self._conn is None:
                self._conn = connect()
                self._conn.execute("PRAGMA query_only = ON")
                stat = disk.stat() if disk.exists() else None
                self._key = (str(disk), (stat.st_dev, stat.st_ino) if stat else None)
            result = operation(self._conn)
            # A callback cannot leave a read snapshot pinned across requests.
            self._conn.rollback()
            return result
        except BaseException:
            # Discard on failure, including a callback that changed connection
            # state. SQLite close rolls back unfinished transactions.
            self._close()
            raise
        finally:
            if str(path) == ":memory:":
                self._close()

    def close(self):
        if not self._closed:
            self._worker.submit(self._close).result()
            self._worker.shutdown(wait=True)
            self._closed = True
