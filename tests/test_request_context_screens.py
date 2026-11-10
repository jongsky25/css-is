"""Keep the reviewed-request context on the discussion, handoff and completion screens (10.15 follow-up)."""
import html
import re
from urllib.parse import urlsplit, parse_qs
import pytest
import documents_navigation as nav
import work
import work_completion
import work_handoff
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_documents_routes import token
from test_request_work_acknowledgement import propose, tables

ORIGIN = '/documents/actions?view=mine&step_state=waiting'
NAV = 'aria-label="Request context"'
BACK = 'Back to reviewed request and comparison'
DRAFT_URL = 'https://docs.google.com/document/d/synthetic_draft_123/edit'
SCREENS = ('discussion', 'draft', 'completion')


def context_query(saved):
    return urlsplit(nav.request_work_url(saved, ORIGIN)).query


def hrefs(page_text):
    return [html.unescape(h) for h in re.findall(r'href="([^"]*)"', page_text)]


def setup(record, viewer, changed=False):
    c, u, doc, unit, url = record
    saved = propose(record, viewer)
    if changed:
        revise_record(c, u, doc, need_0_output='Changed deliverable')
    receipt = nav.record_url(f"/documents/{doc['id']}/requests/0/work", ORIGIN)
    return c, u, doc, saved, receipt, f"/work/{saved['case_id']}?{context_query(saved)}"


def expect_context(page, receipt):
    assert page.status_code in (200, 400, 409), page.status_code
    assert page.text.count(NAV) == 1 and BACK in page.text
    assert html.escape(receipt, quote=True) in page.text and 'Back to Documents queue' in page.text
    assert 'evil.test' not in page.text


def test_work_page_links_carry_the_context_to_each_screen(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer, changed=True)
    page = viewer.get(work_url)
    expect_context(page, receipt)
    links = hrefs(page.text)
    for screen in SCREENS:
        target = next(h for h in links if f"/{screen}" in h and h.startswith(f"/work/{saved['case_id']}/"))
        query = parse_qs(urlsplit(target).query)
        assert query['source_task'] == [str(saved['task_id'])] and query['return_to'] == [ORIGIN], (screen, target)
        screen_page = viewer.get(target)
        expect_context(screen_page, receipt)
        assert 'The saved request changed' in screen_page.text  # the source-change note travels too


