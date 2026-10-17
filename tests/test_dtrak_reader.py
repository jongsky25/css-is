"""Synthetic routing-slip layouts; no uploaded documents are stored in tests."""
import documents_reader as reader


def slip(date='10/16/2026'):
    return f'''Document Tracking Information System (DTRAK)
ROUTING SLIP
DTRAK-3.0
2026-000123456
ORIGINATING OFFICE: Example Office DATE: {date}
Effectivity:
TYPE OF DOCUMENT: Memorandum
SUBJECT: Submission of comments on the
updated service guidelines

ACTION
REQUIRED/ACTION DUE DATE
TAKEN/ REMARKS
Example Office For Appropriate Action 2026-10-20
From: Wrong table sender
Date: 2026-10-21
'''


def test_dtrak_header_and_multiline_subject():
    result = reader.suggest([slip()])
    assert result['suggestions'] == {
        'subject': 'Submission of comments on the updated service guidelines',
        'sender': 'Example Office', 'type': 'Memorandum',
        'references': 'DTRAK: 2026-000123456'}
    assert result['evidence']['subject'][0]['page'] == 1
    assert any('routing-table' in warning for warning in result['warnings'])


def test_dtrak_ambiguous_numeric_date_not_guessed():
    assert 'document_date' not in reader.suggest([slip('10/11/2026')])['suggestions']
    assert 'document_date' not in reader.suggest([slip('02/30/2026')])['suggestions']


def test_other_documents_and_conflicts_still_supported():
    text = 'DTRAK: ABC-123\nSubject: Ordinary letter\nFrom: Another office\nDate: October 17, 2026'
    result = reader.suggest([text])
    assert result['suggestions']['references'] == 'DTRAK: ABC-123'
    assert result['suggestions']['subject'] == 'Ordinary letter'
    result = reader.suggest([slip(), text])
    assert 'subject' not in result['suggestions']
    assert any('Multiple values found for subject' in warning for warning in result['warnings'])


def test_flat_table_headers_stop_subject_and_separate_date():
    text = slip().replace('Example Office DATE: 10/16/2026', 'Example Office\nDATE: 10/16/2026')
    text = text.replace('ACTION\nREQUIRED/ACTION DUE DATE', 'DATE FROM TO ACTION DUE DATE NAME')
    result = reader.suggest([text])
    assert 'document_date' not in result['suggestions']
    assert any('2026-10-16' in warning for warning in result['warnings'])
    assert result['suggestions']['subject'].endswith('service guidelines')


def test_underlying_document_date_and_case_normalization():
    result = reader.suggest([slip(), 'MEMORANDUM\nOctober 14, 2026\nSUBJECT:'])
    assert result['suggestions']['document_date'] == '2026-10-14'
    assert result['suggestions']['type'] == 'Memorandum'
    assert not any('Multiple values found for type' in w for w in result['warnings'])


def test_tracking_caption_recovery_and_deadline_position(monkeypatch):
    import io
    import subprocess
    from PIL import Image
    import documents_ocr
    out = io.BytesIO()
    Image.new('RGB', (1200, 1700), 'white').save(out, 'PNG')
    header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
    def word(text, x, y, width=40):
        return f'5\t1\t1\t1\t1\t1\t{x}\t{y}\t{width}\t15\t95\t{text}\n'
    tsv = header + word('2026-000123456', 400, 300, 180) + word('DUE', 800, 600) + word('DATE', 850, 600)
    tsv += word('2026-10-15', 100, 720, 120) + word('2026-10-20', 795, 720, 120)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0, tsv.encode()))
    result = documents_ocr.routing_deadline(out.getvalue(), 'DTRAK\nORIGINATING OFFICE: Test')
    assert result.startswith('2026-000123456\n')
    assert result.endswith('Deadline: 2026-10-20')
    tsv += word('2026-10-21', 795, 760, 120)
    assert 'Deadline:' not in documents_ocr.routing_deadline(out.getvalue(), 'DTRAK\nORIGINATING OFFICE: Test')


def test_first_page_link_scope():
    import io
    from reportlab.pdfgen import canvas
    out = io.BytesIO(); c = canvas.Canvas(out)
    for subject in ('First', 'Second'):
        c.drawString(50, 700, 'Subject: ' + subject + ' page has enough native text to avoid OCR')
        c.showPage()
    c.save()
    result = reader.read_pdf(out.getvalue(), first_page=True)
    assert result['reading']['page_count'] == 1
    assert result['suggestions']['subject'].startswith('First')


def test_repeated_subject_case_punctuation_and_excerpt():
    complete = 'Submission of comments on the updated service guidelines'
    for duplicate in [complete.upper() + '.', 'Submission of comments on the updated']:
        result = reader.suggest([slip(), 'Subject: ' + duplicate])
        assert result['suggestions']['subject'] == complete
        assert [e['page'] for e in result['evidence']['subject']] == [1, 2]
        assert 'subject' not in result['conflicts']


def test_wrapped_title_and_subject_title():
    for label in ['Title', 'Subject/Title', 'SUBJECT']:
        result = reader.suggest([label + ': Submission of comments on the\nupdated service guidelines\n\nThis is the body.'])
        assert result['suggestions']['subject'] == 'Submission of comments on the updated service guidelines'


def test_real_subject_conflict_is_explained_and_pages_remapped():
    from documents_page_reader import summarize
    result = summarize({'pages': [
        {'page': 5, 'text': 'Subject: Approve the proposal', 'ocr': True},
        {'page': 9, 'text': 'Subject: Reject the proposal', 'ocr': True}]})
    assert 'subject' not in result['suggestions']
    assert [c['page'] for c in result['conflicts']['subject']] == [5, 9]
    assert result['conflicts']['subject'][0]['value'] == 'Approve the proposal'
