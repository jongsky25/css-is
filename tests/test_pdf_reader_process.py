"""Real subprocess failures and OS resource limits, using synthetic PDF data."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import os
from pathlib import Path
import sys
import threading
import time

import pytest
from reportlab.pdfgen import canvas

import documents_reader as reader
import pdf_reader_process as worker


def pdf(*texts):
    out = io.BytesIO()
    document = canvas.Canvas(out)
    for text in texts or ('Subject: A normal document with enough native text to avoid OCR',):
        for index, line in enumerate(text.splitlines()):
            document.drawString(40, 760 - index * 14, line)
        document.showPage()
    document.save()
    return out.getvalue()


@pytest.fixture
def processes(monkeypatch):
    original = worker.subprocess.Popen
    created = []
    started = threading.Event()

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        created.append(process)
        started.set()
        return process

    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    yield created, started
    for process in created:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def inject(monkeypatch, behavior):
    """Replace only the parser constructor, after the real worker sets limits.

    No production fault flag/environment switch exists. The subprocess still
    executes the shipped main(), limits, stdin and JSON boundary.
    """
    original = worker._command
    script = '''import runpy,sys,types,os,time
namespace=runpy.run_path(sys.argv[1])
def parse(*args,**kwargs):
BEHAVIOR
sys.modules['pypdf']=types.SimpleNamespace(PdfReader=parse)
sys.argv=sys.argv[1:]
namespace['main']()
'''.replace('BEHAVIOR', '\n'.join('    '+line for line in behavior.splitlines()))

    def command(limits, selection):
        normal = original(limits, selection)
        return [sys.executable, '-I', '-B', '-c', script, normal[-2], normal[-1]]

    monkeypatch.setattr(worker, '_command', command)


def test_normal_multipage_and_scoped_reads(processes):
    raw = pdf('Subject: First native page has enough words to avoid OCR',
              'From: Another native page with enough words for extraction')
    count, pages = worker.read_native(raw)
    assert count == 2 and sorted(pages) == [0, 1]
    assert 'First native page' in pages[0] and 'Another native page' in pages[1]
    assert set(worker.read_native(raw, selection='first')[1]) == {0}
    assert set(worker.read_native(raw, selection='second')[1]) == {1}
    assert all(process.returncode == 0 for process in processes[0])


def test_fifty_native_pages_remain_supported():
    raw = pdf(*(f'Subject: Native page {i} has enough ordinary text to avoid OCR' for i in range(50)))
    count, pages = worker.read_native(raw)
    assert count == len(pages) == 50


def test_unicode_text_survives_the_bounded_json_pipe():
    assert 'Réunion' in worker.read_native(pdf('Subject: Réunion for staff orientation and updated guidelines'))[1][0]


@pytest.mark.parametrize('scanned_slip', [False, True])
def test_link_reads_document_after_native_or_scanned_dtrak_slip(monkeypatch, processes, scanned_slip):
    import documents_ocr
    slip = ('DTRAK\nORIGINATING OFFICE: Example Office DATE: October 16, 2026\n'
            'TYPE OF DOCUMENT: Memorandum\nSUBJECT: Staff orientation and updated service guidelines')
    following = ('MEMORANDUM\nOctober 14, 2026\n'
                 'Subject: Staff orientation and updated service guidelines')
    raw = pdf('' if scanned_slip else slip, following, 'Date: October 20, 2026 - this third page must not be read')
    calls = []

    def ocr(_raw, indices, **kwargs):
        calls.append(indices)
        return {0: slip}

    monkeypatch.setattr(documents_ocr, 'read_pages', ocr)
    result = reader.read_pdf(raw, first_page=True)
    assert result['suggestions']['document_date'] == '2026-10-14'
    assert result['reading']['page_count'] == 2
    assert result['reading']['ocr_pages'] == ([1] if scanned_slip else [])
    assert calls == ([[0]] if scanned_slip else [])
    assert len(processes[0]) == 2


@pytest.mark.parametrize('behavior,message', [
    ('time.sleep(30)', 'timed out'),
    ('while True: pass', 'complex'),
    ('bytearray(512*1024*1024)', 'complex'),
    ('os._exit(17)', 'complex'),
    ('os.write(1,b"x"*(1024*1024+1)); time.sleep(30)', 'complex'),
    ('os.write(1,b"[]"); os._exit(0)', 'could not be read'),
    ('raise ValueError("PRIVATE-PDF-CONTENT-SENTINEL")', 'could not be read'),
])
def test_limits_crashes_output_bounds_and_recovery(monkeypatch, processes, behavior, message, caplog):
    created, _ = processes
    original = worker._command
    limits = worker.Limits(wall_seconds=.7 if behavior == 'time.sleep(30)' else 8,
                           cpu_seconds=1, memory_bytes=80*1024*1024)
    monkeypatch.setattr(worker, 'LIMITS', limits)
    inject(monkeypatch, behavior)
    with pytest.raises(ValueError, match=message) as error:
        worker.read_native(pdf())
    assert 'PRIVATE-PDF-CONTENT-SENTINEL' not in str(error.value) + caplog.text
    assert created[-1].returncode is not None
    monkeypatch.setattr(worker, '_command', original)
    monkeypatch.setattr(worker, 'LIMITS', worker.Limits())
    assert 'normal document' in worker.read_native(pdf())[1][0]


def test_bounded_concurrency_cancellation_and_reaping(monkeypatch, processes):
    created, started = processes
    original = worker._command
    inject(monkeypatch, 'time.sleep(30)')
    cancelled = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker.read_native, pdf(), cancelled=cancelled)
        assert started.wait(3)
        try:
            with pytest.raises(worker.PDFBusy, match='Another PDF'):
                worker.read_native(pdf())
            assert len(created) == 1  # rejected before another process/queue entry
        finally:
            cancelled.set()
        with pytest.raises(ValueError, match='cancelled'):
            future.result(timeout=3)
    assert created[0].returncode is not None
    monkeypatch.setattr(worker, '_command', original)
    assert worker.read_native(pdf())[0] == 1


@pytest.mark.parametrize('disconnect', [False, True])
def test_async_cancel_or_disconnect_stops_native_worker(monkeypatch, processes, disconnect):
    created, started = processes
    inject(monkeypatch, 'time.sleep(30)')

    async def scenario():
        async def disconnected():
            return started.is_set()
        task = asyncio.create_task(reader.read_pdf_async(pdf(),
            disconnected=disconnected if disconnect else None))
        assert await asyncio.to_thread(started.wait, 3)
        if not disconnect:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        deadline = time.monotonic() + 3
        while any(p.poll() is None for p in created) and time.monotonic() < deadline:
            await asyncio.sleep(.02)
        assert all(p.poll() is not None for p in created)

    asyncio.run(scenario())


def test_worker_has_no_parent_secrets_or_inherited_descriptors(monkeypatch):
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
return types.SimpleNamespace(is_encrypted=False,pages=[types.SimpleNamespace(extract_text=lambda:text)])'''
    try:
        inject(monkeypatch, behavior)
        assert worker.read_native(pdf())[1][0] == 'missing:closed'
    finally:
        for fd in (read_fd, write_fd, inherited):
            os.close(fd)


def test_compressed_text_limit_is_enforced_in_child(processes):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf())))
    page = writer.pages[0]
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf (' + b'A'*200_000 + b') Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    out = io.BytesIO(); writer.write(out)
    assert len(out.getvalue()) < 5000
    with pytest.raises(ValueError, match='too much text'):
        worker.read_native(out.getvalue())
    assert processes[0][-1].returncode == 0


def test_unrelated_http_request_and_busy_response_remain_available(app_mod, viewer, monkeypatch, processes):
    import re
    import storage as st
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    tables = ('document', 'document_job', 'document_event', 'ai_interaction')
    counts = {table: conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables}
    csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', viewer.get('/documents/new').text)[1]
    headers = {'Content-Type': 'application/pdf', 'X-CSRF-Token': csrf}
    inject(monkeypatch, 'time.sleep(30)')
    stop = []
    original = reader.read_pdf

    def record(*args, **kwargs):
        stop.append(kwargs['cancelled'])
        return original(*args, **kwargs)

    monkeypatch.setattr(reader, 'read_pdf', record)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(viewer.post, '/documents/intake/read', content=pdf(), headers=headers)
            assert processes[1].wait(3)
            try:
                assert viewer.get('/documents/new').status_code == 200
                assert not future.done()
                busy = viewer.post('/documents/intake/read', content=pdf(), headers=headers)
                assert busy.status_code == 429 and busy.headers['retry-after'] == '3'
                assert busy.headers['cache-control'] == 'no-store'
                assert len(processes[0]) == 1
            finally:
                stop[0].set()
            assert future.result(timeout=3).status_code == 400
        assert counts == {table: conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables}
    finally:
        conn.close()


def test_worker_is_in_the_deploy_payload():
    import deploy_hf
    assert Path(worker._WORKER).name in deploy_hf.ALLOW


def test_unavailable_limits_fail_closed(monkeypatch, processes):
    monkeypatch.setattr(worker, 'SUPPORTED', False)
    with pytest.raises(ValueError, match='unavailable'):
        worker.read_native(pdf())
    assert not processes[0]


def test_resource_setup_failure_does_not_fall_back_to_web_process(monkeypatch, processes):
    original = worker._command
    script = '''import runpy,sys
namespace=runpy.run_path(sys.argv[1])
def fail(config): raise OSError('synthetic unsupported limit')
namespace['main'].__globals__['apply_limits']=fail
sys.argv=sys.argv[1:]
namespace['main']()
'''

    def command(limits, selection):
        normal = original(limits, selection)
        return [sys.executable, '-I', '-B', '-c', script, normal[-2], normal[-1]]

    monkeypatch.setattr(worker, '_command', command)
    with pytest.raises(ValueError, match='unavailable'):
        worker.read_native(pdf())
    assert processes[0][-1].returncode == 0
    monkeypatch.setattr(worker, '_command', original)
    assert worker.read_native(pdf())[0] == 1


def test_delayed_reaping_keeps_capacity_reserved(monkeypatch, processes):
    original = worker.subprocess.Popen
    release = threading.Event()
    waiting = threading.Event()

    def delayed(*args, **kwargs):
        process = original(*args, **kwargs)
        wait = process.wait
        calls = 0

        def reap(timeout=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise worker.subprocess.TimeoutExpired('synthetic delayed reap', timeout)
            if calls == 2:
                waiting.set()
                release.wait(3)
            return wait(timeout=timeout)

        process.wait = reap
        return process

    monkeypatch.setattr(worker.subprocess, 'Popen', delayed)
    try:
        assert worker.read_native(pdf())[0] == 1
        assert waiting.wait(2)
        with pytest.raises(worker.PDFBusy):
            worker.read_native(pdf())
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while not worker._SLOT.acquire(blocking=False):
        assert time.monotonic() < deadline
        time.sleep(.02)
    worker._SLOT.release()
