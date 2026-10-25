"""Independent HTTP/OAuth/MCP probe in a fresh process with synthetic accounts."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# This fresh process does not inherit pytest's patched business clock. Keep the
# fixed October fixtures in the future even after Philippine midnight; pending
# room requests otherwise expire on startup. OAuth expiry still uses real time.
import tzutil as tz
PROBE_NOW = datetime(2026, 10, 20, 6)
tz.now_local = lambda: PROBE_NOW
tz.today_local = lambda: PROBE_NOW.date()

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
    manager = st.create_admin_user(conn, 'manager@example.invalid', hashed, salt, 'section_manager',
                                   created_by='test', active=True)
    st.mark_onboarded(conn, manager)
    unit = conn.execute("INSERT INTO org_unit(name,short_name,level,path) VALUES ('MCP Unit','MCP','section','MCP')").lastrowid
    owner_rp = conn.execute('INSERT INTO resource_person(name,is_internal,org_unit_id) VALUES (?,1,?)',
                            ('Synthetic owner', unit)).lastrowid
    other_rp = conn.execute('INSERT INTO resource_person(name,is_internal,org_unit_id) VALUES (?,1,?)',
                            ('Synthetic other', unit)).lastrowid
    own_supply = conn.execute('''INSERT INTO supply_request(requester_id,requester_rp_id,requester_snapshot,
        unit_id,unit_snapshot,purpose,date_needed,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)''', (owner, owner_rp, 'Synthetic owner', unit, 'MCP Unit',
                                         'Private supply purpose', '2026-10-28', '2026-10-20', '2026-10-20')).lastrowid
    conn.execute('''INSERT INTO supply_request(requester_id,requester_rp_id,requester_snapshot,
        unit_id,unit_snapshot,purpose,date_needed,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)''', (other, other_rp, 'Synthetic other', unit, 'MCP Unit',
                                         'Other private supply purpose', '2026-10-28', '2026-10-20', '2026-10-20'))
    conn.execute('''INSERT INTO travel_filing(user_id,kind,source_kind,act_title,act_start,act_end,
        deadline_date,status) VALUES (?,?,?,?,?,?,?,?)''',
        (owner, 'ca', 'blank', 'My synthetic travel', '2026-10-27', '2026-10-28', '2026-10-30', 'open'))
    conn.execute('''INSERT INTO travel_filing(user_id,kind,source_kind,act_title,act_start,act_end,
        deadline_date,status) VALUES (?,?,?,?,?,?,?,?)''',
        (other, 'ca', 'blank', 'Other private travel', '2026-10-27', '2026-10-28', '2026-10-30', 'open'))
    st.create_event(conn, 'Managed synthetic activity', '2026-10-27', created_by='manager@example.invalid')
    st.create_event(conn, 'Other hidden activity', '2026-10-27', created_by='other@example.invalid')
    linked_people = []
    linked_forms = []
    for label, hidden, position in [('Visible linked speaker',0,None), ('Hidden linked speaker',1,None), ('Director linked speaker',0,'Director')]:
        pid = conn.execute('INSERT INTO resource_person(name,is_internal,hidden_public,position) VALUES (?,1,?,?)',
                           (label,hidden,position)).lastrowid
        linked_people.append(pid)
        fid = st.create_form_instance(conn,survey_type=3,form='F3',event_date='2026-10-27',rp_id=pid,
                                      venue='Linked outside room',topic='Private session topic')
        linked_forms.append(fid)
    outside = st.create_event(conn,'Managed outside activity','2026-10-27',event_kind='outside',
                              form_instance_ids=linked_forms,created_by='manager@example.invalid')
    st.create_event(conn,'Other hidden outside activity','2026-10-27',event_kind='outside',
                    form_instance_ids=[],created_by='other@example.invalid')

    conn.execute("INSERT INTO supply_role_grant(user_id,role,granted_by,created_at) VALUES (?,'custodian',?,?)",
                 (manager, owner, '2026-10-20'))
    item = conn.execute('''INSERT INTO supply_item(code,description,unit,critical_level,created_by,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?)''', ('MCP-LOW', 'Synthetic low stock', 'pieces', 5, manager,
                                   '2026-10-20', '2026-10-20')).lastrowid
    key = 'synthetic-opening-operation'
    conn.execute('''INSERT INTO supply_operation(operation_key,actor_id,action,payload_sha256,result_json,created_at)
        VALUES (?,?,?,?,?,?)''', (key, manager, 'opening', '0' * 64, '{}', '2026-10-20'))
    conn.execute('''INSERT INTO supply_stock_movement(item_id,kind,quantity_delta,effective_date,posted_at,
        posted_by,actor_snapshot,source_type,source_id,code_snapshot,description_snapshot,unit_snapshot,operation_key)
        VALUES (?,'opening',1,?,?,?,?,?,?,?,?,?,?)''',
        (item, '2026-10-20', '2026-10-20', manager, 'Synthetic manager', 'item', item,
         'MCP-LOW', 'Synthetic low stock', 'pieces', key))
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
    slot = conn.execute("INSERT INTO room_slot(code,label,start_time,end_time,sort,active) "
                        "VALUES ('MCP10','10:00-11:00','10:00','11:00',10,1)").lastrowid
    def booking(title, requester, status):
        rid = conn.execute('INSERT INTO room_reservation(title,day,status,requester_user_id) '
                           'VALUES (?,?,?,?)', (title, '2026-10-24', status, requester)).lastrowid
        conn.execute('INSERT INTO room_reservation_slot(reservation_id,day,slot_id,is_approved) '
                     'VALUES (?,?,?,?)', (rid, '2026-10-24', slot, int(status == 'approved')))
        return rid
    booking('Approved shared room booking', other, 'approved')
    own_pending_room = booking('My pending room request', owner, 'requested')
    booking('Another private pending room request', other, 'requested')
    conn.commit()
    conn.close()

    import app
    import tzutil
    from datetime import date, datetime
    # Fixed-date fixtures must not expire when the real local day advances.
    tzutil.today_local = lambda: date(2026, 10, 24)
    tzutil.now_local = lambda: datetime(2026, 10, 24, 9)
    callback = 'https://chatgpt.com/connector_platform_oauth_redirect'
    verifier = 'synthetic-verifier-0123456789-abcdefghijklmnopqrstuvwxyz'
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with TestClient(app.app, base_url='https://office.example') as client:
        metadata = client.get('/.well-known/oauth-protected-resource/mcp')
        assert metadata.status_code == 200
        assert metadata.json()['resource'] == 'https://office.example/mcp'
        scopes = {'surveys:resource_person_trends:read', 'surveys:csm_trends:read', 'surveys:unit_trends:read', 'surveys:units:read', 'activities:read', 'calendar:read', 'documents:read',
                  'supplies:read', 'travel:read', 'work:read', 'notifications:read', 'surveys:csm:read', 'surveys:activities:read', 'surveys:resource_persons:read', 'surveys:activity_details:read'}
        assert set(metadata.json()['scopes_supported']) == scopes
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
            'redirect_uris': [callback], 'client_name': 'ChatGPT', 'scope': 'work:read',
            'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code']})
        assert registered.status_code == 201, registered.text
        assert set(registered.json()['scope'].split()) == scopes
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
        assert 'Permitted resource-person discovery and year-to-year satisfaction comparisons' in page.text
        assert 'Bureau-wide CSM satisfaction comparisons between consecutive months' in page.text
        assert 'Unit activity satisfaction comparisons between consecutive quarters' in page.text
        assert 'Unit discovery and quarterly activity satisfaction aggregates' in page.text
        assert 'Your visible work items' in page.text
        assert 'Your visible document metadata' in page.text
        assert 'Your visible calendar events, activities and room bookings' in page.text
        assert 'Your supply requests and permitted stock warnings' in page.text
        assert 'Your travel filing status and deadlines' in page.text
        assert 'Your permitted activity schedules and summary counts' in page.text
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
        assert names == {'find_survey_resource_persons', 'compare_resource_person_surveys', 'compare_csm_months', 'compare_unit_activity_surveys', 'find_survey_units', 'get_unit_activity_survey_summary', 'my_work', 'find_documents', 'get_document',
                         'list_work_items', 'get_work_item', 'list_work_tasks', 'list_calendar_events',
                         'list_supply_queue', 'list_my_travel_filings', 'list_activity_progress',
                         'my_office_overview', 'list_my_notifications', 'get_room_availability', 'get_csm_summary', 'get_activity_survey_summary', 'get_resource_person_survey_summary', 'find_survey_activities', 'get_activity_survey_detail'}
        api_token = client.get('/api/v1/work-items', headers={'Authorization': 'Bearer ' + access})
        assert api_token.status_code == 401
        called = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
            'params': {'name': 'my_work', 'arguments': {}}}, headers=headers)
        assert called.status_code == 200, called.text
        assert not called.json()['result'].get('isError'), called.text
        supplies = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 15, 'method': 'tools/call',
            'params': {'name': 'list_supply_queue', 'arguments': {'queue': 'requests'}}}, headers=headers)
        assert supplies.status_code == 200 and not supplies.json()['result'].get('isError'), supplies.text
        assert str(own_supply) in supplies.text
        assert 'Other private supply purpose' not in supplies.text
        assert 'Private supply purpose' not in supplies.text
        warnings = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 16, 'method': 'tools/call',
            'params': {'name': 'list_supply_queue', 'arguments': {'queue': 'warnings'}}}, headers=headers)
        assert warnings.status_code == 200 and warnings.json()['result'].get('isError')
        travel_result = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 17, 'method': 'tools/call',
            'params': {'name': 'list_my_travel_filings', 'arguments': {}}}, headers=headers)
        assert travel_result.status_code == 200 and not travel_result.json()['result'].get('isError'), travel_result.text
        assert 'My synthetic travel' in travel_result.text
        assert 'Other private travel' not in travel_result.text
        activities_unavailable = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 18, 'method': 'tools/call',
            'params': {'name': 'list_activity_progress', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-31'}}}, headers=headers)
        assert activities_unavailable.status_code == 200 and not activities_unavailable.json()['result'].get('isError')
        assert 'not available to this account' in activities_unavailable.text
        conn = st.connect(os.environ['CSS_DB'])
        import mcp_auth
        manager_grant = mcp_auth.Provider._tokens(conn, client_id, manager,
                                                  ['activities:read', 'supplies:read'],
                                                  'https://office.example/mcp')
        conn.commit(); conn.close()
        manager_headers = dict(headers, Authorization='Bearer ' + manager_grant.access_token)
        activities = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 19, 'method': 'tools/call',
            'params': {'name': 'list_activity_progress', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-31'}}}, headers=manager_headers)
        assert activities.status_code == 200 and not activities.json()['result'].get('isError'), activities.text
        assert 'Managed synthetic activity' in activities.text
        assert 'Other hidden activity' not in activities.text
        assert 'Other hidden outside activity' not in activities.text
        assert 'Visible linked speaker' not in activities.text
        activity_data = json.loads(activities.json()['result']['content'][0]['text'])['data']
        outside_data = next(a for a in activity_data if a['title']=='Managed outside activity')
        assert outside_data['survey_context']['survey_type']==3
        assert outside_data['survey_context']['resource_persons']['reason']=='permission_required'
        assert outside_data['survey_context']['activity_report_url']==f'https://office.example/reports?type=3&activity={min(linked_forms)}'
        conn = st.connect(os.environ['CSS_DB'])
        person_grant = mcp_auth.Provider._tokens(conn,client_id,manager,
            ['activities:read','surveys:resource_persons:read'],'https://office.example/mcp')
        conn.commit();conn.close()
        person_headers = dict(headers,Authorization='Bearer '+person_grant.access_token)
        def linked_call():
            return client.post('/mcp',json={'jsonrpc':'2.0','id':190,'method':'tools/call',
                'params':{'name':'list_activity_progress','arguments':{'start_date':'2026-10-24','end_date':'2026-10-31'}}},headers=person_headers)
        os.environ['CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED']='0'
        disabled_links = linked_call()
        assert not disabled_links.json()['result'].get('isError'),disabled_links.text
        assert 'Visible linked speaker' not in disabled_links.text
        assert 'disabled' in disabled_links.text
        os.environ['CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED']='1'
        enabled_links = linked_call()
        assert not enabled_links.json()['result'].get('isError'),enabled_links.text
        assert 'Visible linked speaker' in enabled_links.text
        assert 'Hidden linked speaker' not in enabled_links.text and 'Director linked speaker' not in enabled_links.text
        assert 'Private session topic' not in enabled_links.text
        enabled_data = json.loads(enabled_links.json()['result']['content'][0]['text'])['data']
        linked_context = next(a for a in enabled_data if a['title']=='Managed outside activity')['survey_context']
        linked_metadata = linked_context['resource_persons']
        assert linked_metadata['annual_summary_year']==2026 and not linked_metadata['truncated']
        assert linked_metadata['data'][0]['resource_person_id']==str(linked_people[0])
        assert linked_metadata['data'][0]['annual_report_url']==f'https://office.example/dashboard/people/{linked_people[0]}?period=year:2026'
        annual = client.post('/mcp',json={'jsonrpc':'2.0','id':191,'method':'tools/call',
            'params':{'name':'get_resource_person_survey_summary','arguments':{'resource_person_id':int(linked_metadata['data'][0]['resource_person_id']),'year':2026}}},headers=person_headers)
        assert not annual.json()['result'].get('isError'),annual.text
        assert 'no_matching_responses' in annual.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?',(mcp_auth._digest(person_grant.access_token),))
        conn.commit();conn.close()
        assert linked_call().status_code==401
        os.environ['CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED']='0'

        manager_warnings = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 22, 'method': 'tools/call',
            'params': {'name': 'list_supply_queue', 'arguments': {'queue': 'warnings'}}},
            headers=manager_headers)
        assert manager_warnings.status_code == 200 and not manager_warnings.json()['result'].get('isError')
        assert 'MCP-LOW' in manager_warnings.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? "
                     "WHERE user_id=? AND role='custodian'", (owner, manager))
        conn.commit(); conn.close()
        revoked_warnings = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 23, 'method': 'tools/call',
            'params': {'name': 'list_supply_queue', 'arguments': {'queue': 'warnings'}}},
            headers=manager_headers)
        assert revoked_warnings.status_code == 200 and revoked_warnings.json()['result'].get('isError')
        assert 'MCP-LOW' not in revoked_warnings.text
        overview = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 20, 'method': 'tools/call',
            'params': {'name': 'my_office_overview', 'arguments': {}}}, headers=headers)
        assert overview.status_code == 200 and not overview.json()['result'].get('isError'), overview.text
        assert 'My synthetic travel' in overview.text
        assert 'Other private travel' not in overview.text
        assert 'Other hidden activity' not in overview.text
        calendar = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 10, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-24', 'scope': 'bureau'}}}, headers=headers)
        assert calendar.status_code == 200 and not calendar.json()['result'].get('isError'), calendar.text
        assert 'Visible synthetic meeting' in calendar.text
        assert 'Hidden synthetic meeting' not in calendar.text
        assert 'private.example' not in calendar.text
        assert 'Approved shared room booking' in calendar.text
        assert 'My pending room request' in calendar.text, calendar.text
        assert 'Another private pending room request' not in calendar.text
        assert 'room_booking_status' in calendar.text and 'approved' in calendar.text
        own_calendar = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 14, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-24', 'scope': 'mine'}}}, headers=headers)
        assert own_calendar.status_code == 200 and not own_calendar.json()['result'].get('isError')
        assert 'My pending room request' in own_calendar.text
        assert 'Approved shared room booking' not in own_calendar.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('DELETE FROM calendar_entry_person WHERE entry_id=? AND user_id=?',
                     (visible_event, owner))
        conn.execute("UPDATE room_reservation SET status='withdrawn' WHERE id=?", (own_pending_room,))
        conn.commit(); conn.close()
        calendar_withdrawn = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 13, 'method': 'tools/call',
            'params': {'name': 'list_calendar_events', 'arguments': {
                'start_date': '2026-10-24', 'end_date': '2026-10-24', 'scope': 'bureau'}}}, headers=headers)
        assert calendar_withdrawn.status_code == 200 and not calendar_withdrawn.json()['result'].get('isError')
        assert 'Visible synthetic meeting' not in calendar_withdrawn.text
        assert 'My pending room request' not in calendar_withdrawn.text
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
        denied_notices = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 112, 'method': 'tools/call',
            'params': {'name': 'list_my_notifications', 'arguments': {}}}, headers=limited)
        assert denied_notices.status_code == 200 and denied_notices.json()['result'].get('isError')
        denied_csm = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 114, 'method': 'tools/call',
            'params': {'name': 'get_csm_summary', 'arguments': {'year': 2026, 'month': 10}}}, headers=limited)
        assert denied_csm.status_code == 200 and denied_csm.json()['result'].get('isError')
        conn = st.connect(os.environ['CSS_DB'])
        progress_only = mcp_auth.Provider._tokens(conn, client_id, owner, ['activities:read'], 'https://office.example/mcp')
        conn.commit(); conn.close()
        denied_survey = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 115, 'method': 'tools/call',
            'params': {'name': 'get_activity_survey_summary', 'arguments': {'year': 2026, 'quarter': 4}}},
            headers=dict(headers, Authorization='Bearer ' + progress_only.access_token))
        assert denied_survey.status_code == 200 and denied_survey.json()['result'].get('isError')
        conn = st.connect(os.environ['CSS_DB'])
        quarter_only = mcp_auth.Provider._tokens(conn, client_id, owner, ['surveys:activities:read'], 'https://office.example/mcp')
        conn.commit(); conn.close()
        for tool, arguments in (('find_survey_activities', {'year': 2026, 'quarter': 4}), ('get_activity_survey_detail', {'activity_id': 1})):
            rejected = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 118, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments}}, headers=dict(headers, Authorization='Bearer ' + quarter_only.access_token))
            assert rejected.status_code == 200 and rejected.json()['result'].get('isError')
            disabled_detail = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 119, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments}}, headers=headers)
            assert disabled_detail.status_code == 200 and 'not_available' in disabled_detail.text
        for tool, arguments in (('find_survey_units', {}), ('get_unit_activity_survey_summary', {'unit_id': unit, 'year': 2026, 'quarter': 4})):
            denied_unit = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 120, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments}}, headers=dict(headers, Authorization='Bearer ' + quarter_only.access_token))
            assert denied_unit.status_code == 200 and denied_unit.json()['result'].get('isError')
            disabled_unit = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 121, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments}}, headers=headers)
            assert disabled_unit.status_code == 200 and 'not_available' in disabled_unit.text
        # A unit-summary grant cannot silently gain trend access.
        conn = st.connect(os.environ['CSS_DB'])
        unit_only = mcp_auth.Provider._tokens(conn, client_id, owner, ['surveys:units:read'], 'https://office.example/mcp')
        conn.commit(); conn.close()
        trend_args = {'unit_id': unit, 'year': 2026, 'quarter': 4}
        denied_trend = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 123, 'method': 'tools/call',
            'params': {'name': 'compare_unit_activity_surveys', 'arguments': trend_args}},
            headers=dict(headers, Authorization='Bearer ' + unit_only.access_token))
        assert denied_trend.json()['result'].get('isError')
        disabled_trend = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 124, 'method': 'tools/call',
            'params': {'name': 'compare_unit_activity_surveys', 'arguments': trend_args}}, headers=headers)
        assert not disabled_trend.json()['result'].get('isError') and 'not_available' in disabled_trend.text
        os.environ['CSS_MCP_UNIT_TRENDS_ENABLED'] = '1'
        allowed_trend = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 125, 'method': 'tools/call',
            'params': {'name': 'compare_unit_activity_surveys', 'arguments': trend_args}}, headers=headers)
        assert not allowed_trend.json()['result'].get('isError') and 'not_comparable' in allowed_trend.text
        del os.environ['CSS_MCP_UNIT_TRENDS_ENABLED']
        conn = st.connect(os.environ['CSS_DB'])
        csm_only = mcp_auth.Provider._tokens(conn, client_id, owner, ['surveys:csm:read'], 'https://office.example/mcp')
        conn.commit(); conn.close()
        csm_trend_request = {'jsonrpc': '2.0', 'id': 126, 'method': 'tools/call',
            'params': {'name': 'compare_csm_months', 'arguments': {'year': 2026, 'month': 10}}}
        denied_csm_trend = client.post('/mcp', json=csm_trend_request,
            headers=dict(headers, Authorization='Bearer ' + csm_only.access_token))
        assert denied_csm_trend.json()['result'].get('isError')
        disabled_csm_trend = client.post('/mcp', json=csm_trend_request, headers=headers)
        assert not disabled_csm_trend.json()['result'].get('isError') and 'not_available' in disabled_csm_trend.text
        os.environ['CSS_MCP_CSM_TRENDS_ENABLED'] = '1'
        allowed_csm_trend = client.post('/mcp', json=csm_trend_request, headers=headers)
        assert not allowed_csm_trend.json()['result'].get('isError') and 'not_comparable' in allowed_csm_trend.text
        del os.environ['CSS_MCP_CSM_TRENDS_ENABLED']
        conn = st.connect(os.environ['CSS_DB'])
        person_only = mcp_auth.Provider._tokens(conn, client_id, owner, ['surveys:resource_persons:read'], 'https://office.example/mcp')
        conn.commit(); conn.close()
        for tool, arguments in (('find_survey_resource_persons', {'query': 'Synthetic owner'}), ('compare_resource_person_surveys', {'resource_person_id': owner_rp, 'year': 2026})):
            req = {'jsonrpc':'2.0','id':127,'method':'tools/call','params':{'name':tool,'arguments':arguments}}
            denied_person_trend = client.post('/mcp', json=req, headers=dict(headers, Authorization='Bearer ' + person_only.access_token))
            assert denied_person_trend.json()['result'].get('isError')
            disabled_person_trend = client.post('/mcp', json=req, headers=headers)
            assert not disabled_person_trend.json()['result'].get('isError') and 'not_available' in disabled_person_trend.text
            os.environ['CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED'] = '1'
            enabled_person_trend = client.post('/mcp', json=req, headers=headers)
            assert not enabled_person_trend.json()['result'].get('isError') and 'available' in enabled_person_trend.text
            del os.environ['CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED']
        os.environ['CSS_MCP_UNIT_SURVEYS_ENABLED'] = '1'
        for tool, arguments in (('find_survey_units', {'query': 'MCP Unit'}), ('get_unit_activity_survey_summary', {'unit_id': unit, 'year': 2026, 'quarter': 4})):
            allowed_unit = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 122, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments}}, headers=headers)
            assert allowed_unit.status_code == 200 and not allowed_unit.json()['result'].get('isError')
            assert 'available' in allowed_unit.text
        del os.environ['CSS_MCP_UNIT_SURVEYS_ENABLED']
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?', (mcp_auth._digest(quarter_only.access_token),))
        conn.commit(); conn.close()
        denied_person = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 116, 'method': 'tools/call',
            'params': {'name': 'get_resource_person_survey_summary', 'arguments': {'resource_person_id': owner_rp, 'year': 2026}}},
            headers=dict(headers, Authorization='Bearer ' + progress_only.access_token))
        assert denied_person.status_code == 200 and denied_person.json()['result'].get('isError')
        disabled_person = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 117, 'method': 'tools/call',
            'params': {'name': 'get_resource_person_survey_summary', 'arguments': {'resource_person_id': owner_rp, 'year': 2026}}}, headers=headers)
        assert disabled_person.status_code == 200 and 'not_available' in disabled_person.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?', (mcp_auth._digest(progress_only.access_token),))
        conn.commit(); conn.close()
        for tool, arguments in (('list_my_notifications', {}), ('get_room_availability', {'day': '2026-10-27'}), ('get_csm_summary', {'year': 2026, 'month': 10}), ('get_activity_survey_summary', {'year': 2026, 'quarter': 4})):
            disabled = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 113, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments}}, headers=headers)
            assert disabled.status_code == 200 and not disabled.json()['result'].get('isError'), disabled.text
            assert 'not_available' in disabled.text
        limited_overview = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 21, 'method': 'tools/call',
            'params': {'name': 'my_office_overview', 'arguments': {}}}, headers=limited)
        assert limited_overview.status_code == 200 and not limited_overview.json()['result'].get('isError')
        assert 'not_granted' in limited_overview.text
        assert 'My synthetic travel' not in limited_overview.text
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?',
                     (hashlib.sha256(work_only.access_token.encode()).hexdigest(),))
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?',
                     (hashlib.sha256(manager_grant.access_token.encode()).hexdigest(),))
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
        # Multiple grants can share a creation second; disconnect the token under
        # test rather than whichever active connection the UI happens to show first.
        conn = st.connect(os.environ['CSS_DB'])
        grant = conn.execute('SELECT id FROM mcp_oauth_grant WHERE access_hash=?',
                             (mcp_auth._digest(refreshed.json()['access_token']),)).fetchone()[0]
        conn.close()
        assert '/account/mcp/' + grant + '/revoke' in connections.text
        management_csrf = re.search(r'name="csrf" value="([^"]+)"', connections.text).group(1)
        disconnected = browser.post('/account/mcp/' + grant + '/revoke',
            data={'csrf': management_csrf},
            headers={'Origin': 'https://office.example'}, follow_redirects=False)
        assert disconnected.status_code == 303, disconnected.text
        stale = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'}, headers=headers)
        assert stale.status_code == 401
        # Reproduce a client requesting only work, despite registering all reads.
        # Optional consent must be explicit, and token/refresh must reflect it.
        for choose_calendar in (False, True):
            narrow = client.get('/authorize', params={
                'response_type': 'code', 'client_id': client_id, 'redirect_uri': callback,
                'code_challenge': challenge, 'code_challenge_method': 'S256',
                'resource': 'https://office.example/mcp', 'scope': 'work:read'}, follow_redirects=False)
            narrow_page = browser.get(narrow.headers['location'])
            assert narrow_page.status_code == 200
            assert '<li>Your visible work items and task status</li>' in narrow_page.text
            assert '<input type="checkbox" name="scope_calendar:read" value="1">' in narrow_page.text
            assert 'checked' not in narrow_page.text.replace('Unchecked', '')
            values = {key: re.search(r'name="' + key + r'" value="([^"]+)"', narrow_page.text).group(1)
                      for key in ('ticket', 'csrf')}
            values.update(decision='approve', password='Synthetic123!')
            if choose_calendar:
                values['scope_calendar:read'] = '1'
            consent = browser.post('/mcp-consent', data=values,
                headers={'Origin': 'https://office.example'}, follow_redirects=False)
            assert consent.status_code == 303, consent.text
            narrow_code = parse_qs(urlsplit(consent.headers['location']).query)['code'][0]
            token = client.post('/token', data={'grant_type': 'authorization_code', 'client_id': client_id,
                'code': narrow_code, 'code_verifier': verifier, 'redirect_uri': callback,
                'resource': 'https://office.example/mcp'})
            assert token.status_code == 200, token.text
            expected = {'work:read', 'calendar:read'} if choose_calendar else {'work:read'}
            assert set(token.json()['scope'].split()) == expected
            narrow_headers = dict(headers, Authorization='Bearer ' + token.json()['access_token'])
            calendar_call = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 100, 'method': 'tools/call',
                'params': {'name': 'list_calendar_events', 'arguments': {
                    'start_date': '2026-10-24', 'end_date': '2026-10-24'}}}, headers=narrow_headers)
            assert calendar_call.status_code == 200
            assert bool(calendar_call.json()['result'].get('isError')) == (not choose_calendar)
            rotated = client.post('/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
                'refresh_token': token.json()['refresh_token'], 'resource': 'https://office.example/mcp'})
            assert rotated.status_code == 200
            assert set(rotated.json()['scope'].split()) == expected

        # Legacy stored registrations must also offer choices, without changing grants.
        restricted = client.post('/register', json={
            'redirect_uris': [callback], 'client_name': 'Legacy ChatGPT', 'scope': 'work:read',
            'token_endpoint_auth_method': 'none', 'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code']})
        assert restricted.status_code == 201
        assert set(restricted.json()['scope'].split()) == scopes
        restricted_id = restricted.json()['client_id']
        import json
        conn = st.connect(os.environ['CSS_DB'])
        raw = conn.execute('SELECT metadata_json FROM mcp_oauth_client WHERE id=?', (restricted_id,)).fetchone()[0]
        legacy = json.loads(raw)
        legacy['scope'] = 'work:read'
        conn.execute('UPDATE mcp_oauth_client SET metadata_json=? WHERE id=?', (json.dumps(legacy), restricted_id))
        conn.commit(); conn.close()
        narrow = client.get('/authorize', params={
            'response_type': 'code', 'client_id': restricted_id, 'redirect_uri': callback,
            'code_challenge': challenge, 'code_challenge_method': 'S256',
            'resource': 'https://office.example/mcp', 'scope': 'work:read'}, follow_redirects=False)
        narrow_page = browser.get(narrow.headers['location'])
        assert 'name="scope_calendar:read"' in narrow_page.text
        assert 'name="scope_activities:read"' in narrow_page.text
        assert 'recreate the Office Connect app' not in narrow_page.text
        values = {key: re.search(r'name="' + key + r'" value="([^"]+)"', narrow_page.text).group(1)
                  for key in ('ticket', 'csrf')}
        values.update(decision='approve', password='Synthetic123!', **{'scope_calendar:write': '1'})
        forged = browser.post('/mcp-consent', data=values,
            headers={'Origin': 'https://office.example'}, follow_redirects=False)
        assert forged.status_code == 400, forged.text
        conn = st.connect(os.environ['CSS_DB'])
        assert conn.execute('SELECT COUNT(*) FROM mcp_oauth_code WHERE client_id=?', (restricted_id,)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM mcp_oauth_grant WHERE client_id=?', (restricted_id,)).fetchone()[0] == 0
        old_grant = mcp_auth.Provider._tokens(conn, restricted_id, owner, ['work:read'], 'https://office.example/mcp')
        conn.commit(); conn.close()
        # Separate approval scenario: reset the synthetic attempt limiter only.
        import ratelimit
        ratelimit.reset()
        del values['scope_calendar:write']
        values['scope_calendar:read'] = '1'
        consent = browser.post('/mcp-consent', data=values,
            headers={'Origin': 'https://office.example'}, follow_redirects=False)
        assert consent.status_code == 303, consent.text
        code = parse_qs(urlsplit(consent.headers['location']).query)['code'][0]
        token = client.post('/token', data={'grant_type': 'authorization_code', 'client_id': restricted_id,
            'code': code, 'code_verifier': verifier, 'redirect_uri': callback,
            'resource': 'https://office.example/mcp'})
        assert token.status_code == 200, token.text
        assert set(token.json()['scope'].split()) == {'work:read', 'calendar:read'}
        old_refresh = client.post('/token', data={'grant_type': 'refresh_token', 'client_id': restricted_id,
            'refresh_token': old_grant.refresh_token, 'resource': 'https://office.example/mcp'})
        assert old_refresh.status_code == 200
        assert old_refresh.json()['scope'] == 'work:read'
        browser.close()
