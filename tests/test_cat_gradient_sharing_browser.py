"""Real-page gradient registry survives preview replacement and navigation."""
import os
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in candidate browser check')


def test_shared_cat_gradients_resolve_after_preview_removal(baseline_server):
    from playwright.sync_api import sync_playwright
    origin, cookie, _ = baseline_server
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        context = browser.new_context(service_workers='block');context.add_cookies([cookie])
        page = context.new_page(); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        for route in ['/?view=me', '/me', '/wellness', '/admin/appearance', '/?view=me']:
            page.goto(origin+route, wait_until='load')
            cats=page.locator('svg[data-avatar-kind="cat"]')
            assert cats.count()>0
            assert page.locator('#avg-cat-v2-fur').count()==1
            assert page.locator('#avg-cat-v2-cream').count()==1
            assert page.locator('svg[data-avatar-kind="cat"] defs').count()==0
            result=page.evaluate('''()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);const paints=[...document.querySelectorAll('svg[data-avatar-kind="cat"] [fill^="url(#avg-cat-v2-"]')];return {unique:ids.length===new Set(ids).size,painted:paints.length,valid:paints.every(e=>{const id=e.getAttribute('fill').slice(5,-1);return document.getElementById(id)?.tagName==='linearGradient'&&getComputedStyle(e).fill.includes(id)})}}''')
            assert result['unique'] and result['painted']>0 and result['valid']
            if cats.count()>1:
                cats.first.evaluate('e=>e.remove()')
                assert page.locator('#avg-cat-v2-fur').count()==1
                assert cats.first.locator('[fill="url(#avg-cat-v2-fur)"]').count()>0
        assert not errors
        context.close();browser.close()
