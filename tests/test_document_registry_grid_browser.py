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
    state = {'requests': [], 'fail': False, 'block_vendor': False, 'errors': []}
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
        response = viewer.get(url.path + ('?' + url.query if url.query else ''), follow_redirects=False)
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
