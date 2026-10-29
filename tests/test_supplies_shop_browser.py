"""Increment 2.1 in a real browser at phone and desktop width: steppers, limits, search, sticky bar."""
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

import pytest
import storage as st
import supplies as s
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_supplies import key
from tests.test_supplies_stock import opening


@pytest.fixture
def shop_page(grid_browser, app_mod, viewer):
    c = st.connect(app_mod.DB)
    admin = st.get_admin_user(c, 'admin@test.local')
    user = st.get_admin_user(c, 'viewer@test.local')
    s.grant_role(c, admin, user['id'], 'custodian', operation_key=key())
    s.set_enabled(c, admin, '1', expected_revision=0, operation_key=key())
    unit = c.execute("SELECT id FROM org_unit LIMIT 1").fetchone()
    if not unit:
        unit = (st.add_org_unit(c, 'Synthetic division', 'division', 'TEST/D1'),)
    rp = st.add_rp(c, 'Synthetic requester', True, unit[0] if isinstance(unit[0], int) else unit[0]['id'])
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?', (rp, user['id']))
    c.commit()
    user = st.get_admin_user(c, 'viewer@test.local')
    for code, name, unit_name, stock in (('A1', 'Gold stapler', 'Box', '4'), ('B2', 'Blue ballpen', 'Box', '30'),
                                         ('C3', 'Empty ink', 'Bottle', None)):
        item = s.create_item(c, user, {'code': code, 'description': name, 'unit': unit_name,
                                       'critical_level': '5', 'target_level': '20'}, operation_key=key())
        if stock:
            opening(c, user, item, quantity=stock)
    # Serve real TestClient responses over local HTTP, so the form POST and its 303 redirect behave like
    # production (the pattern used by the rooms and calendar browser tests).
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            try:
                if self.command == 'POST':
                    raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                    response = viewer.post(self.path, content=raw, follow_redirects=False,
                        headers={'Content-Type': self.headers.get('Content-Type', 'application/octet-stream')})
                else:
                    response = viewer.get(self.path, follow_redirects=False)
                status, body, headers = response.status_code, response.content, response.headers.items()
            except Exception:  # show a server error on the page instead of hanging the browser
                status, body, headers = 500, traceback.format_exc().encode(), [('content-type', 'text/plain')]
            calls.append((self.command, urlsplit(self.path).path, status))
            self.send_response(status)
            for key, value in headers:
                if key.lower() not in ('content-length', 'content-encoding', 'set-cookie', 'connection', 'transfer-encoding'):
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser may close a finished navigation during teardown

        do_GET = do_POST = handle_request

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = False  # server_close waits for in-flight requests before the database goes away
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    worker.start()
    context = grid_browser.new_context(base_url='http://127.0.0.1:' + str(server.server_port),
                                       viewport={'width': 375, 'height': 700}, service_workers='block')
    page = context.new_page()
    page.calls = calls
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
    page.goto('/supplies/requests/new')
    try:
        yield page
    finally:
        context.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        c.close()
    assert errors == []


def test_phone_layout_steppers_limits_search_and_sticky_bar(shop_page):
    page = shop_page
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
    assert page.locator('.shop-card').count() == 3
    assert page.locator('#shop-bar').is_hidden()
    qty = page.locator('#shop-grid input[name^=qty_]')
    stapler = page.locator('.shop-card', has_text='Gold stapler').locator('input')
    more = page.get_by_role('button', name='More Gold stapler')
    for _ in range(6):
        more.click()
    assert stapler.input_value() == '4'  # stops at what can be requested
    assert page.locator('#shop-count').inner_text() == '1 item' and page.locator('#shop-bar').is_visible()
    page.get_by_role('button', name='Fewer Gold stapler').click()
    assert stapler.input_value() == '3'
    ballpen = page.locator('.shop-card', has_text='Blue ballpen').locator('input')
    ballpen.fill('99')
    assert ballpen.input_value() == '30'
    assert page.locator('#shop-count').inner_text() == '2 items'
    assert page.locator('.shop-card', has_text='Empty ink').locator('input').is_disabled()
    assert page.locator('.shop-card', has_text='Empty ink').get_by_role('button', name='More Empty ink').is_disabled()
    page.locator('#shop-q').fill('ball')
    assert page.locator('.shop-card:visible').count() == 1
    page.locator('#shop-q').fill('')
    assert page.locator('.shop-card:visible').count() == 3 and stapler.input_value() == '3'
    assert qty.count() == 3
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')


def test_desktop_width_and_save_draft_round_trip(shop_page):
    page = shop_page
    page.set_viewport_size({'width': 1280, 'height': 800})
    page.get_by_role('button', name='More Blue ballpen').click()
    page.get_by_role('button', name='More Blue ballpen').click()
    page.locator('#shop-purpose').fill('Browser test purpose')
    page.get_by_role('button', name='Save draft').click()
    try:
        page.wait_for_url(re.compile(r'/supplies/requests/\d+$'), timeout=15000)
        page.get_by_text('Browser test purpose').first.wait_for(timeout=15000)
    except Exception as exc:
        body = page.inner_text('body')[:800]
        raise AssertionError(f'Draft page not reached. url={page.url} calls={page.calls} body={body!r}') from exc
    assert 'Blue ballpen' in page.content()
