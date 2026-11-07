"""One review action and one read/prefill action before human registration."""
from urllib.parse import urlsplit

import pytest

from tests.test_document_guidance_browser import browser
from tests.test_document_intake_friction import intake_http
import documents_intake as intake


@pytest.mark.parametrize('width,scripts', [(390, True), (1280, True), (390, False)])
def test_inbox_to_read_fill_and_register_next(browser, intake_http, admin, width, scripts):
    conn, user, drive = intake_http
    context = browser.new_context(viewport={'width': width, 'height': 844}, java_script_enabled=scripts)
    page = context.new_page()
    posts, errors = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def serve(route):
        request = route.request
        parts = urlsplit(request.url)
        if parts.hostname != 'office.test':
            route.abort()
            return
        target = parts.path + ('?' + parts.query if parts.query else '')
        if request.method == 'POST':
            posts.append(request.post_data)
            response = admin.post(target, content=request.post_data,
                                  headers={'Content-Type': request.headers['content-type']}, follow_redirects=True)
        else:
            response = admin.get(target, follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={key: value for key, value in response.headers.items()
                               if key.lower() not in ('content-length', 'content-encoding', 'set-cookie')})

    page.route('**/*', serve)
    try:
        page.goto('http://office.test/documents/intake')
        page.get_by_role('button', name='Review', exact=True).first.click()
        assert len(posts) == 1
        page.locator('[name=subject]').fill('My reviewed title')
        page.locator('[name=received_at]').fill('2026-10-18T09:00')
        page.get_by_role('button', name='Read and fill empty fields', exact=True).click()
        assert len(posts) == 2 and len(drive.calls) == 1
        assert page.locator('[name=subject]').input_value() == 'My reviewed title'
        assert page.locator('[name=sender]').input_value() == 'Regional Office'
        assert page.locator('[name=type]').input_value() == 'Letter'
        assert page.locator('[name=received_at]').input_value() == '2026-10-18T09:00'
        assert not page.locator('[name=confirmed]').is_checked()
        assert not page.locator('[name=focus_confirmed]').is_checked()
        assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width == 390:
            assert page.locator('.doc-review-actions').bounding_box()['height'] < 140
            assert page.locator('[name=focus_confirmed]').bounding_box()['width'] < 30
        page.locator('[name=confirmed]').check()
        page.get_by_role('button', name='Register and review next', exact=True).click()
        assert len(posts) == 3
        assert page.get_by_role('heading', name='Letter 2.pdf', exact=True).is_visible()
        assert intake.get(conn, user, 2)['claimed_by'] == user['id']
        doc = conn.execute('SELECT subject,instruction_state,lead_id FROM document').fetchone()
        assert tuple(doc) == ('My reviewed title', 'pending', None)
        assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0] == 0
        assert not errors
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=f'/tmp/intake-review-{width}-{scripts}.png', full_page=True)
    finally:
        context.close()
