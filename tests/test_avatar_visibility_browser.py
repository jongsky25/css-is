import os, json, socket, time, shutil
from pathlib import Path
import pytest
from tests.avatar_integration_support import baseline_server, PROBE, snapshot, reset
pytestmark=pytest.mark.skipif(os.getenv("CSS_AVATAR_BASELINE")!="1",reason="Opt-in browser acceptance")

def test_native_visibility_and_touch(baseline_server, tmp_path):
    """Use a native tab without Playwright's forced-active-page override."""
    import subprocess
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    out=Path(os.getenv('CSS_AVATAR_OUT','docs/avatars/application'));out.mkdir(parents=True,exist_ok=True)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    process=subprocess.Popen([shutil.which('chromium'),'--headless','--no-sandbox',f'--remote-debugging-port={port}',
                              f'--user-data-dir={tmp_path / "native-profile"}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        import urllib.request
        for attempt in range(100):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=1):break
            except OSError:time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}',no_defaults=True)
            context=browser.contexts[0];context.add_cookies([cookie]);context.add_init_script(PROBE)
            page=context.pages[0];page.set_viewport_size({'width':390,'height':844});page.goto(origin+'/?view=me')
            cdp=context.new_cdp_session(page);page.wait_for_timeout(500)
            illustrated_filters=page.locator('.avwrap svg[data-avatar-art="v2"]').evaluate_all('(els)=>els.map(el=>getComputedStyle(el).filter)')
            if illustrated_filters: assert all(value=='none' for value in illustrated_filters)
            visible=snapshot(page,cdp)
            page.screenshot(path=str(out/'home-native.png'))
            page.evaluate("document.querySelector('.avwrap').closest('.av-play').style.marginTop='2000px'")
            reset(page);page.wait_for_timeout(int(os.getenv('CSS_AVATAR_SECONDS','30'))*1000)
            offscreen=snapshot(page,cdp)
            page.evaluate("document.querySelector('.avwrap').closest('.av-play').style.marginTop=''")
            other=context.new_page();other.goto('about:blank');other.bring_to_front()
            page.wait_for_function('document.hidden')
            reset(page);before=snapshot(page,cdp)
            other.wait_for_timeout(int(os.getenv('CSS_AVATAR_SECONDS','30'))*1000)
            hidden=snapshot(page,cdp)
            assert hidden['hidden']
            other.close();page.bring_to_front();page.wait_for_function('!document.hidden')
            # Touch uses trusted browser input on the real drag surface.
            cdp.send('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':1})
            box=page.locator('.avwrap').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
            before_drag=page.locator('.avwrap').get_attribute('style')
            cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+25,'y':y+10}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            after_drag=page.locator('.avwrap').get_attribute('style')
            assert before_drag!=after_drag, 'Touch drag did not move the real Home companion'
            before_nudge=page.locator('.avwrap').get_attribute('style')
            page.locator('.av-play-btn').focus();page.keyboard.press('ArrowLeft')
            assert before_nudge!=page.locator('.avwrap').get_attribute('style'), 'Keyboard nudge did not move companion'
            keyboard_style=page.locator('.avwrap').get_attribute('style')
            page.goto(origin+'/me');page.wait_for_timeout(300)
            picker_animations=page.evaluate('''()=>document.getAnimations().filter(a=>a.effect.target.closest('.avcard')).map(a=>({name:a.animationName,state:a.playState,kind:a.effect.target.closest('.avcard').querySelector('svg').dataset.avatarKind}))''')
            page.emulate_media(reduced_motion='reduce')
            for theme in ['light','dark','contrast']:
                page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                page.screenshot(path=str(out/f'profile-native-{theme}.png'),full_page=True)
            (out/'native-visibility-touch.json').write_text(json.dumps({'illustrated_svg_filters':illustrated_filters,'picker_animations':picker_animations,'visible':visible,'offscreen':offscreen,'hidden_start':before,'hidden_end':hidden,
                 'touch_drag_changed_style':before_drag!=after_drag,'keyboard_nudge_style':keyboard_style,
                 'method':'Native Chromium tabs; connect_over_cdp(no_defaults=True), no visibility getter override'},indent=2))
            browser.close()
    finally:
        process.terminate();process.wait(timeout=10)