def test_each_screen_links_back_to_the_work_item_with_the_context(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    for screen in SCREENS:
        page = viewer.get(f"/work/{saved['case_id']}/{screen}?{context_query(saved)}")
        expect_context(page, receipt)
        back = [h for h in hrefs(page.text) if urlsplit(h).path == f"/work/{saved['case_id']}"]
        assert back and all('source_task=' in h for h in back), (screen, back)
        detail = viewer.get(back[0])
        expect_context(detail, receipt)  # exactly one notice on the work page itself


def test_without_context_nothing_changes(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    plain = f"/work/{saved['case_id']}"
    page = viewer.get(plain)
    assert NAV not in page.text
    assert not [h for h in hrefs(page.text) if 'source_task' in h]
    for screen in SCREENS:
        screen_page = viewer.get(f"{plain}/{screen}")
        assert screen_page.status_code == 200 and NAV not in screen_page.text
        assert not [h for h in hrefs(screen_page.text) if 'source_task' in h]


def test_forged_or_foreign_context_shows_nothing_and_hostile_queues_are_dropped(proposal_record, viewer, admin):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    case = saved['case_id']
    other = work.create(c, u, {'title': 'Other work', 'outcome': 'Other output', 'unit_id': str(proposal_record[3])})
    for query in ('source_task=99999', 'source_task=x', f"source_task={saved['task_id']}"):
        for screen in SCREENS:
            target = f"/work/{other['id']}/{screen}?{query}"
            assert NAV not in viewer.get(target).text, target  # a task from another case grants nothing
    for screen in SCREENS:
        page = viewer.get(f"/work/{case}/{screen}?source_task={saved['task_id']}&return_to=https://evil.test/")
        assert NAV in page.text and 'evil.test' not in page.text and 'Back to Documents queue' not in page.text
        denied = admin.get(f"/work/{case}/{screen}?{context_query(saved)}")
        assert denied.status_code == 404 and BACK not in denied.text


def test_page_loads_write_nothing(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer, changed=True)
    before = tables(c); audits = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    for screen in SCREENS:
        viewer.get(f"/work/{saved['case_id']}/{screen}?{context_query(saved)}")
    assert tables(c) == before and c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audits


def test_posting_a_message_keeps_the_context_on_success_and_on_error(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    query = context_query(saved)
    page = viewer.get(f"/work/{saved['case_id']}/discussion?{query}")
    action = [html.unescape(a) for a in re.findall(r'action="(/work/\d+/discussion/messages[^"]*)"', page.text)][-1]
    assert 'source_task=' in action and 'return_to=' in action
    empty = viewer.post(action, data={'csrf': token(page), 'action': 'post', 'body': ''}, follow_redirects=False)
    assert empty.status_code in (400, 409) and NAV in empty.text and BACK in empty.text
    posted = viewer.post(action, data={'csrf': token(page), 'action': 'post', 'body': 'A note for the team'}, follow_redirects=False)
    assert posted.status_code == 303
    location = posted.headers['location']
    assert 'focus=' in location and 'source_task=' in location and 'return_to=' in location and location.endswith(re.search(r'#message-\d+$', location)[0])
    expect_context(viewer.get(location), receipt)


def test_following_a_discussion_keeps_the_context(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    query = context_query(saved)
    page = viewer.get(f"/work/{saved['case_id']}/discussion?{query}")
    action = [html.unescape(a) for a in re.findall(r'action="(/work/\d+/discussion/preferences[^"]*)"', page.text)]
    assert action and all('source_task=' in a for a in action)
    response = viewer.post(action[0], data={'csrf': token(page), 'action': 'follow'}, follow_redirects=False)
    assert response.status_code == 303 and 'source_task=' in response.headers['location']
    expect_context(viewer.get(response.headers['location']), receipt)


def test_saving_the_working_draft_keeps_the_context(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    url = f"/work/{saved['case_id']}/draft?{context_query(saved)}"
    page = viewer.get(url)
    assert re.search(r'<form class="work-form" method="post">', page.text)  # no explicit action: posts to this URL
    bad = viewer.post(url, data={'csrf': token(page), 'action': 'unknown'}, follow_redirects=False)
    assert bad.status_code == 400 and NAV in bad.text
    saved_draft = viewer.post(url, data={'csrf': token(page), 'action': 'set_draft', 'draft_id': 0, 'title': 'Working copy',
                                         'url': DRAFT_URL, 'reason': 'First draft'}, follow_redirects=False)
    assert saved_draft.status_code == 303 and saved_draft.headers['location'].endswith('#working-draft')
    assert 'source_task=' in saved_draft.headers['location'] and 'return_to=' in saved_draft.headers['location']
    expect_context(viewer.get(saved_draft.headers['location']), receipt)


def test_completion_actions_keep_the_context(proposal_record, viewer, monkeypatch):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    url = f"/work/{saved['case_id']}/completion?{context_query(saved)}"
    page = viewer.get(url)
    bad = viewer.post(url, data={'csrf': token(page), 'action': 'unknown'}, follow_redirects=False)
    assert bad.status_code == 400 and NAV in bad.text and BACK in bad.text
    monkeypatch.setattr(work_completion, 'configure', lambda *args, **kwargs: None)  # route behavior only
    ok = viewer.post(url, data={'csrf': token(page), 'action': 'scope', 'revision': '1', 'mode': 'internal', 'reason': 'x'}, follow_redirects=False)
    assert ok.status_code == 303 and 'source_task=' in ok.headers['location'] and ok.headers['location'].startswith(f"/work/{saved['case_id']}/completion?")
    expect_context(viewer.get(ok.headers['location']), receipt)


def test_handoff_notes_link_back_to_their_task_with_the_context(proposal_record, viewer):
    c, u, doc, saved, receipt, work_url = setup(proposal_record, viewer)
    work_handoff.set_draft(c, u, saved['case_id'], 0, {'title': 'Working copy', 'url': DRAFT_URL, 'reason': 'First draft'})
    draft = work_handoff.current(c, saved['case_id'])
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0]
    work_handoff.post(c, u, saved['case_id'], saved['task_id'], revision, draft['id'], 'Place the table in section two.', None)
    page = viewer.get(f"/work/{saved['case_id']}/draft?task_id={saved['task_id']}&{context_query(saved)}")
    expect_context(page, receipt)
    task_links = [h for h in hrefs(page.text) if urlsplit(h).path == f"/work/{saved['case_id']}" and f"#task-{saved['task_id']}" in h]
    assert task_links and all('source_task=' in h for h in task_links), task_links
    all_notes = [h for h in hrefs(page.text) if h.endswith('#handoffs') and urlsplit(h).path.endswith('/draft')]
    assert all_notes and all('source_task=' in h for h in all_notes), all_notes
