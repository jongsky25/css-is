"""Opt-in real-page pointer behavior after batching geometry reads."""
import json
import os
from pathlib import Path
import re
import shutil

import pytest
from tests.avatar_integration_support import baseline_server, PROBE

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in browser verification')


def test_curiosity_and_lean_survive_batched_geometry(baseline_server, app_mod):
    import storage as st
    from playwright.sync_api import sync_playwright
    origin, cookie, uid = baseline_server
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        context = browser.new_context(viewport={'width':1440,'height':1000}, timezone_id='UTC')
        context.add_cookies([cookie]); context.add_init_script(PROBE)
        page = context.new_page(); errors=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        for kind, maximum in [('cat',8),('dog',8),('bird',8),('owl',12)]:
            conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,kind,'Pointer Check');conn.close()
            assert page.goto(origin+'/?view=me').status == 200
            wrap=page.locator('.avwrap[data-kind="'+kind+'"]'); box=wrap.bounding_box()
            page.mouse.move(box['x']+box['width']*.75, box['y']+40)
            page.wait_for_timeout(50)
            state=wrap.evaluate('''w=>({tilt:w.querySelector('.av-tiltstage').style.transform,
                head:w.querySelector('.av-head').style.transform})''')
            assert 'rotateY(' in state['tilt'] and 'rotateX(' in state['tilt'], (kind,state)
            angle=float(re.search(r'rotate\(([-\d.]+)deg\)',state['head'])[1])
            assert -maximum <= angle <= maximum
            page.mouse.move(10,10);page.wait_for_timeout(50)
            assert wrap.locator('.av-tiltstage').evaluate('e=>e.style.transform') == ''
            results.append({'kind':kind,'pointer_inside':state,'head_angle_within_limit':True,'tilt_resets_outside':True})
        assert not errors
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent
    (out/'pointer-behavior.json').write_text(json.dumps({'results':results,'errors':errors},indent=2))
