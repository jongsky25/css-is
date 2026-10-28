"""Verify a clamped chase stops mutating unchanged movement styles."""
import os
import shutil
import pytest
from tests.avatar_integration_support import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser verification')


def test_clamped_chase_avoids_redundant_style_writes(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();page.goto(origin+'/?view=me')
        button=page.locator('.av-play-btn');button.focus()
        for _ in range(120):page.keyboard.press('ArrowLeft')
        page.wait_for_timeout(500)
        play=page.locator('.av-play').first.bounding_box()
        wrap=page.locator('.avwrap[data-interactive]').first.bounding_box()
        assert play['x']>80
        page.mouse.move(play['x']-80,wrap['y']+wrap['height']*.6)
        page.wait_for_timeout(400)
        page.evaluate('''()=>{const w=document.querySelector('.avwrap[data-interactive]'),m=w.querySelector('.avmove');
          window.chaseWrites=[];window.chaseObserver=new MutationObserver(rs=>chaseWrites.push(...rs.map(r=>({target:r.target===w?'wrap':'art',old:r.oldValue,value:r.target.getAttribute('style')}))));
          for(const e of [w,m])chaseObserver.observe(e,{attributes:true,attributeFilter:['style'],attributeOldValue:true});}''')
        page.wait_for_timeout(1000)
        state=page.evaluate('''()=>({writes:chaseWrites,chasing:document.querySelector('.avwrap[data-interactive]').classList.contains('av-chasing'),facing:document.querySelector('.avwrap[data-interactive] .avmove').style.transform})''')
        assert state['chasing']
        assert state['facing']=='scale(-1, 1)'
        assert state['writes']==[],state
        page.mouse.move(play['x']+play['width']/2,wrap['y']+wrap['height']*.6)
        page.wait_for_timeout(200)
        assert page.locator('.avwrap[data-interactive] .avmove').evaluate('e=>e.style.transform')=='scale(1, 1)'
        context.close();browser.close()
