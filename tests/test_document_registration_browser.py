"""Browser/network failure tests against the actual registration route and form."""
from urllib.parse import urlsplit
import re

import pytest
import storage as st

pw = pytest.importorskip('playwright.sync_api')


@pytest.fixture(scope='module')
def browser():
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip('Install Chromium with python -m playwright install chromium')
            raise
        yield browser
        browser.close()


@pytest.fixture
def registration_page(browser, app_mod, viewer):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    context = browser.new_context()
    page = context.new_page()
    state = {'posts': [], 'checks': 0, 'lose_before': False, 'lose_after': False, 'lose_check': False, 'invalid': False}
    def serve(route):
        request = route.request
        url = urlsplit(request.url)
        if url.hostname != 'office.test':
            route.abort(); return
        if url.path == '/documents/new' and request.method == 'POST':
            state['posts'].append(request.post_data)
            if state['lose_before']:
                state['lose_before'] = False
                route.abort(); return
            if state['invalid']:
                state['invalid'] = False
                route.fulfill(status=400, content_type='application/json', body='{"state":"invalid","error":"Review the document type."}')
                return
            response = viewer.post(url.path, content=request.post_data,
                headers={'Content-Type': request.headers['content-type'], 'Accept': request.headers.get('accept', '')}, follow_redirects=False)
            if state['lose_after']:
                state['lose_after'] = False
                route.abort(); return
        else:
            if url.path.startswith('/documents/registrations/'):
                state['checks'] += 1
                if state['lose_check']:
                    state['lose_check'] = False
                    route.abort(); return
            response = viewer.get(url.path + ('?' + url.query if url.query else ''), follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
            headers={k: v for k, v in response.headers.items() if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})
    page.route('**/*', serve)
    page.goto('http://office.test/documents/new')
    assert page.locator('#intake-details').is_visible()
    assert not page.locator('#intake-source-options').evaluate('(element) => element.open')
    page.locator('[name=subject]').fill('Browser retry correspondence')
    page.locator('[name=type]').fill('memorandum')
    page.locator('#intake-approve').click()
    page.locator('[name=confirmed]').check()
    yield page, state, conn
    context.close()
    conn.close()


def submit(page):
    page.get_by_role('button', name='Register correspondence', exact=True).click()


def test_lost_reply_is_recovered_by_read_only_status_check(registration_page):
    page, state, conn = registration_page
    state['lose_after'] = True
    submit(page)
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    assert len(state['posts']) == 1 and state['checks'] == 1
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM document_registration').fetchone()[0] == 1


def test_uncertain_retry_keeps_identical_payload_and_never_autoreplays(registration_page):
    page, state, conn = registration_page
    state['lose_before'] = True
    submit(page)
    page.locator('#registration-retry').wait_for(state='visible')
    assert 'Save not confirmed' in page.locator('#registration-status').inner_text()
    assert page.locator('[name=subject]').input_value() == 'Browser retry correspondence'
    assert page.locator('[name=subject]').is_disabled()
    assert len(state['posts']) == 1 and conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
    # Even a programmatic DOM change cannot alter the retry snapshot.
    page.locator('[name=subject]').evaluate("element => element.value = 'Changed DOM value'")
    page.locator('#registration-check').click()
    assert len(state['posts']) == 1
    page.locator('#registration-retry').click()
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    assert state['posts'][0] == state['posts'][1]
    assert conn.execute('SELECT subject FROM document').fetchone()[0] == 'Browser retry correspondence'
    assert conn.execute('SELECT value FROM document_sequence').fetchone()[0] == 1


def test_lost_result_check_can_be_retried_without_another_write(registration_page):
    page, state, conn = registration_page
    state['lose_after'] = state['lose_check'] = True
    submit(page)
    page.locator('#registration-retry').wait_for(state='visible')
    assert len(state['posts']) == 1
    page.locator('#registration-check').click()
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    assert len(state['posts']) == 1 and state['checks'] == 2
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1


