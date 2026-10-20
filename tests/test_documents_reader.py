import io
import socket
import pytest
from reportlab.pdfgen import canvas
import documents_reader as reader


def pdf(*lines):
    out = io.BytesIO()
    c = canvas.Canvas(out)
    text = c.beginText(50, 800)
    for line in lines:
        text.textLine(line)
    c.drawText(text)
    c.save()
    return out.getvalue()


def test_pdf_fields_evidence_and_ambiguity():
    result = reader.read_pdf(pdf('MEMORANDUM', 'Subject: Staff orientation', 'From: Training Office',
        'Date: October 17, 2026', 'Deadline: 2026-11-02', 'DTRAK: ABC-123'))
    assert result['suggestions'] == {'subject': 'Staff orientation', 'type': 'Memorandum',
        'sender': 'Training Office', 'document_date': '2026-10-17', 'due_date': '2026-11-02', 'references': 'DTRAK: ABC-123'}
    assert result['evidence']['subject'] == [{'page': 1, 'text': 'Subject: Staff orientation'}]
    result = reader.suggest(['Subject: One\nSubject: Two\nDate: 01/02/2026\nDeadline: tomorrow\nApprove this document'])
    assert result['suggestions'] == {}
    assert 'Multiple values' in result['warnings'][0]


def test_bad_scanned_encrypted_and_large_pdfs():
    from pypdf import PdfWriter
    for data in (b'', b'not pdf', b'%PDF-broken', b'%PDF-' + b'x' * reader.MAX_BYTES):
        with pytest.raises(ValueError): reader.read_pdf(data)
    writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
    out = io.BytesIO(); writer.write(out)
    with pytest.raises(ValueError, match='No readable text'): reader.read_pdf(out.getvalue())
    writer.encrypt('secret'); out = io.BytesIO(); writer.write(out)
    with pytest.raises(ValueError, match='Password'): reader.read_pdf(out.getvalue())
    writer = PdfWriter()
    for _ in range(51): writer.add_blank_page(width=100, height=100)
    out = io.BytesIO(); writer.write(out)
    with pytest.raises(ValueError, match='50 pages'): reader.read_pdf(out.getvalue())


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_private_dns_rejected(monkeypatch, address):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', (address, 443))])
    with pytest.raises(ValueError, match='public'): reader.public_target('https://example.test/doc.pdf')


@pytest.mark.parametrize('url', ['http://example.test/a', 'https://user:pass@example.test/a',
    'https://example.test:8443/a', 'file:///tmp/a', 'https://example.test/\r\nInjected'])
def test_invalid_links(url):
    with pytest.raises(ValueError): reader.public_target(url)


def test_redirects_checked_and_download_bounded(monkeypatch):
    checked = []
    def target(url):
        from urllib.parse import urlsplit
        checked.append(url)
        if 'private' in url: raise ValueError('private destination')
        return urlsplit(url), '93.184.216.34'
    class Response:
        status = 302
        def getheader(self, name): return 'https://private.test/a' if name == 'Location' else None
    class Connection:
        sock = None
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(reader, 'public_target', target)
    monkeypatch.setattr(reader, '_PinnedHTTPS', Connection)
    with pytest.raises(ValueError, match='private'): reader.fetch_pdf('https://public.test/a')
    assert len(checked) == 2
    Response.status = 200
    monkeypatch.setattr(Response, 'getheader', lambda self, name: str(reader.MAX_BYTES + 1) if name == 'Content-Length' else None)
    with pytest.raises(ValueError, match='20 MiB'): reader.fetch_pdf('https://public.test/a')


