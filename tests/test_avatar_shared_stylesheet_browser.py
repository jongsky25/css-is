"""Opt-in real HTTP stylesheet transport check, separate from memory measurement."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server,PROBE

pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE')!='1' or not Path('static/css/avatars.css').exists(),reason='Opt-in candidate-only browser check')


def test_shared_stylesheet_real_http(baseline_server):
    from playwright.sync_api import sync_playwright
    origin,cookie,_=baseline_server;css=Path('static/css/avatars.css').read_bytes();rows=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(service_workers='block');context.add_cookies([cookie]);context.add_init_script(PROBE)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        cdp=context.new_cdp_session(page);cdp.send('Network.enable');cached=[]
        cdp.on('Network.requestServedFromCache',lambda e:cached.append(e))
        for route in ['/?view=me','/wellness','/?view=me']:
            page.goto(origin+route,wait_until='load')
            link=page.locator('link[href="/static/css/avatars.css?v=1"]');assert link.count()==1
            assert link.evaluate('e=>e.sheet.cssRules.length')>100
            assert page.locator('.avwrap').first.evaluate('e=>getComputedStyle(e).display')=='inline-block'
            rows.append(page.evaluate("performance.getEntriesByType('resource').filter(r=>r.name.includes('/static/css/avatars.css')).map(r=>({name:r.name,transfer:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize}))"))
        response=context.request.get(origin+'/static/css/avatars.css?v=1')
        assert response.ok and response.body()==css and 'text/css' in response.headers['content-type']
        assert len(rows)==3 and all(len(r)==1 for r in rows)
        # A revalidated response may carry headers, but must not retransmit the CSS body.
        assert all(r[0]['encoded']==0 and r[0]['decoded']==0 for r in rows[1:])
        assert not errors
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']);out.mkdir(parents=True,exist_ok=True)
    (out/'stylesheet-http.json').write_text(json.dumps({'css_sha256':hashlib.sha256(css).hexdigest(),'observations':rows,'cached_events':len(cached),'errors':errors,'scope':'Real HTTP, no routing. HTTP reuse only; not service-worker/offline acceptance.'},indent=2)+'\n')
