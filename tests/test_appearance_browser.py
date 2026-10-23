"""Browser → real application routes → SQLite → live seasonal rendering."""
import shutil

import pytest

import appearance as rules
import appearance_storage as store
import storage as st

pw = pytest.importorskip('playwright.sync_api')


@pytest.fixture(scope='module')
def seasonal_browser():
    with pw.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=shutil.which('chromium') or None,
                                                 args=['--no-sandbox'])
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip('Install Chromium to run browser appearance checks')
            raise
        yield browser
        browser.close()


def page_for(browser, client, **options):
    context = browser.new_context(service_workers='block', **options)
    page = context.new_page()

    def serve(route):
        request = route.request
        response = client.request(request.method, request.url,
                                  content=request.post_data_buffer,
                                  headers={k: v for k, v in request.headers.items() if k in
                                           ('content-type', 'origin', 'referer', 'accept', 'sec-fetch-site')},
                                  follow_redirects=True)
        route.fulfill(status=response.status_code, body=response.content,
                      headers={k: v for k, v in response.headers.items() if k.lower() not in
                               ('content-length', 'content-encoding', 'set-cookie')})

    page.route('http://testserver/**', serve)
    return context, page


def test_publish_private_preview_mobile_and_live_outfit_without_form_reload(seasonal_browser, admin, viewer, app_mod, tmp_path):
    admin_context, editor = page_for(seasonal_browser, admin, viewport={'width': 1440, 'height': 1000})
    viewer_context, page = page_for(seasonal_browser, viewer)
    errors = []
    editor.on('pageerror', lambda error: errors.append(str(error)))
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto('http://testserver/me')
        page.locator('#avatar_name').fill('Keep my unsaved edit')
        editor.goto('http://testserver/admin/appearance')
        editor.locator('#appearance-editor input[name="theme"][value="halloween"]').check()
        # Selecting the preset enables artwork and updates the private preview.
        pw.expect(editor.locator('#appearance-editor input[name="artwork"]')).to_be_checked()
        pw.expect(editor.frame_locator('#appearance-preview').locator('.halloween-banner')).to_be_visible()
        editor.locator('#editor-outfit').select_option('christmas')
        editor.locator('#appearance-editor input[name="effects"]').check()
        editor.get_by_role('button', name='Update preview').click()
        frame = editor.frame_locator('#appearance-preview')
        pw.expect(frame.locator('html')).to_have_attribute('data-season', 'halloween')
        pw.expect(frame.locator('html')).to_have_attribute('data-appearance-preview', '1')
        assert viewer.get('/appearance/current').json()['theme'] == 'default'
        editor.get_by_role('button', name='Mobile', exact=True).click()
        pw.expect(editor.locator('#appearance-preview')).to_have_css('width', '390px')
        editor.get_by_role('button', name='Publish now', exact=True).click()
        pw.expect(editor.get_by_role('status').filter(has_text='Appearance settings saved')).to_be_visible()
        pw.expect(editor.frame_locator('#appearance-preview').locator('html')).to_have_attribute('data-season', 'halloween')
        pw.expect(editor.frame_locator('#appearance-preview').locator('h1')).to_be_visible()
        editor.screenshot(path=str(tmp_path / 'appearance-desktop.png'))
        page.bring_to_front()
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        pw.expect(page.locator('html')).to_have_attribute('data-season', 'halloween')
        svg = page.locator('svg[data-avatar-kind="cat"]').first
        pw.expect(svg).to_have_attribute('data-avatar-month', '12')
        assert svg.locator('.av-acc path').count() > 0
        pw.expect(page.locator('#avatar_name')).to_have_value('Keep my unsaved edit')
        # Catalog examples retain their explicitly chosen outfits during polling.
        pw.expect(editor.locator('[data-appearance-sample] svg').first).to_have_attribute('data-avatar-month', '0')
        editor.set_viewport_size({'width': 390, 'height': 844})
        assert editor.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        editor.screenshot(path=str(tmp_path / 'appearance-mobile.png'))
        editor.emulate_media(reduced_motion='reduce')
        assert editor.locator('.season-decoration').evaluate('(element)=>getComputedStyle(element).animationName') == 'none'
        editor.evaluate("document.documentElement.dataset.theme='contrast'")
        assert editor.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == '#002060'
        connection = st.connect(app_mod.DB)
        try:
            assert store.load(connection)['override']['selection']['outfit'] == 'christmas'
        finally:
            connection.close()
        assert not errors
    finally:
        viewer_context.close()
        admin_context.close()


