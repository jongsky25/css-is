"""Chromium checks of the response framing policy; no external network."""
import re
from urllib.parse import urlsplit

import pytest

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
def page(browser, client):
    context = browser.new_context()
    page = context.new_page()

    def serve(route):
        url = urlsplit(route.request.url)
        if url.hostname in ('office.test', 'foreign.test') and url.path == '/host':
            route.fulfill(content_type='text/html', body=
                          '<iframe src="http://office.test/login"></iframe>')
        elif url.hostname == 'office.test':
            response = client.get(url.path, follow_redirects=False)
            route.fulfill(status=response.status_code, body=response.content,
                          headers={k: v for k, v in response.headers.items()
                                   if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})
        else:
            route.abort()

    page.route('**/*', serve)
    yield page
    context.close()


def test_foreign_site_cannot_frame_login(page):
    with page.expect_console_message(predicate=lambda msg: 'frame-ancestors' in msg.text):
        page.goto('http://foreign.test/host')


def test_same_origin_preview_and_existing_inline_scripts_work(page):
    page.goto('http://office.test/host')
    login = page.frame_locator('iframe')
    pw.expect(login.locator('input[name="username"]')).to_be_visible()
    # The shared layout's inline theme script still runs under report-only CSP.
    pw.expect(login.locator('html')).to_have_attribute('data-theme', re.compile(r'light|dark|contrast'))


def test_a_form_post_carries_the_sites_own_origin_so_the_write_check_can_pass(browser, client):
    """Chromium sends "Origin: null" (and no Referer) on a form POST under "Referrer-Policy: no-referrer"; the
    application rejects such a write, so every login and save failed. The policy the app really serves must let the
    browser send the site's own origin."""
    policy = client.get('/login', follow_redirects=False).headers['referrer-policy']
    seen = {}
    context = browser.new_context()
    page = context.new_page()

    def serve(route):
        request = route.request
        if request.method == 'POST':
            seen.update(origin=request.headers.get('origin'), referer=request.headers.get('referer'))
            route.fulfill(status=200, body='posted', headers={'Referrer-Policy': policy})
        else:
            route.fulfill(status=200, content_type='text/html', headers={'Referrer-Policy': policy},
                          body='<form method="post" action="/login"><input name="u" value="x"><button>go</button></form>')

    page.route('**/*', serve)
    page.goto('http://office.test/login')
    page.click('button')
    page.wait_for_load_state()
    context.close()
    assert seen.get('origin') == 'http://office.test', f"Referrer-Policy {policy!r} sent Origin={seen.get('origin')!r}"
