"""Container-only resizing must refresh keyboard movement bounds."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.avatar_integration_support import baseline_server, PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1',reason='Opt-in real HTTP browser check')


def test_container_resize_without_window_resize_or_scroll(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='UTC',reduced_motion='reduce')
        context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();page.goto(origin+'/?view=me')
        wrap=page.locator('.avwrap[data-interactive]')
        wrap.locator('.av-play-btn').focus();page.wait_for_timeout(300)
        scroll=page.evaluate('scrollY')
        page.evaluate("const play=document.querySelector('.av-play');play.style.height=(play.clientHeight+150)+'px'")
        page.wait_for_timeout(300)
        for _ in range(100):page.keyboard.press('ArrowDown')
        page.wait_for_timeout(300)
        result=wrap.evaluate('''w=>{const p=w.closest('.av-play'),r=w.getBoundingClientRect(),b=p.getBoundingClientRect();return {bottom:r.bottom-b.top,height:p.clientHeight,scrollY:scrollY}}''')
        Path(os.environ['CSS_AVATAR_OUT'],'container-resize.json').write_text(json.dumps(result,indent=2))
        assert result['scrollY']==scroll
        assert abs(result['height']-result['bottom'])<=2,result
        context.close();browser.close()
