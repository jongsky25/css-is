"""Real authenticated Chromium: native filtering, vendor paging, safe links and fallback."""
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import expect
import auth
import storage as st
from tests.conftest import session_token
from tests.test_travel_grid import claims
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app


@pytest.fixture
def claims_page(grid_browser,app_mod,claims,monkeypatch):
    conn,owner,other,add=claims
    for i in range(1,36):add(i, act_title=('<img src=x onerror="window.claimInjected=true"> '+('Long activity '*15)) if i==1 else f'Visit {i:03}')
    add(99,user_id=other,act_title='OTHER_PRIVATE_CLAIM')
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        context=grid_browser.new_context(viewport={'width':390,'height':900},service_workers='block')
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(st.get_admin_user(conn,'viewer@test.local')),'url':base}])
        context.add_init_script("localStorage.setItem('css_tour_optout','1')")
        page=context.new_page();state={'errors':[],'posts':[],'fail':False,'block':False}
        page.on('pageerror',lambda e:state['errors'].append(str(e)))
        page.on('request',lambda r:state['posts'].append(urlsplit(r.url).path) if r.method=='POST' and urlsplit(r.url).path!='/telemetry' else None)
        def serve(route):
            u=urlsplit(route.request.url)
            if u.hostname!='127.0.0.1' or (state['block'] and u.path.endswith('/tabulator.min.js')) or (state['fail'] and 'format=json' in u.query):route.abort()
            else:route.continue_()
        page.route('**/*',serve)
        try:yield page,context,base,state
        finally:context.close()


@pytest.mark.parametrize('width',[320,390,1440])
@pytest.mark.parametrize('theme',['light','dark','contrast'])
def test_grid_pages_filters_keyboard_links_and_phone_geometry(claims_page,width,theme,tmp_path):
    page,context,base,state=claims_page
    page.set_viewport_size({'width':width,'height':900})
    context.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(base+'/travel/table?sort=ref_code&dir=asc')
    expect(page.locator('#claims-native')).to_contain_text('page 1 of 2')
    page.get_by_role('button',name='Open interactive table').click()
    expect(page.locator('#claims-status')).to_contain_text('Interactive page 1 of 2')
    expect(page.locator('#claims-grid .tabulator-row')).to_have_count(30)
    link=page.locator('#claims-grid').get_by_role('link',name='TF-2610-0001',exact=True)
    expect(link).to_have_attribute('href','/travel/f/TF-2610-0001')
    assert page.locator('#claims-grid img').count()==0 and not page.evaluate('!!window.claimInjected')
    assert 'OTHER_PRIVATE_CLAIM' not in page.content()
    link.focus();assert link.evaluate('(el)=>document.activeElement===el')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('#claims-grid .tabulator-cell').first.bounding_box()['width']>40
    page.screenshot(path=str(tmp_path/f'claims-{width}-{theme}.png'),full_page=True)
    page.locator('#claims-grid button[data-page=next]').click()
    expect(page.locator('#claims-status')).to_contain_text('Interactive page 2 of 2')
    expect(page.locator('#claims-grid .tabulator-row')).to_have_count(5)
    expect(page.locator('#claims-grid')).to_contain_text('TF-2610-0031')
    expect(page.locator('#claims-standard-link')).to_have_attribute('href',__import__('re').compile('page=2'))
    # A native GET changes the complete server selection, rather than sorting only visible rows.
    page.get_by_label('Reference or activity').fill('Visit 035')
    page.get_by_role('button',name='Apply selection').click()
    expect(page.locator('#claims-native')).to_contain_text('TF-2610-0035')
    expect(page.locator('#claims-native')).not_to_contain_text('TF-2610-0034')
    assert not state['errors'] and not state['posts']


@pytest.mark.parametrize('failure',['nojs','vendor','request','retry'])
def test_native_fallback_and_recovery(claims_page,failure):
    page,context,base,state=claims_page
    if failure=='nojs':context.new_cdp_session(page).send('Emulation.setScriptExecutionDisabled',{'value':True})
    if failure=='vendor':state['block']=True
    page.goto(base+'/travel/table?sort=ref_code&dir=asc')
    if failure in ('request','retry'):
        state['fail']=True
        page.get_by_role('button',name='Open interactive table').click()
        expect(page.locator('#claims-status')).to_contain_text('Interactive table unavailable')
        expect(page.locator('#claims-native')).to_be_visible()
        if failure=='retry':
            state['fail']=False
            page.get_by_role('button',name='Open interactive table').click()
            expect(page.locator('#claims-status')).to_contain_text('Interactive page 1 of 2')
            page.get_by_role('button',name='Show standard table').click()
    expect(page.locator('#claims-native')).to_be_visible()
    page.get_by_role('link',name='Next page',exact=True).click()
    expect(page.locator('#claims-native')).to_contain_text('page 2 of 2')
    expect(page.locator('#claims-native')).to_contain_text('TF-2610-0031')
    assert not state['errors'] and not state['posts']
