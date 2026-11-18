"""Traverse source-review history without losing permission or queue context."""
import html
import re
from urllib.parse import urlsplit, parse_qs
import pytest
import documents_request_work as proposals
from test_document_request_work_routes import proposal_record
from test_document_understanding_review_routes import review_record
from test_request_work_acknowledgement import propose, tables
from test_request_work_acknowledgement_history import acknowledge_after_change
from test_document_registration_browser import browser
from test_request_reconciliation_browser import open_page, fits

ORIGIN = '/documents/actions?view=mine&step_state=waiting'


def seed_history(record, viewer, count=45):
    c, u, doc, unit, url = record
    saved = propose(record, viewer)
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'Changed source', 'Review 0')
    for n in range(1, count):
        c.execute('''INSERT INTO document_request_work_review
            (document_id,request_index,source_hash,understanding_revision,task_revision,case_id,task_id,actor_id,note,created_at)
            VALUES (?,0,?,1,1,?,?,?,?,'2026-11-18T00:00:00')''',
            (doc['id'], f'synthetic-{n}', saved['case_id'], saved['task_id'], u['id'], f'Review {n}'))
    c.commit()
    return saved


def history(page):
    match = re.search(r'<details id="acknowledgement-history".*?</details>', page.text, re.S)
    assert match, page.text[:200]
    return match[0]


def older(page):
    match = re.search(r'href="([^"]+)">Older reviews</a>', history(page))
    return html.unescape(match[1]) if match else None


def test_all_pages_are_complete_ordered_and_read_only(proposal_record, viewer):
    import documents_navigation as nav
    c, u, doc, unit, url = proposal_record
    saved = seed_history(proposal_record, viewer)
    before = tables(c); reviews = c.execute('SELECT * FROM document_request_work_review').fetchall()
    audit = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    target = nav.record_url(url, ORIGIN)
    observed = []
    for size in (20,20,5):
        page = viewer.get(target)
        assert page.status_code == 200 and page.headers['cache-control'] == 'no-store'
        section = history(page)
        notes = re.findall(r'“Review (\d+)”', section)
        assert len(notes) == size
        assert section.count('(latest)') == (1 if not observed else 0)
        if observed:
            assert re.search(r'<details[^>]*\bopen', section) and 'Latest reviews' in section
        observed.extend(map(int, notes))
        target = older(page)
        if target:
            assert parse_qs(urlsplit(target).query)['return_to'] == [ORIGIN]
            assert urlsplit(target).fragment == 'acknowledgement-history'
    assert observed == list(reversed(range(45))) and target is None
    assert tables(c) == before and c.execute('SELECT * FROM document_request_work_review').fetchall() == reviews
    assert c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audit


def test_new_reviews_do_not_shift_older_pages_and_empty_cursor_can_return(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = seed_history(proposal_record, viewer, 21)
    target = older(viewer.get(url))
    acknowledge_after_change(c, u, doc, saved, viewer, url, 'New arrival', 'Newest arrival')
    section = history(viewer.get(target))
    assert '“Review 0”' in section and '(latest)' not in section and 'Newest arrival' not in section
    empty = viewer.get(url + '?review_before=1')
    assert empty.status_code == 200 and 'No earlier reviews on this page.' in history(empty)
    assert 'Latest reviews' in history(empty) and older(empty) is None


@pytest.mark.parametrize('cursor', ['', '0', '-1', 'abc', '1.5', '١', '9223372036854775808', '9'*200])
def test_invalid_cursors_are_bounded(proposal_record, viewer, cursor):
    seed_history(proposal_record, viewer, 2)
    response = viewer.get(proposal_record[-1], params={'review_before':cursor})
    assert response.status_code == 400 and response.headers['cache-control'] == 'no-store'
    assert 'Invalid source-review history cursor.' in response.text


def test_cursor_grants_no_access_and_never_selects_another_request(proposal_record, viewer, admin):
    c, u, doc, unit, url = proposal_record
    saved = seed_history(proposal_record, viewer, 21)
    target = older(viewer.get(url))
    response = admin.get(target)
    assert response.status_code == 404 and 'Review 0' not in response.text
    # An unrelated/high ID is only a bound on the already authorized request.
    page = viewer.get(url + '?review_before=9223372036854775807&return_to=https://evil.test')
    assert page.status_code == 200 and 'evil.test' not in page.text
    assert len(re.findall(r'“Review (\d+)”', history(page))) == 20
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u['id'],));c.commit()
    assert 'acknowledgement-history' not in viewer.get(target).text


@pytest.mark.parametrize('scripts',[False,True])
def test_phone_keyboard_can_reach_the_last_review_and_return(browser, proposal_record, viewer, scripts):
    import documents_navigation as nav
    saved = seed_history(proposal_record, viewer, 21)
    target = nav.record_url(proposal_record[-1], ORIGIN)
    writes=[]
    context,page=open_page(browser,viewer,390,scripts,writes)
    page.route('**/telemetry',lambda route:route.fulfill(status=204))
    try:
        page.goto('http://office.test'+target)
        page.locator('#acknowledgement-history summary').focus();page.keyboard.press('Enter')
        link=page.get_by_role('link',name='Older reviews',exact=True)
        link.focus();page.keyboard.press('Enter')
        page.wait_for_url('**review_before=**')
        assert page.locator('#acknowledgement-history').get_attribute('open') is not None
        assert '“Review 0”' in page.locator('#acknowledgement-history').inner_text() and fits(page)
        link=page.get_by_role('link',name='Latest reviews',exact=True)
        link.focus();page.keyboard.press('Enter')
        page.wait_for_url(lambda url: 'review_before' not in urlsplit(url).query)
        assert parse_qs(urlsplit(page.url).query)['return_to']==[ORIGIN]
        assert fits(page) and not writes
    finally:context.close()


def test_history_is_scoped_to_request_even_when_cursor_is_from_another_request(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = seed_history(proposal_record, viewer, 21)
    c.execute("""INSERT INTO document_request_work
        SELECT document_id,1,source_json,source_hash,payload_hash,case_id,task_id,actor_id,created_at
        FROM document_request_work WHERE document_id=? AND request_index=0""",(doc['id'],))
    c.execute("""INSERT INTO document_request_work_review
        (document_id,request_index,source_hash,understanding_revision,task_revision,case_id,task_id,actor_id,note,created_at)
        VALUES (?,1,'other-request',1,1,?,?,?,'Other request private note','2026-11-18T00:00:00')""",
        (doc['id'],saved['case_id'],saved['task_id'],u['id']))
    foreign_cursor=c.execute('SELECT MAX(id) FROM document_request_work_review').fetchone()[0]
    c.commit()
    page=viewer.get(url,params={'review_before':foreign_cursor})
    assert page.status_code==200 and 'Other request private note' not in page.text
    assert 'History of reviews of source changes (21)' in page.text
    assert '“Review 20”' in history(page)
