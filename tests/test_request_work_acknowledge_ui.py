"""Acknowledge a changed request source from the comparison screen (design R2)."""
import re
import pytest
import storage as st
import documents_request_work as proposals
import work_review
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_documents_routes import token
from test_request_work_acknowledgement import propose, add_reviewed_outgoing, tables

ALERT_SINCE_PROPOSAL = 'has changed since this proposal'
ALERT_SINCE_REVIEW = 'has changed since the last reviewed change'


def form_fields(page):
    html = re.search(r'<form[^>]*work/acknowledge.*?</form>', page.text, re.S)
    assert html, 'acknowledge form missing'
    body = html[0]
    return {name: re.search(rf'name="{name}" value="([^"]*)"', body)[1] for name in ('csrf', 'source_hash', 'task_revision')}


def acknowledge_url(doc, index=0):
    return f"/documents/{doc['id']}/requests/{index}/work/acknowledge"


def prepared(record, viewer):
    c, u, doc, unit, url = record
    saved = propose(record, viewer)
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    return c, u, doc, saved, url


def test_form_is_offered_to_the_lead_only_when_the_source_changed(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    propose(proposal_record, viewer)
    assert 'work/acknowledge' not in viewer.get(url).text
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    page = viewer.get(url)
    assert ALERT_SINCE_PROPOSAL in page.text and 'Mark this source change as reviewed' in page.text
    assert 'required' in re.search(r'name="confirmed"[^>]*>', page.text)[0]
    assert page.headers['cache-control'] == 'no-store'


def test_someone_without_authority_sees_the_change_but_no_form(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    propose(proposal_record, viewer, lead=False)
    c.execute('UPDATE work_case SET lead_id=NULL'); c.commit()
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    saved = proposals.existing(c, u, doc['id'], 0)
    case = proposals.work.raw(c, saved['case_id'])
    page = viewer.get(url)
    if proposals.can_acknowledge(u, case, c):
        pytest.skip('creator holds officer authority in this fixture')
    assert ALERT_SINCE_PROPOSAL in page.text and 'work/acknowledge' not in page.text
    assert 'Only the work item lead or an authorized unit officer' in page.text


def test_acknowledging_clears_the_warning_everywhere_and_keeps_the_comparison(proposal_record, viewer):
    c, u, doc, saved, url = prepared(proposal_record, viewer)
    before_overview = viewer.get(f"/documents/{doc['id']}/understanding").text
    before_work = viewer.get(f"/work/{saved['case_id']}?source_task={saved['task_id']}").text
    assert 'Source changed' in before_overview and 'The saved request changed' in before_work
    page = viewer.get(url)
    fields = form_fields(page)
    response = viewer.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes', 'note': 'Output wording agreed'}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == url
    after = viewer.get(url).text
    assert ALERT_SINCE_PROPOSAL not in after and 'work/acknowledge' not in after
    assert 'A source change was reviewed on' in after and 'Output wording agreed' in after
    assert '1 source fields changed since the proposal' in after  # the comparison still shows what changed
    assert 'Source changed' not in viewer.get(f"/documents/{doc['id']}/understanding").text
    assert 'The saved request changed' not in viewer.get(f"/work/{saved['case_id']}?source_task={saved['task_id']}").text


def test_a_later_source_change_brings_the_warning_back(proposal_record, viewer):
    c, u, doc, saved, url = prepared(proposal_record, viewer)
    fields = form_fields(viewer.get(url))
    assert viewer.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes'}, follow_redirects=False).status_code == 303
    revise_record(c, u, doc, need_0_output='Changed a second time')
    page = viewer.get(url).text
    assert ALERT_SINCE_REVIEW in page and 'The source changed again after that review.' in page
    assert 'Mark this source change as reviewed' in page


def test_note_is_escaped_and_the_return_context_survives(proposal_record, viewer):
    c, u, doc, saved, url = prepared(proposal_record, viewer)
    origin = '/documents/actions?view=mine&step_state=waiting'
    contextual = f"{url}?return_to={origin}"
    page = viewer.get(contextual)
    fields = form_fields(page)
    action = re.search(r'<form[^>]*action="([^"]*work/acknowledge[^"]*)"', page.text)[1].replace('&amp;', '&').replace('&#34;', '"')
    response = viewer.post(action, data={**fields, 'confirmed': 'yes', 'note': '<script>alert(1)</script>'}, follow_redirects=False)
    assert response.status_code == 303 and 'return_to=' in response.headers['location']
    after = viewer.get(response.headers['location']).text
    assert '<script>alert(1)</script>' not in after and '&lt;script&gt;alert(1)&lt;/script&gt;' in after


def test_double_submit_stale_hash_and_missing_csrf_write_nothing_extra(proposal_record, viewer):
    c, u, doc, saved, url = prepared(proposal_record, viewer)
    fields = form_fields(viewer.get(url))
    data = {**fields, 'confirmed': 'yes'}
    assert viewer.post(acknowledge_url(doc), data={**data, 'csrf': ''}, follow_redirects=False).status_code == 403
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0
    assert viewer.post(acknowledge_url(doc), data=data, follow_redirects=False).status_code == 303
    assert viewer.post(acknowledge_url(doc), data=data, follow_redirects=False).status_code == 303
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 1
    revise_record(c, u, doc, need_0_output='Changed again')
    stale = viewer.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes', 'source_hash': '0' * 64}, follow_redirects=False)
    assert stale.status_code == 409 and 'Reload' in stale.text
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 1


def test_unconfirmed_post_is_rejected_with_the_form_still_available(proposal_record, viewer):
    c, u, doc, saved, url = prepared(proposal_record, viewer)
    fields = form_fields(viewer.get(url))
    response = viewer.post(acknowledge_url(doc), data={**fields, 'note': 'kept note'}, follow_redirects=False)
    assert response.status_code == 400 and 'Confirm that you checked' in response.text
    assert 'kept note' in response.text and 'Mark this source change as reviewed' in response.text
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0


def test_unrelated_accounts_get_no_access_and_page_loads_write_nothing(proposal_record, viewer, admin):
    c, u, doc, saved, url = prepared(proposal_record, viewer)
    fields = form_fields(viewer.get(url))
    assert admin.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes'}, follow_redirects=False).status_code in (403, 404)
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0
    before = tables(c); audits = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    viewer.get(url); viewer.get(f"/documents/{doc['id']}/understanding"); viewer.get(f"/work/{saved['case_id']}")
    assert tables(c) == before and c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audits


def test_acknowledging_does_not_touch_linked_reviews_or_the_work(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    out_id = add_reviewed_outgoing(c, u, unit, saved['case_id'])
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    packet = work_review.latest(c, out_id)
    before = tables(c)
    fields = form_fields(viewer.get(url))
    assert viewer.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes'}, follow_redirects=False).status_code == 303
    assert tables(c) == before and work_review.current(c, packet) is False