def test_definite_validation_error_preserves_fields_and_allows_correction(registration_page):
    page, state, conn = registration_page
    state['invalid'] = True
    submit(page)
    page.wait_for_function("document.getElementById('registration-status').textContent.includes('Review the document type')")
    assert page.locator('[name=subject]').is_enabled()
    assert page.locator('[name=subject]').input_value() == 'Browser retry correspondence'
    page.locator('[name=type]').fill('letter')
    page.locator('#intake-approve').click()
    page.locator('[name=confirmed]').check()
    submit(page)
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    assert len(state['posts']) == 2
    assert conn.execute('SELECT type FROM document').fetchone()[0] == 'letter'


def test_changed_successful_submission_does_not_claim_the_edits_were_saved(registration_page, viewer):
    page, state, conn = registration_page
    payload = page.locator('#intake-form').evaluate('form => Object.fromEntries(new FormData(form))')
    result = viewer.post('/documents/new', data={**payload, 'subject': 'Previously saved subject'},
                         headers={'Accept': 'application/json'})
    assert result.status_code == 200
    submit(page)
    page.wait_for_function("document.getElementById('registration-status').textContent.includes('changed details have not been applied')")
    assert page.url.endswith('/documents/new')
    assert page.locator('#registration-result').is_visible()
    assert conn.execute('SELECT subject FROM document').fetchone()[0] == 'Previously saved subject'
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1


def test_understanding_review_confirmation_persistence_and_safe_text(registration_page):
    import documents_understanding
    page, state, conn = registration_page
    page.set_viewport_size({'width':390,'height':844})
    result = documents_understanding.suggest(['Please submit comments on health financing.'])
    result['requests'][0]['evidence'] += ' <img src=x onerror=alert(1)>'
    page.evaluate("data => document.getElementById('intake-form').dispatchEvent(new CustomEvent('document-understanding-result', {detail:data}))", result)
    page.get_by_role('button',name='Use this request for review',exact=True).click()
    assert page.locator('[name=need_0_action]').input_value().startswith('Please submit')
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    assert page.locator('#understanding-suggestions img').count()==0
    page.get_by_role('button',name='Use focus area for review',exact=True).click()
    page.locator('[name=need_0_output]').fill('Consolidated comments matrix')
    page.locator('[name=need_0_confirmed]').check()
    page.locator('[name=focus_confirmed]').check()
    page.locator('[name=need_0_output]').fill('Final comments matrix')
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    page.locator('[name=need_0_confirmed]').check()
    page.locator('#intake-approve').click()
    page.locator('[name=confirmed]').check()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#document-understanding').screenshot(path='/tmp/document-understanding-phone.png')
    submit(page)
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    # Full source interpretation is now an explicit disclosure in Requests & work.
    details = page.get_by_text('Source requests and focus details', exact=True)
    details.click()
    assert page.get_by_text('Final comments matrix',exact=True).is_visible()
    doc_id=conn.execute('SELECT id FROM document').fetchone()[0]
    saved=documents_understanding.read(conn,doc_id)
    assert saved['focus_primary']=='financing' and saved['need_0_confirmed']=='yes'
    assert conn.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0]==0


def test_understanding_source_change_preserves_corrections_but_requires_review(registration_page):
    page, _, _ = registration_page
    page.get_by_role('button',name='Add request',exact=True).click()
    page.locator('[name=need_0_action]').fill('Manually corrected request')
    page.locator('[name=need_0_confirmed]').check()
    page.locator('#intake-source-options > summary').click()
    page.locator('#intake-source').fill('https://example.invalid/changed.pdf')
    assert page.locator('[name=need_0_action]').input_value()=='Manually corrected request'
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    assert 'Source cleared or changed' in page.locator('#understanding-warning').inner_text()


