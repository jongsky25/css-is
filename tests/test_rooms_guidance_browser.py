"""A17 browser journeys use the real page, read API, form and room services."""
import json
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

import rooms
import storage as st
from tests.test_document_guidance_browser import browser
from tests.test_rooms_pages import conn, bookable_day, slot_id


@pytest.fixture
def room_page(browser, viewer, conn, monkeypatch):
    # Serve actual TestClient responses over local HTTP, including real 303 redirects.
    # This fixture maps one synthetic signed-in client; it is not a production host.
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    monkeypatch.setattr(rooms, '_emit', lambda *a, **k: None)
    state = {'posts':[], 'errors':[], 'api_status':200, 'api_reads':[]}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            parts = urlsplit(self.path)
            if parts.path == '/rooms/api/day':
                state['api_reads'].append(self.path)
                if state['api_status'] != 200:
                    self.send_response(state['api_status']); self.end_headers()
                    self.wfile.write(b'Availability unavailable')
                    return
            if self.command == 'POST':
                state['posts'].append(parts.path)
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                response = viewer.post(self.path, content=raw,
                    headers={'Content-Type': self.headers.get('Content-Type','application/octet-stream')}, follow_redirects=False)
            else:
                response = viewer.get(self.path, follow_redirects=False)
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in ('content-length','content-encoding','set-cookie','connection','transfer-encoding'):
                    self.send_header(key,value)
            self.send_header('Content-Length', str(len(response.content)))
            self.end_headers()
            try:
                self.wfile.write(response.content)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The browser may close a completed navigation during fixture teardown.

        do_GET = do_POST = handle_request

    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    server.daemon_threads = False  # server_close waits for in-flight TestClient requests before DB teardown
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval':.05}, daemon=True)
    worker.start()
    context = browser.new_context(base_url='http://127.0.0.1:' + str(server.server_port),
        viewport={'width':1440,'height':1000}, reduced_motion='reduce', service_workers='block')
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    page = context.new_page()
    page.on('pageerror', lambda e: state['errors'].append(str(e)))
    page.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
    try:
        yield page, state, conn, context
    finally:
        context.close()
        server.shutdown(); server.server_close(); worker.join(timeout=2)
    assert not state['errors']


def room_writes(state):
    # Passive page-hide telemetry is independent of a reservation mutation.
    return [path for path in state['posts'] if path != '/telemetry']


def goto(page, path):
    page.goto(path)
    expect(page.locator('#rm-wrap')).to_be_visible()


def set_day(page, day):
    page.locator('#rm-day').fill(day.isoformat() if hasattr(day,'isoformat') else day)
    page.locator('#rm-day').press('Tab')


