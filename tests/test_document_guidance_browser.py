"""Keyboard navigation to real document controls never submits an action."""
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.test_document_guidance_routes import detail_record

pw=pytest.importorskip('playwright.sync_api')


@pytest.fixture(scope='module')
def browser():
    with pw.sync_playwright() as playwright:
        system=Path('/usr/bin/chromium')
        try:
            browser=playwright.chromium.launch(executable_path=str(system) if system.exists() else None)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip('Install Chromium with python -m playwright install chromium')
            raise
        yield browser
        browser.close()


@pytest.mark.parametrize('width,theme,action',[(390,'light','attach'),(1280,'dark','attach'),(390,'light','contribution')])
def test_guidance_keyboard_link_reveals_and_focuses_existing_form(browser,detail_record,viewer,width,theme,action):
    c,user,doc,url=detail_record
    if action=='contribution':
        c.execute("UPDATE document SET direction='IN',policy_json=? WHERE id=?",('{"closure":[]}',doc['id']));c.commit()
        aid=c.execute('SELECT id FROM document_assignment WHERE document_id=?',(doc['id'],)).fetchone()[0]
        selector='#document-contribution-'+str(aid)
        link_selector='#document-next a[href^="#document-contribution-"]'
        field='textarea[name=outcome]'
    else:
        selector='#document-action-attach'
        link_selector='#document-next a.doc-next-action'
        field='input[name=url]'
    context=browser.new_context(viewport={'width':width,'height':850},color_scheme=theme)
    page=context.new_page()
    posts=[];errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def serve(route):
        request=route.request;parts=urlsplit(request.url)
        if parts.hostname!='office.test':route.abort();return
        if request.method!='GET':posts.append(request.url);route.abort();return
        response=viewer.get(parts.path+('?' + parts.query if parts.query else ''),follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    try:
        page.goto('http://office.test'+url)
        target=page.locator(selector)
        assert not target.evaluate('element => element.open')
        link=page.locator(link_selector)
        link.focus();link.press('Enter')
        page.wait_for_function("selector => document.activeElement === document.querySelector(selector + ' > summary')", arg=selector)
        assert target.evaluate('element => element.open && element.closest(".doc-secondary").open')
        assert target.locator(field).is_visible()
        assert not posts
        assert target.locator('summary').evaluate('element => element.tabIndex') == 0
        target.evaluate('element => element.open = false')
        link.click()
        page.wait_for_function("selector => document.querySelector(selector).open", arg=selector)
        # Arrival with a bookmarked action also opens the actual control.
        page.reload()
        page.wait_for_function("selector => document.activeElement === document.querySelector(selector + ' > summary')", arg=selector)
        # A malformed or missing fragment must not break the page script.
        page.evaluate("location.hash = '%E0%A4%A'")
        page.wait_for_timeout(50)
        page.evaluate("location.hash = 'missing-action'")
        page.wait_for_timeout(50)
        assert not errors
        assert not posts
        assert c.execute('SELECT revision FROM document WHERE id=?',(doc['id'],)).fetchone()[0]==doc['revision']
        panel=page.locator('#document-next')
        assert panel.evaluate('element => element.scrollWidth <= element.clientWidth')
    finally:
        context.close()