def test_timed_transition_updates_open_page_and_preserves_form(seasonal_browser, viewer, app_mod, monkeypatch):
    now = rules.local_timestamp('2026-10-31T23:59')
    clock = [now]
    original_resolve = rules.resolve
    monkeypatch.setattr(rules, 'resolve', lambda config, now=None: original_resolve(config, clock[0]))
    connection = st.connect(app_mod.DB)
    try:
        store.mutate(connection, 'test', 0, 'event', {'name': 'Halloween ending', 'theme': 'halloween',
                     'outfit': 'halloween', 'start': '2026-10-01T00:00', 'end': '2026-11-01T00:00',
                     'timezone': 'Asia/Manila', 'status': 'published'})
    finally:
        connection.close()
    context, page = page_for(seasonal_browser, viewer)
    try:
        page.clock.install(time=now * 1000)
        page.goto('http://testserver/me')
        pw.expect(page.locator('html')).to_have_attribute('data-season', 'halloween')
        page.locator('#avatar_name').fill('Do not reload')
        clock[0] += 60
        page.clock.fast_forward(61000)
        pw.expect(page.locator('html')).to_have_attribute('data-season', 'default')
        pw.expect(page.locator('svg[data-avatar-kind="cat"]').first).to_have_attribute('data-avatar-month', '11')
        pw.expect(page.locator('#avatar_name')).to_have_value('Do not reload')
    finally:
        context.close()


def test_full_scene_controls_same_month_costume_change_and_mobile(seasonal_browser, admin, viewer):
    from tests.test_appearance import submit
    assert submit(admin, 'publish', theme='halloween', outfit='halloween', artwork_present='1',
                  artwork='1', effects='1', banner='Boo, team!').status_code == 303
    context, page = page_for(seasonal_browser, viewer, viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    try:
        page.goto('http://testserver/me')
        pw.expect(page.locator('.halloween-banner')).to_be_visible()
        pw.expect(page.locator('[data-season-banner-message]')).to_have_text('Boo, team!')
        assert page.locator('.nav-toggle > summary').evaluate('(el)=>getComputedStyle(el).color') == page.locator('.topnav .brand').evaluate('(el)=>getComputedStyle(el).color')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert page.locator('.halloween-flying-bat').evaluate('(el)=>getComputedStyle(el).animationName') == 'none'
        page.locator('#avatar_name').fill('Keep this edit')
        svg = page.locator('svg[data-avatar-kind="cat"]').first
        pw.expect(svg).to_have_attribute('data-avatar-outfit', 'halloween')
        head = svg.locator('.av-head').first
        head.evaluate('(el)=>el.dataset.preserved="yes"')
        assert submit(admin, 'publish', theme='halloween', outfit='halloween_pumpkin', artwork_present='1',
                      banner='Pumpkin time!').status_code == 303
        page.bring_to_front()
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        pw.expect(svg).to_have_attribute('data-avatar-outfit', 'halloween_pumpkin')
        pw.expect(svg).to_have_attribute('data-avatar-month', '10')
        pw.expect(svg.locator('.av-head').first).to_have_attribute('data-preserved', 'yes')
        assert svg.locator('.av-costume-front ellipse').count() == 1
        pw.expect(page.locator('.halloween-banner')).to_be_hidden()
        pw.expect(page.locator('#avatar_name')).to_have_value('Keep this edit')
        assert submit(admin, 'publish', theme='halloween', outfit='halloween_vampire', artwork_present='1',
                      artwork='1', banner='Welcome, night shift!').status_code == 303
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        pw.expect(svg).to_have_attribute('data-avatar-outfit', 'halloween_vampire')
        pw.expect(page.locator('.halloween-banner')).to_be_visible()
        pw.expect(page.locator('[data-season-banner-message]')).to_have_text('Welcome, night shift!')
        page.emulate_media(media='print')
        pw.expect(page.locator('.halloween-banner')).to_be_hidden()
        pw.expect(page.locator('.halloween-footer')).to_be_hidden()
    finally:
        context.close()
