"""Real Chromium form consent and an independent bearer HTTP reader, locally."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect
from starlette.testclient import TestClient

import auth
from examples.read_api import ReadClient,ApiFailure
from tests.test_document_guidance_browser import browser
from tests.test_integration_access import connected,api,workspace
from tests.test_work import case


@pytest.mark.parametrize('width',[390,1440])
def test_browser_consent_actual_tool_read_and_revocation(browser,connected,width):
    c,u,unit,clients,app=connected
    case(c,u[0],unit)
    adapter=TestClient(app.app,raise_server_exceptions=False)
    posts=[];errors=[];redirect_hits=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def handle_request(self):
            if self.path=='/api/v1/client-redirect':
                self.send_response(302);self.send_header('Location','/must-not-receive');self.end_headers();return
            if self.path=='/must-not-receive':redirect_hits.append(True)
            raw=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
            if self.command=='POST':posts.append((urlsplit(self.path).path,self.headers.get('Origin')))
            response=adapter.request(self.command,base+self.path,content=raw,
                headers={k:v for k,v in self.headers.items() if k.lower() not in ('content-length','connection','accept-encoding')},
                follow_redirects=False)
            self.send_response(response.status_code)
            for k,v in response.headers.items():
                if k.lower() not in ('content-length','content-encoding','connection','transfer-encoding'):
                    self.send_header(k,v)
            self.send_header('Content-Length',str(len(response.content)));self.end_headers()
            try:self.wfile.write(response.content)
            except (BrokenPipeError,ConnectionResetError):pass
        do_GET=do_POST=handle_request
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=False
    base=f'http://127.0.0.1:{server.server_port}'
    worker=Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);worker.start()
    context=browser.new_context(base_url=base,viewport={'width':width,'height':900},service_workers='block')
    context.add_cookies([{'name':auth.COOKIE_NAME,'value':clients[0].cookies.get(auth.COOKIE_NAME),'url':base}])
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname=='127.0.0.1' else route.abort())
    try:
        page.goto('/account/integrations')
        page.get_by_label('Tool name',exact=False).fill('Browser tracker')
        page.get_by_label('Work and task metadata',exact=True).check()
        page.get_by_label('I authorize this named tool',exact=False).check()
        from tests.conftest import PW
        page.get_by_label('Confirm your current password').fill(PW)
        page.get_by_role('button',name='Create read credential').focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('heading',name='Save this credential now')).to_be_visible()
        token=page.get_by_label('New credential',exact=True).input_value()
        client=ReadClient(base+'/api/v1',credential=token)
        assert list(client.pages('work-items'))[0]
        with pytest.raises(ApiFailure,match='HTTP 302'):client.get('/client-redirect')
        assert not redirect_hits
        with pytest.raises(ValueError,match='cannot perform writes'):client._request('/work-items',data=b'{}')
        with pytest.raises(ApiFailure,match='HTTP 403'):client.get('/documents')
        with pytest.raises(ApiFailure,match='HTTP 403'):client.get('/write-context')
        page.get_by_role('link',name='I have saved it — close the secret').click()
        expect(page.get_by_label('New credential',exact=True)).to_have_count(0)
        assert token not in page.content()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.get_by_role('button',name='Revoke Browser tracker',exact=True).click()
        expect(page.locator('article')).to_contain_text('Revoked')
        with pytest.raises(ApiFailure,match='HTTP 401'):client.get('/work-items')
        business_posts=[(p,o) for p,o in posts if p.startswith('/account/integrations')]
        assert len(business_posts)==2 and all(origin==base for _,origin in business_posts)
        assert not errors
    finally:
        context.close();server.shutdown();server.server_close();worker.join(timeout=2);adapter.close()
