"""Exercise actual scanned PDF rendering/OCR as well as bounded failure paths."""
import io
import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import documents_ocr as ocr
import ocr_engine
import ocr_process
import ocr_tesseract
import documents_reader as reader


def scanned_pdf(mixed=False):
    image = Image.new('RGB', (1700, 2200), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('DejaVuSans.ttf', 42)
    for y, line in enumerate(['MEMORANDUM', 'Subject: Staff orientation', 'From: Training Office',
                              'Date: October 17, 2026', 'Deadline: November 2, 2026', 'DTRAK: ABC-123']):
        draw.text((100, 130 + y * 90), line, font=font, fill='black')
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(612, 792))
    if mixed:
        c.drawString(50, 700, 'This is a typed cover page with enough native text to avoid unnecessary OCR processing.')
        c.showPage()
    c.drawImage(ImageReader(image), 0, 0, 612, 792)
    c.save()
    image.close()
    return out.getvalue()


@pytest.mark.skipif(not shutil.which('tesseract'), reason='Install Tesseract for real OCR integration')
@pytest.mark.parametrize('mixed', [False, True])
def test_real_scanned_pdf_fields_and_page_evidence(mixed):
    result = reader.read_pdf(scanned_pdf(mixed))
    assert result['suggestions']['subject'] == 'Staff orientation'
    assert result['suggestions']['sender'] == 'Training Office'
    assert result['suggestions']['document_date'] == '2026-10-17'
    assert result['suggestions']['due_date'] == '2026-11-02'
    assert result['evidence']['subject'][0]['page'] == (2 if mixed else 1)
    assert result['reading']['ocr_pages'] == ([2] if mixed else [1])
    assert 'Staff orientation' in result['text_preview'][-1]['text']
    assert 'OCR was used on pages ' + ('2' if mixed else '1') in result['warnings'][0]


def test_ocr_png_input_and_worker_result(monkeypatch):
    def run(png, deadline, **kwargs):
        assert png.startswith(b'\x89PNG')
        return b'Subject: Read in memory'
    monkeypatch.setattr(ocr_tesseract, 'run', run)
    result = ocr_engine.extract(scanned_pdf(), {'mode': 'pdf', 'indices': [0], 'seconds': 45})
    assert result == {'pages': {'0': 'Subject: Read in memory'}, 'subjects': {}}


@pytest.mark.parametrize('error, code', [(FileNotFoundError(), 'unavailable'),
    (subprocess.TimeoutExpired('tesseract', 15), 'timeout'),
    (subprocess.CalledProcessError(1, 'tesseract'), 'unreadable')])
def test_ocr_engine_failure_codes_are_fixed(monkeypatch, error, code):
    def run(*args, **kwargs): raise error
    monkeypatch.setattr(ocr_tesseract, 'run', run)
    with pytest.raises(ValueError, match='^' + code + '$'):
        ocr_engine.extract(scanned_pdf(), {'mode': 'pdf', 'indices': [0], 'seconds': 45})


def test_ocr_page_and_concurrency_limits():
    with pytest.raises(ValueError, match='more than 10'): ocr.read_pages(b'', list(range(11)))
    ocr_process._SLOT.acquire()
    try:
        with pytest.raises(ValueError, match='Another'): ocr.read_pages(scanned_pdf(), [0])
    finally:
        ocr_process._SLOT.release()


def test_scanned_upload_creates_no_records(app_mod, viewer, monkeypatch):
    import re
    import storage as st
    c = st.connect(app_mod.DB)
    old = st.get_setting(c, 'documents.enabled', '0')
    st.set_setting(c, 'documents.enabled', '1')
    tables = ('document', 'document_sequence', 'document_file_version', 'document_job', 'document_event', 'ai_interaction')
    counts = {t: c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in tables}
    try:
        page = viewer.get('/documents/new')
        csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', page.text)[1]
        monkeypatch.setattr(ocr, 'read_pages', lambda raw, indices, **kwargs: {0: 'Subject: Read the scanned document'})
        response = viewer.post('/documents/intake/read', content=scanned_pdf(),
            headers={'content-type': 'application/pdf', 'x-csrf-token': csrf})
        assert response.status_code == 200, response.text
        assert response.json()['suggestions']['subject'] == 'Read the scanned document'
        assert response.headers['cache-control'] == 'no-store'
        assert counts == {t: c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in tables}
    finally:
        st.set_setting(c, 'documents.enabled', old); c.close()
