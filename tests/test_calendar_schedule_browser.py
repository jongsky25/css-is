"""Actual hour grid, native links/fallback, responsive layout and timezone behavior."""
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import expect

import auth
import storage as st
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app


@pytest.fixture
def schedule_page(grid_browser,app_mod,monkeypatch):
    conn=st.connect(app_mod.DB)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        user=st.get_admin_user(conn,'viewer@test.local')
        context=grid_browser.new_context(viewport={'width':390,'height':900},timezone_id='America/Los_Angeles',service_workers='block')
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        context.add_init_script("localStorage.setItem('css_tour_optout','1')")
        page=context.new_page();errors=[];writes=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:writes.append(urlsplit(r.url).path) if r.method=='POST' and urlsplit(r.url).path!='/telemetry' else None)
        page.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname=='127.0.0.1' else route.abort())
        try:yield page,conn,base,errors,writes
        finally:context.close()
    conn.close()


def seed(conn):
    eid=st.cal_create(conn,'CALSP Nine','2026-10-20',start_time='09:00',end_time='10:00',audience='bureau')
    st.cal_create(conn,'CALSP <img src=x onerror=alert(1)>','2026-10-20',start_time='09:30',end_time='10:30',audience='bureau')
    st.cal_create(conn,'CALSP No end','2026-10-20',start_time='13:00',audience='bureau')
    return eid


@pytest.mark.parametrize('width',[320,360,390,768,1024,1440,1920])
@pytest.mark.parametrize('theme',['light','dark','contrast'])
def test_hour_grid_timezone_mobile_day_links_and_accessible_list(schedule_page,width,theme,tmp_path):
    page,conn,base,errors,writes=schedule_page;eid=seed(conn)
    page.set_viewport_size({'width':width,'height':900})
    page.context.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(base+'/calendar?view=schedule&day=2026-10-20&q=CALSP')
    expect(page.locator('[data-schedule-status]')).to_contain_text('Hour grid ready')
    grid=page.locator('#cal-schedule-grid');expect(grid).to_be_visible()
    assert page.get_by_role('columnheader').count()==(1 if width<760 else 7)
    link=grid.locator(f'a[href="/calendar/entries/{eid}"]')
    expect(link).to_contain_text('09:00')
    link.scroll_into_view_if_needed()
    assert page.get_by_role('columnheader').first.bounding_box()['width'] > 40
    # A global phone table rule must not collapse the widget's internal table.
    assert grid.locator('.fc-scrollgrid').evaluate('(n)=>getComputedStyle(n).display')=='table'
    assert link.bounding_box()['width'] > 40
    expect(grid.locator('.fc-daygrid-event').filter(has_text='CALSP No end')).to_contain_text('End time not set')
    assert grid.locator('img').count()==0
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/f'schedule-{width}-{theme}.png'),full_page=True)
    link.focus();before=page.url;link.press('ArrowRight')
    assert page.url==before  # Widget keys must not invoke the page's week shortcuts.
    link.press('Enter')
    expect(page.get_by_role('dialog',name='CALSP Nine',exact=True)).to_be_visible()
    page.keyboard.press('Escape');expect(link).to_be_focused()
    if width<760:
        page.get_by_label('Show day in the hour grid').select_option('2026-10-21')
        expect(grid.locator(f'a[href="/calendar/entries/{eid}"]')).to_have_count(0)
        page.get_by_label('Show day in the hour grid').select_option('2026-10-20')
        expect(grid.locator(f'a[href="/calendar/entries/{eid}"]')).to_have_count(1)
    page.get_by_role('button',name='Show weekly list').click()
    expect(page.get_by_role('heading',name='Full week as a list')).to_be_focused()
    expect(page.locator('#cal-schedule-list')).to_be_visible()
    assert not errors and not writes


def test_resizing_keeps_selected_day_and_focus_without_changing_week(schedule_page):
    page,conn,base,errors,writes=schedule_page;seed(conn)
    page.set_viewport_size({'width':1440,'height':900})
    page.goto(base+'/calendar?view=schedule&day=2026-10-20&q=CALSP')
    expect(page.locator('[data-schedule-status]')).to_contain_text('Hour grid ready')
    grid=page.locator('#cal-schedule-grid');grid.focus();before=page.url
    page.set_viewport_size({'width':390,'height':900})
    expect(page.get_by_role('columnheader')).to_have_count(1)
    expect(grid).to_be_focused()
    page.get_by_label('Show day in the hour grid').select_option('2026-10-21')
    page.set_viewport_size({'width':1440,'height':900})
    expect(page.get_by_role('columnheader')).to_have_count(7)
    expect(grid).to_contain_text('CALSP Nine')
    page.set_viewport_size({'width':390,'height':900})
    expect(page.get_by_role('columnheader')).to_have_count(1)
    expect(grid).not_to_contain_text('CALSP Nine')
    assert page.url==before and not errors and not writes


@pytest.mark.parametrize('scripts',[False,True])
def test_native_or_blocked_bundle_retains_complete_readable_week(schedule_page,scripts):
    page,conn,base,errors,writes=schedule_page;seed(conn)
    if scripts:
        page.route('**/static/vendor/fullcalendar/fullcalendar-with-timezone.js*',lambda r:r.abort())
    else:
        page.context.new_cdp_session(page).send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto(base+'/calendar?view=schedule&day=2026-10-20&q=CALSP')
    expect(page.locator('#cal-schedule-list')).to_be_visible()
    expect(page.locator('#cal-schedule-list')).to_contain_text('CALSP Nine')
    expect(page.locator('#cal-schedule-list')).to_contain_text('CALSP No end')
    if scripts:expect(page.locator('[data-schedule-status]')).to_contain_text('hour grid is unavailable')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors and not writes
