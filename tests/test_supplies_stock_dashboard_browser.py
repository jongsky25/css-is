"""Real ECharts/Tabulator and server fallback over authenticated Supplies routes."""
import json
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_supplies_grid_browser import inventory_page,download


def open_dashboard(page):
    page.goto('http://office.test/supplies/stock-dashboard')
    page.wait_for_function("document.getElementById('stock-chart-status').textContent.includes('Charts loaded')")


def test_stock_chart_click_csv_retry_reset_and_low_list(inventory_page):
    page,state,c=inventory_page;open_dashboard(page)
    data=json.loads(page.locator('#stock-dashboard-data').text_content())
    assert sum(row['count'] for row in data['physical'])==36
    assert page.locator('.dashboard-chart svg').count()==2
    assert page.get_by_role('region',name='Items below critical level').locator('tbody tr').count()==5
    assert page.evaluate('window.inventoryInjected') is None
    page.locator('#stock-physical-chart').scroll_into_view_if_needed()
    # Physical states: unrecorded, inactive, out_of_stock, critical, normal.
    point=page.evaluate("echarts.getInstanceByDom(document.getElementById('stock-physical-chart')).convertToPixel({seriesIndex:0},[2,3])")
    box=page.locator('#stock-physical-chart').bounding_box();page.mouse.click(box['x']+point[0],box['y']+point[1])
    page.wait_for_url('**/supplies/items?**')
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('4 matching records')")
    assert page.locator('.tabulator-row').count()==4 and len(download(page))==5
    state['fail']=True;page.select_option('#inventory-sort','code:desc')
    page.wait_for_function("!document.getElementById('inventory-standard').hidden")
    assert page.locator('#inventory-standard tbody tr').count()==4
    state['fail']=False;page.get_by_role('button',name='Interactive inventory',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('4 matching records')")
    page.get_by_role('button',name='Reset table',exact=True).click()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('36 matching records')")
    assert 'interactive=' not in page.url


def test_stock_mobile_failed_charts_no_script_filters_and_revoked_grant(inventory_page):
    page,state,c=inventory_page
    page.set_viewport_size({'width':390,'height':844});open_dashboard(page)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    page.route('**/static/vendor/echarts/**',lambda route:route.abort())
    response=page.goto('http://office.test/supplies/stock-dashboard?active=all')
    assert response.headers['cache-control']=='no-store'
    assert '37 matching catalog items' in page.locator('#stock-dashboard').inner_text()
    state['block_vendor']=True
    page.get_by_role('region',name='Physical stock counts').get_by_role('link',name='Normal',exact=True).click()
    assert page.locator('#inventory-standard').is_visible()
    assert page.locator('#inventory-standard tbody tr').count()==30
    assert '30 items found' in page.locator('.supply-wrap').inner_text()
    session=page.context.new_cdp_session(page);session.send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto('http://office.test/supplies/items?interactive=1&physical=critical&active=active')
    assert page.locator('#inventory-standard tbody tr').count()==4
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(state['user']['id'],state['grant']['id']));c.commit()
    forbidden=page.goto('http://office.test/supplies/stock-dashboard?active=all')
    assert forbidden.status==403 and forbidden.headers['cache-control']=='no-store'
    active=page.goto('http://office.test/supplies/stock-dashboard')
    assert active.status==200 and '36 matching catalog items' in page.locator('#stock-dashboard').inner_text()


def test_linked_inventory_fallback_paging_and_recovered_assets(inventory_page):
    page,state,c=inventory_page
    state['block_vendor']=True
    response=page.goto('http://office.test/supplies/items?interactive=1&active=all')
    assert response.headers['cache-control']=='no-store'
    assert page.locator('#inventory-standard tbody tr').count()==30
    page.get_by_role('link',name='Next matching page',exact=True).click()
    assert page.locator('#inventory-standard tbody tr').count()==7
    state['block_vendor']=False;page.reload()
    page.wait_for_function("document.getElementById('inventory-table-status').textContent.includes('page 2 of 2')")
    assert page.locator('.tabulator-row').count()==7
    assert len(download(page))==38
