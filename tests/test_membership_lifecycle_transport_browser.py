"""Opt-in exact-browser transport capability; not a memory comparison slot."""
from http.server import ThreadingHTTPServer
import json
import os
import threading
import pytest
from playwright.sync_api import sync_playwright
from scripts.avatar_baseline.element_membership_lifecycle import BROWSER, Handler

pytestmark = pytest.mark.skipif(os.getenv('CSS_MEMBERSHIP_TRANSPORT') != '1', reason='Opt-in pinned transport capability')


def test_binding_survives_departing_document():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(BROWSER), args=['--no-sandbox'])
            assert browser.version == '156.0.8078.47'
            context = browser.new_context()
            context.add_init_script('''addEventListener('pagehide', event => {
                const m = location.pathname.match(/^\\/fixture\\/(\\d+)$/);
                if (m) globalThis.membershipLifecycle(JSON.stringify({index: Number(m[1]), persisted: event.persisted}));
            });''')
            page = context.new_page(); cdp = context.new_cdp_session(page); received = []
            cdp.on('Runtime.bindingCalled', lambda e: received.append(json.loads(e['payload'])))
            cdp.send('Runtime.enable'); cdp.send('Runtime.addBinding', {'name': 'membershipLifecycle'})
            origin = f'http://127.0.0.1:{server.server_port}'
            page.goto(origin + '/fixture/0'); page.wait_for_timeout(220)
            page.goto(origin + '/fixture/1'); page.wait_for_timeout(220)
            assert received == [{'index': 0, 'persisted': False}]
            browser.close()
    finally:
        server.shutdown(); server.server_close()