@pytest.mark.parametrize('width,theme', [(320,'light'), (390,'dark'), (900,'light'), (1440,'dark')])
def test_board_to_request_preserves_form_focus_and_reserves_only_after_approval(room_page, width, theme):
    page, state, conn, context = room_page
    day = bookable_day(conn)
    page.set_viewport_size({'width':width,'height':900})
    context.add_init_script('localStorage.setItem("theme", ' + json.dumps(theme) + ')')
    goto(page, '/rooms?week=' + day.isoformat())
    panel = page.locator('#rm-panel')
    if width < 1200:
        assert panel.evaluate('(el)=>el.inert')
        assert not page.get_by_role('textbox', name='Meeting title').count()
        opener = page.locator('#rm-open')
        opener.focus()
        opener.press('Enter')
        expect(page.get_by_role('dialog', name='Request the room')).to_be_visible()
        expect(page.locator('#rm-day')).to_be_focused()
        assert page.locator('.rm-board').evaluate('(el)=>el.inert')
        close = page.get_by_role('button', name='Close room request')
        close.focus()
        close.press('Shift+Tab')
        expect(page.get_by_role('button', name='Request room', exact=True)).to_be_focused()
        page.keyboard.press('Tab')
        expect(close).to_be_focused()
        page.keyboard.press('Escape')
        expect(opener).to_be_focused()
        expect(panel).not_to_be_visible()
        opener.press('Enter')
    set_day(page, day)
    page.locator('#rm-title').fill('Browser reservation')
    expect(page.locator('#rm-clash')).to_contain_text('Free to request')
    assert not room_writes(state)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if width < 1200:
        page.keyboard.press('Escape')
        page.locator('#rm-open').click()
        expect(page.locator('#rm-title')).to_have_value('Browser reservation')
    page.get_by_role('button', name='Request room', exact=True).click()
    page.wait_for_url(re.compile(r'.*/rooms/mine\?ok=CR-'))
    expect(page.get_by_role('group', name='Reservation next step')).to_contain_text('No hours are reserved')
    res = conn.execute('SELECT id,status FROM room_reservation WHERE title=?', ('Browser reservation',)).fetchone()
    assert res and res[1] == 'requested'
    assert room_writes(state) == ['/rooms/request']
    assert not conn.execute('SELECT 1 FROM room_reservation_slot WHERE is_approved=1').fetchone()
    rooms.approve(conn, res[0], 'approver')
    page.reload()
    expect(page.get_by_role('group', name='Reservation next step')).to_contain_text('The room is reserved for these hours')


def test_date_outside_board_is_checked_and_failure_keeps_details_for_retry(room_page):
    page, state, conn, context = room_page
    target = rooms.add_working_days(conn, bookable_day(conn), 10)
    held = rooms.request(conn, title='Private pending is not exposed', day=target, slot_ids=[slot_id(conn,9)],
                         requester_user_id=st.get_admin_user(conn,'encoder@test.local')['id'])
    rooms.approve(conn, held['id'], 'approver')
    goto(page, '/rooms')
    page.locator('#rm-title').fill('Kept draft')
    state['api_status'] = 503
    set_day(page, target)
    expect(page.locator('#rm-clash')).to_contain_text('Could not check availability')
    expect(page.locator('#rm-title')).to_have_value('Kept draft')
    state['api_status'] = 200
    page.get_by_role('button',name='Check availability',exact=True).click()
    expect(page.locator('#rm-clash')).to_contain_text('booked or unavailable')
    assert 'Private pending is not exposed' not in page.locator('#rm-panel').inner_text()
    page.locator('input[name=standby]').check()
    expect(page.locator('#rm-clash')).to_contain_text('Standby only — no hours are reserved')
    assert not room_writes(state)


def test_stale_day_response_cannot_replace_current_availability(room_page):
    page, state, conn, context = room_page
    # Model a transport that does not support abort; the request generation guard still wins.
    context.add_init_script('window.AbortController = undefined')
    first = rooms.add_working_days(conn, bookable_day(conn), 10)
    second = rooms.add_working_days(conn, first, 1)
    held = rooms.request(conn, title='Taken', day=second, slot_ids=[slot_id(conn,9)],
                         requester_user_id=st.get_admin_user(conn,'encoder@test.local')['id'])
    rooms.approve(conn, held['id'], 'approver')
    delayed = []
    page.route('**/rooms/api/day?date=' + first.isoformat(), lambda route: delayed.append(route))
    goto(page, '/rooms')
    set_day(page, first)
    page.wait_for_timeout(20)
    assert delayed
    set_day(page, second)
    expect(page.locator('#rm-clash')).to_contain_text('booked or unavailable')
    delayed[0].fulfill(status=200, content_type='application/json', body=json.dumps(rooms.day_view(conn,first)))
    page.wait_for_timeout(40)
    expect(page.locator('#rm-clash')).to_contain_text('booked or unavailable')
    assert not room_writes(state)


