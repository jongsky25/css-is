"""Bound native PDF parsing independently of web threads and OCR rendering."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time


MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 50
MAX_TEXT = 100_000
MAX_RESULT_BYTES = 1024 * 1024
SUPPORTED = sys.platform == 'linux'
_SLOT = threading.BoundedSemaphore(1)
_WORKER = Path(__file__).resolve().with_name('pdf_reader_worker.py')


@dataclass(frozen=True)
class Limits:
    wall_seconds: float = 15
    cpu_seconds: int = 5
    memory_bytes: int = 256 * 1024 * 1024


LIMITS = Limits()
MESSAGES = {
    'bytes': 'Choose a PDF no larger than 20 MiB.',
    'encrypted': 'Password-protected PDFs are not supported. Continue manually.',
    'pages': 'Choose a PDF with at most 50 pages.',
    'text': 'This PDF contains too much text. Continue manually.',
    'resource': 'This PDF is too complex to read safely. Try fewer pages or continue manually.',
    'timeout': 'Reading the PDF timed out. Try fewer pages or continue manually.',
    'cancelled': 'PDF reading was cancelled.',
    'unavailable': 'Protected PDF reading is unavailable on this server. Read selected pages in the browser or continue manually.',
    'unreadable': 'The PDF could not be read. Continue manually.',
}


class PDFBusy(ValueError):
    pass


def _command(limits, selection):
    config = {'cpu': limits.cpu_seconds, 'memory': limits.memory_bytes,
              'max_bytes': MAX_BYTES, 'max_pages': MAX_PAGES,
              'max_text': MAX_TEXT, 'selection': selection}
    return [sys.executable, '-I', '-B', str(_WORKER), json.dumps(config)]


def _exchange(process, raw, deadline, cancelled):
    output = bytearray()
    offset = 0
    with selectors.DefaultSelector() as selector:
        for pipe, event in ((process.stdin, selectors.EVENT_WRITE),
                            (process.stdout, selectors.EVENT_READ)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, event)
        reading = True
        while reading or process.poll() is None:
            if cancelled is not None and cancelled.is_set():
                raise ValueError(MESSAGES['cancelled'])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError(MESSAGES['timeout'])
            for key, _ in selector.select(min(.05, remaining)):
                pipe = key.fileobj
                if pipe is process.stdin:
                    try:
                        offset += os.write(pipe.fileno(), memoryview(raw)[offset:offset + 65536])
                    except BrokenPipeError:
                        offset = len(raw)
                    if offset == len(raw):
                        selector.unregister(pipe)
                        pipe.close()
                else:
                    chunk = os.read(pipe.fileno(), 65536)
                    if not chunk:
                        selector.unregister(pipe)
                        reading = False
                    else:
                        if len(output) + len(chunk) > MAX_RESULT_BYTES:
                            raise ValueError(MESSAGES['resource'])
                        output.extend(chunk)
        return bytes(output)


def _decode(raw, selection):
    try:
        result = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError(MESSAGES['unreadable']) from None
    if not isinstance(result, dict):
        raise ValueError(MESSAGES['unreadable'])
    if result.get('ok') is False:
        code = result.get('error')
        raise ValueError(MESSAGES.get(code, MESSAGES['unreadable']) if isinstance(code, str)
                         else MESSAGES['unreadable'])
    count, pages = result.get('page_count'), result.get('pages')
    if result.get('ok') is not True or type(count) is not int or not 1 <= count <= MAX_PAGES:
        raise ValueError(MESSAGES['unreadable'])
    if selection == 'second' and count < 2:
        raise ValueError(MESSAGES['unreadable'])
    expected = {str(i) for i in range(count)} if selection == 'all' else {'0' if selection == 'first' else '1'}
    if not isinstance(pages, dict) or set(pages) != expected:
        raise ValueError(MESSAGES['unreadable'])
    if any(not isinstance(text, str) for text in pages.values()):
        raise ValueError(MESSAGES['unreadable'])
    if sum(map(len, pages.values())) > MAX_TEXT:
        raise ValueError(MESSAGES['text'])
    return count, {int(index): text for index, text in pages.items()}


def read_native(raw, *, selection='all', cancelled=None):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError(MESSAGES['bytes'])
    if not raw.startswith(b'%PDF-'):
        raise ValueError('This is not a PDF file. For private links, select the PDF from your device.')
    if selection not in ('all', 'first', 'second'):
        raise ValueError(MESSAGES['unreadable'])
    if not SUPPORTED:
        raise ValueError(MESSAGES['unavailable'])
    if cancelled is not None and cancelled.is_set():
        raise ValueError(MESSAGES['cancelled'])
    if not _SLOT.acquire(blocking=False):
        raise PDFBusy('Another PDF is being read. Try again shortly or continue manually.')
    process = None
    release = True
    try:
        deadline = time.monotonic() + LIMITS.wall_seconds
        # No cookies, provider/session secrets, inherited DB handles or shell.
        process = subprocess.Popen(_command(LIMITS, selection), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True,
            start_new_session=True, cwd='/', env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
        output = _exchange(process, raw, deadline, cancelled)
        if process.returncode:
            raise ValueError(MESSAGES['resource'])
        return _decode(output, selection)
    except (OSError, subprocess.SubprocessError):
        raise ValueError(MESSAGES['unavailable']) from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            for pipe in (process.stdin, process.stdout):
                pipe.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Fail closed if the OS delays reaping: no replacement parser
                # may start until this process has actually ended.
                release = False
                def reap():
                    try:
                        process.wait()
                    finally:
                        _SLOT.release()
                threading.Thread(target=reap, daemon=True).start()
        if release:
            _SLOT.release()
