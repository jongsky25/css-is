"""Download real server PDFs through authenticated browser routes, even without JS."""
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader
import storage as st
import supplies
import documents_dashboard
import supplies_stock_dashboard
from tests.test_document_registry_grid_browser import grid_browser,grid_page
from tests.test_supplies_grid_browser import inventory_page
from tests.test_supplies_stock import receive


def download(page,filename):
    with page.expect_download() as result:
        page.get_by_role('link',name='Export PDF report',exact=True).click()
    saved=result.value
    assert saved.suggested_filename==filename
    payload=Path(saved.path()).read_bytes();assert payload.startswith(b'%PDF-')
    return ' '.join(' '.join(p.extract_text().split()) for p in PdfReader(BytesIO(payload)).pages)


def test_supplies_pdf_applied_scope_fresh_data_no_script_and_revoked_access(inventory_page):
    page,state,c=inventory_page
    c.execute('UPDATE supply_item SET critical_level=50,target_level=NULL');c.commit()
    page.set_viewport_size({'width':390,'height':844})
    page.goto('http://office.test/supplies/stock-dashboard?unit=Ream&q=INV-')
    page.get_by_label('Dashboard unit',exact=True).select_option('Box')
    identifier=c.execute("SELECT id FROM supply_item WHERE code='INV-000'").fetchone()[0]
    receive(c,state['user'],supplies.get_item(c,state['user'],identifier),quantity='1')
    with page.expect_response('**/supplies/stock-dashboard/export.pdf?**') as response:
        text=download(page,'office-connect-supplies-stock-report.pdf')
    assert response.value.headers['cache-control']=='no-store'
    assert 'Unit: Ream' in text and '31 matching catalog items' in text
    assert all(f'INV-{i:03}' in text for i in range(31)) and 'INV-031' not in text
    assert 'Not set' in text and '<img src=x' in text
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    session=page.context.new_cdp_session(page);session.send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto('http://office.test/supplies/stock-dashboard?unit=Ream&q=INV-')
    assert '31 below critical level' in download(page,'office-connect-supplies-stock-report.pdf')
    page.goto('http://office.test/supplies/stock-dashboard?active=all')
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(state['user']['id'],state['grant']['id']));c.commit()
    denied=page.goto('http://office.test/supplies/stock-dashboard/export.pdf?active=all')
    assert denied.status==403 and denied.headers['cache-control']=='no-store'
    assert 'attachment' not in denied.headers.get('content-disposition','')
    page.get_by_role('link',name='Reset dashboard filters',exact=True).click()
    assert '36 matching catalog items' in page.locator('#stock-dashboard').inner_text()


def test_document_pdf_fresh_visibility_no_script_and_bounded_error(grid_page,app_mod,monkeypatch):
    page,state=grid_page;c=st.connect(app_mod.DB)
    admin=st.get_admin_user(c,'admin@test.local')
    page.goto('http://office.test/documents/dashboard?queue=OUT&q=Register')
    page.locator('[name=queue]').select_option('IN')
    page.get_by_role('searchbox',name='Search permitted records',exact=True).fill('PRIVATE')
    c.execute("UPDATE document SET visibility='restricted',creator_id=? WHERE id=(SELECT MIN(id) FROM document)",(admin['id'],));c.commit()
    with page.expect_response('**/documents/dashboard/export.pdf?**') as response:
        text=download(page,'office-connect-document-workload-report.pdf')
    assert response.value.headers['cache-control']=='no-store'
    assert 'Queue: Outgoing' in text and 'Applied search: Register' in text and '34 matching documents' in text
    assert 'Register item' not in text and 'PRIVATE' not in text
    session=page.context.new_cdp_session(page);session.send('Emulation.setScriptExecutionDisabled',{'value':True})
    st.set_setting(c,'documents.enabled','0');c.commit()
    page.goto('http://office.test/documents/dashboard?queue=OUT&q=Register')
    assert '34 matching documents' in download(page,'office-connect-document-workload-report.pdf')
    monkeypatch.setattr(documents_dashboard,'MAX_PRESENTATION_LEADS',0)
    refused=page.goto('http://office.test/documents/dashboard/export.pdf?queue=OUT&q=Register')
    assert refused.status==400 and refused.headers['cache-control']=='no-store'
    assert 'Narrow the dashboard' in page.locator('main').inner_text()
    assert 'attachment' not in refused.headers.get('content-disposition','')
    assert 'queue=OUT' in page.get_by_role('link',name='Return to dashboard',exact=True).get_attribute('href')
    forbidden=page.goto('http://office.test/documents/dashboard/export.pdf?queue=instruction')
    assert forbidden.status==403 and forbidden.headers['cache-control']=='no-store'
    invalid=page.goto('http://office.test/documents/dashboard/export.pdf?queue=bad')
    assert invalid.status==400
    c.close()


def test_supply_pdf_limit_refuses_instead_of_truncating(inventory_page,monkeypatch):
    page,state,c=inventory_page
    monkeypatch.setattr(supplies_stock_dashboard,'MAX_PRESENTATION_ITEMS',1)
    refused=page.goto('http://office.test/supplies/stock-dashboard/export.pdf')
    assert refused.status==400 and refused.headers['cache-control']=='no-store'
    assert 'Narrow the dashboard' in page.locator('main').inner_text()
    page.get_by_role('link',name='Return to dashboard',exact=True).click()
    assert '36 matching catalog items' in page.locator('#stock-dashboard').inner_text()
