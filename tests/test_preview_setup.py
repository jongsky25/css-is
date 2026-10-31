"""Verify the deployable bundle and isolated phone-review login flow."""
import importlib.util
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outbound_connections_blocked(monkeypatch):
    # Restore process-wide hooks after this isolated check.
    with monkeypatch.context() as patch:
        patch.setattr(socket.socket, 'connect', socket.socket.connect)
        patch.setattr(socket.socket, 'connect_ex', socket.socket.connect_ex)
        load_script('preview_app').block_external_connections()
        with socket.socket() as sock:
            try:
                sock.connect(('192.0.2.1', 443))
            except OSError as exc:
                assert 'disabled in preview' in str(exc)
            else:
                raise AssertionError('External connection was not blocked')


def test_bundle_private_preview_login_and_mobile(tmp_path):
    deploy = load_script('deploy_preview_hf')
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    deploy.stage(bundle)
    assert not list(bundle.rglob('*.db'))
    assert not (bundle / 'deploy_hf.py').exists()
    assert not (bundle / '.env.local').exists()
    assert deploy.TARGET == 'equityinhealth/office-connect-preview'
    sentinel = tmp_path / 'must-not-touch.db'
    sentinel.write_bytes(b'not a production database; do not read or write')
    before = sentinel.read_bytes()
    password = secrets.token_urlsafe(24)
    env = dict(os.environ, OFFICE_PREVIEW_PASSWORD=password, CSS_DB=str(sentinel),
               CSS_PERSIST_DIR=str(tmp_path / 'must-not-create'),
               HF_TOKEN='fake-test-token', SPACE_HOST='')
    with (tmp_path / 'server.log').open('w') as log:
        process = subprocess.Popen([sys.executable, str(bundle / 'scripts/preview_app.py')],
                                   cwd=bundle, env=env, stdout=log, stderr=log,
                                   start_new_session=True)
        try:
            with httpx.Client(base_url='http://127.0.0.1:7860', trust_env=False) as client:
                for _ in range(120):
                    assert process.poll() is None, (tmp_path / 'server.log').read_text()
                    try:
                        ready = client.get('/preview-health')
                        if ready.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.25)
                else:
                    raise AssertionError('Preview did not start')
                page = client.get('/login')
                assert page.status_code == 200
                assert 'PREVIEW — synthetic data only' in page.text
                assert 'Set up the first account' not in page.text
                assert page.headers['x-office-connect-environment'] == 'preview'
                denied = client.post('/login', data={'username':'preview@example.invalid',
                                                    'password':'wrong'},
                                     headers={'Origin':'http://127.0.0.1:7860'})
                assert denied.status_code == 401
                response = client.post('/login', data={'username':'preview@example.invalid',
                                                       'password':password},
                                       headers={'Origin':'http://127.0.0.1:7860'})
                assert response.status_code == 303
                assert client.get('/me').status_code == 200
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(args=['--no-sandbox'])
                try:
                    page = browser.new_page(viewport={'width':390, 'height':844})
                    page.goto('http://127.0.0.1:7860/login')
                    assert page.get_by_role('note').is_visible()
                    page.locator('input[name="username"]').fill('preview@example.invalid')
                    page.locator('input[name="password"]').fill(password)
                    page.locator('button[type="submit"]').click()
                    page.wait_for_url(lambda url: '/login' not in url)
                    assert page.get_by_role('note').first.is_visible()
                finally:
                    browser.close()
        finally:
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=15)
    assert sentinel.read_bytes() == before
    assert not (tmp_path / 'must-not-create').exists()
