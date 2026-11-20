"""Phone and no-script journeys through the actual private advisory routes."""
import pytest
from tests.test_document_registration_browser import browser
from urllib.parse import urlsplit


def serve_page(page, client):
    def serve(route):
        request=route.request; parsed=urlsplit(request.url)
        if parsed.hostname != "office.test":
            route.abort(); return
        target=parsed.path+("?"+parsed.query if parsed.query else "")
        response=client.request(request.method,target,content=request.post_data,
            headers={"content-type":request.headers.get("content-type", "")},follow_redirects=request.method=='POST')
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ("content-length","content-encoding","set-cookie")})
    page.route("**/*",serve)
from tests.test_advisory_draft_routes import draft_route


@pytest.mark.parametrize('scripts',[True,False])
def test_phone_draft_save_validation_and_history(browser,draft_route,manager,scripts):
    conn,user,unit,ev,url=draft_route
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=scripts)
    page=context.new_page()
    serve_page(page,manager)
    try:
        page.goto('http://office.test'+url)
        page.locator('[name=unit_id]').select_option(str(unit))
        page.locator('[name=headline]').fill('Phone advisory')
        page.locator('[name=contact_name]').fill('Test contact')
        page.locator('[name=audience]').select_option('external')
        page.locator('[name=external]').fill('bad address')
        page.get_by_role('button',name='Save private draft').click()
        assert page.locator('[role=alert]').is_visible()
        assert page.locator('[name=headline]').input_value()=='Phone advisory'
        page.locator('[name=external]').fill('test@example.invalid')
        page.get_by_role('button',name='Save private draft').click()
        assert page.locator('[name=headline]').count()==1, page.locator('body').inner_text()
        history_url=page.get_by_role('link',name='Version and action history').get_attribute('href')
        page.goto('http://office.test'+history_url.removesuffix('/history'))
        page.locator('[name=headline]').fill('Phone advisory revised')
        page.locator('[name=summary]').fill('Clarify title')
        page.get_by_role('button',name='Save private draft').click()
        page.get_by_role('link',name='Version and action history').click()
        assert page.get_by_role('heading',name='Revision 2',exact=True).is_visible()
        assert page.get_by_role('heading',name='Revision 1',exact=True).is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('link',name='Back to advisory',exact=False).click()
        assert page.locator('[name=headline]').input_value()=='Phone advisory revised'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert conn.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==0
    finally:context.close()
