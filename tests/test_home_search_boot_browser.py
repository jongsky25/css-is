"""Opt-in real Home search verification after deferring its viewport lookup."""
import json
import os
from pathlib import Path
import shutil

import pytest
from tests.test_avatar_baseline_browser import baseline_server, PROBE

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in browser verification')


def test_home_responsive_placeholder_and_search(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server
    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        for mobile in [False,True]:
            context=browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1000},timezone_id='UTC',has_touch=mobile)
            context.add_cookies([cookie]);context.add_init_script(PROBE)
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            assert page.goto(origin+'/?view=me').status == 200
            field=page.locator('.oc-search .gsearch-input')
            expected='Search or ask a question…' if mobile else 'Search people, pages, your calendar — or ask a question…'
            assert field.get_attribute('placeholder')==expected
            field.fill('wellness')
            link=page.locator('.oc-search .gsearch-results a[href="/wellness"]').first
            link.wait_for(state='visible')
            link.click();page.wait_for_url(origin+'/wellness')
            assert not errors
            results.append({'mobile':mobile,'placeholder':expected,'search_result_href':'/wellness','navigation_completed':True,'errors':errors})
            context.close()
        browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent
    (out/'home-search-boot.json').write_text(json.dumps({'results':results},indent=2))
