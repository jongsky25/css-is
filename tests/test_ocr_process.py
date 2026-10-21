"""Real worker, OS limits and OCR child-process cleanup, using synthetic inputs."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from PIL import Image
import pytest

import documents_ocr
import documents_page_reader as pages
import documents_reader as reader
import ocr_process as worker
import ocr_tesseract
from test_documents_ocr import scanned_pdf
from test_documents_page_reader import page_image


def wait_until(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(.02)


@pytest.fixture
def processes(monkeypatch):
    original = subprocess.Popen
    created, started = [], threading.Event()
    def launch(args, **kwargs):
        process = original(args, **kwargs)
        if str(worker._WORKER) in args:
            created.append(process)
            started.set()
        return process
    monkeypatch.setattr(subprocess, 'Popen', launch)
    yield created, started
    for process in created:
        worker._kill_group(process)
        process.wait(timeout=3)


def inject(monkeypatch, behavior):
    """Replace extraction AFTER the shipped main applies real OS limits.

    This is a test-only command seam, with no runtime fault flags or env knobs.
    """
    original = worker._command
    script = '''import runpy,sys,os,time,subprocess,types
namespace=runpy.run_path(sys.argv[1])
apply=namespace['apply_limits']
def extract(raw,config):
BEHAVIOR
def setup(config):
    apply(config)
    sys.path.insert(0,os.path.dirname(sys.argv[1]))
    import ocr_engine
    ocr_engine.extract=extract
namespace['main'].__globals__['apply_limits']=setup
sys.argv=sys.argv[1:]
namespace['main']()
'''.replace('BEHAVIOR', '\n'.join('    '+line for line in behavior.splitlines()))
    # setup runs after sys.argv was shifted: capture the script path first.
    script = script.replace("namespace=runpy.run_path(sys.argv[1])", "worker_path=sys.argv[1]\nnamespace=runpy.run_path(worker_path)")
    script = script.replace('os.path.dirname(sys.argv[1])', 'os.path.dirname(worker_path)')
    def command(limits, mode, indices):
        normal = original(limits, mode, indices)
        return [sys.executable, '-I', '-B', '-c', script, normal[-2], normal[-1]]
    monkeypatch.setattr(worker, '_command', command)


def executable(monkeypatch, tmp_path, code):
    script = tmp_path / 'synthetic-tesseract'
    script.write_text('#!' + sys.executable + '\n' + code + '\n')
    script.chmod(0o700)
    original = worker._command
    def command(limits, mode, indices):
        normal = original(limits, mode, indices)
        config = json.loads(normal[-1])
        config['tesseract'] = str(script)
        return normal[:-1] + [json.dumps(config)]
    monkeypatch.setattr(worker, '_command', command)
    return script


def children(process):
    result = []
    # Some managed Linux environments omit /proc/PID/task/TID/children.
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(') ', 1)[1].split()
            if int(fields[1]) == process.pid:
                result.append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return result


def active(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[0] not in ('Z', 'X')
    except FileNotFoundError:
        return False


@pytest.mark.parametrize('behavior,message', [
    ('time.sleep(30)', 'timed out'),
    ('while True: pass', 'complex'),
    ('bytearray(1024*1024*1024)', 'complex'),
    ('os._exit(17)', 'complex'),
    ('os.write(1,b"x"*(2*1024*1024+1)); time.sleep(30)', 'complex'),
    ('os.write(1,b"[]"); os._exit(0)', 'could not be read'),
    ('raise RuntimeError("PRIVATE-SCAN-CONTENT")', 'could not be read'),
])
def test_worker_limits_crashes_output_and_recovery(monkeypatch, processes, behavior, message, caplog):
    original = worker._command
    monkeypatch.setattr(worker, 'LIMITS', worker.Limits(
        wall_seconds=.7 if behavior == 'time.sleep(30)' else 8,
        cpu_seconds=1, memory_bytes=96*1024*1024))
    inject(monkeypatch, behavior)
    with pytest.raises(ValueError, match=message) as error:
        pages.read_image(page_image())
    assert 'PRIVATE-SCAN-CONTENT' not in str(error.value) + caplog.text
    assert processes[0][-1].returncode is not None
    monkeypatch.setattr(worker, '_command', original)
    monkeypatch.setattr(worker, 'LIMITS', worker.Limits())
    assert 'Page selection test' in pages.read_image(page_image())['text']


@pytest.mark.parametrize('mode', ['pdf', 'image'])
def test_worker_has_no_parent_secret_or_inherited_descriptor(monkeypatch, mode):
    import fcntl
    read_fd, write_fd = os.pipe()
    inherited = fcntl.fcntl(read_fd, fcntl.F_DUPFD, 64)
    os.set_inheritable(inherited, True)
    monkeypatch.setenv('CSS_SESSION_SECRET', 'PRIVATE-SESSION-SENTINEL')
    behavior = f'''try:
    os.read({inherited},1)
    descriptor='open'
except OSError:
    descriptor='closed'
text=os.environ.get('CSS_SESSION_SECRET','missing')+':'+descriptor
return {{'text':text,'subject_reading':None}} if config['mode']=='image' else {{'pages':{{'0':text}},'subjects':{{}}}}'''
    try:
        inject(monkeypatch, behavior)
        result = worker.read(page_image() if mode == 'image' else scanned_pdf(), mode=mode, indices=[0])
        assert (result['text'] if mode == 'image' else result[0][0]) == 'missing:closed'
    finally:
        for fd in (read_fd, write_fd, inherited):
            os.close(fd)


@pytest.mark.parametrize('disconnect', [False, True])
@pytest.mark.parametrize('mode', ['pdf', 'image'])
def test_async_cancellation_stops_tesseract_and_reaps_worker(monkeypatch, tmp_path, processes, disconnect, mode):
    original = worker._command
    executable(monkeypatch, tmp_path, 'import sys,time\nsys.stdin.buffer.read()\ntime.sleep(30)')
    created, started = processes
    seen = []
    async def scenario():
        async def disconnected():
            return bool(seen)
        function = pages.read_image_async if mode == 'image' else reader.read_pdf_async
        raw = page_image() if mode == 'image' else scanned_pdf()
        task = asyncio.create_task(function(raw, disconnected=disconnected if disconnect else None))
        assert await asyncio.to_thread(started.wait, 3)
        await asyncio.to_thread(wait_until, lambda: bool(children(created[-1])))
        seen.extend(children(created[-1]))
        if not disconnect:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.to_thread(wait_until, lambda: created[-1].poll() is not None and not any(map(active, seen)))
    asyncio.run(scenario())
    assert created[-1].returncode is not None and seen
    monkeypatch.setattr(worker, '_command', original)
    wait_until(lambda: worker._SLOT.acquire(blocking=False))
    worker._SLOT.release()
    assert 'Page selection test' in pages.read_image(page_image())['text']


def test_wall_timeout_kills_tesseract_group(monkeypatch, tmp_path, processes):
    executable(monkeypatch, tmp_path, 'import sys,time,signal\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nsys.stdin.buffer.read()\ntime.sleep(30)')
    monkeypatch.setattr(worker, 'LIMITS', worker.Limits(wall_seconds=1))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(pages.read_image, page_image())
        assert processes[1].wait(3)
        wait_until(lambda: bool(children(processes[0][-1])))
        descendants = children(processes[0][-1])
        with pytest.raises(ValueError, match='timed out'):
            future.result(timeout=4)
    wait_until(lambda: not any(map(active, descendants)))
    assert processes[0][-1].returncode is not None


@pytest.mark.parametrize('behavior,message', [
    ('import sys;sys.stdin.buffer.read();sys.stdout.write("x"*(2*1024*1024+1))', 'complex'),
    ('import sys;sys.stdin.buffer.read();sys.stdout.write("x"*100001)', 'too much text'),
    ('import sys;sys.stderr.write("PRIVATE-OCR-ERROR");sys.exit(3)', 'could not be read'),
])
def test_tesseract_output_is_bounded_and_errors_private(monkeypatch, tmp_path, processes, behavior, message, caplog):
    original = worker._command
    executable(monkeypatch, tmp_path, behavior)
    with pytest.raises(ValueError, match=message) as error:
        pages.read_image(page_image())
    assert 'PRIVATE-OCR-ERROR' not in str(error.value) + caplog.text
    assert processes[0][-1].returncode is not None
    monkeypatch.setattr(worker, '_command', original)
    assert 'Page selection test' in pages.read_image(page_image())['text']


def test_tesseract_uses_only_pipes_and_fixed_options(monkeypatch, tmp_path):
    script = tmp_path / 'tesseract'
    script.write_text('#!' + sys.executable + '\nimport sys\nassert sys.stdin.buffer.read().startswith(b"\\x89PNG")\nsys.stdout.write("Subject: Read in memory")\n')
    script.chmod(0o700)
    monkeypatch.setattr(ocr_tesseract, 'EXECUTABLE', str(script))
    original, captured = subprocess.Popen, []
    def launch(args, **kwargs):
        assert args == [str(script), 'stdin', 'stdout', '-l', 'eng', '--psm', '3', '-c', 'debug_file=/dev/null']
        assert kwargs == dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True)
        process = original(args, **kwargs)
        captured.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', launch)
    assert ocr_tesseract.run(b'\x89PNG synthetic', time.monotonic() + 3) == b'Subject: Read in memory'
    assert captured[-1].returncode == 0


def test_renderer_can_be_stopped_before_ocr(monkeypatch, processes):
    original = worker._command
    # The real PDFium opens a valid PDF; its render call is replaced only in
    # the test child to model a native render that never returns.
    script = '''import runpy,sys,os,time
path=sys.argv[1];namespace=runpy.run_path(path);apply=namespace['apply_limits']
def setup(config):
    apply(config)
    sys.path.insert(0,os.path.dirname(path))
    import ocr_engine
    ocr_engine.render=lambda page: time.sleep(30)
namespace['main'].__globals__['apply_limits']=setup
sys.argv=sys.argv[1:];namespace['main']()
'''
    def command(limits, mode, indices):
        normal = original(limits, mode, indices)
        return [sys.executable, '-I', '-B', '-c', script, normal[-2], normal[-1]]
    monkeypatch.setattr(worker, '_command', command)
    monkeypatch.setattr(worker, 'LIMITS', worker.Limits(wall_seconds=.7))
    with pytest.raises(ValueError, match='timed out'):
        documents_ocr.read_pages(scanned_pdf(), [0])
    assert processes[0][-1].returncode is not None


def test_missing_tesseract_and_limits_fail_closed(monkeypatch, tmp_path, processes):
    script = executable(monkeypatch, tmp_path, 'pass')
    script.unlink()
    with pytest.raises(ValueError, match='unavailable'):
        pages.read_image(page_image())
    monkeypatch.setattr(worker, 'SUPPORTED', False)
    before = len(processes[0])
    with pytest.raises(ValueError, match='unavailable'):
        pages.read_image(page_image())
    assert len(processes[0]) == before


def test_worker_payload_is_complete():
    import deploy_hf
    assert {'ocr_worker.py', 'ocr_engine.py', 'ocr_tesseract.py', 'ocr_process.py', 'bounded_pipes.py'} <= set(deploy_hf.ALLOW)


def test_tesseract_inherits_limits_and_clean_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('CSS_SESSION_SECRET', 'PRIVATE-SESSION-SENTINEL')
    executable(monkeypatch, tmp_path, '''import sys,os,json,resource
sys.stdin.buffer.read()
sys.stdout.write(json.dumps({'cpu':resource.getrlimit(resource.RLIMIT_CPU),
 'memory':resource.getrlimit(resource.RLIMIT_AS),'core':resource.getrlimit(resource.RLIMIT_CORE),
 'files':resource.getrlimit(resource.RLIMIT_FSIZE),'descriptors':resource.getrlimit(resource.RLIMIT_NOFILE),
 'secret':os.environ.get('CSS_SESSION_SECRET'),'threads':os.environ.get('OMP_THREAD_LIMIT')}))''')
    result = json.loads(pages.read_image(page_image())['text'])
    assert result == dict(cpu=[35, 36], memory=[512*1024*1024]*2, core=[0, 0],
                          files=[0, 0], descriptors=[32, 32], secret=None, threads='1')


@pytest.mark.parametrize('result', [
    {'ok': True, 'text': 1},
    {'ok': True, 'text': 'valid', 'subject_reading': {'status': 'read', 'method': 'dtrak_subject_cell', 'preview': 'javascript:invalid'}},
    {'ok': True, 'text': 'valid', 'subject_reading': {'status': 'read', 'method': 'dtrak_subject_cell', 'box': [0, 0, float('nan'), 1]}},
])
def test_bad_worker_response_is_rejected(monkeypatch, result):
    inject(monkeypatch, f'return {result!r}'.replace('nan', "float('nan')"))
    with pytest.raises(ValueError, match='could not be read'):
        pages.read_image(page_image())


def test_resource_setup_failure_does_not_use_web_process(monkeypatch, processes):
    original = worker._command
    script = '''import runpy,sys
namespace=runpy.run_path(sys.argv[1])
def fail(config): raise OSError('synthetic resource failure')
namespace['main'].__globals__['apply_limits']=fail
sys.argv=sys.argv[1:];namespace['main']()
'''
    def command(limits, mode, indices):
        normal = original(limits, mode, indices)
        return [sys.executable, '-I', '-B', '-c', script, normal[-2], normal[-1]]
    monkeypatch.setattr(worker, '_command', command)
    with pytest.raises(ValueError, match='unavailable'):
        pages.read_image(page_image())
    assert processes[0][-1].returncode == 0
    monkeypatch.setattr(worker, '_command', original)
    assert 'Page selection test' in pages.read_image(page_image())['text']


def test_delayed_group_cleanup_keeps_capacity_reserved(monkeypatch):
    original = worker._live_group
    release, waiting = threading.Event(), threading.Event()
    def delayed(pid):
        if not release.is_set():
            waiting.set()
            return True
        return original(pid)
    monkeypatch.setattr(worker, '_live_group', delayed)
    try:
        assert 'Page selection test' in pages.read_image(page_image())['text']
        assert waiting.wait(2)
        with pytest.raises(worker.PDFBusy):
            documents_ocr.read_pages(scanned_pdf(), [0])
    finally:
        release.set()
    wait_until(lambda: worker._SLOT.acquire(blocking=False))
    worker._SLOT.release()


def test_crashed_worker_leaves_no_live_descendants(monkeypatch, processes):
    inject(monkeypatch, '''subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os._exit(17)''')
    with pytest.raises(ValueError, match='complex'):
        pages.read_image(page_image())
    wait_until(lambda: not worker._live_group(processes[0][-1].pid))
    wait_until(lambda: worker._SLOT.acquire(blocking=False))
    worker._SLOT.release()


def test_ten_scanned_pages_supported():
    from pypdf import PdfReader, PdfWriter
    source = PdfReader(io.BytesIO(scanned_pdf())).pages[0]
    document = PdfWriter()
    for _ in range(10):
        document.add_page(source)
    out = io.BytesIO(); document.write(out)
    readings = documents_ocr.read_pages(out.getvalue(), list(range(10)))
    assert len(readings) == 10 and all('Staff orientation' in text for text in readings.values())


def test_scanned_dtrak_subject_preview_crosses_the_worker_boundary():
    from test_documents_dtrak import SUBJECT, fixture
    result = pages.read_image(fixture())
    reading = result['subject_reading']
    assert reading['status'] == 'read' and reading['value'] == SUBJECT
    assert reading['preview'].startswith('data:image/jpeg;base64,')
    assert 0 <= reading['box'][0] < reading['box'][2] <= 1


@pytest.mark.parametrize('first_mode', ['pdf', 'image'])
def test_http_busy_is_shared_between_pdf_and_page_and_other_pages_work(app_mod, viewer, monkeypatch, processes, first_mode):
    import re
    import storage as st
    conn = st.connect(app_mod.DB)
    old = st.get_setting(conn, 'documents.enabled', '0')
    st.set_setting(conn, 'documents.enabled', '1')
    tables = ('document', 'document_sequence', 'document_file_version', 'document_job', 'document_event', 'ai_interaction')
    counts = {t: conn.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in tables}
    csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', viewer.get('/documents/new').text)[1]
    stop = []
    original = worker.read
    def record(*args, **kwargs):
        stop.append(kwargs['cancelled'])
        return original(*args, **kwargs)
    monkeypatch.setattr(pages, 'read', record)
    monkeypatch.setattr(documents_ocr, 'read', record)
    inject(monkeypatch, 'time.sleep(30)')
    raw = scanned_pdf() if first_mode == 'pdf' else page_image()
    path = '/documents/intake/read' if first_mode == 'pdf' else '/documents/intake/page'
    headers = {'content-type': 'application/pdf' if first_mode == 'pdf' else 'image/jpeg', 'x-csrf-token': csrf}
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(viewer.post, path, content=raw, headers=headers)
            assert processes[1].wait(3)
            try:
                assert viewer.get('/documents/new').status_code == 200 and not future.done()
                busy_path = '/documents/intake/page' if first_mode == 'pdf' else '/documents/intake/read'
                busy_raw = page_image() if first_mode == 'pdf' else scanned_pdf()
                busy_type = 'image/jpeg' if first_mode == 'pdf' else 'application/pdf'
                busy = viewer.post(busy_path, content=busy_raw, headers={'content-type': busy_type, 'x-csrf-token': csrf})
                assert busy.status_code == 429 and busy.headers['retry-after'] == '3'
                assert busy.headers['cache-control'] == 'no-store'
                assert len(processes[0]) == 1
            finally:
                stop[0].set()
            assert future.result(timeout=3).status_code == 400
        assert counts == {t: conn.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in tables}
    finally:
        st.set_setting(conn, 'documents.enabled', old)
        conn.close()
