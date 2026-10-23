"""Exercise the actual vendor build, authenticated routes and fallback in Chromium."""
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

import documents as docs
import storage as st


@pytest.fixture(scope='module')
def grid_browser():
    with sync_playwright() as p:
        executable = None if Path(p.chromium.executable_path).exists() else shutil.which('chromium')
        browser = p.chromium.launch(executable_path=executable)
        yield browser
        browser.close()


@pytest.fixture
def grid_page(grid_browser, app_mod, viewer):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    user = st.get_admin_user(conn, 'viewer@test.local')
    for index in range(35):
        doc = docs.register(conn, user, {'subject': f'Register item {index:02}', 'type': 'memo', 'direction': 'OUT'})
        conn.execute('UPDATE document SET due_date=?,status=? WHERE id=?',
                     (f'2026-11-{1+index%28:02}', 'in_action' if index % 2 else 'draft', doc['id']))
        conn.commit()
    docs.register(conn, user, {'subject': '<img src=x onerror="window.gridInjected=true">', 'type': 'memo', 'direction': 'OUT'})
    conn.commit()
    context = grid_browser.new_context()
    page = context.new_page()
    state = {'requests': [], 'fail': False, 'block_vendor': False, 'fail_view_save': False, 'fail_export': False, 'export_requests': [], 'errors': []}
    page.on('pageerror', lambda error: state['errors'].append(str(error)))
    def serve(route):
        url = urlsplit(route.request.url)
        if url.hostname != 'office.test':
            route.abort(); return
        if state['block_vendor'] and url.path.endswith('/tabulator.min.js'):
            route.abort(); return
        if url.path == '/documents/grid-data':
            state['requests'].append(url.query)
            if state['fail']:
                route.abort(); return
        if url.path == '/documents/grid-export.csv':
            state['export_requests'].append(url.query)
            if state['fail_export']:
                route.fulfill(status=400, content_type='application/json', body='{"error":"Narrow your filters before exporting."}')
                return
        if url.path == '/documents/grid-views' and route.request.method == 'POST' and state['fail_view_save']:
            route.fulfill(status=409, content_type='application/json', body='{"error":"This saved view changed in another tab. Reload the page before changing it."}')
            return
        response = viewer.request(route.request.method, url.path + ('?' + url.query if url.query else ''),
            content=route.request.post_data_buffer,
            headers={k:v for k,v in route.request.headers.items() if k.lower() in ('content-type','x-csrf-token')},
            follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content,
            headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
    page.route('**/*', serve)
    page.goto('http://office.test/documents')
    yield page, state
    assert state['errors'] == []
    context.close()
    conn.close()


def open_grid(page):
    page.get_by_role('button', name='Interactive table', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('matching records')")
    page.locator('.tabulator-row').first.wait_for()


def test_real_grid_remote_sort_filters_columns_and_safe_record_links(grid_page):
    page, state = grid_page
    assert page.locator('#registry-standard').is_visible()
    open_grid(page)
    assert len(page.locator('.tabulator-row').all()) == 30
    assert page.locator('#registry-standard').is_hidden()
    assert page.evaluate('window.gridInjected') is None
    assert '<img src=x' in page.locator('#registry-grid').inner_text()
    number = page.locator('.tabulator-col[tabulator-field=number]')
    number.scroll_into_view_if_needed()
    original_width = number.bounding_box()['width']
    handle = page.locator('.tabulator-col[tabulator-field=number] + .tabulator-col-resize-handle').bounding_box()
    page.mouse.move(handle['x'] + handle['width']/2, handle['y'] + handle['height']/2)
    page.mouse.down()
    page.mouse.move(handle['x'] + handle['width']/2 + 40, handle['y'] + handle['height']/2, steps=5)
    page.mouse.up()
    assert number.bounding_box()['width'] > original_width + 20
    page.select_option('#registry-sort', 'due_date:asc')
    page.wait_for_function("document.querySelector('.tabulator-row [tabulator-field=due_date]').textContent === '2026-11-01'")
    page.select_option('#registry-sort', 'subject:asc')
    page.wait_for_function("document.querySelector('.tabulator-row [tabulator-field=subject]').textContent.includes('<img')")
    # Header sorting and the keyboard selector stay in sync in both directions.
    page.locator('.tabulator-col[tabulator-field=subject]').click()
    page.wait_for_function("document.getElementById('registry-sort').value === 'subject:desc'")
    page.locator('[name=status]').select_option('in_action')
    page.get_by_role('button', name='Apply filters', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('17 matching records')")
    assert len(page.locator('.tabulator-row').all()) == 17
    assert 'status=in_action' in state['requests'][-1]
    assert 'dir=desc' in state['requests'][-1]
    page.locator('#registry-columns summary').click()
    page.get_by_label('Lead', exact=True).uncheck()
    assert not page.locator('.tabulator-cell[tabulator-field=lead]:visible').count()
    page.get_by_role('button', name='Reset table', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('36 matching records')")
    assert page.locator('.tabulator-cell[tabulator-field=lead]:visible').count()
    page.locator('.tabulator-page[data-page=next]').click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('page 2 of 2')")
    assert page.locator('.tabulator-row').count() == 6
    page.locator('.tabulator-row a').first.click()
    page.wait_for_url(re.compile(r'/documents/\d+$'))


def test_failed_refresh_removes_interactive_rows_and_can_retry(grid_page):
    page, state = grid_page
    open_grid(page)
    state['fail'] = True
    page.locator('#registry-sort').select_option('due_date:asc')
    page.locator('#registry-standard').wait_for(state='visible')
    assert page.locator('#registry-interactive').is_hidden()
    assert page.locator('.tabulator-row').count() == 0
    assert 'could not load' in page.locator('#registry-table-status').inner_text()
    state['fail'] = False
    open_grid(page)


def test_vendor_failure_leaves_standard_table_and_pagination(grid_page):
    page, state = grid_page
    state['block_vendor'] = True
    page.reload()
    assert page.locator('#registry-view-controls').is_hidden()
    assert page.locator('#registry-standard').is_visible()
    page.get_by_role('link', name='Older documents', exact=True).click()
    assert 'before=' in page.url
    assert page.locator('#registry-standard tbody tr').count() == 6


def test_mobile_sort_and_column_controls_fit_viewport(grid_page):
    page, _ = grid_page
    page.set_viewport_size({'width': 390, 'height': 844})
    open_grid(page)
    assert page.locator('#registry-interactive').bounding_box()['width'] <= 390
    page.locator('#registry-sort').focus()
    page.keyboard.press('e')
    page.keyboard.press('Enter')
    page.get_by_role('button', name='Standard table', exact=True).click()
    assert page.locator('#registry-standard').is_visible()


def test_saved_view_restores_filters_sort_columns_widths_and_can_be_updated_deleted(grid_page):
    page, state = grid_page
    open_grid(page)
    page.locator('[name=status]').select_option('in_action')
    page.get_by_role('button', name='Apply filters', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('17 matching records')")
    page.select_option('#registry-sort', 'due_date:asc')
    page.wait_for_function("document.querySelector('.tabulator-row [tabulator-field=due_date]').textContent === '2026-11-02'")
    page.locator('#registry-columns summary').click()
    page.get_by_label('Lead', exact=True).uncheck()
    number = page.locator('.tabulator-col[tabulator-field=number]')
    number.scroll_into_view_if_needed()
    handle = page.locator('.tabulator-col[tabulator-field=number] + .tabulator-col-resize-handle').bounding_box()
    page.mouse.move(handle['x'] + handle['width']/2, handle['y'] + handle['height']/2)
    page.mouse.down()
    page.mouse.move(handle['x'] + handle['width']/2 + 50, handle['y'] + handle['height']/2, steps=5)
    page.mouse.up()
    width = number.bounding_box()['width']
    page.locator('#registry-views summary').click()
    name = '<img src=x onerror="window.viewInjected=true">'
    page.get_by_label('View name', exact=True).fill(name)
    page.get_by_role('button', name='Save new view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-view-status').textContent === 'View saved to your account.'")
    assert 'saved_view=' in page.url
    assert page.evaluate('window.viewInjected') is None
    page.reload()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('17 matching records')")
    page.locator('.tabulator-row').first.wait_for()
    assert page.locator('[name=status]').input_value() == 'in_action'
    assert page.locator('#registry-sort').input_value() == 'due_date:asc'
    assert not page.locator('.tabulator-cell[tabulator-field=lead]:visible').count()
    assert abs(page.locator('.tabulator-col[tabulator-field=number]').bounding_box()['width'] - width) < 2
    page.locator('#registry-views summary').click()
    assert page.get_by_label('View name', exact=True).input_value() == name
    page.get_by_label('View name', exact=True).fill('Renamed view')
    page.get_by_role('button', name='Update selected view', exact=True).click()
    page.wait_for_function("document.querySelector('#registry-saved-view option:checked').textContent === 'Renamed view'")
    page.get_by_role('button', name='Reset table', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('36 matching records')")
    assert 'saved_view=' not in page.url
    page.select_option('#registry-saved-view', label='Renamed view')
    page.get_by_role('button', name='Open view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('17 matching records')")
    page.locator('#registry-views summary').click()
    page.get_by_role('button', name='Delete selected view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-view-status').textContent.includes('deleted')")
    assert page.locator('#registry-saved-view option').count() == 1
    assert page.locator('.tabulator-row').count() == 17
    assert page.evaluate('window.viewInjected') is None


def test_deadline_labels_in_standard_and_interactive_tables(grid_page, app_mod):
    page, _ = grid_page
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE document SET due_date='2026-10-19',status='in_action' WHERE id=(SELECT MAX(id) FROM document)")
    conn.commit(); conn.close()
    page.reload()
    assert page.locator('#registry-standard [data-deadline=overdue]').count() == 1
    assert page.locator('#registry-standard [data-deadline=overdue]').inner_text() == 'Overdue'
    open_grid(page)
    assert page.locator('#registry-grid [data-deadline=overdue]').count() == 1
    assert '2026-10-19' in page.locator('.tabulator-row').first.inner_text()


def test_saved_view_restores_queue_search_and_failed_save_keeps_current_table(grid_page, app_mod):
    page, state = grid_page
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE document SET subject='Searchneedle record' WHERE id=(SELECT MIN(id) FROM document)")
    conn.commit(); conn.close()
    page.goto('http://office.test/documents?queue=OUT&q=Searchneedle')
    open_grid(page)
    assert page.locator('.tabulator-row').count() == 1
    page.locator('#registry-views summary').click()
    page.get_by_label('View name', exact=True).fill('Outgoing search')
    page.get_by_role('button', name='Save new view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-view-status').textContent === 'View saved to your account.'")
    state['fail_view_save'] = True
    page.get_by_label('View name', exact=True).fill('Unsaved rename')
    page.get_by_role('button', name='Update selected view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-view-status').textContent.includes('another tab')")
    assert page.locator('.tabulator-row').count() == 1
    assert page.get_by_label('View name', exact=True).input_value() == 'Unsaved rename'
    state['fail_view_save'] = False
    page.goto('http://office.test/documents')
    open_grid(page)
    page.locator('#registry-views summary').click()
    page.select_option('#registry-saved-view', label='Outgoing search')
    page.get_by_role('button', name='Open view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('1 matching records')")
    assert 'queue=OUT' in page.url
    assert page.locator('input[name=q]').input_value() == 'Searchneedle'
    assert page.locator('.tabulator-row').count() == 1


def test_deadline_quick_filters_save_reload_and_reset(grid_page, app_mod):
    import tzutil as tz
    from datetime import timedelta
    page, state = grid_page
    conn = st.connect(app_mod.DB)
    today = tz.today_local()
    identifiers = [r[0] for r in conn.execute('SELECT id FROM document ORDER BY id DESC LIMIT 5')]
    for identifier, due, workflow in zip(identifiers,
            [(today-timedelta(days=1)).isoformat(), today.isoformat(), None, None, today.isoformat()],
            ['in_action', 'in_action', 'in_action', 'closed', 'cancelled']):
        conn.execute('UPDATE document SET due_date=?,status=? WHERE id=?', (due, workflow, identifier))
    conn.commit(); conn.close()
    open_grid(page)
    for deadline in ('overdue', 'due_today', 'due_soon', 'unknown'):
        page.get_by_label('Deadline', exact=True).select_option(deadline)
        page.get_by_role('button', name='Apply filters', exact=True).click()
        page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('1 matching records')")
        badge = 'due_today' if deadline == 'due_soon' else deadline
        page.locator(f'#registry-grid [data-deadline={badge}]').wait_for()
        assert 'deadline=' + deadline in state['requests'][-1]
        assert page.locator('.tabulator-row').count() == 1
    page.locator('#registry-views summary').click()
    page.get_by_label('View name', exact=True).fill('Missing deadlines')
    page.get_by_role('button', name='Save new view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-view-status').textContent === 'View saved to your account.'")
    page.reload()
    page.locator('#registry-grid [data-deadline=unknown]').wait_for()
    assert page.get_by_label('Deadline', exact=True).input_value() == 'unknown'
    assert page.locator('.tabulator-row').count() == 1
    page.get_by_role('button', name='Reset table', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('36 matching records')")
    assert page.get_by_label('Deadline', exact=True).input_value() == ''
    assert 'deadline=' in state['requests'][-1]



def download_view(page):
    import csv
    import io
    with page.expect_download() as received:
        page.get_by_role('button', name='Export current view (CSV)', exact=True).click()
    download = received.value
    assert download.suggested_filename == 'document-view.csv'
    return list(csv.reader(io.StringIO(Path(download.path()).read_text(encoding='utf-8-sig'))))


def test_current_view_download_all_pages_applied_filters_columns_and_saved_view(grid_page):
    page, state = grid_page
    open_grid(page)
    page.select_option('#registry-sort', 'subject:asc')
    page.wait_for_function("document.querySelector('.tabulator-row [tabulator-field=subject]').textContent.includes('<img')")
    page.locator('.tabulator-page[data-page=next]').click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('page 2 of 2')")
    page.locator('#registry-columns summary').click()
    page.get_by_label('Lead', exact=True).uncheck()
    page.locator('[name=status]').select_option('in_action')  # Draft choice is not applied yet.
    data = download_view(page)
    assert data[0] == ['Number', 'Subject', 'Verification', 'Workflow', 'Due date']
    assert len(data) == 37 and data[1][1].startswith('<img src=x')
    assert [r[1] for r in data[2:]] == [f'Register item {i:02}' for i in range(35)]
    assert 'page=' not in state['export_requests'][-1]
    assert 'status=in_action' not in state['export_requests'][-1]
    page.get_by_role('button', name='Apply filters', exact=True).click()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('17 matching records')")
    page.locator('#registry-views summary').click()
    page.get_by_label('View name', exact=True).fill('Export action records')
    page.get_by_role('button', name='Save new view', exact=True).click()
    page.wait_for_function("document.getElementById('registry-view-status').textContent === 'View saved to your account.'")
    page.reload()
    page.wait_for_function("document.getElementById('registry-table-status').textContent.includes('17 matching records')")
    data = download_view(page)
    assert len(data) == 18 and data[0][-1] == 'Due date'
    assert [r[1] for r in data[1:]] == [f'Register item {i:02}' for i in range(1,35,2)]
    assert all(r[3] == 'in action' for r in data[1:])
    assert 'status=in_action' in state['export_requests'][-1]


def test_failed_export_keeps_grid_and_can_retry(grid_page):
    page, state = grid_page
    open_grid(page)
    state['fail_export'] = True
    page.get_by_role('button', name='Export current view (CSV)', exact=True).click()
    page.wait_for_function("document.getElementById('registry-export-status').textContent.includes('Narrow your filters')")
    assert page.locator('.tabulator-row').count() == 30
    assert page.locator('#registry-standard').is_hidden()
    state['fail_export'] = False
    assert len(download_view(page)) == 37
