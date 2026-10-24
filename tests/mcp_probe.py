"""Independent HTTP/OAuth/MCP probe in a fresh process with synthetic accounts."""
import base64
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

with tempfile.TemporaryDirectory(prefix='office-mcp-probe-') as directory:
    os.environ['CSS_DB'] = str(Path(directory) / 'synthetic.db')
    os.environ['CSS_BASE_URL'] = 'https://office.example'
    os.environ['CSS_MCP_ENABLED'] = '1'
    os.environ['CSS_SESSION_SECRET'] = 'synthetic-mcp-only-session-key'
    import auth
    import storage as st
    conn = st.connect(os.environ['CSS_DB'])
    st.init_db(conn)
    hashed, salt = auth.hash_password('Synthetic123!')
    owner = st.create_admin_user(conn, 'mcp@example.invalid', hashed, salt, 'viewer',
                                 created_by='test', active=True)
    st.mark_onboarded(conn, owner)
    other = st.create_admin_user(conn, 'other@example.invalid', hashed, salt, 'viewer',
                                 created_by='test', active=True)
    st.mark_onboarded(conn, other)
    owned_doc = conn.execute('''INSERT INTO document
        (number,direction,subject,type,creator_id,status,visibility,verification,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        ('MCP-OWN', 'IN', 'Visible synthetic subject', 'Letter', owner, 'registered',
         'restricted', 'verified', '2026-10-20T00:00:00', '2026-10-20T00:00:00')).lastrowid
    hidden_doc = conn.execute('''INSERT INTO document
        (number,direction,subject,type,creator_id,status,visibility,verification,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        ('MCP-HIDDEN', 'IN', 'Hidden synthetic subject', 'Letter', other, 'registered',
         'restricted', 'verified', '2026-10-20T00:00:00', '2026-10-20T00:00:00')).lastrowid
    conn.execute('INSERT INTO document_access(document_id,user_id,source) VALUES (?,?,?)',
                 (owned_doc, owner, 'synthetic-probe'))
    conn.execute('INSERT INTO document_access(document_id,user_id,source) VALUES (?,?,?)',
                 (hidden_doc, other, 'synthetic-probe'))
    visible_event = st.cal_create(conn, 'Visible synthetic meeting', '2026-10-24', audience='people',
                                  people=[owner], by=other, meeting_url='https://private.example/meeting')
    st.cal_create(conn, 'Hidden synthetic meeting', '2026-10-24', audience='people',
                  people=[other], by=other)
    conn.commit()
    conn.close()

    import app
    callback = 'https://chatgpt.com/connector_platform_oauth_redirect'
    verifier = 'synthetic-verifier-0123456789-abcdefghijklmnopqrstuvwxyz'
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with TestClient(app.app, base_url='https://office.example') as client:
        metadata = client.get('/.well-known/oauth-protected-resource/mcp')
        assert metadata.status_code == 200
        assert metadata.json()['resource'] == 'https://office.example/mcp'
        assert set(metadata.json()['scopes_supported']) == {'calendar:read', 'work:read', 'documents:read'}
        denied = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                          'params': {'protocolVersion': '2025-06-18',
                                                     'capabilities': {}, 'clientInfo': {'name': 'probe', 'version': '1'}}},
                             headers={'accept': 'application/json, text/event-stream'})
        assert denied.status_code == 401
        hostile = client.post('/register', json={
            'redirect_uris': ['https://evil.example/callback'], 'client_name': 'ChatGPT',
            'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'], 'scope': 'work:read'})
        assert hostile.status_code == 400
        registered = client.post('/register', json={
            'redirect_uris': [callback], 'client_name': 'ChatGPT',
            'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code']})
        assert registered.status_code == 201, registered.text
        assert set(registered.json()['scope'].split()) == {'calendar:read', 'work:read', 'documents:read'}
        client_id = registered.json()['client_id']
        auth_url = client.get('/authorize', params={
            'response_type': 'code', 'client_id': client_id, 'redirect_uri': callback,
            'code_challenge': challenge, 'code_challenge_method': 'S256',
            'state': 'probe-state',
            'resource': 'https://office.example/mcp'}, follow_redirects=False)
        assert auth_url.status_code in (302, 303), auth_url.text
        consent_url = auth_url.headers['location']
        browser = TestClient(app.app, base_url='https://office.example')
        browser.cookies.set(auth.COOKIE_NAME, app._issue_session(
            {'id': owner, 'username': 'mcp@example.invalid', 'role': 'viewer'}))
        page = browser.get(consent_url)
        assert page.status_code == 200, page.text
        assert 'Your visible work items' in page.text
        assert 'Your visible document metadata' in page.text
        assert 'Your visible calendar events and activities' in page.text
        assert page.headers['referrer-policy'] == 'same-origin'
        ticket = re.search(r'name="ticket" value="([^"]+)"', page.text).group(1)
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        bad_origin = browser.post('/mcp-consent', data={'ticket': ticket, 'csrf': csrf,
            'decision': 'approve', 'password': 'Synthetic123!'},
            headers={'Origin': 'https://evil.example'}, follow_redirects=False)
        assert bad_origin.status_code == 403
        assert bad_origin.headers['content-type'].startswith('text/html')
        wrong_password = browser.post('/mcp-consent', data={'ticket': ticket, 'csrf': csrf,
            'decision': 'approve', 'password': 'wrong'},
            headers={'Referer': consent_url}, follow_redirects=False)
        assert wrong_password.status_code == 403
        assert wrong_password.headers['content-type'].startswith('text/html')
        assert 'password could not be verified' in wrong_password.text
        approved = browser.post('/mcp-consent', data={'ticket': ticket, 'csrf': csrf,
            'decision': 'approve', 'password': 'Synthetic123!'},
                                headers={'Referer': consent_url}, follow_redirects=False)
        assert approved.status_code == 303, approved.text
        code = parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
        assert parse_qs(urlsplit(approved.headers['location']).query)['state'] == ['probe-state']
        exchanged = client.post('/token', data={'grant_type': 'authorization_code', 'client_id': client_id,
            'code': code, 'code_verifier': verifier, 'redirect_uri': callback,
            'resource': 'https://office.example/mcp'})
        assert exchanged.status_code == 200, exchanged.text
        access = exchanged.json()['access_token']
        replay = client.post('/token', data={'grant_type': 'authorization_code', 'client_id': client_id,
            'code': code, 'code_verifier': verifier, 'redirect_uri': callback,
            'resource': 'https://office.example/mcp'})
        assert replay.status_code == 400
        headers = {'Authorization': 'Bearer ' + access, 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2025-06-18'}
        initialized = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-06-18', 'capabilities': {},
                       'clientInfo': {'name': 'probe', 'version': '1'}}}, headers=headers)
        assert initialized.status_code == 200, initialized.text
        listed = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, headers=headers)
        assert listed.status_code == 200, listed.text
        names = {tool['name'] for tool in listed.json()['result']['tools']}
        assert {'my_work', 'find_documents', 'get_document'} <= names
        assert names == {'my_work', 'find_documents', 'get_document',
                         'list_work_items', 'get_work_item', 'list_work_tasks', 'list_calendar_events'}
        api_token = client.get('/api/v1/work-items', headers={'Authorization': 'Bearer ' + access})
        assert api_token.status_code == 401
        called = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
            'params': {'name': 'my_work', 'arguments': {}}}, headers=headers)
        assert called.status_code == 200, called.text
        assert not called.json()['result'].get('isError'), called.text
        calendar = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 10, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-24', 'scope': 'bureau'}}}, headers=headers)
        assert calendar.status_code == 200 and not calendar.json()['result'].get('isError'), calendar.text
        assert 'Visible synthetic meeting' in calendar.text
        assert 'Hidden synthetic meeting' not in calendar.text
        assert 'private.example' not in calendar.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('DELETE FROM calendar_entry_person WHERE entry_id=? AND user_id=?',
                     (visible_event, owner))
        conn.commit(); conn.close()
        calendar_withdrawn = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 13, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-24', 'scope': 'bureau'}}}, headers=headers)
        assert calendar_withdrawn.status_code == 200 and not calendar_withdrawn.json()['result'].get('isError')
        assert 'Visible synthetic meeting' not in calendar_withdrawn.text
        invalid_range = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 11, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-01', 'end_date': '2026-12-31'}}}, headers=headers)
        assert invalid_range.status_code == 200 and invalid_range.json()['result'].get('isError')
        import mcp_auth
        conn = st.connect(os.environ['CSS_DB'])
        work_only = mcp_auth.Provider._tokens(conn, client_id, owner, ['work:read'],
                                             'https://office.example/mcp')
        conn.commit(); conn.close()
        limited = dict(headers, Authorization='Bearer ' + work_only.access_token)
        no_scope = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 12, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-24'}}}, headers=limited)
        assert no_scope.status_code == 200 and no_scope.json()['result'].get('isError')
        assert 'Visible synthetic meeting' not in no_scope.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?',
                     (hashlib.sha256(work_only.access_token.encode()).hexdigest(),))
        conn.commit(); conn.close()
        visible = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
            'params': {'name': 'get_document', 'arguments': {'document_id': owned_doc}}}, headers=headers)
        assert visible.status_code == 200 and not visible.json()['result'].get('isError'), visible.text
        assert 'Visible synthetic subject' in visible.text
        hidden = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call',
            'params': {'name': 'get_document', 'arguments': {'document_id': hidden_doc}}}, headers=headers)
        assert hidden.status_code == 200 and hidden.json()['result'].get('isError'), hidden.text
        assert 'Hidden synthetic subject' not in hidden.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?', (owned_doc, owner))
        conn.commit(); conn.close()
        withdrawn = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
            'params': {'name': 'get_document', 'arguments': {'document_id': owned_doc}}}, headers=headers)
        assert withdrawn.status_code == 200 and withdrawn.json()['result'].get('isError'), withdrawn.text
        assert 'Visible synthetic subject' not in withdrawn.text
        refreshed = client.post('/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
            'refresh_token': exchanged.json()['refresh_token'], 'resource': 'https://office.example/mcp'})
        assert refreshed.status_code == 200, refreshed.text
        old = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 8, 'method': 'tools/list'}, headers=headers)
        assert old.status_code == 401
        headers['Authorization'] = 'Bearer ' + refreshed.json()['access_token']
        current = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 9, 'method': 'tools/list'}, headers=headers)
        assert current.status_code == 200
        # A browser user can disconnect the grant; the next protocol request
        # must then fail even if ChatGPT still holds the old bearer token.
        connections = browser.get('/account/integrations')
        assert connections.status_code == 200 and 'ChatGPT connections' in connections.text
        grant = re.search(r'/account/mcp/([0-9a-f]{32})/revoke', connections.text).group(1)
        management_csrf = re.search(r'name="csrf" value="([^"]+)"', connections.text).group(1)
        disconnected = browser.post('/account/mcp/' + grant + '/revoke',
            data={'csrf': management_csrf},
            headers={'Origin': 'https://office.example'}, follow_redirects=False)
        assert disconnected.status_code == 303, disconnected.text
        stale = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'}, headers=headers)
        assert stale.status_code == 401
        browser.close()
