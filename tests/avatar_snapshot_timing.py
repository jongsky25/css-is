"""Bracket existing snapshot calls without new browser requests or proc reads."""
import time
from pathlib import Path


class SnapshotTiming:
    def __init__(self, monkeypatch, page_class, session_class):
        self.active = None
        self.monkeypatch = monkeypatch
        self._wrap(page_class, 'evaluate', lambda obj, args: 'page.evaluate')
        self._wrap(session_class, 'send', lambda obj, args: 'cdp:' + args[0])
        self._wrap(Path, 'read_text', lambda obj, args: str(obj) if str(obj).startswith('/proc/') else None)

    def _wrap(self, cls, name, label):
        original = getattr(cls, name)
        def call(obj, *args, **kwargs):
            kind = label(obj, args) if self.active is not None else None
            if kind is None:
                return original(obj, *args, **kwargs)
            row = {'call': kind, 'begin_ns': time.monotonic_ns()}
            try:
                return original(obj, *args, **kwargs)
            except Exception as error:
                row['error_type'] = type(error).__name__
                raise
            finally:
                row['end_ns'] = time.monotonic_ns()
                self.active.append(row)
        self.monkeypatch.setattr(cls, name, call)

    def capture(self, callback, *args):
        if self.active is not None:
            raise RuntimeError('Nested snapshot capture')
        self.active = []
        begin = time.monotonic_ns()
        try:
            result = callback(*args)
            return result, {'interval_ns': [begin, time.monotonic_ns()], 'calls': self.active}
        finally:
            self.active = None
