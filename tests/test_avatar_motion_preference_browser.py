"""Input uses cached preferences while live accessibility changes still work."""
import os
import shutil
import pytest
from tests.avatar_integration_support import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser verification')


def test_pointer_uses_event_updated_motion_preference(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();page.goto(origin+'/?view=me');page.wait_for_timeout(200)
        page.evaluate('''()=>{window.avatarPreferenceReads=0;
          const d=Object.getOwnPropertyDescriptor(MediaQueryList.prototype,'matches');
          Object.defineProperty(MediaQueryList.prototype,'matches',{...d,get(){
            if(new Error().stack.includes('/avatars.js'))avatarPreferenceReads++;
            return d.get.call(this);}});}''')
        wrap=page.locator('.avwrap[data-interactive]').first
        box=wrap.bounding_box();x=box['x']+box['width']*.7;y=box['y']+40
        for i in range(20):page.mouse.move(x+i%3,y)
        page.wait_for_timeout(100)
        assert 'rotateY' in wrap.locator('.av-tiltstage').get_attribute('style')
        page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(100)
        frozen=wrap.locator('.av-tiltstage').get_attribute('style')
        page.mouse.move(10,10);page.wait_for_timeout(100)
        assert wrap.locator('.av-tiltstage').get_attribute('style')==frozen
        page.emulate_media(reduced_motion='no-preference');page.wait_for_timeout(100)
        page.mouse.move(x,y);page.mouse.move(10,10);page.wait_for_timeout(100)
        assert wrap.locator('.av-tiltstage').evaluate('e=>e.style.transform')==''
        assert page.evaluate('avatarPreferenceReads')==0
        context.close();browser.close()
