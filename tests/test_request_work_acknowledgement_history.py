"""History of reviews of a request's source changes, shown on the comparison screen."""
import re
import pytest
import documents_request_work as proposals
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_request_work_acknowledgement import propose, tables
from test_request_work_acknowledge_ui import form_fields, acknowledge_url

HISTORY = 'id="acknowledgement-history"'


def acknowledge_after_change(c, u, doc, saved, viewer, url, output, note):
    revise_record(c, u, doc, need_0_output=output)
    fields = form_fields(viewer.get(url))
    response = viewer.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes', 'note': note}, follow_redirects=False)
    assert response.status_code == 303
    return response


def test_history_appears_from_the_second_review_newest_first(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    assert HISTORY not in viewer.get(url).text
    revise_record(c, u, doc, need_0_output='Changed once')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed twice', 'First note')
    assert HISTORY not in viewer.get(url).text  # one entry is already shown as the status line
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed three times', 'Second note')
    page = viewer.get(url).text
    assert HISTORY in page and 'History of reviews of source changes (2)' in page
    section = page[page.index(HISTORY):]
    section = section[:section.index('</details>')]
    assert section.index('Second note') < section.index('First note')
    assert '(latest)' in section and section.count('(latest)') == 1
    assert 'Former staff member' not in section and 'after saved review' in section
    assert 'not shown' not in section


def test_notes_are_escaped_and_the_link_goes_to_the_saved_review_history(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed once')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed twice', '<script>alert(1)</script>')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed three times', 'Plain')
    page = viewer.get(url).text
    assert '<script>alert(1)</script>' not in page and '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert f"/documents/{doc['id']}/understanding" in page[page.index(HISTORY):]


def test_service_limit_reports_how_many_earlier_entries_are_not_listed(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed once')
    for number in range(3):
        acknowledge_after_change(c, u, doc, saved, viewer, url, f'Change {number}', f'Note {number}')
    existing = proposals.existing(c, u, doc['id'], 0)
    full = proposals.acknowledgement_history(c, existing)
    assert [e['note'] for e in full['entries']] == ['Note 2', 'Note 1', 'Note 0'] and full['older'] == 0 and full['total'] == 3
    short = proposals.acknowledgement_history(c, existing, limit=2)
    assert [e['note'] for e in short['entries']] == ['Note 2', 'Note 1'] and short['older'] == 1 and short['total'] == 3


def test_older_entries_notice_wording_for_one_and_many(proposal_record, viewer, monkeypatch):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed once')
    for number in range(3):
        acknowledge_after_change(c, u, doc, saved, viewer, url, f'Change {number}', f'Note {number}')
    original = proposals.acknowledgement_history
    monkeypatch.setattr(proposals, 'acknowledgement_history', lambda conn, saved, limit=2: original(conn, saved, limit))
    page = viewer.get(url).text
    assert '1 earlier review is not shown. The full record is kept.' in page and 'Note 0' not in page


def test_history_does_not_change_the_warning_or_write_anything(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed once')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed twice', 'A')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed three times', 'B')
    state = proposals.existing(c, u, doc['id'], 0)
    assert state['changed'] is False and state['changed_since_proposal'] is True
    before = tables(c); audits = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    viewer.get(url); viewer.get(f"/documents/{doc['id']}/understanding")
    assert tables(c) == before and c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audits


def test_someone_without_access_gets_no_history(proposal_record, viewer, admin):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed once')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed twice', 'Secret note')
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed three times', 'Other note')
    response = admin.get(url)
    assert response.status_code == 404 and 'Secret note' not in response.text and HISTORY not in response.text
