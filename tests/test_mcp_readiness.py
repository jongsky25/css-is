"""Phone status checks keep catalog, activation and owner consent independent."""
import json
import time
from types import SimpleNamespace

from starlette.testclient import TestClient

import mcp_auth
import mcp_read
from tests.test_integration_read_api import api
from tests.test_work import workspace


def grant(c, owner, name, scopes):
    c.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', (name, json.dumps({'client_name': name}), int(time.time())))
    token = mcp_auth.Provider._tokens(c, name, owner, scopes, 'https://office.example/mcp')
    c.commit()
    return token


def test_running_catalog_owner_isolation_and_read_only_status(api, monkeypatch):
    c, users, _, clients, app = api
    first = grant(c, users[0]['id'], 'My phone connection', ['work:read', 'surveys:activity_details:read'])
    other = grant(c, users[1]['id'], 'Other private connection', ['surveys:csm:read'])
    server, _ = mcp_read.build_server(app.get_conn, 'https://office.example')
    monkeypatch.setattr(app, '_MCP_ENABLED', True)
    monkeypatch.setattr(app, '_mcp_server', server, raising=False)
    monkeypatch.setenv('CSS_MCP_ACTIVITY_DETAILS_ENABLED', '1')
    monkeypatch.delenv('CSS_MCP_CSM_ENABLED', raising=False)
    monkeypatch.setenv('UNRELATED_PRIVATE_SECRET', 'DO-NOT-EXPOSE-THIS')
    before = c.execute('SELECT * FROM mcp_oauth_grant ORDER BY id').fetchall()
    response = clients[0].get('/account/integrations/mcp')
    assert response.status_code == 200, response.text[:1000]
    html = response.text
    assert '25 registered tools' in html
    assert 'find_survey_activities' in html and 'get_activity_survey_detail' in html
    assert 'My phone connection' in html and 'Other private connection' not in html
    assert 'Individual activity scorecards: <strong>Granted</strong>' in html
    assert 'Monthly CSM summaries: <strong>Missing</strong>' in html
    assert 'Hosting switch: <strong>Enabled</strong>' in html
    assert 'Hosting switch: <strong>Disabled</strong>' in html
    assert 'DO-NOT-EXPOSE-THIS' not in html
    for token in (first.access_token, first.refresh_token, other.access_token):
        assert token not in html and mcp_auth._digest(token) not in html
    assert 'no-store' in response.headers['cache-control']
    assert response.headers['referrer-policy'] == 'same-origin'
    assert c.execute('SELECT * FROM mcp_oauth_grant ORDER BY id').fetchall() == before
    assert '/account/integrations/mcp' in clients[0].get('/account/integrations').text
    assert 'saved tool list is not visible here' in html


def test_disabled_failed_catalog_and_grant_lifecycle(api, monkeypatch):
    c, users, _, clients, app = api
    grant(c, users[0]['id'], 'Expired connection', ['work:read'])
    grant(c, users[0]['id'], 'Revoked connection', ['work:read'])
    c.execute('UPDATE mcp_oauth_grant SET refresh_expires=1 WHERE client_id=?', ('Expired connection',))
    c.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE client_id=?', ('Revoked connection',))
    c.commit()
    monkeypatch.setattr(app, '_MCP_ENABLED', False)
    page = clients[0].get('/account/integrations/mcp')
    assert page.status_code == 200
    assert 'Refresh expired' in page.text and 'Revoked' in page.text
    assert 'no live catalog is available' in page.text
    assert '0 registered tools' not in page.text
    assert 'Server tools: <strong>Not checked</strong>' in page.text

    async def failed():
        raise RuntimeError('synthetic unavailable catalog')
    monkeypatch.setattr(app, '_MCP_ENABLED', True)
    monkeypatch.setattr(app, '_mcp_server', SimpleNamespace(list_tools=failed), raising=False)
    page = clients[0].get('/account/integrations/mcp')
    assert page.status_code == 200
    assert 'catalog could not be inspected' in page.text
    assert 'synthetic unavailable catalog' not in page.text


def test_anonymous_and_stale_session_cannot_see_readiness(api):
    c, users, _, clients, app = api
    with TestClient(app.app, raise_server_exceptions=False) as anonymous:
        response = anonymous.get('/account/integrations/mcp', follow_redirects=False)
        assert response.status_code in (303, 307)
        assert 'registered tools' not in response.text
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],))
    c.commit()
    response = clients[0].get('/account/integrations/mcp', follow_redirects=False)
    assert response.status_code in (303, 307, 403)
    assert 'registered tools' not in response.text


def test_phone_navigation_and_prompt_selection_without_scripts(api, monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil

    c, users, _, clients, app = api
    grant(c, users[0]['id'], 'Phone check', ['surveys:activity_details:read'])
    server, _ = mcp_read.build_server(app.get_conn, 'https://office.example')
    monkeypatch.setattr(app, '_MCP_ENABLED', True)
    monkeypatch.setattr(app, '_mcp_server', server, raising=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium') or None,
                                             args=['--no-sandbox'])
        try:
            for width in (320, 390):
                context, page = page_for(browser, clients[0], viewport={'width': width, 'height': 844},
                                         java_script_enabled=False)
                try:
                    page.goto('http://testserver/account/integrations')
                    page.get_by_role('link', name='Check ChatGPT readiness').click()
                    expect(page.get_by_role('heading', name='ChatGPT readiness', exact=True)).to_be_visible()
                    assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                    page.get_by_text('Show running tool names', exact=True).click()
                    expect(page.locator('li').filter(has_text='get_activity_survey_detail').first).to_be_visible()
                    expect(page.get_by_label('Individual activity scorecard')).to_have_value(
                        'Use Office Connect find_survey_activities for Q3 2026. Pass an activity_id returned by that tool to get_activity_survey_detail. Show the source link and five-dimension scorecard, or explain why scores are withheld.')
                    expect(page.get_by_role('link', name='Open Q3 2026 activity source report')).to_have_attribute(
                        'href', '/reports?type=2&period=quarter:2026-Q3')
                    page.get_by_role('link', name='Back to Connected tools').click()
                    expect(page.get_by_role('heading', name='Connected tools', exact=True)).to_be_visible()
                finally:
                    context.close()
        finally:
            browser.close()
