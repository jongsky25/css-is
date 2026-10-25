"""Actual server, native fallback and live spelling suggestions in Chromium."""
import json
from urllib.parse import urlsplit,parse_qs

import auth
import storage as st
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app


def seed(conn,name,username):
    rp=conn.execute('INSERT INTO resource_person(name,is_internal,position) VALUES (?,1,?)',(name,'Synthetic Officer')).lastrowid
    uid=st.create_admin_user(conn,username,'x','y','viewer',rp_id=rp)
    st.mark_onboarded(conn,uid);conn.commit()
    return uid


def context_for(browser,conn,base,**options):
    user=st.get_admin_user(conn,'viewer@test.local')
    context=browser.new_context(viewport={'width':390,'height':844},**options)
    context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
    return context


def test_live_mobile_exact_before_close_keyboard_scope_and_native_fallback(grid_browser,app_mod,monkeypatch,tmp_path):
    conn=st.connect(app_mod.DB)
    exact=seed(conn,'Zircon Jhon Example','search-exact@example.test')
    close=seed(conn,'Zircon John Long-Family-Name Example','search-close@example.test')
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        context=context_for(grid_browser,conn,base)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(base+'/')
            page.locator('#navSearchBtn').click();page.locator('#cmdkInput').fill('zircon jhon')
            near=page.locator(f'#cmdkResults a[href="/people/{close}"]');near.wait_for()
            assert 'Close match' in near.inner_text()
            assert near.locator('.pi-tag').evaluate('(node)=>node.getBoundingClientRect().right<=node.closest(".palette").getBoundingClientRect().right-4')
            page.screenshot(path=str(tmp_path/'search-colleague-mobile.png'),full_page=True)
            anchors=page.locator('#cmdkResults a[role="option"]').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("href"))')
            assert anchors.index('/people/'+str(exact))<anchors.index('/people/'+str(close))
            assert 'No matching page' not in page.locator('#cmdkResults').inner_text()
            page.locator('#cmdkInput').fill('reimbursment')
            page.locator('#cmdkResults a[href="/travel"]').wait_for()
            assert 'Close match' in page.locator('#cmdkResults a[href="/travel"]').inner_text()
            page.screenshot(path=str(tmp_path/'search-close-mobile.png'),full_page=True)
            selected=page.locator('#cmdkResults a[aria-selected="true"]').get_attribute('href')
            with page.expect_navigation(wait_until='domcontentloaded') as navigation:page.locator('#cmdkInput').press('Enter')
            assert navigation.value.status<400
            page.goto(base+'/css')
            box=page.locator('form[data-search] .gsearch-input');box.fill('zircon jhon')
            page.locator('.gsearch-results .palette-exit').wait_for()
            # Wait for the scoped request to settle: only the exit row remains.
            page.wait_for_function("!document.querySelector('.gsearch-results .palette-loading')")
            assert 'Zircon' not in page.locator('.gsearch-results').inner_text()
            page.locator('.gsearch-results .palette-exit a').click()
            page.locator(f'#cmdkResults a[href="/people/{close}"]').wait_for()
            assert not errors
        finally:context.close()
        native=context_for(grid_browser,conn,base,java_script_enabled=False)
        page=native.new_page()
        try:
            response=page.goto(base+'/search?q=reimbursment')
            assert response.status==200 and response.headers['cache-control']=='no-store'
            assert 'Close matches' in page.locator('main').inner_text()
            with page.expect_navigation(wait_until='domcontentloaded') as navigation:page.locator('.search-list a[href="/travel"]').click()
            assert navigation.value.status<400 and urlsplit(page.url).path.startswith('/travel')
        finally:native.close()
    conn.close()


