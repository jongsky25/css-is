"""Native filter, pagination and stable queue-return journeys with synthetic data."""
from urllib.parse import urlsplit, parse_qs

import pytest
from playwright.sync_api import expect
from tests.test_document_guidance_browser import browser
from tests.test_document_guidance_routes import detail_record
from tests.test_document_registry_pagination import seed_many


@pytest.mark.parametrize('width,scripts',[(390,True),(1280,True),(390,False)])
def test_filter_page_and_return_with_keyboard(browser,detail_record,viewer,width,scripts):
    c,user,doc,url=detail_record
    ids=seed_many(c,user,None,34)
    c.execute("UPDATE document SET due_date='2026-01-01',lead_id=?,instruction_state='routed'",(user['id'],));c.commit()
    context=browser.new_context(viewport={'width':width,'height':844},java_script_enabled=scripts)
    page=context.new_page();writes=[];errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def serve(route):
        req=route.request;parts=urlsplit(req.url)
        if parts.hostname!='office.test':route.abort();return
        if req.method!='GET':writes.append(req.url);route.abort();return
        response=viewer.get(parts.path+('?' + parts.query if parts.query else ''),follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    try:
        page.goto('http://office.test/documents/actions')
        form=page.get_by_role('form',name='Filter My next steps')
        form.get_by_label('Documents with…').select_option('ready')
        form.get_by_label('Overdue only').check()
        button=form.get_by_role('button',name='Apply filters');button.focus();button.press('Enter')
        expect(page.get_by_role('status')).to_contain_text('35 matching documents')
        expect(page.get_by_role('status')).to_contain_text('30 documents on this page')
        page.screenshot(path=f'/tmp/my-next-steps-results-{width}-{scripts}.png',full_page=True)
        page.get_by_role('link',name='Next page',exact=True).click()
        expect(page.get_by_role('status')).to_contain_text('5 documents on this page')
        anchor=page.locator('.doc-action-card').first.get_attribute('id')
        page.locator('.doc-action-card h3 a').first.click()
        back=page.get_by_role('link',name='← Back to My desk',exact=True)
        expect(back).to_be_visible();back.click()
        expect(page.get_by_role('status')).to_contain_text('5 documents on this page')
        parts=urlsplit(page.url)
        assert parts.fragment==anchor
        assert parse_qs(parts.query)['step_state']==['ready']
        assert parse_qs(parts.query)['overdue']==['1']
        # Applying another filter resets the cursor, including without scripts.
        page.get_by_label('Documents with…').select_option('attention')
        page.get_by_role('button',name='Apply filters').click()
        expect(page.get_by_role('status')).to_contain_text('0 matching documents')
        assert 'before' not in parse_qs(urlsplit(page.url).query)
        assert page.locator('.doc-action-card').count()==0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width==390:
            page.locator('body').evaluate("el => el.style.zoom='200%'")
            expect(page.get_by_role('button',name='Apply filters')).to_be_visible()
        assert not writes and not errors
        page.screenshot(path=f'/tmp/my-next-steps-{width}-{scripts}.png',full_page=True)
    finally:context.close()
