"""Bounded current-main mobile frame checks; no GC or native hook instrumentation."""
import json
import os
from pathlib import Path
import shutil
import time

import pytest
from tests.avatar_integration_support import baseline_server, PROBE

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in browser acceptance')


@pytest.mark.parametrize('kind', ['cat', 'fern', 'fish', 'bat'])
def test_mobile_frame_budget_on_current_application(baseline_server, app_mod, kind):
    import storage as st
    from playwright.sync_api import sync_playwright
    origin, cookie, uid = baseline_server
    conn = st.connect(app_mod.DB)
    st.set_user_avatar(conn, uid, kind, 'Release companion')
    conn.close()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, timezone_id='UTC')
        context.add_cookies([cookie])
        context.add_init_script(PROBE)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        cdp = context.new_cdp_session(page)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        page.goto(origin + '/?view=me')
        page.wait_for_timeout(2000)
        page.evaluate('avatarProbe.frames=[]')
        started = time.monotonic()
        actions = 0
        while time.monotonic() - started < 30:
            box = page.locator('.avwrap').first.bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2 + (10 if actions % 2 else -10), box['y'] + 20)
            if actions % 5 == 0:
                page.locator('.av-play-btn').first.click()
            page.wait_for_timeout(800)
            actions += 1
        frames = page.evaluate('avatarProbe.frames')
        result = {'kind': kind, 'seconds': time.monotonic() - started, 'cpu': 4,
                  'frame_count': len(frames), 'frame_p95_ms': sorted(frames)[int(.95 * (len(frames) - 1))],
                  'actions': actions, 'errors': errors, 'browser': browser.version}
        out = Path(os.environ['CSS_AVATAR_OUT']).parent
        out.mkdir(parents=True, exist_ok=True)
        (out / ('frame-' + kind + '.json')).write_text(json.dumps(result, indent=2))
        assert len(frames) > 100 and actions > 10
        assert result['frame_p95_ms'] <= 33 and not errors, result
        context.close()
        browser.close()