def test_old_response_cannot_restore_results_after_clear_or_query_reuse(grid_browser,app_mod,monkeypatch):
    conn=st.connect(app_mod.DB)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        context=context_for(grid_browser,conn,base,service_workers='block')
        # Exercise the sequence guard even on a browser without AbortController.
        context.add_init_script('window.AbortController=undefined')
        page=context.new_page();held=[]
        def serve(route):
            q=parse_qs(urlsplit(route.request.url).query).get('q',[''])[0]
            if q in ('deferredword','clearedword'):
                held.append(route);page.evaluate('(n)=>window.heldSearchRequests=n',len(held))
            else:route.continue_()
        page.route('**/api/search?*',serve)
        try:
            page.goto(base+'/');page.locator('#navSearchBtn').click();box=page.locator('#cmdkInput')
            with page.expect_request(lambda r:'/api/search?' in r.url and 'deferredword' in r.url):box.fill('deferredword')
            # Run the route callback before interacting with the pending request.
            page.wait_for_function('window.heldSearchRequests===1')
            with page.expect_request(lambda r:'/api/search?' in r.url and 'deferredword' in r.url):
                box.fill('');box.fill('deferredword')
            page.wait_for_function('window.heldSearchRequests===2')
            fresh=[{'title':'Fresh <img src=x onerror="window.searchInjected=1">','url':'/fresh','hint':'Safe label','section':'Help','match':'close'}]
            with page.expect_response(lambda r:'deferredword' in r.url):held[1].fulfill(status=200,content_type='application/json',body=json.dumps(fresh))
            page.locator('#cmdkResults a[href="/fresh"]').wait_for()
            with page.expect_response(lambda r:'deferredword' in r.url):held[0].fulfill(status=200,content_type='application/json',body=json.dumps([{'title':'Old result','url':'/old','section':'Help','match':'close'}]))
            page.evaluate('()=>new Promise(requestAnimationFrame)')
            assert page.locator('#cmdkResults a[href="/old"]').count()==0
            assert page.locator('#cmdkResults a[href="/fresh"]').count()==1
            assert page.locator('#cmdkResults img').count()==0 and page.evaluate('window.searchInjected') is None
            with page.expect_request(lambda r:'clearedword' in r.url):
                box.fill('');box.fill('clearedword')
            page.wait_for_function('window.heldSearchRequests===3');box.fill('')
            with page.expect_response(lambda r:'clearedword' in r.url):held[2].fulfill(status=200,content_type='application/json',body=json.dumps(fresh))
            page.evaluate('()=>new Promise(requestAnimationFrame)')
            assert page.locator('#cmdkResults a[href="/fresh"]').count()==0
        finally:context.close()
    conn.close()


def test_delayed_tour_does_not_take_search_focus(grid_browser,app_mod,monkeypatch):
    conn=st.connect(app_mod.DB)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        for path,palette in [('/',True),('/css',False)]:
            context=context_for(grid_browser,conn,base)
            page=context.new_page();page.clock.install()
            try:
                page.goto(base+path)
                if palette:
                    page.locator('#navSearchBtn').click();expected='#cmdkInput'
                else:
                    expected='form[data-search] .gsearch-input';page.locator(expected).focus()
                page.clock.fast_forward(700)
                assert page.locator('.tour-card').count()==0
                assert page.locator(expected).evaluate('(node)=>node===document.activeElement')
            finally:context.close()
    conn.close()


def test_search_service_failure_keeps_local_exact_navigation(grid_browser,app_mod,monkeypatch):
    conn=st.connect(app_mod.DB)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        context=context_for(grid_browser,conn,base,service_workers='block');page=context.new_page()
        page.route('**/api/search?*',lambda route:route.abort())
        try:
            page.goto(base+'/');page.locator('#navSearchBtn').click()
            with page.expect_request(lambda r:'/api/search?' in r.url):page.locator('#cmdkInput').fill('calendar')
            page.wait_for_function("!document.querySelector('#cmdkResults .palette-loading')")
            assert page.locator('#cmdkResults a[href="/calendar"]').count()==1
            assert 'Close match' not in page.locator('#cmdkResults').inner_text()
        finally:context.close()
    conn.close()