def test_structured_request_suggestion_reviews_and_saves_deadline(registration_page):
    import documents_understanding
    page, _, conn=registration_page
    data=documents_understanding.suggest(['Regional offices are requested to submit the comments matrix via email to reports@example.test by 20 November 2026.'])
    page.evaluate("data => document.getElementById('intake-form').dispatchEvent(new CustomEvent('document-understanding-result', {detail:data}))",data)
    assert 'Deadline: 2026-11-20' in page.locator('#understanding-suggestions').inner_text()
    assert 'Evidence: by 20 November 2026' in page.locator('#understanding-suggestions').inner_text()
    page.get_by_role('button',name='Use this request for review',exact=True).click()
    assert page.locator('[name=need_0_output]').input_value()=='the comments matrix'
    assert page.locator('[name=need_0_recipient]').input_value()=='Regional offices'
    assert page.locator('[name=need_0_deadline]').input_value()=='2026-11-20'
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    page.locator('[name=need_0_confirmed]').check()
    page.locator('#intake-approve').click()
    page.locator('[name=confirmed]').check()
    submit(page)
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    doc_id=conn.execute('SELECT id FROM document').fetchone()[0]
    saved=documents_understanding.read(conn,doc_id)
    assert saved['need_0_deadline']=='2026-11-20'
    assert saved['need_0_submission']=='via email to reports@example.test'
    assert conn.execute('SELECT due_date FROM document').fetchone()[0] is None


def test_direction_change_requires_review_without_losing_entries(registration_page):
    page, state, conn = registration_page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('[name=direction]').select_option('OUT')
    assert page.locator('#intake-work').is_hidden()
    assert page.locator('#intake-register').is_hidden()
    assert not page.locator('[name=confirmed]').is_checked()
    assert page.locator('[name=subject]').input_value() == 'Browser retry correspondence'
    assert not state['posts']
    page.locator('#intake-source-options > summary').click()
    assert page.locator('#intake-pdf').is_visible()
    page.locator('#intake-source-options > summary').click()
    assert page.locator('[name=subject]').input_value() == 'Browser retry correspondence'
    page.locator('#intake-approve').click()
    page.locator('[name=confirmed]').check()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    submit(page)
    page.wait_for_url(re.compile(r'/documents/\d+$'))
    row=conn.execute('SELECT direction,status FROM document').fetchone()
    assert row[0] == 'OUT'
    assert row[1] != 'released'
    assert len(state['posts']) == 1


def test_manual_registration_without_scripts_needs_no_source(browser, app_mod, viewer):
    # Browser routing does not reliably intercept redirected native POSTs. A loopback
    # bridge retains real HTTP/303 behavior while all app requests use synthetic data.
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    posts, redirects = [], []

    class Bridge(BaseHTTPRequestHandler):
        def dispatch(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if self.command == 'POST':
                posts.append(self.path)
            result = viewer.request(self.command, self.path, content=body,
                headers={'Content-Type': self.headers.get('Content-Type', '')}, follow_redirects=False)
            if result.is_redirect:
                redirects.append((result.status_code, result.headers['location']))
            self.send_response(result.status_code)
            for key, value in result.headers.items():
                if key.lower() not in ('content-length', 'content-encoding', 'transfer-encoding', 'set-cookie'):
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(result.content)))
            self.end_headers()
            self.wfile.write(result.content)
        do_GET = dispatch
        do_POST = dispatch
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Bridge)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
    try:
        page.goto(f'http://127.0.0.1:{server.server_port}/documents/new')
        assert page.locator('#intake-details').is_visible()
        assert page.locator('#intake-source-options').get_attribute('open') is None
        page.locator('[name=direction]').select_option('IN')
        page.locator('[name=subject]').fill('Manual no-script incoming')
        page.locator('[name=type]').fill('memo')
        page.locator('[name=confirmed]').check()
        submit(page)
        page.wait_for_url(re.compile(r'/documents/\d+$'))
        row = conn.execute('SELECT subject,direction FROM document').fetchone()
        assert tuple(row) == ('Manual no-script incoming', 'IN')
        assert posts == ['/documents/new']
        assert redirects == [(303, urlsplit(page.url).path)]
        assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM document_registration').fetchone()[0] == 1
    finally:
        context.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        conn.close()
