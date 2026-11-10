"""Real-browser checks for the reconciliation interface: phone and desktop, with and without
JavaScript, driven by the keyboard. Requests are served from the test application; nothing
leaves the machine and every write the page makes is recorded."""
import pytest
from urllib.parse import urlsplit
import documents_navigation as nav
import documents_request_work as proposals
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_document_registration_browser import browser
from test_documents_routes import token
from test_request_work_acknowledgement import propose
from test_request_work_acknowledge_ui import form_fields, acknowledge_url

ORIGIN = '/documents/actions?view=mine&step_state=waiting'
NEW = '2026-11-25'
SIZES = [pytest.param(390, id='phone'), pytest.param(1280, id='desktop')]
SCRIPTS = [pytest.param(False, id='no-script'), pytest.param(True, id='script')]


def open_page(browser, viewer, width, scripts, writes):
    context = browser.new_context(viewport={'width': width, 'height': 844}, java_script_enabled=scripts)
    page = context.new_page()

    def serve(route):
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.hostname != 'office.test':
            route.abort(); return
        target = parsed.path + ('?' + parsed.query if parsed.query else '')
        if request.method == 'POST':
            writes.append(target)
            response = viewer.post(target, content=request.post_data, headers={'content-type': request.headers['content-type']},
                                   follow_redirects=False)
        else:
            response = viewer.get(target, follow_redirects=False)
        if response.status_code in (301, 302, 303, 307) and response.headers.get('location'):
            # Chromium does not follow a redirect fabricated by route.fulfill for a POST, so the
            # application's 303 is replayed as a zero-delay refresh: a GET of the same location,
            # which works with scripts disabled.
            location = response.headers['location']
            route.fulfill(status=200, content_type='text/html',
                          body=f'<!doctype html><meta http-equiv="refresh" content="0;url={location}">')
            return
        route.fulfill(status=response.status_code, body=response.content,
                      headers={k: v for k, v in response.headers.items() if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})
    page.route('**/*', serve)
    return context, page


def fits(page):
    return page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def press(page, locator, key='Enter'):
    locator.focus()
    page.keyboard.press(key)


def current(page):
    parts = urlsplit(page.url)
    return parts.path + ('?' + parts.query if parts.query else '')


@pytest.mark.parametrize('scripts', SCRIPTS)
@pytest.mark.parametrize('width', SIZES)
def test_keyboard_marks_a_changed_source_as_reviewed(browser, proposal_record, viewer, width, scripts):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    start = nav.record_url(url, ORIGIN)
    writes = []
    context, page = open_page(browser, viewer, width, scripts, writes)
    try:
        page.goto('http://office.test' + start)
        assert fits(page) and page.get_by_role('alert').filter(has_text='has changed since this proposal').is_visible()
        button = page.get_by_role('button', name='Mark as reviewed')
        press(page, button)  # native validation stops an unconfirmed submit, with or without scripts
        assert writes == [] and c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0
        page.locator('[name=confirmed]').focus(); page.keyboard.press('Space')
        assert page.locator('[name=confirmed]').is_checked()
        page.locator('[name=note]').focus(); page.keyboard.type('Wording agreed')
        press(page, button)
        page.get_by_role('status').filter(has_text='A source change was reviewed').wait_for(state='visible')
        assert len(writes) == 1 and '/work/acknowledge' in writes[0]
        assert current(page) == start and 'Wording agreed' in page.content() and fits(page)
        assert page.get_by_role('alert').filter(has_text='has changed since this proposal').count() == 0
        row = c.execute('SELECT actor_id,note FROM document_request_work_review').fetchone()
        assert row == (u['id'], 'Wording agreed')
        page.screenshot(path=f'/tmp/reconciliation-ack-{width}-{scripts}.png', full_page=True)
    finally:
        context.close()


