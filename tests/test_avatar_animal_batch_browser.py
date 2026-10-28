"""Real authenticated care and rig contracts for the current bounded art batch."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in browser artwork acceptance')

@pytest.mark.parametrize('kind', os.getenv('CSS_AVATAR_BATCH_KINDS', 'dog,rabbit,bird,turtle').split(','))
def test_animal_care_and_rig(baseline_server, app_mod, kind):
    import storage as st
    from playwright.sync_api import sync_playwright
    origin, cookie, uid = baseline_server
    conn = st.connect(app_mod.DB)
    st.set_user_avatar(conn, uid, kind, 'Synthetic companion')
    conn.close()
    out = Path(os.environ['CSS_AVATAR_OUT']).parent
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        context = browser.new_context(viewport={'width':390,'height':844}, has_touch=True)
        context.add_cookies([cookie])
        page = context.new_page(); errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        assert page.goto(origin+'/?view=me').status == 200
        svg = page.locator('.avwrap[data-interactive] svg[data-avatar-kind]').first
        assert svg.get_attribute('data-avatar-kind') == kind
        assert svg.get_attribute('data-avatar-stage') == '6'
        assert svg.evaluate('e=>getComputedStyle(e).filter') == 'none'
        for hook in ['.av-head','.av-eye','.av-food','.av-anchor-head','.av-anchor-neck']:
            assert svg.locator(hook).count() > 0
        for hook in {'dog':['.av-tail','.av-ear-l','.av-ear-r'], 'rabbit':['.av-ear-l','.av-ear-r'], 'bird':['.av-wing-l','.av-wing-r'], 'turtle':['.av-head']}.get(kind,[]):
            assert svg.locator(hook).count() > 0
        assert page.goto(origin+'/wellness').status == 200
        with page.expect_response(lambda r:r.url.endswith('/avatar/care')) as response:
            page.locator('.av-care-btn').click(force=True)
        assert response.value.status == 200 and response.value.json()['ok']
        conn=st.connect(app_mod.DB);profile=st.get_user_profile(conn,uid);conn.close()
        assert profile['avatar_kind']==kind and profile['avatar_last_care_at']
        page.screenshot(path=str(out/f'care-{kind}.png'),full_page=True)
        assert not errors
        (out/f'care-{kind}.json').write_text(json.dumps({'kind':kind,'stage':6,'response':response.value.json(),'persisted':True,'errors':errors},indent=2))
        context.close();browser.close()
