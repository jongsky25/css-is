"""End-to-end context across the remaining shared-work surfaces."""
import html
import json
import re
from urllib.parse import parse_qs, urlsplit
import pytest
import work
import work_discussion
from test_document_request_work_routes import proposal_record
from test_document_understanding_review_routes import review_record
from test_request_context_screens import setup, context_query, expect_context, hrefs, NAV, ORIGIN
from test_documents_routes import token


def prepare(record, viewer):
    c, u, doc, saved, receipt, target = setup(record, viewer, changed=True)
    c.execute('UPDATE work_case SET lead_id=? WHERE id=?', (u['id'], saved['case_id']))
    c.commit()
    message = work_discussion.post(c, u, saved['case_id'], 'Consider the revised request')
    return c, u, doc, saved, receipt, target, message


def actions(page):
    return [html.unescape(a) for a in re.findall(r'action="([^"]+)"', page.text)]


def test_remaining_pages_and_forms_preserve_context(proposal_record, viewer):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    case = saved['case_id']; query = context_query(saved)
    for path in (f'/work/{case}/consolidation', f'/work/{case}/decisions',
                 f'/work/{case}/messages/{message}/actions', '/work/team', '/work/support'):
        page = viewer.get(path + '?' + query)
        expect_context(page, receipt)
        assert 'The saved request changed' in page.text
        for link in hrefs(page.text) + actions(page):
            p = urlsplit(link)
            if p.path in ('/work/team', '/work/support', f'/work/{case}') or p.path.startswith(f'/work/{case}/'):
                q = parse_qs(p.query)
                assert q.get('source_task') == [str(saved['task_id'])], link
                assert q.get('return_to') == [ORIGIN], link
    page = viewer.get(target)
    for endpoint in ('block', 'dependency_add'):
        assert any('/' + endpoint + '?' in a and 'source_task=' in a for a in actions(page))


def test_message_decision_and_resolution_keep_context_and_errors(proposal_record, viewer):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    case = saved['case_id']; tid = saved['task_id']; query = context_query(saved)
    url = f'/work/{case}/messages/{message}/actions?{query}'
    page = viewer.get(url)
    bad = viewer.post(url, data={'csrf': token(page), 'source_revision': '1', 'action': 'wrong'}, follow_redirects=False)
    assert bad.status_code == 400
    expect_context(bad, receipt)
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (tid,)).fetchone()[0]
    fields = {'csrf': token(page), 'source_revision': '1', 'action': 'decision', 'kind': 'change',
              'body': 'Review the revised approach', 'affected_tasks': str(tid),
              'task_revisions': json.dumps({str(tid): revision})}
    result = viewer.post(url, data=fields, follow_redirects=False)
    assert result.status_code == 303, result.text
    detail = viewer.get(result.headers['location']); expect_context(detail, receipt)
    resolve = next(a for a in actions(detail) if '/resolve?' in a)
    bad = viewer.post(resolve, data={'csrf': token(detail), 'task_id': tid, 'revision': 0,
                                    'outcome': 'retain', 'reason': 'Still applies'}, follow_redirects=False)
    assert bad.status_code == 409
    expect_context(bad, receipt)
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (tid,)).fetchone()[0]
    done = viewer.post(resolve, data={'csrf': token(detail), 'task_id': tid, 'revision': revision,
                                     'outcome': 'retain', 'reason': 'Still applies'}, follow_redirects=False)
    assert done.status_code == 303
    expect_context(viewer.get(done.headers['location']), receipt)
    assert 'Existing contribution retained' in viewer.get(done.headers['location']).text


def test_blocker_and_team_save_keep_context(proposal_record, viewer):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    page = viewer.get(target)
    action = next(a for a in actions(page) if '/block?' in a)
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0]
    fields = {'csrf': token(page), 'revision': revision, 'reason': 'Waiting for figures',
              'followup_owner_id': u['id'], 'followup_date': '2026-11-25'}
    bad = viewer.post(action, data={**fields, 'revision': 0}, follow_redirects=False)
    assert bad.status_code == 409; expect_context(bad, receipt)
    good = viewer.post(action, data=fields, follow_redirects=False)
    assert good.status_code == 303 and urlsplit(good.headers['location']).fragment == f"task-{saved['task_id']}"
    expect_context(viewer.get(good.headers['location']), receipt)
    team = viewer.get('/work/team?' + context_query(saved))
    action = next(a for a in actions(team) if '/milestone?' in a)
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0]
    fields = {'csrf': token(team), 'revision': revision, 'reason': 'Updated planning date', 'due_date': '2026-11-26'}
    bad = viewer.post(action, data={**fields, 'revision': 0}, follow_redirects=False)
    assert bad.status_code == 409; expect_context(bad, receipt)
    good = viewer.post(action, data=fields, follow_redirects=False)
    assert good.status_code == 303
    expect_context(viewer.get(good.headers['location']), receipt)


def test_aggregate_context_does_not_spread_to_other_cases_or_leak_after_revocation(proposal_record, viewer, admin):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    other = work.create(c, u, {'title': 'Unrelated case', 'outcome': 'Different output', 'unit_id': proposal_record[3]})
    for path in ('/work/team', '/work/support'):
        page = viewer.get(path + '?' + context_query(saved))
        expect_context(page, receipt)
        for link in hrefs(page.text):
            if urlsplit(link).path == f"/work/{other['id']}":
                assert 'source_task' not in link
        denied = admin.get(path + '?' + context_query(saved))
        assert NAV not in denied.text and receipt not in denied.text
        forged = viewer.get(path + '?source_task=invalid&return_to=https://evil.test')
        assert NAV not in forged.text and 'evil.test' not in forged.text
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (u['id'],)); c.commit()
    for path in ('/work/team', '/work/support', f"/work/{saved['case_id']}/consolidation"):
        assert NAV not in viewer.get(path + '?' + context_query(saved)).text


def test_reads_and_consolidation_validation_do_not_write(proposal_record, viewer):
    from test_request_work_acknowledgement import tables
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    before = tables(c)
    audits = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    for path in (f"/work/{saved['case_id']}/consolidation", f"/work/{saved['case_id']}/decisions",
                 f"/work/{saved['case_id']}/messages/{message}/actions", '/work/team', '/work/support'):
        expect_context(viewer.get(path + '?' + context_query(saved)), receipt)
    page = viewer.get(target)
    response = viewer.post(f"/work/{saved['case_id']}/consolidation/{doc['id']}?{context_query(saved)}",
                           data={'csrf': token(page), 'action': 'wrong'}, follow_redirects=False)
    assert response.status_code == 400
    expect_context(response, receipt)
    assert tables(c) == before
    assert c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audits
