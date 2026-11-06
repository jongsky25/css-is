"""Synthetic request review contracts, with no external services."""
import json
import pytest
import documents as docs
import documents_intake as intake
import documents_understanding as understanding
import documents_page_reader as reader
import documents_operations as operations
from test_documents import registry, register
from test_documents_intake import seed, fields, Drive


def reviewed():
    return {'need_0_action': 'Submit comments', 'need_0_kind': 'explicit',
            'need_0_output': 'Comments matrix', 'need_0_deadline': '2026-11-20',
            'need_0_evidence': 'Please submit comments by 20 November 2026.',
            'need_0_page': '2', 'need_0_confirmed': 'yes', 'needs_status': 'requests',
            'focus_primary': 'governance', 'focus_confirmed': 'yes'}


def test_request_evidence_page_mapping_and_multiple_requests():
    result = reader.summarize({'pages': [
        {'page': 7, 'text': 'Please submit comments on local health systems.\n\nKindly nominate a representative.', 'ocr': True},
        {'page': 2, 'text': 'Health financing consultation', 'ocr': False}]})
    data = result['understanding']
    assert len(data['requests']) == 2
    assert all(item['page']=='7' and item['kind']=='explicit' for item in data['requests'])
    assert data['requests'][0]['action'] in data['requests'][0]['evidence']
    assert {item['value'] for item in data['focus']} == {'governance', 'financing'}
    assert all(not item['deadline'] for item in data['requests'])


@pytest.mark.parametrize('text,status', [('', 'unclear'), ('Unclear OCR: p1ease s#bm1t', 'unclear'),
    ('For information only.', 'information_only'),
    ('For information only. Please provide comments.', 'requests'),
    ('You are not requested to submit a report.', 'unclear'),
    ('Please do not submit a report.', 'unclear')])
def test_never_equates_missing_request_with_information_only(text, status):
    assert understanding.suggest([text])['status'] == status


def test_bounded_results_and_no_invented_details():
    data = understanding.suggest([' '.join(f'Please submit report {i}.' for i in range(8))])
    assert len(data['requests']) == 5
    assert 'More than five' in data['warning']
    assert all(not item['recipient'] and not item['deadline'] for item in data['requests'])


@pytest.mark.parametrize('change', [
    {'need_0_confirmed': ''}, {'focus_confirmed': ''}, {'need_0_deadline': '2026-02-30'},
    {'focus_primary': 'invented'}, {'need_0_kind': 'system'}, {'needs_status':'information_only'},
    {'need_0_action': ''}, {'need_0_evidence': 'x'*1001}])
def test_invalid_review_rolls_back_registration_and_number(registry, change):
    c, users, unit, _ = registry
    with pytest.raises(ValueError): register(c, users[0], unit, **{**reviewed(), **change})
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM document_understanding').fetchone()[0] == 0


def test_confirmed_requests_persist_without_assignments(registry):
    c, users, unit, _ = registry
    doc = register(c, users[0], unit, **reviewed())
    assert understanding.read(c,doc['id'])['need_0_output'] == 'Comments matrix'
    assert c.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0] == 0
    assert c.execute('SELECT actor_id FROM document_understanding').fetchone()[0] == users[0]['id']


def test_information_only_requires_explicit_confirmation():
    with pytest.raises(ValueError, match='information only'):
        understanding.clean({'needs_status':'information_only'}, require_confirmation=True)
    understanding.clean({'needs_status':'information_only','needs_status_confirmed':'yes'}, require_confirmation=True)


def test_source_change_discards_structured_draft_and_stale_confirmation(registry):
    c, users, _, _ = registry
    files = seed(registry)
    item = intake.claim(c,users[1],1,1)
    intake.save(c,users[1],1,item['revision'],{**fields(),**reviewed()})
    files[0].update(content_key='new-checksum',fingerprint='v2')
    intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':files})
    draft = intake.get(c,users[1],1)['draft']
    assert draft['subject'] == fields()['subject']
    assert 'need_0_action' not in draft and 'focus_confirmed' not in draft


def test_drive_transient_full_text_bounded_evidence_and_review_persistence(registry):
    c, users, _, _ = registry
    seed(registry)
    item = intake.claim(c,users[1],1,1)
    class ReadingDrive(Drive):
        def call(self, action, payload, operation):
            result = super().call(action,payload,operation)
            if action == 'extract':
                assert payload['understanding'] is True
                result['understanding_text'] = 'Private irrelevant background.\n\nPlease submit comments on health financing.'
            return result
    item = intake.save(c,users[1],1,item['revision'],{**fields(),**reviewed()})
    item = intake.extract(c,users[1],1,item['revision'],ReadingDrive())
    assert item['draft']['need_0_confirmed'] == ''
    assert 'Private irrelevant background' not in json.dumps(item)
    assert item['suggestions']['understanding']['requests'][0]['page']=='Source (page unavailable)'
    doc = intake.register(c,users[1],1,item['revision'],{**fields(),**reviewed()},adapter=Drive())
    assert understanding.read(c,doc['id'])['need_0_action']=='Submit comments'


def test_legacy_relay_is_explicitly_unavailable_not_information_only():
    data = operations.sanitize_extraction({'suggestions':{},'excerpts':['For information only.']})['understanding']
    assert data['status']=='unclear' and not data['requests']
    assert 'unavailable' in data['warning']


def test_focus_evidence_contains_match_in_long_paragraph():
    data=understanding.suggest(['Background '*100 + 'health financing consultation.'])
    assert 'health financing' in data['focus'][0]['evidence']
