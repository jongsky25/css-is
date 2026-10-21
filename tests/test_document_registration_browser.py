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
    page.locator('#intake-skip').click()
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
