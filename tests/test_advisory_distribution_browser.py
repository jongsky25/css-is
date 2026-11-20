"""Phone issuance confirmation, failed delivery and filtered register without live I/O."""
import pytest
import auth
from starlette.testclient import TestClient
from tests.conftest import session_token
from tests.test_advisory_distribution import approved
from tests.test_advisory_review import cycle
from tests.test_advisory_workflow import drafts
from tests.test_document_registration_browser import browser
from tests.test_advisory_draft_browser import serve_page
import advisory_distribution as dist
import documents as d
import documents_operations as ops
import storage as st

@pytest.mark.parametrize('scripts',[True,False])
def test_phone_issue_filter_retry_and_publication(browser,approved,app_mod,monkeypatch,scripts):
    import mailer
    data,r=approved;c,u,*_=data
    client=TestClient(app_mod.app);client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
    context=browser.new_context(viewport={'width':390,'height':844},java_script_enabled=scripts)
    page=context.new_page();serve_page(page,client)
    url='http://office.test/advisories/'+str(r['id'])
    try:
        page.goto(url)
        page.get_by_role('link',name='Review issuance and recipients').click()
        assert page.get_by_role('heading',name='2 unique email recipients').is_visible()
        page.locator('[name=ack_missing]').check();page.locator('[name=reason]').fill('Approved PDF and audience confirmed')
        page.get_by_role('button',name='Issue and queue PDF emails').click()
        assert d.raw(c,r['document_id'])['status']=='issued'
        page.goto(url);page.locator('#issue-reason').fill('Authorized public copy')
        page.get_by_role('button',name='Publish exact issue publicly').click()
        assert 'Publicly published' in page.locator('body').inner_text()
        st.set_setting(c,'documents.sending_enabled','1');c.commit()
        monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True);monkeypatch.setattr(mailer,'email_configured',lambda:False)
        operation=c.execute('SELECT job_id FROM advisory_delivery ORDER BY rowid LIMIT 1').fetchone()[0]
        assert ops.execute(c,operation)['state']=='failed'
        page.goto('http://office.test/advisories')
        page.locator('#status').select_option('delivery_failures');page.locator('#audience').select_option('both')
        page.get_by_role('button',name='Filter',exact=True).click()
        assert '1 permitted advisory record' in page.locator('body').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.goto(url);page.get_by_text('Recipient delivery attempts',exact=False).click()
        page.locator('#delivery-'+operation).fill('Configured mail transport')
        page.get_by_role('button',name='Retry confirmed failure').click()
        assert c.execute('SELECT COUNT(*) FROM advisory_delivery').fetchone()[0]==3
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not c.execute('SELECT 1 FROM document_dispatch').fetchone()
    finally:context.close();client.close()
