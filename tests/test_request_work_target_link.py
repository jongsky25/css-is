"""Offer a changed request deadline through the existing "Adjust internal target" action (design R3)."""
import html
import re
import pytest
import documents_request_work as proposals
import documents_navigation as nav
import storage as st
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_documents_routes import token
from test_request_work_acknowledgement import propose, tables

NEW = '2026-11-25'
LINK_TEXT = 'Review the internal target'


def link(page):
    found = re.search(r'<a href="([^"]*suggest_target=1[^"]*)">' + LINK_TEXT, page)
    return html.unescape(found[1]) if found else None


def milestone(page_text):
    """The target form's action, whether its details are open, and its prefilled date."""
    index = page_text.index('/milestone')
    start = page_text.rfind('<details class="work-task-action"', 0, index)
    tag = page_text[start:page_text.index('>', start) + 1]
    form = page_text[index:page_text.index('</form>', index)]
    action = html.unescape(re.search(r'action="([^"]*milestone[^"]*)"', page_text[index - 120:])[1])
    return action, ' open' in tag, re.search(r'name="due_date" value="([^"]*)"', form)[1]


def changed_deadline(record, viewer, value=NEW):
    c, u, doc, unit, url = record
    saved = propose(record, viewer)
    revise_record(c, u, doc, need_0_deadline=value)
    return c, u, doc, saved, url


def test_link_prefills_the_existing_form_and_saving_keeps_the_context(proposal_record, viewer):
    c, u, doc, saved, url = changed_deadline(proposal_record, viewer)
    page = viewer.get(url)
    target = link(page.text)
    assert target and NEW in page.text and target.startswith(f"/work/{saved['case_id']}?")
    work = viewer.get(target)
    assert work.status_code == 200 and 'The date below comes from the changed request' in work.text
    action, opened, prefilled = milestone(work.text)
    assert opened and prefilled == NEW
    revision = c.execute('SELECT revision,due_date FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()
    assert revision[1] != NEW  # nothing was applied by following the link
    response = viewer.post(action, data={'csrf': token(work), 'revision': str(revision[0]), 'due_date': NEW,
                                         'reason': 'Request deadline moved'}, follow_redirects=False)
    assert response.status_code == 303 and 'source_task=' in response.headers['location']
    assert 'suggest_target' not in response.headers['location']
    assert c.execute('SELECT due_date FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0] == NEW
    assert link(viewer.get(url).text) is None  # the target now matches the request


def test_no_link_when_the_deadline_did_not_change_or_already_matches(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    assert link(viewer.get(url).text) is None
    revise_record(c, u, doc, need_0_output='Changed deliverable only')
    assert link(viewer.get(url).text) is None  # the deadline itself did not change
    revise_record(c, u, doc, need_0_deadline=NEW)
    assert link(viewer.get(url).text)
    c.execute('UPDATE work_task SET due_date=? WHERE id=?', (NEW, saved['task_id'])); c.commit()
    assert link(viewer.get(url).text) is None


def test_no_link_for_a_cleared_or_invalid_deadline(proposal_record, viewer, monkeypatch):
    c, u, doc, saved, url = changed_deadline(proposal_record, viewer)
    assert link(viewer.get(url).text)
    for value in ('', '2026-13-45', '25/11/2026', '٢٠٢٦-١١-٢٥'):
        original = proposals.source
        def fake(conn, doc_id, index, _v=value, _o=original):
            result = _o(conn, doc_id, index); result['need_0_deadline'] = _v; return result
        monkeypatch.setattr(proposals, 'source', fake)
        assert proposals.suggested_target(c, u, proposals.existing(c, u, doc['id'], 0)) is None, value
        monkeypatch.setattr(proposals, 'source', original)


def test_no_link_without_authority_for_finished_work_or_a_disabled_module(proposal_record, viewer):
    c, u, doc, saved, url = changed_deadline(proposal_record, viewer)
    assert link(viewer.get(url).text)
    c.execute('UPDATE work_case SET lead_id=NULL'); c.commit()
    case = proposals.work.raw(c, saved['case_id'])
    if proposals.can_acknowledge(u, case, c):
        pytest.skip('creator holds officer authority in this fixture')
    assert link(viewer.get(url).text) is None
    c.execute('UPDATE work_case SET lead_id=?', (u['id'],))
    for status in ('done', 'cancelled'):
        c.execute('UPDATE work_task SET status=? WHERE id=?', (status, saved['task_id'])); c.commit()
        assert link(viewer.get(url).text) is None, status
    c.execute("UPDATE work_task SET status='todo' WHERE id=?", (saved['task_id'],)); c.commit()
    assert link(viewer.get(url).text)
    st.set_setting(c, 'work.enabled', '0'); c.commit()
    assert link(viewer.get(url).text) is None


def test_a_forged_flag_or_date_in_the_url_prefills_nothing(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    case = saved['case_id']
    plain = viewer.get(f"/work/{case}?source_task={saved['task_id']}&suggest_target=1")
    assert 'comes from the changed request' not in plain.text  # the deadline did not change
    revise_record(c, u, doc, need_0_deadline=NEW)
    for query in (f"suggest_target=1", f"source_task=99999&suggest_target=1", f"source_task=x&suggest_target=1"):
        assert 'comes from the changed request' not in viewer.get(f"/work/{case}?{query}").text, query
    forged = viewer.get(f"/work/{case}?source_task={saved['task_id']}&suggest_target=1&suggest_date=1999-01-01&due_date=1999-01-01")
    assert milestone(forged.text)[2] == NEW and '1999-01-01' not in forged.text


def test_an_official_deadline_conflict_still_blocks_the_save(proposal_record, viewer):
    c, u, doc, saved, url = changed_deadline(proposal_record, viewer)
    c.execute('UPDATE document SET due_date=? WHERE id=?', ('2026-11-22', doc['id'])); c.commit()
    work = viewer.get(link(viewer.get(url).text))
    action, opened, prefilled = milestone(work.text)
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0]
    before = c.execute('SELECT due_date,revision FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()
    response = viewer.post(action, data={'csrf': token(work), 'revision': str(revision), 'due_date': prefilled,
                                         'reason': 'Try it'}, follow_redirects=False)
    assert response.status_code == 400 and 'cannot follow a linked official deadline' in response.text
    assert c.execute('SELECT due_date,revision FROM work_task WHERE id=?', (saved['task_id'],)).fetchone() == before


def test_loading_the_pages_and_the_link_writes_nothing(proposal_record, viewer):
    c, u, doc, saved, url = changed_deadline(proposal_record, viewer)
    before = tables(c); audits = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    target = link(viewer.get(url).text)
    viewer.get(target); viewer.get(f"/work/{saved['case_id']}")
    assert tables(c) == before and c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audits


def test_the_link_keeps_the_return_context(proposal_record, viewer):
    c, u, doc, saved, url = changed_deadline(proposal_record, viewer)
    origin = '/documents/actions?view=mine&step_state=waiting'
    target = link(viewer.get(nav.record_url(url, origin)).text)
    assert 'return_to=' in target and 'suggest_target=1' in target
    assert 'Back to reviewed request and comparison' in viewer.get(target).text