def test_server_conflict_is_visible_in_mobile_panel_and_preserves_values(room_page):
    page, state, conn, context = room_page
    day = bookable_day(conn)
    page.set_viewport_size({'width':390,'height':844})
    goto(page, '/rooms?date=' + day.isoformat())
    # A prefilled date alone does not submit or open a hidden form.
    page.locator('#rm-open').click()
    page.locator('#rm-title').fill('Kept after conflict')
    held = rooms.request(conn, title='New competing booking', day=day, slot_ids=[slot_id(conn,9)],
                         requester_user_id=st.get_admin_user(conn,'encoder@test.local')['id'])
    rooms.approve(conn, held['id'], 'approver')
    page.get_by_role('button', name='Request room', exact=True).click()
    expect(page.locator('#rm-form-error')).to_be_focused()
    expect(page.locator('#rm-form-error')).to_contain_text('already booked')
    expect(page.locator('#rm-title')).to_have_value('Kept after conflict')
    assert conn.execute('SELECT count(*) FROM room_reservation').fetchone()[0] == 1
    assert room_writes(state) == ['/rooms/request']


def test_owned_replacement_link_focuses_existing_row_without_a_post(room_page):
    page, state, conn, context = room_page
    day = bookable_day(conn)
    uid = st.get_admin_user(conn,'viewer@test.local')['id']
    original = rooms.request(conn,title='Moved meeting',day=day,slot_ids=[slot_id(conn,9)],requester_user_id=uid)
    rooms.approve(conn, original['id'], 'approver')
    moved = rooms.request_move(conn, original['id'], rooms.add_working_days(conn,day,1), st.get_admin_user_by_id(conn,uid))
    rooms.approve(conn, moved['id'], 'approver')
    page.goto('/rooms/mine')
    link = page.locator(f"#room-{original['id']}").get_by_role('link', name=moved['ref_code'])
    link.focus()
    link.press('Enter')
    expect(page.locator(f"#room-{moved['id']}")).to_be_focused()
    assert not room_writes(state)


def test_resize_and_day_selection_keep_keyboard_access(room_page):
    page, state, conn, context = room_page
    day = bookable_day(conn)
    goto(page, '/rooms?week=' + day.isoformat())
    title = page.locator('#rm-title')
    title.fill('Resize draft')
    title.focus()
    page.set_viewport_size({'width':390,'height':844})
    expect(page.get_by_role('dialog',name='Request the room')).to_be_visible()
    expect(title).to_have_value('Resize draft')
    page.set_viewport_size({'width':1440,'height':1000})
    expect(title).to_be_focused()
    expect(page.locator('#rm-panel')).not_to_have_attribute('aria-modal','true')
    page.set_viewport_size({'width':390,'height':844})
    expect(page.get_by_role('dialog',name='Request the room')).to_be_visible()
    page.keyboard.press('Escape')
    links = page.get_by_role('navigation',name='Choose a day').get_by_role('link')
    links.nth(2).focus()
    links.nth(2).press('Enter')
    expect(links.nth(2)).to_have_attribute('aria-current','true')
    assert not page.get_by_role('tablist',name='Day').count()
    assert not room_writes(state)


def test_request_form_remains_usable_without_javascript(room_page):
    page, state, conn, context = room_page
    day = bookable_day(conn)
    session = context.new_cdp_session(page)
    session.send('Emulation.setScriptExecutionDisabled', {'value':True})
    goto(page, '/rooms?date=' + day.isoformat())
    expect(page.locator('#rm-panel')).to_be_visible()
    expect(page.locator('#rm-check')).to_be_hidden()
    page.locator('#rm-title').fill('Native form request')
    page.get_by_role('button',name='Request room',exact=True).click()
    page.wait_for_url(re.compile(r'.*/rooms/mine\?ok=CR-'))
    expect(page.get_by_role('group',name='Reservation next step')).to_contain_text('No hours are reserved')
    assert room_writes(state) == ['/rooms/request']
    assert conn.execute("SELECT status FROM room_reservation WHERE title='Native form request'").fetchone()[0] == 'requested'
    session.detach()