def test_intake_read_http_transient(app_mod, viewer, monkeypatch):
    import re
    import storage as st
    c = st.connect(app_mod.DB)
    old = st.get_setting(c, 'documents.enabled', '0')
    st.set_setting(c, 'documents.enabled', '1')
    tables = ('document', 'document_sequence', 'document_file_version', 'document_job',
              'document_event', 'ai_interaction')
    counts = {t: c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in tables}
    try:
        page = viewer.get('/documents/new')
        csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', page.text)[1]
        headers = {'content-type': 'application/pdf', 'x-csrf-token': csrf}
        raw = pdf('Subject: <script>alert(1)</script>', 'Date: 2026-10-17')
        result = viewer.post('/documents/intake/read', content=raw, headers=headers)
        assert result.status_code == 200, result.text
        assert result.headers['cache-control'] == 'no-store'
        assert result.json()['suggestions']['document_date'] == '2026-10-17'
        assert viewer.post('/documents/intake/read', content=raw, headers={'content-type': 'application/pdf'}).status_code == 403
        assert viewer.post('/documents/intake/read', content=b'x' * (reader.MAX_BYTES + 1), headers=headers).status_code == 400
        assert viewer.post('/documents/intake/read', content=b'%PDF-invalid', headers=headers).status_code == 400
        monkeypatch.setattr(reader, 'fetch_pdf', lambda url: raw)
        linked = viewer.post('/documents/intake/read', json={'url': 'https://example.test/a.pdf'}, headers={'x-csrf-token': csrf})
        assert linked.status_code == 200
        assert linked.json()['suggestions'] == result.json()['suggestions']
        assert any('Read the first page' in w for w in linked.json()['warnings'])
        received = []
        def record_size(data, **kwargs):
            received.append(len(data))
            return result.json()
        monkeypatch.setattr(reader, 'read_pdf', record_size)
        boundary = viewer.post('/documents/intake/read', content=b'%PDF-' + b'x' * (reader.MAX_BYTES - 5), headers=headers)
        assert boundary.status_code == 200
        assert received == [20 * 1024 * 1024]
        assert counts == {t: c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in tables}
    finally:
        st.set_setting(c, 'documents.enabled', old); c.close()


def test_reading_status_and_preview_without_field_matches():
    text = 'This document contains ordinary prose without labelled correspondence fields.'
    result = reader.read_pdf(pdf(text))
    assert result['suggestions'] == {}
    assert result['reading'] == {'page_count': 1, 'ocr_pages': []}
    assert text in result['text_preview'][0]['text']
    assert result['text_preview'][0]['page'] == 1
    assert result['text_preview'][0]['truncated'] is False
    result = reader.read_pdf(pdf('Long prose ' * 400))
    assert len(result['text_preview'][0]['text']) == 2000
    assert result['text_preview'][0]['truncated'] is True


def test_wrapped_labels_missing_colon_and_numbered_order():
    result = reader.suggest(['Department Order No. 2019-0225\nSUBJECT：\nStaff orientation\nFROM\nTraining Office\nDATE October 17, 2026'])
    assert result['suggestions'] == {'subject': 'Staff orientation', 'sender': 'Training Office',
        'type': 'Department Order', 'references': 'Department Order No. 2019-0225', 'document_date': '2026-10-17'}
    assert result['evidence']['subject'][0]['page'] == 1


def test_empty_label_does_not_consume_next_label_or_infer_assignments():
    result = reader.suggest(['Subject:\nFrom:\nTraining Office\nDate: tomorrow\nUrgent\nAssign to John'])
    assert result['suggestions'] == {'sender': 'Training Office'}


def test_twenty_mib_pdf_accepted_and_one_byte_over_rejected():
    # A valid PDF with an unreferenced stream exercises the byte boundary without
    # changing the page count or generating a costly 20 MiB page raster.
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf('Subject: Boundary acceptance', 'From: Training Office'))))
    padding = DecodedStreamObject()
    padding.set_data(b'x')
    writer._add_object(padding)
    raw = b''
    size = reader.MAX_BYTES - 2000
    for _ in range(4):
        padding.set_data(b'x' * size)
        output = io.BytesIO(); writer.write(output); raw = output.getvalue()
        if len(raw) == reader.MAX_BYTES: break
        size += reader.MAX_BYTES - len(raw)
    assert len(raw) == 20 * 1024 * 1024
    assert reader.read_pdf(raw)['suggestions']['subject'] == 'Boundary acceptance'
    with pytest.raises(ValueError, match='20 MiB'):
        reader.read_pdf(raw + b' ')
