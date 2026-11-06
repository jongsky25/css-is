"""Review form and history against the real routes at phone width."""
from urllib.parse import urlsplit
import pytest
from test_document_registration_browser import browser
from test_document_understanding_review_routes import review_record
import documents_understanding as understanding


def test_correct_saved_review_on_phone_and_retain_original(browser,review_record,viewer):
    conn,user,doc,url=review_record
    context=browser.new_context(viewport={'width':390,'height':844})
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def serve(route):
        request=route.request
        parsed=urlsplit(request.url)
        if parsed.hostname!='office.test': route.abort();return
        target=parsed.path+('?' + parsed.query if parsed.query else '')
        if request.method=='POST':
            response=viewer.post(target,content=request.post_data,headers={'content-type':request.headers['content-type']},follow_redirects=True)
        else: response=viewer.get(target,follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve)
    page.goto('http://office.test'+url)
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    page.locator('[name=need_0_output]').fill('Updated comments matrix')
    page.locator('[name=need_0_confirmed]').check()
    page.locator('[name=focus_confirmed]').check()
    page.locator('[name=reason]').fill('Checked the updated source on page 2')
    page.locator('[name=review_confirmed]').check()
    page.locator('[name=need_0_deadline]').fill('2026-12-01')
    assert not page.locator('[name=need_0_confirmed]').is_checked()
    assert not page.locator('[name=review_confirmed]').is_checked()
    page.locator('[name=need_0_confirmed]').check()
    page.locator('[name=review_confirmed]').check()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button',name='Save reviewed requests',exact=True).click()
    # TestClient follows the POST redirect: Playwright does not reroute a
    # redirected request, which would otherwise escape the synthetic host.
    page.get_by_role('status').filter(has_text='Review saved').wait_for(state='visible')
    assert page.locator('#understanding-history').get_by_text('Updated comments matrix',exact=True).is_visible()
    original=page.locator('details').filter(has=page.locator('summary',has_text='Review 1 ·'))
    original.locator('summary').first.click()
    assert page.locator('#understanding-history').get_by_text('Comments matrix',exact=True).is_visible()
    assert understanding.read(conn,doc['id'])['need_0_deadline']=='2026-12-01'
    page.screenshot(path='/tmp/understanding-review-phone.png',full_page=True)
    assert not errors
    context.close()
