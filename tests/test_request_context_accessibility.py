"""Keyboard, accessible link names, reflow and emulated-touch return journeys."""
import pytest
from test_document_request_work_routes import proposal_record
from test_document_understanding_review_routes import review_record
from test_document_registration_browser import browser
from test_request_context_extended import prepare
from test_request_context_screens import context_query
from test_request_reconciliation_browser import open_page, fits


@pytest.mark.parametrize('scripts', [False, True])
@pytest.mark.parametrize('width', [390, 1280])
def test_remaining_screens_keyboard_round_trip(browser, proposal_record, viewer, scripts, width):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    writes = []
    context, page = open_page(browser, viewer, width, scripts, writes)
    # Isolate passive UX telemetry; every business POST remains captured below.
    page.route('**/telemetry', lambda route: route.fulfill(status=204))
    try:
        for path in (f"/work/{saved['case_id']}/consolidation", f"/work/{saved['case_id']}/decisions",
                     f"/work/{saved['case_id']}/messages/{message}/actions", '/work/team', '/work/support'):
            page.goto('http://office.test' + path + '?' + context_query(saved))
            if path in ('/work/team', '/work/support'):
                button = page.get_by_role('button', name='Apply filters' if path == '/work/team' else 'Apply filter', exact=True)
                button.focus()
                with page.expect_navigation():
                    page.keyboard.press('Enter')
                assert 'source_task=' in page.url and 'return_to=' in page.url
            navigation = page.get_by_role('navigation', name='Request context', exact=True)
            assert navigation.count() == 1 and navigation.is_visible() and fits(page)
            link = navigation.get_by_role('link', name='Back to reviewed request and comparison', exact=True)
            link.focus()
            assert link.evaluate('(e) => e === document.activeElement')
            assert link.evaluate('(e) => getComputedStyle(e).outlineStyle') != 'none'
            page.keyboard.press('Tab')
            queue = navigation.get_by_role('link', name='Back to Documents queue', exact=True)
            assert queue.evaluate('(e) => e === document.activeElement')
            for item in (link, queue):
                box = item.bounding_box()
                assert box['height'] >= 44 and box['width'] >= 44
            page.keyboard.press('Shift+Tab'); page.keyboard.press('Enter')
            page.wait_for_url('http://office.test' + receipt)
            assert page.locator('#request-comparison').is_visible() and fits(page)
        assert not writes
    finally:
        context.close()


def test_emulated_touch_opens_context_link(browser, proposal_record, viewer):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
    page = context.new_page()
    from urllib.parse import urlsplit
    def serve(route):
        p = urlsplit(route.request.url)
        if p.hostname != 'office.test' or route.request.method != 'GET':
            route.abort(); return
        response = viewer.get(p.path + ('?' + p.query if p.query else ''))
        route.fulfill(status=response.status_code, body=response.content,
                      headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*', serve)
    try:
        page.goto('http://office.test/work/team?' + context_query(saved))
        page.get_by_role('link', name='Back to reviewed request and comparison', exact=True).tap()
        page.wait_for_url('http://office.test' + receipt)
        assert page.locator('#request-comparison').is_visible() and fits(page)
    finally:
        context.close()


@pytest.mark.parametrize('scripts', [False, True])
def test_request_navigation_reflows_with_large_text(browser, proposal_record, viewer, scripts):
    c, u, doc, saved, receipt, target, message = prepare(proposal_record, viewer)
    writes = []
    context, page = open_page(browser, viewer, 320, scripts, writes, large_text=True)
    page.route('**/telemetry', lambda route: route.fulfill(status=204))
    try:
        for path in (target, f"/work/{saved['case_id']}/consolidation?{context_query(saved)}", receipt):
            page.goto('http://office.test' + path)
            # Apply enlarged text in the initial HTML, including without scripts.
            assert page.evaluate("getComputedStyle(document.documentElement).fontSize") == '32px'
            assert fits(page), page.evaluate("""() => ({
                viewport: innerWidth, scroll: document.documentElement.scrollWidth,
                overflow: [...document.querySelectorAll('body *')].map(e => {
                    const r = e.getBoundingClientRect();
                    return {tag: e.tagName, cls: e.className, id: e.id,
                            left: r.left, right: r.right, width: r.width};
                }).filter(r => r.width && (r.right > innerWidth || r.left < 0)).slice(0, 30)
            })""")
            if path == target:
                choice = page.get_by_label('Document', exact=True)
                choice.select_option(str(doc['id']))
                assert choice.input_value() == str(doc['id']) and fits(page)
            if path != receipt:
                link = page.get_by_role('link', name='Back to reviewed request and comparison', exact=True)
                assert link.is_visible()
                link.focus()
                assert link.evaluate('(e) => e === document.activeElement')
        assert not writes
    finally:
        context.close()
