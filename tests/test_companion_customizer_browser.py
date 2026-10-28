"""Real mobile customization and shared motion-policy integration."""
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in browser integration')


def test_mobile_preview_cancel_save_and_seasonal_update(baseline_server,app_mod):
    import storage as st
    from playwright.sync_api import sync_playwright, expect
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,'cat','Miso');conn.close()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844},has_touch=True,reduced_motion='reduce')
        context.add_cookies([cookie]);context.add_init_script(PROBE);page=context.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+'/me#companion')
        page.locator('#avatar-appearance-mode').select_option('personal')
        page.locator('#avatar-primary').select_option('small_cap')
        expect(page.locator('#companion-customizer-preview [data-equipment="small_cap"]')).to_have_count(1)
        conn=st.connect(app_mod.DB);assert st.get_user_profile(conn,uid)['avatar_wardrobe']['mode']=='seasonal';conn.close()
        page.locator('#companion-customizer-cancel').click()
        expect(page.locator('#avatar-appearance-mode')).to_have_value('seasonal')
        expect(page.locator('#companion-customizer-preview [data-equipment]')).to_have_count(0)
        page.locator('#avatar-appearance-mode').select_option('personal')
        page.locator('#avatar-primary').select_option('small_cap');page.locator('#avatar-secondary').select_option('bandana')
        expect(page.locator('#companion-customizer-preview [data-equipment]')).to_have_count(2)
        page.locator('#companion-customizer button[type=submit]').click()
        page.wait_for_url('**/?msg=*')
        expect(page.locator('.avwrap[data-interactive] svg[data-avatar-kind="cat"] [data-equipment]')).to_have_count(2)
        page.goto(origin+'/wellness')
        expect(page.locator('.avwrap[data-interactive] svg[data-avatar-kind="cat"] [data-equipment]')).to_have_count(2)
        # Existing refresh runs after focus; personal equipment must survive it.
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.wait_for_timeout(350)
        expect(page.locator('.avwrap[data-interactive] svg[data-avatar-kind="cat"][data-avatar-mode="personal"] [data-equipment]')).to_have_count(2)
        page.goto(origin+'/me#companion');page.locator('[name=avatar_kind][value=fern]').check(force=True)
        expect(page.locator('#avatar-primary')).to_have_value('')
        expect(page.locator('#avatar-secondary')).to_have_value('')
        expect(page.locator('#companion-customizer-preview svg[data-avatar-kind="fern"]')).to_have_count(1)
        assert page.locator('#avatar-primary option[value=small_cap]').is_disabled()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        out=Path(os.environ['CSS_AVATAR_OUT']).parent;out.mkdir(parents=True,exist_ok=True)
        page.locator('#companion-customizer').screenshot(path=str(out/'mobile-customizer.png'))
        assert not errors
        context.close();browser.close()


def test_motion_suspends_resumes_and_releases_removed_companions(baseline_server):
    from playwright.sync_api import sync_playwright, expect
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1100,'height':900})
        context.add_cookies([cookie]);context.add_init_script(PROBE);page=context.new_page()
        page.goto(origin+'/wellness')
        wrap=page.locator('.avwrap[data-interactive]').first
        wrap.scroll_into_view_if_needed();expect(wrap).to_have_attribute('data-motion-paused','0')
        page.evaluate('window.testCompanion=document.querySelector(".avwrap[data-interactive]")')
        page.emulate_media(reduced_motion='reduce');expect(wrap).to_have_attribute('data-motion-paused','1')
        assert wrap.evaluate("w=>!w._avIdleT&&!w._avRoamT&&!w._avChaseI")
        page.emulate_media(reduced_motion='no-preference');expect(wrap).to_have_attribute('data-motion-paused','0')
        wrap.evaluate("w=>w.closest('.av-play').style.marginTop='3000px'")
        page.evaluate('window.scrollTo(0,0)');expect(wrap).to_have_attribute('data-motion-paused','1')
        assert wrap.evaluate("w=>!w._avIdleT&&!w._avRoamT&&!w._avChaseI")
        wrap.scroll_into_view_if_needed();expect(wrap).to_have_attribute('data-motion-paused','0')
        wrap.locator('.av-care-btn').click(force=True)
        assert wrap.evaluate("w=>w.classList.contains('av-caring-feed')||w.classList.contains('av-caring-water')")
        assert wrap.evaluate("w=>!w.classList.contains('av-do-hop')&&!w.classList.contains('av-do-wag')")
        wrap.evaluate('w=>w.remove()');page.wait_for_timeout(100)
        assert page.evaluate('!testCompanion._avIdleT&&!testCompanion._avRoamT&&!testCompanion._avChaseI')
        context.close();browser.close()


def test_water_followthrough_preserves_leaf_placement(baseline_server,app_mod):
    import storage as st
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,'plant','Sprout');conn.close()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1100,'height':900});context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();page.goto(origin+'/wellness')
        wrap=page.locator('.avwrap[data-interactive]').first
        leaf=wrap.locator('.av-leaf').first
        before=leaf.evaluate('e=>getComputedStyle(e).transform')
        wrap.locator('.av-care-btn').click(force=True)
        page.evaluate("document.getAnimations().filter(a=>a.animationName==='av-leaf-settle').forEach(a=>{a.pause();a.currentTime=1400})")
        assert leaf.evaluate('e=>getComputedStyle(e).transform')==before
        assert leaf.locator('path').first.evaluate('e=>getComputedStyle(e).animationName')=='av-leaf-settle'
        context.close();browser.close()