@pytest.mark.parametrize('scripts', SCRIPTS)
@pytest.mark.parametrize('width', SIZES)
def test_keyboard_follows_the_target_link_and_applies_the_date_through_the_form(browser, proposal_record, viewer, width, scripts):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_deadline=NEW)
    start = nav.record_url(url, ORIGIN)
    writes = []
    context, page = open_page(browser, viewer, width, scripts, writes)
    try:
        page.goto('http://office.test' + start)
        press(page, page.get_by_role('link', name='Review the internal target'))
        page.wait_for_url('**suggest_target=1**')
        assert writes == [] and fits(page)  # following the link changes nothing
        field = page.locator('details.work-task-action[open] input[name=due_date]')
        assert field.input_value() == NEW and page.get_by_text('The date below comes from the changed request').is_visible()
        assert c.execute('SELECT due_date FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0] != NEW
        reason = page.locator('details.work-task-action[open] textarea[name=reason]')
        reason.focus(); page.keyboard.type('Request deadline moved')
        press(page, page.get_by_role('button', name='Adjust internal target'))
        page.wait_for_function('!location.search.includes("suggest_target")')
        assert len(writes) == 1 and '/milestone' in writes[0]
        assert c.execute('SELECT due_date FROM work_task WHERE id=?', (saved['task_id'],)).fetchone()[0] == NEW
        assert page.get_by_role('link', name='Back to reviewed request and comparison').is_visible() and fits(page)
        page.screenshot(path=f'/tmp/reconciliation-target-{width}-{scripts}.png', full_page=True)
    finally:
        context.close()


@pytest.mark.parametrize('scripts', SCRIPTS)
@pytest.mark.parametrize('width', SIZES)
def test_keyboard_opens_the_history_and_it_fits_the_screen(browser, proposal_record, viewer, width, scripts):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    start = nav.record_url(url, ORIGIN)
    for number, note in enumerate(('First note', 'Second note')):
        revise_record(c, u, doc, need_0_output=f'Changed {number}')
        fields = form_fields(viewer.get(url))
        assert viewer.post(acknowledge_url(doc), data={**fields, 'confirmed': 'yes', 'note': note}, follow_redirects=False).status_code == 303
    writes = []
    context, page = open_page(browser, viewer, width, scripts, writes)
    try:
        page.goto('http://office.test' + start)
        summary = page.locator('#acknowledgement-history > summary')
        assert summary.is_visible() and not page.locator('#acknowledgement-history ol').is_visible()
        press(page, summary)  # a native disclosure: works without scripts
        items = page.locator('#acknowledgement-history li')
        items.first.wait_for(state='visible')
        assert items.count() == 2 and 'Second note' in items.nth(0).inner_text() and 'First note' in items.nth(1).inner_text()
        assert '(latest)' in items.nth(0).inner_text() and fits(page) and writes == []
        page.screenshot(path=f'/tmp/reconciliation-history-{width}-{scripts}.png', full_page=True)
    finally:
        context.close()


@pytest.mark.parametrize('scripts', SCRIPTS)
@pytest.mark.parametrize('width', SIZES)
@pytest.mark.parametrize('screen,link,heading', [
    ('discussion', 'Discuss this work item', None),
    ('completion', 'Release and completion checklist', 'Release and completion'),
    ('draft', None, 'Draft and handoffs'),
])
def test_keyboard_round_trip_through_the_other_work_screens(browser, proposal_record, viewer, width, scripts, screen, link, heading):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    start = nav.record_url(url, ORIGIN)
    writes = []
    context, page = open_page(browser, viewer, width, scripts, writes)
    try:
        page.goto('http://office.test' + start)
        press(page, page.get_by_role('link', name='Open the work item and contribution'))
        page.wait_for_url('**/work/**')
        target = page.get_by_role('link', name=link, exact=True) if link else page.locator(f'a[href*="/{screen}"]').first
        press(page, target)
        page.wait_for_url(f'**/{screen}**')
        notice = page.get_by_role('navigation', name='Request context')
        assert notice.is_visible() and page.get_by_text('The saved request changed').is_visible() and fits(page)
        assert page.get_by_role('link', name='Back to Documents queue').is_visible()
        press(page, page.get_by_role('link', name='Back to reviewed request and comparison'))
        page.wait_for_url('**/requests/0/work**')
        assert current(page) == start and writes == [] and fits(page)
        page.screenshot(path=f'/tmp/reconciliation-{screen}-{width}-{scripts}.png', full_page=True)
    finally:
        context.close()
