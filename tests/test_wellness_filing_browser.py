"""Phone interaction through real routes and a synthetic SQLite fixture."""
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

import storage as st
from tests.test_wellness import wellness_org, _client_for_id
from tests.test_appearance_browser import page_for


def test_phone_exact_time_preflight_preserves_then_files(wellness_org, app_mod, future_weekday):
    conn, uid = wellness_org['conn'], wellness_org['emp']
    st.create_wellness_claim(conn, uid, future_weekday, '09:00', 'exercise')
    client = _client_for_id(app_mod, uid)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None)
        context, page = page_for(browser, client, viewport={'width': 390, 'height': 844}, has_touch=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://testserver/wellness/apply')
        page.locator('label.datepill').filter(has=page.locator('input[value="' + future_weekday + '"]')).click()
        unavailable = page.locator('.slotpill.disabled').filter(has=page.locator('input[value="09:00"]'))
        unavailable.tap()
        expect(page.locator('#timeStatus')).to_contain_text('Overlaps')
        unavailable.focus()
        unavailable.press('Enter')
        expect(page.locator('#timeStatus')).to_contain_text('09:00')
        page.get_by_text('Choose an exact time', exact=True).tap()
        expect(page.locator('#customTimeInput')).to_be_focused()
        page.locator('#customTimeInput').fill('09:11')
        expect(page.locator('#customTimeRadio')).to_be_checked()
        page.locator('.acts label').filter(has=page.locator('input[value="exercise"]')).click()
        page.locator('[name="note"]').fill('Synthetic browser note')
        page.locator('#wellnessApplyForm button[type="submit"]').click()
        expect(page.locator('#timeStatus')).to_contain_text('overlaps')
        expect(page.locator('#customTimeInput')).to_have_value('09:11')
        expect(page.locator('[name="note"]')).to_have_value('Synthetic browser note')
        assert conn.execute('SELECT count(*) FROM wellness_claim WHERE user_id=?', (uid,)).fetchone()[0] == 1
        def unavailable_check(route):
            route.fulfill(status=503, body='Unavailable')
        page.route('**/wellness/apply/validate', unavailable_check)
        page.locator('#customTimeInput').fill('10:11')
        page.locator('#wellnessApplyForm button[type="submit"]').click()
        expect(page.locator('#timeStatus')).to_contain_text('Could not check availability')
        expect(page.locator('[name="note"]')).to_have_value('Synthetic browser note')
        assert conn.execute('SELECT count(*) FROM wellness_claim WHERE user_id=?', (uid,)).fetchone()[0] == 1
        page.unroute('**/wellness/apply/validate', unavailable_check)
        page.locator('#wellnessApplyForm button[type="submit"]').click()
        expect(page.get_by_role('heading', name='Wellness break', exact=True)).to_be_visible()
        rows = conn.execute('SELECT start_time,note FROM wellness_claim WHERE user_id=? ORDER BY id', (uid,)).fetchall()
        assert len(rows) == 2
        assert tuple(rows[-1]) == ('10:11', 'Synthetic browser note')
        assert not errors
        context.close()
        browser.close()


def test_preflight_does_not_count_as_submit_or_clear_abandonment():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None)
        page = browser.new_page()
        page.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body='<form id="filing"><input name="note"></form><form id="unfinished"><input name="note"></form>'))
        page.goto('http://testserver/wellness/apply')
        page.evaluate("""() => {
          window.events = [];
          navigator.sendBeacon = (url, body) => {body.text().then(text => events.push(...JSON.parse(text).events)); return true;};
        }""")
        page.add_script_tag(content=(Path(__file__).resolve().parents[1] / 'static/js/telemetry.js').read_text())
        page.evaluate("""() => {
          const form = document.querySelector('#filing');
          form.dataset.submitPreflight = 'pending';
          form.querySelector('input').dispatchEvent(new Event('input', {bubbles:true}));
          for (let i=0;i<3;i++) form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
          form.dataset.submitPreflight = 'ready';
          form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
          const unfinished = document.querySelector('#unfinished');
          unfinished.dataset.submitPreflight = 'pending';
          unfinished.querySelector('input').dispatchEvent(new Event('input', {bubbles:true}));
          unfinished.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
          window.dispatchEvent(new Event('pagehide'));
        }""")
        page.wait_for_function("events.some(e => e.event_type === 'form_abandon')")
        events = page.evaluate('events')
        assert sum(e['event_type'] == 'form_submit' for e in events) == 1
        assert sum(e['event_type'] == 'form_abandon' for e in events) == 1
        browser.close()
