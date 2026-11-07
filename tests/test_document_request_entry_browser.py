"""Progressive entry keeps original field identities and no-script editing."""
from urllib.parse import urlsplit

import pytest

from tests.test_document_registration_browser import browser, registration_page
from tests.test_document_understanding_review_routes import review_record


def test_add_request_is_progressive_and_preserves_entered_values(registration_page):
    page, state, conn = registration_page
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.locator('[data-request]:visible').count() == 0
    page.locator('#document-understanding').screenshot(path='/tmp/request-entry-empty-phone.png')
    before = page.locator('#intake-form').evaluate('form => Object.fromEntries(new FormData(form))')
    add = page.get_by_role('button', name='Add request', exact=True)
    add.focus()
    add.press('Enter')
    assert page.locator('[data-request]:visible').count() == 1
    assert page.locator('[name=need_0_action]').evaluate('element => element === document.activeElement')
    assert page.locator('#intake-form').evaluate('form => Object.fromEntries(new FormData(form))') == before
    page.locator('[name=need_0_action]').fill('Please review the report')
    page.locator('[name=need_0_output]').fill('Reviewed report')
    for index in range(1, 5):
        add.click()
        assert page.locator(f'[data-request="{index}"]').is_visible()
        assert page.locator(f'[name=need_{index}_action]').evaluate('element => element === document.activeElement')
    assert add.is_disabled()
    assert page.locator('[name=need_0_output]').input_value() == 'Reviewed report'
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    assert not state['posts']
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_suggestion_reveals_empty_slot_without_overwriting_partial_entry(registration_page):
    import documents_understanding
    page, state, conn = registration_page
    page.get_by_role('button', name='Add request', exact=True).click()
    page.locator('[name=need_0_output]').fill('Partially entered output')
    data = documents_understanding.suggest(['Please submit comments on health financing.'])
    page.evaluate("data => document.getElementById('intake-form').dispatchEvent(new CustomEvent('document-understanding-result', {detail:data}))", data)
    page.get_by_role('button', name='Use this request for review', exact=True).click()
    assert page.locator('[name=need_0_output]').input_value() == 'Partially entered output'
    assert page.locator('[name=need_0_action]').input_value() == ''
    assert page.locator('[data-request="1"]').is_visible()
    assert page.locator('[name=need_1_action]').input_value().startswith('Please submit')
    assert not page.locator('[name=need_1_confirmed]').is_checked()
    assert page.locator('[data-request="2"]').is_hidden()
    assert not state['posts']


def serve_page(page, viewer):
    posts = []
    def serve(route):
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.hostname != 'office.test':
            route.abort()
            return
        target = parsed.path + ('?' + parsed.query if parsed.query else '')
        if request.method == 'POST':
            posts.append(request.post_data)
            response = viewer.post(target, content=request.post_data,
                                   headers={'content-type': request.headers['content-type']}, follow_redirects=True)
        else:
            response = viewer.get(target, follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={key: value for key, value in response.headers.items()
                               if key.lower() not in ('content-length', 'content-encoding', 'set-cookie')})
    page.route('**/*', serve)
    return posts


@pytest.mark.parametrize('scripts', [True, False])
def test_saved_requests_and_no_script_fields_remain_available(browser, review_record, viewer, scripts):
    conn, user, doc, url = review_record
    context = browser.new_context(viewport={'width': 390, 'height': 844}, java_script_enabled=scripts)
    page = context.new_page()
    posts = serve_page(page, viewer)
    try:
        page.goto('http://office.test' + url)
        assert page.locator('[name=need_0_output]').input_value() == 'Comments matrix'
        assert page.locator('[name=need_0_output]').is_visible()
        assert page.locator('[data-request]:visible').count() == (1 if scripts else 5)
        if scripts:
            page.get_by_role('button', name='Add request', exact=True).click()
            assert page.locator('[name=need_1_action]').is_visible()
        else:
            assert page.get_by_role('button', name='Add request', exact=True).count() == 0
            page.locator('[data-request="1"] summary').click()
            assert page.locator('[name=need_1_action]').is_visible()
        assert not posts
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('[name=need_1_action]').fill('Provide updated data')
        page.locator('[name=need_1_confirmed]').check()
        page.locator('[name=need_0_confirmed]').check()
        page.locator('[name=focus_confirmed]').check()
        page.locator('[name=reason]').fill('Reviewed a second source request')
        page.locator('[name=review_confirmed]').check()
        page.get_by_role('button', name='Save reviewed requests', exact=True).click()
        page.get_by_role('status').filter(has_text='Review saved').wait_for()
        import documents_understanding
        saved = documents_understanding.read(conn, doc['id'])
        assert saved['need_0_output'] == 'Comments matrix'
        assert saved['need_1_action'] == 'Provide updated data'
        assert saved['need_1_confirmed'] == 'yes'
        assert len(posts) == 1
    finally:
        context.close()


def test_validation_error_keeps_partial_request_visible_at_same_slot(browser, review_record, viewer):
    conn, user, doc, url = review_record
    context = browser.new_context(viewport={'width': 390, 'height': 844})
    page = context.new_page()
    serve_page(page, viewer)
    try:
        page.goto('http://office.test' + url)
        for _ in range(3):
            page.get_by_role('button', name='Add request', exact=True).click()
        page.locator('[name=need_3_output]').fill('Partial output <script>unsafe()</script>')
        page.locator('[name=need_0_confirmed]').check()
        page.locator('[name=focus_confirmed]').check()
        page.locator('[name=reason]').fill('Review incomplete source')
        page.locator('[name=review_confirmed]').check()
        page.get_by_role('button', name='Save reviewed requests', exact=True).click()
        page.get_by_role('alert').filter(has_text='Enter the requested action').first.wait_for()
        assert page.locator('[data-request="3"]').is_visible()
        assert page.locator('[name=need_3_output]').input_value() == 'Partial output <script>unsafe()</script>'
        assert page.locator('[data-request="1"]').is_hidden()
        assert page.locator('[data-request="2"]').is_hidden()
        assert page.locator('[name=need_0_output]').input_value() == 'Comments matrix'
        assert conn.execute('SELECT COUNT(*) FROM document_understanding_revision').fetchone()[0] == 0
    finally:
        context.close()
