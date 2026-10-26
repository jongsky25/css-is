"""Explicit and automatic preview edits must load outside the lazy-load margin."""
import os
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in real HTTP browser check')


@pytest.mark.parametrize('manual',[True,False],ids=['update-button','automatic-change'])
def test_edited_preview_loads_when_far_below_viewport(baseline_server,manual):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        cdp=context.new_cdp_session(page);cdp.send('Network.enable')
        cdp.send('Network.setBlockedURLs',{'urls':['https://*']})
        page.goto(origin+'/admin/appearance')
        page.evaluate("document.querySelector('.appearance-preview-panel').style.marginTop='10000px'")
        frame=page.locator('#appearance-preview')
        for outfit in ['halloween','halloween_vampire','halloween_pumpkin','christmas']:
            page.locator('#editor-outfit').select_option(outfit)
            if manual:page.locator('#appearance-preview-button').click()
            assert frame.bounding_box()['y']>5000
            page.frame_locator('#appearance-preview').locator(
                f'svg[data-avatar-outfit="{outfit}"]').first.wait_for(timeout=10000)
            # Loading completes without bringing the preview into view.
            assert frame.bounding_box()['y']>5000
        assert not errors
        context.close();browser.close()
