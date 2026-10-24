"""Use real ECharts SVG and Tabulator with authenticated local routes."""
import json

import storage as st
from tests.test_document_registry_grid_browser import grid_browser, grid_page, download_view


def open_dashboard(page):
    page.goto('http://office.test/documents/dashboard')
    page.wait_for_function("document.getElementById('dashboard-chart-status').textContent.includes('Charts loaded')")


def test_real_charts_click_open_matching_grid_and_csv_then_reset(grid_page):
    page,state=grid_page
    open_dashboard(page)
    data=json.loads(page.locator('#document-dashboard-data').text_content())
    assert data['total']==36
    assert {row['key']:row['count'] for row in data['deadlines']}=={
        'overdue':0,'due_soon':0,'scheduled':35,'unknown':1,'inactive':0}
    assert page.locator('.dashboard-chart svg').count()==3
    page.locator('#dashboard-workflow-chart').scroll_into_view_if_needed()
    # Click inside the actual draft bar using ECharts' coordinate transform.
    point=page.evaluate("echarts.getInstanceByDom(document.getElementById('dashboard-workflow-chart')).convertToPixel({seriesIndex:0},[9,1])")
    box=page.locator('#dashboard-workflow-chart').bounding_box()
    page.mouse.click(box['x']+point[0],box['y']+point[1])
    page.wait_for_url('**/documents?**status=draft')
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('19 matching records')")
    assert page.locator('.tabulator-row').count()==19
    assert page.locator('#registry-standard tbody tr').count()==19
    assert len(download_view(page))==20
    state['fail']=True
    page.select_option('#registry-sort','subject:asc')
    page.wait_for_function("!document.getElementById('registry-standard').hidden")
    assert page.locator('#registry-standard tbody tr').count()==19
    state['fail']=False
    page.get_by_role('button',name='Interactive table',exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('19 matching records')")
    page.get_by_role('button',name='Reset table',exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('36 matching records')")
    assert 'interactive=' not in page.url and 'status=' not in page.url
    page.go_back()
    page.wait_for_function("document.querySelectorAll('.dashboard-chart svg').length===3")


def test_chart_and_table_vendor_failures_keep_filtered_accessible_fallback(grid_page):
    page,state=grid_page
    page.route('**/static/vendor/echarts/**',lambda route:route.abort())
    page.goto('http://office.test/documents/dashboard')
    assert '36 matching records' in page.locator('#document-dashboard').inner_text()
    assert page.get_by_role('link',name='Later deadlines',exact=True).is_visible()
    state['block_vendor']=True
    page.get_by_role('link',name='Later deadlines',exact=True).click()
    assert page.locator('#registry-standard').is_visible()
    assert page.locator('#registry-standard tbody tr').count()==30
    assert '35 matching records with the linked filters' in page.locator('.documents').inner_text()
    page.get_by_role('link',name='Next matching page',exact=True).click()
    assert page.locator('#registry-standard tbody tr').count()==5
    assert 'Page 2 of 2' in page.get_by_role('navigation',name='Linked register pages').inner_text()
    state['block_vendor']=False
    page.reload()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('page 2 of 2')")
    assert page.locator('.tabulator-row').count()==5


def test_mobile_lead_labels_are_text_and_lead_link_matches_current_scope(grid_page,app_mod):
    page,state=grid_page
    c=st.connect(app_mod.DB)
    name='<img src=x onerror="window.dashboardInjected=true">'
    uid=st.create_admin_user(c,name,'unused','unused','viewer',active=False)
    c.execute('UPDATE document SET lead_id=? WHERE id IN (SELECT id FROM document ORDER BY id LIMIT 2)',(uid,));c.commit();c.close()
    page.set_viewport_size({'width':390,'height':844})
    open_dashboard(page)
    assert page.evaluate('window.dashboardInjected') is None
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    assert page.locator('#dashboard-leads-chart svg text').filter(has_text='<img src=x').count()>=1
    page.get_by_role('link',name=name,exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('2 matching records')")
    assert page.locator('.tabulator-row').count()==2 and page.evaluate('window.dashboardInjected') is None


def test_dashboard_no_store_invalid_options_and_linked_table_without_scripts(grid_page,app_mod):
    page,state=grid_page
    response=page.goto('http://office.test/documents/dashboard?queue=OUT')
    assert response.status==200 and response.headers['cache-control']=='no-store'
    invalid=page.goto('http://office.test/documents/dashboard?queue=invalid')
    assert invalid.status==400 and invalid.headers['cache-control']=='no-store'
    forbidden=page.goto('http://office.test/documents/dashboard?queue=instruction')
    assert forbidden.status==403 and forbidden.headers['cache-control']=='no-store'
    # Disable all scripts before navigation, retaining the real authenticated server route.
    session=page.context.new_cdp_session(page)
    session.send('Emulation.setScriptExecutionDisabled',{'value':True})
    linked=page.goto('http://office.test/documents?queue=OUT&interactive=1&deadline=scheduled')
    assert linked.headers['cache-control']=='no-store'
    assert page.locator('#registry-standard').is_visible()
    assert page.locator('#registry-standard tbody tr').count()==30
    assert '35 matching records with the linked filters' in page.locator('.documents').inner_text()
    page.get_by_role('link',name='Next matching page',exact=True).click()
    assert page.locator('#registry-standard tbody tr').count()==5
    # Remove access to one matching record and verify fresh server-side pagination/clamping.
    c=st.connect(app_mod.DB)
    c.execute("UPDATE document SET visibility='restricted',creator_id=(SELECT id FROM admin_user WHERE username='admin@test.local') WHERE id=(SELECT MIN(id) FROM document)")
    c.commit();c.close()
    page.reload()
    assert '34 matching records with the linked filters' in page.locator('.documents').inner_text()
    assert page.locator('#registry-standard tbody tr').count()==4
