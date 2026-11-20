"""Phone forms use the persisted three-person review workflow, also without JS."""
import pytest
import auth
from starlette.testclient import TestClient
from tests.conftest import session_token
from tests.test_advisory_review import cycle
from tests.test_advisory_workflow import drafts
from tests.test_document_registration_browser import browser
from tests.test_advisory_draft_browser import serve_page
import advisory_workflow as aw
import documents as d

@pytest.mark.parametrize('scripts',[True,False])
def test_phone_review_return_and_resubmission(browser,cycle,app_mod,scripts):
    data,r=cycle;c,users,*_=data
    clients=[];contexts=[]
    try:
        pages=[]
        for user in users:
            client=TestClient(app_mod.app)
            client.cookies.set(auth.COOKIE_NAME,session_token(user));clients.append(client)
            context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=scripts)
            contexts.append(context);page=context.new_page();serve_page(page,client);pages.append(page)
        author,director,chief=pages
        url='http://office.test/advisories/'+str(r['id'])
        def action(page,label,reason):
            page.goto(url);page.locator('#action-reason').fill(reason)
            page.get_by_role('button',name=label,exact=True).click()
            assert page.get_by_role('heading',name='Review and approval').is_visible(),page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        action(author,'Submit to Division Chief','Initial submission')
        action(chief,'Endorse to Director','Reviewed exact PDF')
        action(director,'Return for changes','Please clarify the headline')
        author.goto(url);author.locator('[name=headline]').fill('Revised on phone')
        author.locator('[name=summary]').fill('Clarified headline')
        author.get_by_role('button',name='Save private draft',exact=True).click()
        action(author,'Submit to Division Chief','Addressed Director feedback')
        action(chief,'Endorse to Director','Revised PDF reviewed')
        action(director,'Approve this revision','Approved exact revision')
        assert d.raw(c,r['document_id'])['status']=='approved'
        assert len(aw.history(c,users[0],r['id']))==2
        director.goto(url);director.get_by_text('Action history',exact=True).click()
        assert director.get_by_text('Please clarify the headline',exact=False).is_visible()
    finally:
        for context in contexts:context.close()
        for client in clients:client.close()
