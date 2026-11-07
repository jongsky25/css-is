"""Daily navigation and progressive workspace behavior with actual authorized routes."""
from urllib.parse import urlsplit

import pytest

from tests.test_document_guidance_browser import browser
from tests.test_document_guidance_routes import detail_record, Targets


def test_register_filters_and_navigation_respect_roles(detail_record, viewer, admin):
    conn, user, doc, url = detail_record
    page = viewer.get('/documents?queue=OUT&q=Guided')
    assert page.status_code == 200
    assert '<option value="OUT" selected>Outgoing</option>' in page.text
    assert 'name="q" maxlength="120" value="Guided"' in page.text
    assert '>Inbox</a>' in page.text
    assert '>Settings</a>' not in page.text
    assert '>Inbox</a>' not in admin.get('/documents/actions').text
    detail = viewer.get(url)
    targets = Targets(detail.text)
    assert len(targets.ids) == len(set(targets.ids))
    assert all(target in targets.ids for target in targets.links)


@pytest.mark.parametrize('width,scripts', [(390, True), (1280, True), (390, False)])
def test_workspace_current_action_and_supporting_sections(browser, detail_record, viewer, width, scripts):
    conn, user, doc, url = detail_record
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
        if request.method != 'GET':
            posts.append(request.url)
            route.abort()
            return
        response = viewer.get(parts.path + ('?' + parts.query if parts.query else ''), follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={key: value for key, value in response.headers.items()
                               if key.lower() not in ('content-length', 'content-encoding', 'set-cookie')})

    page.route('**/*', serve)
    try:
        page.goto('http://office.test' + url)
        nav = page.get_by_role('navigation', name='Documents', exact=True)
        assert nav.get_by_role('link').all_text_contents() == ['My desk', 'Inbox', 'Register', 'Overview']
        form = page.locator('#document-action-attach form')
        assert form.count() == 1
        assert form.get_attribute('action') == url + '/attach'
        assert form.locator('[name=csrf]').get_attribute('value')
        assert form.locator('[name=revision]').get_attribute('value') == str(doc['revision'])
        if scripts:
            assert form.is_visible()
            assert page.locator('#document-current-action #document-action-attach').count() == 1
            form.locator('[name=url]').fill('https://drive.google.com/file/d/syntheticdraft123/view')
            page.get_by_role('navigation', name='This document').get_by_role('link', name='Files', exact=True).click()
            assert page.locator('#document-files').evaluate('element => element.open')
            assert not page.locator('.doc-secondary').evaluate('element => element.open')
            page.get_by_role('navigation', name='This document').get_by_role('link', name='Next action', exact=True).click()
            assert form.locator('[name=url]').input_value() == 'https://drive.google.com/file/d/syntheticdraft123/view'
        else:
            page.get_by_text('Record details and additional actions', exact=True).click()
            page.locator('#document-action-attach > summary').click()
            assert form.is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=f'/tmp/document-workspace-{width}-{scripts}.png', full_page=True)
        assert not posts and not errors
        assert conn.execute('SELECT revision FROM document WHERE id=?', (doc['id'],)).fetchone()[0] == doc['revision']
    finally:
        context.close()
