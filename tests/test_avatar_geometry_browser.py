"""Opt-in geometry invalidation and repeated-input layout-read regression."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server,PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser verification')


def test_cached_geometry_preserves_drag_chase_resize_scroll(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,timezone_id='UTC')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+'/?view=me');page.wait_for_timeout(600)
        wrap=page.locator('.avwrap[data-interactive]');button=wrap.locator('.av-play-btn')
        page.evaluate('''()=>{window.avatarGeometryReads=0;for(const el of document.querySelectorAll('.avwrap[data-interactive],.avwrap[data-interactive] .av-head,.av-play')){
          const original=el.getBoundingClientRect;el.getBoundingClientRect=function(){avatarGeometryReads++;return original.call(this)}}}''')
        # Browser input deliberately queries its own native bounds; the counter
        # detects production JS calls on the measured elements only.
        box=button.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
        before=wrap.get_attribute('style')
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+30,y+20,steps=6);page.mouse.up()
        page.wait_for_timeout(300)
        assert wrap.get_attribute('style')!=before
        for index in range(8):
            page.mouse.move(x+(index%3)*8,y+5);page.wait_for_timeout(90)
        reads=page.evaluate('avatarGeometryReads')
        assert reads==0, f'Repeated input still reads live bounds: {reads}'
        # Change layout, scroll, and drive beyond the play area. Cached clamp
        # bounds must follow both changes and preserve keyboard movement.
        page.set_viewport_size({'width':640,'height':844});page.wait_for_timeout(300)
        page.evaluate("document.querySelector('.av-play').style.height='420px'")
        page.wait_for_timeout(300);page.evaluate('window.scrollTo(0,80)');page.wait_for_timeout(150)
        box=button.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+900,y+900,steps=5);page.mouse.up();page.wait_for_timeout(150)
        clamp=wrap.evaluate('''w=>{const p=w.closest('.av-play'),r=w.getBoundingClientRect(),b=p.getBoundingClientRect();return {left:r.left-b.left,top:r.top-b.top,right:r.right-b.left,bottom:r.bottom-b.top,width:p.clientWidth,height:p.clientHeight}}''')
        assert clamp['left']>=-1 and clamp['top']>=-1 and clamp['right']<=clamp['width']+2 and clamp['bottom']<=clamp['height']+2,clamp
        previous=wrap.get_attribute('style');button.focus();page.keyboard.press('ArrowLeft')
        assert wrap.get_attribute('style')!=previous
        assert not errors
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent;out.mkdir(parents=True,exist_ok=True)
    (out/'geometry-behavior.json').write_text(json.dumps({'steady_input_live_geometry_reads':reads,'resize_scroll_clamp':clamp,'errors':errors},indent=2))
