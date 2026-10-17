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
        'document_date': '2026-10-16', 'references': 'DTRAK: 2026-000123456'}
    assert result['evidence']['subject'][0]['page'] == 1
    assert 'routing table' in result['warnings'][0]


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
    assert result['suggestions']['document_date'] == '2026-10-16'
    assert result['suggestions']['subject'].endswith('service guidelines')
