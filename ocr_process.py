"""One cancellable OCR process group per application process; no parser queue."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

from bounded_pipes import PipeLimit, exchange
from pdf_reader_process import MAX_BYTES, MAX_PAGES, MAX_TEXT, PDFBusy

MAX_OCR_PAGES = 10
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_RESULT_BYTES = 2 * 1024 * 1024
SUPPORTED = sys.platform == 'linux'
_SLOT = threading.BoundedSemaphore(1)
_WORKER = Path(__file__).resolve().with_name('ocr_worker.py')


@dataclass(frozen=True)
class Limits:
    wall_seconds: float = 45
    cpu_seconds: int = 35
    memory_bytes: int = 512 * 1024 * 1024


LIMITS = Limits()
MESSAGES = {
    'bytes': 'Choose a PDF no larger than 20 MiB.',
    'image_bytes': 'A page image must be no larger than 2 MiB.',
    'image': 'Use a JPEG or PNG page image with at most 4 million pixels.',
    'pages': 'This PDF needs OCR on more than 10 pages. Split it into smaller PDFs or enter the details manually.',
    'size': 'This PDF has an unsupported page size. Continue manually.',
    'text': 'This reading contains too much text. Choose fewer pages or continue manually.',
    'empty': 'No readable text was found on this page. Try a clearer copy.',
    'resource': 'This scan is too complex to read safely. Choose fewer pages or continue manually.',
    'timeout': 'Reading the scan timed out. Try fewer pages or continue manually.',
    'cancelled': 'Scan reading was cancelled.',
    'unavailable': 'Protected OCR is unavailable on this server. Continue manually or try again later.',
    'unreadable': 'The scanned page could not be read. Retry it or continue manually.',
}


def _command(limits, mode, indices):
    config = {'cpu': limits.cpu_seconds, 'memory': limits.memory_bytes,
              'seconds': limits.wall_seconds, 'mode': mode, 'indices': indices,
              'max_bytes': MAX_BYTES if mode == 'pdf' else MAX_IMAGE_BYTES,
              'tesseract': shutil.which('tesseract', path=os.defpath) or '/usr/bin/tesseract'}
    return [sys.executable, '-I', '-B', str(_WORKER), json.dumps(config)]


def _subject(reading):
    if reading is None:
        return None
    if not isinstance(reading, dict):
        raise ValueError(MESSAGES['unreadable'])
    result = {}
    for key, limit in (('status', 30), ('method', 40), ('value', 500), ('raw', 1500), ('reason', 300)):
        value = reading.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(MESSAGES['unreadable'])
        result[key] = value
    if result['status'] not in ('read', 'empty', 'rejected', 'failed', 'region_not_found') or result['method'] != 'dtrak_subject_cell':
        raise ValueError(MESSAGES['unreadable'])
    if 'box' in reading:
        box = reading['box']
        if (not isinstance(box, list) or len(box) != 4 or
                any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in box) or
                not (box[0] < box[2] and box[1] < box[3])):
            raise ValueError(MESSAGES['unreadable'])
        result['box'] = box
    if 'preview' in reading:
        preview = reading['preview']
        if (not isinstance(preview, str) or len(preview) > 200_000 or
                not re.fullmatch(r'data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}', preview)):
            raise ValueError(MESSAGES['unreadable'])
        result['preview'] = preview
    return result


def _decode(output, mode, indices):
    try:
        result = json.loads(output)
    except (ValueError, RecursionError):
        raise ValueError(MESSAGES['unreadable']) from None
    if not isinstance(result, dict):
        raise ValueError(MESSAGES['unreadable'])
    if result.get('ok') is False:
        code = result.get('error')
        raise ValueError(MESSAGES.get(code, MESSAGES['unreadable']) if isinstance(code, str) else MESSAGES['unreadable'])
    if result.get('ok') is not True:
        raise ValueError(MESSAGES['unreadable'])
    if mode == 'image':
        text = result.get('text')
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            raise ValueError(MESSAGES['unreadable'])
        return {'text': text, 'subject_reading': _subject(result.get('subject_reading'))}
    pages, subjects = result.get('pages'), result.get('subjects')
    expected = {str(i) for i in indices}
    if (not isinstance(pages, dict) or set(pages) != expected or
            any(not isinstance(text, str) for text in pages.values()) or
            not isinstance(subjects, dict) or not set(subjects) <= expected):
        raise ValueError(MESSAGES['unreadable'])
    if sum(map(len, pages.values())) > MAX_TEXT:
        raise ValueError(MESSAGES['text'])
    return {int(i): text for i, text in pages.items()}, {int(i): _subject(s) for i, s in subjects.items()}


def _kill_group(process):
    # Always terminate the group, even if its leader crashed/exited first.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _reap(process):
    process.wait()
    # The shipped web process is PID 1. Reap any group members it adopted;
    # another init/subreaper owns these descendants in other environments.
    try:
        while os.waitpid(-process.pid, os.WNOHANG)[0]:
            pass
    except ChildProcessError:
        pass


def _live_group(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    found = False
    try:
        entries = list(Path('/proc').iterdir())
    except OSError:
        return True
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(') ', 1)[1].split()
            if int(fields[2]) == pid:
                found = True
                if fields[0] not in ('Z', 'X'):
                    return True
        except (OSError, ValueError, IndexError):
            continue
    # If group inspection is unavailable, retain capacity conservatively.
    return not found


def read(raw, *, mode='pdf', indices=None, cancelled=None):
    indices = [] if indices is None else indices
    if mode not in ('pdf', 'image'):
        raise ValueError(MESSAGES['unreadable'])
    if (mode == 'pdf' and (not isinstance(indices, (list, tuple)) or not indices or
            len(indices) > MAX_OCR_PAGES or any(type(i) is not int or not 0 <= i < MAX_PAGES for i in indices) or
            len(set(indices)) != len(indices))):
        raise ValueError(MESSAGES['pages'])
    limit = MAX_BYTES if mode == 'pdf' else MAX_IMAGE_BYTES
    if not raw or len(raw) > limit:
        raise ValueError(MESSAGES['bytes' if mode == 'pdf' else 'image_bytes'])
    if mode == 'pdf' and not raw.startswith(b'%PDF-'):
        raise ValueError(MESSAGES['unreadable'])
    if not SUPPORTED:
        raise ValueError(MESSAGES['unavailable'])
    if cancelled is not None and cancelled.is_set():
        raise ValueError(MESSAGES['cancelled'])
    if not _SLOT.acquire(blocking=False):
        raise PDFBusy('Another scan is being read. Try again shortly or continue manually.')
    process, release = None, True
    try:
        deadline = time.monotonic() + LIMITS.wall_seconds
        process = subprocess.Popen(_command(LIMITS, mode, indices), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True,
            start_new_session=True, cwd='/', env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                'OMP_THREAD_LIMIT': '1', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'})
        output = exchange(process, raw, deadline=deadline, max_output=MAX_RESULT_BYTES, cancelled=cancelled)
        if process.returncode:
            raise ValueError(MESSAGES['resource'])
        return _decode(output, mode, indices)
    except PipeLimit as exc:
        raise ValueError(MESSAGES[exc.code]) from None
    except (OSError, subprocess.SubprocessError):
        raise ValueError(MESSAGES['unavailable']) from None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    process.send_signal(signal.SIGTERM)
                    process.wait(timeout=.2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
            _kill_group(process)
            process.stdin.close()
            process.stdout.close()
            try:
                process.wait(timeout=2)
                _reap(process)
                if _live_group(process.pid):
                    raise subprocess.TimeoutExpired('OCR process group', 2)
                _reap(process)
            except subprocess.TimeoutExpired:
                release = False
                def reap():
                    try:
                        _reap(process)
                        while _live_group(process.pid):
                            _kill_group(process)
                            time.sleep(.05)
                        _reap(process)
                    finally:
                        _SLOT.release()
                threading.Thread(target=reap, daemon=True).start()
        if release:
            _SLOT.release()
