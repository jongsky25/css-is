"""Opt-in static-preview policy and live keyboard reaction verification."""
import json
import os
from pathlib import Path
import shutil

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser verification')


def test_previews_static_live_companion_replays(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+'/?view=me');page.wait_for_timeout(200)
        home=page.evaluate('''()=>({decorative:document.querySelectorAll('.avwrap:not([data-interactive])').length,
          decorative_running:document.getAnimations().filter(a=>a.playState==='running'&&a.effect.target.closest('.avwrap:not([data-interactive])')).length,
          live_running:document.getAnimations().filter(a=>a.playState==='running'&&a.effect.target.closest('.avwrap[data-interactive]')).length})''')
        assert home['decorative_running']==0 and home['live_running']>0
        page.locator('.av-play-btn').focus();page.keyboard.press('Enter');page.wait_for_timeout(150)
        first=page.evaluate("()=>document.getAnimations().find(a=>a.animationName==='av-bounce').currentTime")
        page.keyboard.press('Enter');page.wait_for_timeout(50)
        second=page.evaluate("()=>document.getAnimations().find(a=>a.animationName==='av-bounce').currentTime")
        assert second<first, 'A second live tap did not restart the active bounce'
        page.goto(origin+'/me');page.wait_for_timeout(300)
        profile=page.evaluate('''()=>({previews:document.querySelectorAll('.avcard svg').length,
          running:document.getAnimations().filter(a=>a.playState==='running'&&a.effect.target.closest('.avcard, .avwrap:not([data-interactive])')).length})''')
        assert profile['previews']>=16 and profile['running']==0
        assert not errors
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent
    (out/'static-preview-policy.json').write_text(json.dumps({'home':home,'profile':profile,'first_bounce_time_ms':first,'replayed_bounce_time_ms':second,'errors':errors},indent=2))
