"""Opt-in preview loading diagnosis, excluded from memory measurements."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_PREVIEW_DIAGNOSTIC')!='1',reason='Opt-in diagnostic')


def test_preview_loading(baseline_server):
    from playwright.sync_api import sync_playwright, TimeoutError
    origin,cookie,_=baseline_server
    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        if os.getenv('CSS_AVATAR_PREVIEW_EAGER')=='1':
            script=Path('static/js/appearance-admin.js').read_text().replace(
                "document.getElementById('appearance-preview').src='/?'+params.toString();",
                "var frame=document.getElementById('appearance-preview');frame.loading='eager';frame.src='/?'+params.toString();")
            context.route('**/static/js/appearance-admin.js*',lambda route:route.fulfill(status=200,content_type='application/javascript',body=script))
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        for displaced in [False,True]:
            page.goto(origin+'/admin/appearance')
            if displaced:
                page.evaluate("document.querySelector('.appearance-preview-panel').style.marginTop='10000px'")
            for outfit in ['halloween','halloween_vampire','halloween_pumpkin','christmas']:
                page.locator('#editor-outfit').select_option(outfit)
                page.locator('#appearance-preview-button').click(force=True)
                row={'displaced':displaced,'outfit':outfit}
                def state():
                    return page.locator('#appearance-preview').evaluate('''f=>({src:f.src,loading:f.loading,bounds:f.getBoundingClientRect().toJSON(),url:f.contentWindow.location.href,ready:f.contentDocument.readyState,avatars:[...f.contentDocument.querySelectorAll('svg[data-avatar-outfit]')].map(s=>s.dataset.avatarOutfit)})''')
                row['before']=state()
                selector=page.frame_locator('#appearance-preview').locator(f'svg[data-avatar-outfit="{outfit}"]').first
                try:
                    selector.wait_for(timeout=30000);row['loaded']=True
                except TimeoutError:
                    row['loaded']=False;row['timeout']=state()
                    page.locator('#appearance-preview').scroll_into_view_if_needed()
                    selector.wait_for(timeout=30000);row['loaded_after_scroll']=True
                row['after']=state();results.append(row)
        context.close();browser.close()
    Path(os.environ['CSS_AVATAR_OUT'],'preview-loading.json').write_text(json.dumps({'results':results,'errors':errors},indent=2))
    assert not errors
    if os.getenv('CSS_AVATAR_PREVIEW_EAGER')=='1':assert all(r['loaded'] for r in results)
