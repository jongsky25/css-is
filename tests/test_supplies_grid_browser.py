"""Real vendored Tabulator, authenticated Supplies routes, CSV and failure recovery."""
import csv
import io
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import storage as st
import supplies as s
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_supplies import key
from tests.test_supplies_stock import opening


@pytest.fixture
def inventory_page(grid_browser,app_mod,viewer):
    c=st.connect(app_mod.DB)
    admin=st.get_admin_user(c,'admin@test.local');user=st.get_admin_user(c,'viewer@test.local')
    grant=s.grant_role(c,admin,user['id'],'custodian',operation_key=key())
    s.set_enabled(c,admin,'1',expected_revision=0,operation_key=key())
    for index in range(36):
        item=s.create_item(c,user,{'code':f'INV-{index:03}','description':
            '<img src=x onerror="window.inventoryInjected=true">' if index==0 else f'Item {index:03}',
            'unit':'Ream' if index<31 else 'Box','critical_level':'5','target_level':'20'},operation_key=key())
        if index<35:opening(c,user,item,quantity=str(index))
    inactive=s.create_item(c,user,{'code':'INACTIVE','description':'Hidden historical item','unit':'Secret unit',
        'critical_level':'0','target_level':''},operation_key=key())
    c.execute('UPDATE supply_item SET active=0 WHERE id=?',(inactive['id'],));c.commit()
    context=grid_browser.new_context();page=context.new_page()
    state={'requests':[],'errors':[],'fail':False,'block_vendor':False,'export_fail':False,'grant':grant,'user':user}
    page.on('pageerror',lambda error:state['errors'].append(str(error)))
    def serve(route):
        url=urlsplit(route.request.url)
        if url.hostname!='office.test':route.abort();return
        if state['block_vendor'] and url.path.endswith('/tabulator.min.js'):route.abort();return
        if url.path=='/supplies/inventory-data':
            state['requests'].append(url.query)
            if state['fail']:route.abort();return
        if url.path=='/supplies/inventory-export.csv' and state['export_fail']:
            route.fulfill(status=400,content_type='application/json',body='{"error":"Narrow the filters before exporting."}');return
        response=viewer.request(route.request.method,url.path+('?' +url.query if url.query else ''),
            content=route.request.post_data_buffer,
            headers={k:v for k,v in route.request.headers.items() if k.lower() in ('content-type','x-csrf-token')},follow_redirects=False)
        route.fulfill(status=response.status_code,body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*',serve);page.goto('http://office.test/supplies/items')
    yield page,state,c
    assert state['errors']==[]
    context.close();c.close()


def open_inventory(page):
    page.get_by_role('button',name='Interactive inventory',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('matching records')")
    page.locator('.tabulator-row').first.wait_for()


def download(page):
    with page.expect_download() as result:
        page.get_by_role('button',name='Export current inventory (CSV)',exact=True).click()
    downloaded=result.value
    assert downloaded.suggested_filename=='supply-inventory.csv'
    return list(csv.reader(io.StringIO(Path(downloaded.path()).read_text(encoding='utf-8-sig'))))


def test_inventory_filters_all_pages_csv_saved_view_columns_and_reset(inventory_page):
    page,state,c=inventory_page;open_inventory(page)
    assert page.locator('.tabulator-row').count()==30
    assert '<img src=x' in page.locator('#inventory-grid').inner_text() and page.evaluate('window.inventoryInjected') is None
    page.get_by_label('Unit filter',exact=True).select_option('Ream')
    page.get_by_role('button',name='Apply filters',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('31 matching records')")
    page.select_option('#inventory-sort','on_hand:desc')
    page.wait_for_function("document.querySelector('.tabulator-row [tabulator-field=on_hand]').textContent==='30'")
    page.locator('#inventory-columns summary').click()
    page.get_by_label('Target level',exact=True).uncheck()
    exported=download(page)
    assert len(exported)==32 and 'Target level' not in exported[0]
    assert [r[0] for r in exported[1:]]==[f'INV-{i:03}' for i in reversed(range(31))]
    page.get_by_label('Physical stock filter',exact=True).select_option('out_of_stock')
    assert len(download(page))==32 # draft filter does not change applied export
    page.locator('#inventory-views summary').click()
    page.get_by_label('View name',exact=True).fill('Reams by stock')
    page.get_by_role('button',name='Save new view',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-view-status').textContent.includes('View saved')")
    page.reload()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('31 matching records')")
    assert page.get_by_label('Unit filter',exact=True).input_value()=='Ream'
    assert page.get_by_label('Physical stock filter',exact=True).input_value()==''
    assert len(download(page))==32
    page.get_by_role('button',name='Reset table',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('36 matching records')")
    assert len(download(page))==37
    page.get_by_label('Physical stock filter',exact=True).select_option('out_of_stock')
    page.get_by_role('button',name='Apply filters',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('1 matching records')")
    assert page.locator('.tabulator-row [tabulator-field=on_hand]').inner_text()=='0'
    page.get_by_label('Physical stock filter',exact=True).select_option('unrecorded')
    page.get_by_role('button',name='Apply filters',exact=True).click()
    page.wait_for_function("document.querySelector('.tabulator-row [tabulator-field=on_hand]').textContent==='Not recorded'")
    page.locator('.tabulator-row a').first.click();page.wait_for_url('**/supplies/items/*')


def test_inventory_failure_vendor_fallback_export_recovery_and_mobile(inventory_page):
    page,state,c=inventory_page
    page.set_viewport_size({'width':390,'height':844});open_inventory(page)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    state['export_fail']=True
    page.get_by_role('button',name='Export current inventory (CSV)',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-export-status').textContent.includes('Narrow the filters')")
    assert page.locator('#inventory-interactive').is_visible()
    state['export_fail']=False
    assert len(download(page))==37
    state['fail']=True
    page.select_option('#inventory-sort','code:desc')
    page.wait_for_function("!document.getElementById('inventory-standard').hidden")
    assert page.locator('.tabulator-row').count()==0
    state['fail']=False;open_inventory(page)
    state['block_vendor']=True;page.reload()
    assert page.locator('#inventory-standard').is_visible()
    assert page.locator('#inventory-view-controls').is_hidden()


def test_inventory_inactive_saved_view_rechecks_revoked_grant(inventory_page):
    page,state,c=inventory_page;open_inventory(page)
    page.get_by_label('Catalog status filter',exact=True).select_option('all')
    page.get_by_role('button',name='Apply filters',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('37 matching records')")
    page.locator('#inventory-views summary').click();page.get_by_label('View name',exact=True).fill('All items')
    page.get_by_role('button',name='Save new view',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-view-status').textContent.includes('View saved')")
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(state['user']['id'],state['grant']['id']));c.commit()
    page.get_by_role('button',name='Apply filters',exact=True).click()                         # the page itself would now redirect (Supplies 4.1)
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('could not load')")
    assert page.locator('#inventory-standard').is_visible() and 'INACTIVE' not in page.locator('#inventory-standard').inner_text()
    assert page.locator('.tabulator-row').count()==0
