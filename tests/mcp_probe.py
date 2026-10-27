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
    conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?', (owner_rp, owner))
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
    earlier_person_form=st.create_form_instance(conn,survey_type=3,form='F3',event_date='2026-09-01',
        venue='A different activity',rp_id=linked_people[0])
    for selected_form,value in ((linked_forms[0],6),(earlier_person_form,2)):
        for _ in range(10):
            response=conn.execute('INSERT INTO response(form_instance_id,submitted_at) VALUES (?,?)',
                                   (selected_form,'2026-10-20')).lastrowid
            conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,0)',
                             [(response,k,v) for k,v in [('A',7),*[(f'B{i}',value) for i in range(1,10)],('C',3)]])


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
        scopes = {'surveys:person_activities:read', 'surveys:resource_person_trends:read', 'surveys:csm_trends:read', 'surveys:unit_trends:read', 'surveys:units:read', 'activities:read', 'calendar:read', 'documents:read',
                  'supplies:read', 'travel:read', 'work:read', 'notifications:read', 'surveys:csm:read', 'surveys:activities:read', 'surveys:resource_persons:read', 'surveys:activity_details:read'}
        assert set(metadata.json()['scopes_supported']) == scopes | {'notifications:mark_read', 'supplies:request:draft', 'work:comment:draft', 'reports:view:save', 'calendar:entry:create', 'travel:filing:draft', 'work:task:acknowledge', 'work:task:submit', 'supplies:request:submit', 'travel:review:request', 'travel:filing:submit', 'rooms:request', 'meals:request', 'work_arrangements:request', 'activities:dates:update', 'activities:draft:save', 'activities:draft:create', 'activities:announcement:publish', 'work:task:accept', 'supplies:request:approve'}
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
        assert set(registered.json()['scope'].split()) == scopes | {'notifications:mark_read', 'supplies:request:draft', 'work:comment:draft', 'reports:view:save', 'calendar:entry:create', 'travel:filing:draft', 'work:task:acknowledge', 'work:task:submit', 'supplies:request:submit', 'travel:review:request', 'travel:filing:submit', 'rooms:request', 'meals:request', 'work_arrangements:request', 'activities:dates:update', 'activities:draft:save', 'activities:draft:create', 'activities:announcement:publish', 'work:task:accept', 'supplies:request:approve'}
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
        assert names == {'get_supply_approval_context', 'prepare_supply_request_approval', 'get_supply_approval_operation', 'get_task_acceptance_context', 'prepare_task_acceptance', 'get_task_acceptance_operation', 'get_activity_announcement_context', 'prepare_activity_announcement', 'get_activity_announcement_operation', 'get_activity_creation_context', 'prepare_activity_from_draft', 'get_activity_creation_operation', 'get_activity_draft_context', 'prepare_activity_draft', 'get_activity_draft_operation', 'get_activity_date_context', 'prepare_activity_date_update', 'get_activity_date_operation', 'get_my_work_arrangement_context', 'prepare_work_arrangement_request', 'get_work_arrangement_operation', 'get_my_meal_request_context', 'prepare_meal_request', 'get_meal_request_operation', 'get_my_room_request_context', 'prepare_room_request', 'get_room_request_operation', 'get_my_travel_submission_context', 'prepare_travel_filing_submission', 'get_travel_submission_operation', 'get_my_travel_review_context', 'prepare_travel_review_request', 'get_travel_review_request_operation', 'prepare_supply_request_submission', 'get_supply_submission_operation', 'prepare_task_submission', 'get_task_submission_operation', 'prepare_task_acknowledgement', 'get_task_acknowledgement_operation', 'prepare_travel_reimbursement_draft', 'get_travel_draft_operation', 'prepare_personal_calendar_entry', 'get_personal_calendar_operation', 'prepare_saved_report_view', 'get_saved_report_view_operation', 'prepare_task_comment_draft', 'get_task_comment_draft_operation', 'prepare_supply_request_draft', 'get_supply_draft_operation', 'mark_my_notification_read', 'get_mcp_operation', 'get_resource_person_activity_survey', 'find_survey_resource_persons', 'compare_resource_person_surveys', 'compare_csm_months', 'compare_unit_activity_surveys', 'find_survey_units', 'get_unit_activity_survey_summary', 'my_work', 'find_documents', 'get_document',
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
        assert json.loads(annual.json()['result']['content'][0]['text'])['submissions']==20
        conn = st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?',(mcp_auth._digest(person_grant.access_token),))
        conn.commit();conn.close()
        assert linked_call().status_code==401
        os.environ['CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED']='0'
        conn=st.connect(os.environ['CSS_DB'])
        old_annual_grant=mcp_auth.Provider._tokens(conn,client_id,manager,
            ['surveys:resource_persons:read'],'https://office.example/mcp')
        scoped_person_grant=mcp_auth.Provider._tokens(conn,client_id,manager,
            ['surveys:person_activities:read'],'https://office.example/mcp')
        conn.commit();conn.close()
        scoped_headers=dict(headers,Authorization='Bearer '+scoped_person_grant.access_token)
        def activity_person_call(selected_headers,person_id=linked_people[0]):
            return client.post('/mcp',json={'jsonrpc':'2.0','id':192,'method':'tools/call',
                'params':{'name':'get_resource_person_activity_survey','arguments':{
                    'activity_id':int(linked_context['activity_id']),'resource_person_id':person_id}}},headers=selected_headers)
        # An old activities/annual grant must not gain the new activity-scoped read.
        assert activity_person_call(manager_headers).json()['result'].get('isError')
        old_annual_headers=dict(headers,Authorization='Bearer '+old_annual_grant.access_token)
        denied_old_annual=activity_person_call(old_annual_headers)
        assert denied_old_annual.json()['result'].get('isError') and 'surveys:person_activities:read' in denied_old_annual.text
        os.environ['CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED']='0'
        disabled=activity_person_call(scoped_headers)
        assert not disabled.json()['result'].get('isError')
        assert 'disabled' in disabled.text and 'Visible linked speaker' not in disabled.text
        os.environ['CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED']='0'
        os.environ['CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED']='1'
        selected=activity_person_call(scoped_headers)
        assert not selected.json()['result'].get('isError'),selected.text
        score=json.loads(selected.json()['result']['content'][0]['text'])
        assert score['state']=='rated' and score['submissions']==10 and len(score['dimensions'])==5
        assert score['scope']=='one_resource_person_one_activity'
        assert score['web_url']==f'https://office.example/dashboard/people/{linked_people[0]}/activity/{min(linked_forms)}'
        assert activity_person_call(scoped_headers,linked_people[1]).json()['result'].get('isError')
        assert 'Hidden linked speaker' not in activity_person_call(scoped_headers,linked_people[1]).text
        annual_denied=client.post('/mcp',json={'jsonrpc':'2.0','id':193,'method':'tools/call',
            'params':{'name':'get_resource_person_survey_summary','arguments':{'resource_person_id':linked_people[0],'year':2026}}},headers=scoped_headers)
        assert annual_denied.json()['result'].get('isError')
        conn=st.connect(os.environ['CSS_DB'])
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1 WHERE access_hash=?',(mcp_auth._digest(scoped_person_grant.access_token),))
        conn.commit();conn.close()
        assert activity_person_call(scoped_headers).status_code==401
        os.environ['CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED']='0'


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
        # No optional grant, then each optional permission independently.
        for choice in range(22):
            (choose_calendar, choose_write, choose_supply, choose_comment, choose_view,
             choose_personal, choose_travel, choose_ack, choose_submit, choose_supply_submit,
             choose_review, choose_paper, choose_room, choose_meal, choose_wa, choose_dates, choose_activity_draft, choose_creation, choose_announcement, choose_accept, choose_supply_approval) = [choice == i for i in range(1, 22)]
            if choose_activity_draft or choose_creation:
                # A role change revokes sessions/grants: issue a current fixture
                # session BEFORE starting this case's fresh OAuth authorization.
                conn=st.connect(os.environ['CSS_DB'])
                conn.execute("UPDATE admin_user SET role='section_manager' WHERE id=?",(owner,));conn.commit()
                draft_actor=st.get_admin_user_by_id(conn,owner);conn.close()
                browser.cookies.set(auth.COOKIE_NAME,app._issue_session(draft_actor))
            # Each case tests a separate authorization choice, not rate limits.
            import ratelimit
            ratelimit.reset()
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
            if choose_write:
                values['scope_notifications:mark_read'] = '1'
            if choose_supply:
                values['scope_supplies:request:draft'] = '1'
            if choose_comment:
                values['scope_work:comment:draft'] = '1'
            if choose_view:
                values['scope_reports:view:save'] = '1'
            if choose_personal:
                values['scope_calendar:entry:create'] = '1'
            if choose_travel:
                values['scope_travel:filing:draft'] = '1'
            if choose_ack:
                values['scope_work:task:acknowledge'] = '1'
            if choose_submit:
                values['scope_work:task:submit'] = '1'
            if choose_supply_submit:
                values['scope_supplies:request:submit'] = '1'
            if choose_review:
                values['scope_travel:review:request'] = '1'
            if choose_paper:
                values['scope_travel:filing:submit'] = '1'
            if choose_room:
                values['scope_rooms:request'] = '1'
            if choose_meal:
                values['scope_meals:request'] = '1'
            if choose_wa:
                values['scope_work_arrangements:request'] = '1'
            if choose_dates:
                values['scope_activities:dates:update'] = '1'
            if choose_activity_draft:
                values['scope_activities:draft:save'] = '1'
            if choose_creation:
                values['scope_activities:draft:create'] = '1'
            if choose_announcement:
                values['scope_activities:announcement:publish'] = '1'
            if choose_accept:
                values['scope_work:task:accept'] = '1'
            if choose_supply_approval:
                values['scope_supplies:request:approve'] = '1'
            consent = browser.post('/mcp-consent', data=values,
                headers={'Origin': 'https://office.example'}, follow_redirects=False)
            assert consent.status_code == 303, consent.text
            narrow_code = parse_qs(urlsplit(consent.headers['location']).query)['code'][0]
            token = client.post('/token', data={'grant_type': 'authorization_code', 'client_id': client_id,
                'code': narrow_code, 'code_verifier': verifier, 'redirect_uri': callback,
                'resource': 'https://office.example/mcp'})
            assert token.status_code == 200, token.text
            expected = {'work:read', 'calendar:read'} if choose_calendar else {'work:read'}
            if choose_write:
                expected.add('notifications:mark_read')
            if choose_supply:
                expected.add('supplies:request:draft')
            if choose_comment:
                expected.add('work:comment:draft')
            if choose_view:
                expected.add('reports:view:save')
            if choose_personal:
                expected.add('calendar:entry:create')
            if choose_travel:
                expected.add('travel:filing:draft')
            if choose_ack:
                expected.add('work:task:acknowledge')
            if choose_submit:
                expected.add('work:task:submit')
            if choose_supply_submit:
                expected.add('supplies:request:submit')
            if choose_review:
                expected.add('travel:review:request')
            if choose_paper:
                expected.add('travel:filing:submit')
            if choose_room:
                expected.add('rooms:request')
            if choose_meal:
                expected.add('meals:request')
            if choose_wa:
                expected.add('work_arrangements:request')
            if choose_dates:
                expected.add('activities:dates:update')
            if choose_activity_draft:
                expected.add('activities:draft:save')
            if choose_creation:
                expected.add('activities:draft:create')
            if choose_announcement:
                expected.add('activities:announcement:publish')
            if choose_accept:
                expected.add('work:task:accept')
            if choose_supply_approval:
                expected.add('supplies:request:approve')
            assert set(token.json()['scope'].split()) == expected
            narrow_headers = dict(headers, Authorization='Bearer ' + token.json()['access_token'])
            calendar_call = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 100, 'method': 'tools/call',
                'params': {'name': 'list_calendar_events', 'arguments': {
                    'start_date': '2026-10-24', 'end_date': '2026-10-24'}}}, headers=narrow_headers)
            assert calendar_call.status_code == 200
            assert bool(calendar_call.json()['result'].get('isError')) == (not choose_calendar)
            if choose_write:
                # Full remote journey: real OAuth bearer -> MCP preview ->
                # browser confirmation -> receipt using the rotated token.
                previous_flags = {name: os.environ.get(name) for name in
                    ('CSS_MCP_NOTIFICATIONS_ENABLED', 'CSS_MCP_NOTIFICATION_WRITES_ENABLED')}
                for name in previous_flags:
                    os.environ[name] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                st.set_setting(conn, 'work.enabled', '1')
                st.set_setting(conn, 'documents.enabled', '1')
                write_case = conn.execute('INSERT INTO work_case(title,outcome,unit_id,creator_id,created_at,updated_at) '
                    'VALUES (?,?,?,?,?,?)', ('Synthetic notice work', 'Outcome', unit, owner, '2026-10-20', '2026-10-20')).lastrowid
                write_comment = conn.execute('INSERT INTO work_comment(case_id,author_id,created_at) VALUES (?,?,?)',
                    (write_case, other, '2026-10-20')).lastrowid
                conn.execute('INSERT INTO work_comment_revision VALUES (?,1,?,?)',
                    (write_comment, 'Private synthetic message body', '2026-10-20'))
                write_notice = conn.execute("INSERT INTO work_notice(comment_id,user_id,revision,reason,created_at) VALUES (?,?,1,'mention',?)",
                    (write_comment, owner, '2026-10-20')).lastrowid
                conn.commit()
                write_args = {'notification_id': write_notice, 'operation_id': 'remote-notice-write-operation-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 101, 'method': 'tools/call',
                    'params': {'name': 'mark_my_notification_read', 'arguments': write_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert preview['status'] == 'awaiting_confirmation'
                assert conn.execute('SELECT COUNT(*) FROM work_comment_read WHERE comment_id=?', (write_comment,)).fetchone()[0] == 0
                conn.close()
            if choose_supply:
                os.environ['CSS_MCP_SUPPLY_DRAFTS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                st.set_setting(conn, 'supplies.enabled', '1')
                stock_before = conn.execute('SELECT * FROM supply_stock_movement').fetchall()
                supply_count = conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0]
                conn.close()
                supply_args = {'purpose': 'Synthetic draft only', 'date_needed': '2026-11-02',
                    'lines': [{'item_id': item, 'requested_quantity': 2}], 'operation_id': 'remote-supply-draft-operation-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 103, 'method': 'tools/call',
                    'params': {'name': 'prepare_supply_request_draft', 'arguments': supply_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                supply_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert supply_preview['status'] == 'awaiting_confirmation'
                confirmation = browser.get(supply_preview['confirmation_url'])
                assert confirmation.status_code == 200, confirmation.text
                supply_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                         for name in ('csrf', 'preview_digest')}
                supply_confirm_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == supply_count
                conn.close()
            if choose_comment:
                os.environ['CSS_MCP_COMMENT_DRAFTS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                st.set_setting(conn, 'work.enabled', '1')
                st.set_setting(conn, 'documents.enabled', '1')
                comment_case = conn.execute('INSERT INTO work_case(title,outcome,unit_id,creator_id,created_at,updated_at) '
                    'VALUES (?,?,?,?,?,?)', ('Synthetic comment draft work', 'Outcome', unit, owner, '2026-10-20', '2026-10-20')).lastrowid
                comment_task = conn.execute('INSERT INTO work_task(case_id,title,expected_output,unit_id,creator_id,status,created_at,updated_at) '
                    'VALUES (?,?,?,?,?,?,?,?)', (comment_case, 'Synthetic task', 'An output', unit, owner, 'proposed', '2026-10-20', '2026-10-20')).lastrowid
                conn.commit()
                message_count = conn.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0]
                notice_count = conn.execute('SELECT COUNT(*) FROM work_notice').fetchone()[0]
                conn.close()
                comment_args = {'work_item_id': comment_case, 'task_id': comment_task,
                    'body': 'Synthetic private task draft', 'operation_id': 'remote-comment-draft-operation-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 105, 'method': 'tools/call',
                    'params': {'name': 'prepare_task_comment_draft', 'arguments': comment_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                comment_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert comment_preview['status'] == 'awaiting_confirmation'
                assert 'Synthetic private task draft' not in prepared.text
                confirmation = browser.get(comment_preview['confirmation_url'])
                assert confirmation.status_code == 200, confirmation.text
                comment_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                          for name in ('csrf', 'preview_digest')}
                comment_confirm_values['confirm'] = 'yes'
            if choose_view:
                os.environ['CSS_MCP_REPORT_VIEWS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                before_views = conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0]
                before_responses = conn.execute('SELECT COUNT(*) FROM response').fetchone()[0]
                conn.close()
                view_args = {'name': 'Synthetic saved CSM selection', 'report_type': 'csm_month',
                    'year': 2026, 'month': 9, 'operation_id': 'remote-report-view-operation-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 107, 'method': 'tools/call',
                    'params': {'name': 'prepare_saved_report_view', 'arguments': view_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                view_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert view_preview['status'] == 'awaiting_confirmation'
                confirmation = browser.get(view_preview['confirmation_url'])
                assert confirmation.status_code == 200, confirmation.text
                assert 'date_from=2026-09-01' in confirmation.text and 'date_to=2026-09-30' in confirmation.text
                view_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                       for name in ('csrf', 'preview_digest')}
                view_confirm_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == before_views
                conn.close()
            if choose_personal:
                os.environ['CSS_MCP_PERSONAL_CALENDAR_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                before_entries = conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0]
                before_outbox = conn.execute('SELECT COUNT(*) FROM calendar_outbox').fetchone()[0]
                conn.close()
                personal_args = {'title': 'Synthetic personal plan', 'start_date': '2026-11-02',
                    'start_time': '09:00', 'end_time': '10:00', 'note': 'Private synthetic planning note',
                    'operation_id': 'remote-personal-calendar-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 109, 'method': 'tools/call',
                    'params': {'name': 'prepare_personal_calendar_entry', 'arguments': personal_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                personal_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert personal_preview['status'] == 'awaiting_confirmation'
                assert 'Private synthetic planning note' not in prepared.text
                confirmation = browser.get(personal_preview['confirmation_url'])
                assert confirmation.status_code == 200 and '09:00 to 10:00' in confirmation.text, confirmation.text
                personal_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                           for name in ('csrf', 'preview_digest')}
                personal_confirm_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == before_entries
                conn.close()
            if choose_travel:
                os.environ['CSS_MCP_TRAVEL_DRAFTS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                before_filings = conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0]
                conn.close()
                travel_args = {'title': 'Synthetic reimbursement draft', 'start_date': '2026-10-14',
                    'end_date': '2026-10-16', 'dpo_no': 'DPO-SYNTHETIC', 'role': 'participant',
                    'answers': {'flew': True}, 'operation_id': 'remote-travel-draft-operation-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 111, 'method': 'tools/call',
                    'params': {'name': 'prepare_travel_reimbursement_draft', 'arguments': travel_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                travel_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert travel_preview['status'] == 'awaiting_confirmation'
                assert 'DPO-SYNTHETIC' not in prepared.text
                confirmation = browser.get(travel_preview['confirmation_url'])
                assert confirmation.status_code == 200 and 'DPO-SYNTHETIC' in confirmation.text, confirmation.text
                assert 'Admin Unit' in confirmation.text and 'reminders' in confirmation.text
                travel_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                         for name in ('csrf', 'preview_digest')}
                travel_confirm_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == before_filings
                conn.close()
            if choose_ack:
                os.environ['CSS_MCP_TASK_ACKNOWLEDGEMENTS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                import work
                ack_case = work.create(conn, st.get_admin_user_by_id(conn, owner),
                    {'title': 'Synthetic acknowledgement work', 'outcome': 'Synthetic output', 'unit_id': unit})['id']
                ack_task = conn.execute('INSERT INTO work_task(case_id,title,expected_output,unit_id,creator_id,owner_id,status,created_at,updated_at) '
                    'VALUES (?,?,?,?,?,?,?,?,?)', (ack_case, 'Synthetic assigned task', 'An output', unit, owner, owner,
                    'todo', '2026-10-20', '2026-10-20')).lastrowid
                ack_revision = conn.execute('SELECT revision FROM work_task WHERE id=?', (ack_task,)).fetchone()[0]
                conn.commit()
                conn.close()
                ack_args = {'work_item_id': ack_case, 'task_id': ack_task, 'revision': ack_revision,
                    'reason': 'Synthetic shared progress note', 'operation_id': 'remote-task-acknowledgement-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 113, 'method': 'tools/call',
                    'params': {'name': 'prepare_task_acknowledgement', 'arguments': ack_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                ack_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert ack_preview['status'] == 'awaiting_confirmation'
                assert 'Synthetic shared progress note' not in prepared.text
                confirmation = browser.get(ack_preview['confirmation_url'])
                assert confirmation.status_code == 200 and 'Synthetic shared progress note' in confirmation.text, confirmation.text
                ack_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                      for name in ('csrf', 'preview_digest')}
                ack_confirm_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,revision FROM work_task WHERE id=?', (ack_task,)).fetchone() == ('todo', ack_revision)
                conn.close()
            if choose_submit:
                os.environ['CSS_MCP_TASK_SUBMISSIONS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                import work
                submission_case = work.create(conn, st.get_admin_user_by_id(conn, owner),
                    {'title': 'Synthetic submission work', 'outcome': 'Synthetic output', 'unit_id': unit})['id']
                submission_task = conn.execute('INSERT INTO work_task(case_id,title,expected_output,unit_id,creator_id,owner_id,status,created_at,updated_at) '
                    'VALUES (?,?,?,?,?,?,?,?,?)', (submission_case, 'Synthetic assigned output', 'An output', unit, owner, owner,
                    'in_progress', '2026-10-20', '2026-10-20')).lastrowid
                submission_revision = conn.execute('SELECT revision FROM work_task WHERE id=?', (submission_task,)).fetchone()[0]
                conn.commit()
                conn.close()
                submission_args = {'work_item_id': submission_case, 'task_id': submission_task, 'revision': submission_revision,
                    'reason': 'Synthetic review note', 'submission': 'Synthetic exact output and evidence',
                    'operation_id': 'remote-task-submission-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 115, 'method': 'tools/call',
                    'params': {'name': 'prepare_task_submission', 'arguments': submission_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                submission_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert submission_preview['status'] == 'awaiting_confirmation'
                assert 'Synthetic exact output and evidence' not in prepared.text
                confirmation = browser.get(submission_preview['confirmation_url'])
                assert confirmation.status_code == 200 and 'Synthetic exact output and evidence' in confirmation.text, confirmation.text
                assert 'In progress → For review' in confirmation.text
                submission_confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                             for name in ('csrf', 'preview_digest')}
                submission_confirm_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,revision FROM work_task WHERE id=?', (submission_task,)).fetchone() == ('in_progress', submission_revision)
                conn.close()
            if choose_supply_submit:
                os.environ['CSS_MCP_SUPPLY_SUBMISSIONS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                supply_target = conn.execute("SELECT id,revision FROM supply_request WHERE requester_id=? AND approval_status='draft' AND purpose='Synthetic draft only' ORDER BY id LIMIT 1", (owner,)).fetchone()
                assert supply_target
                submission_stock_before = conn.execute('SELECT * FROM supply_stock_movement').fetchall()
                submission_reservations_before = conn.execute('SELECT * FROM supply_reservation').fetchall()
                control_before = conn.execute('SELECT * FROM supply_sequence').fetchall()
                conn.close()
                supply_submit_args = {'request_id': supply_target[0], 'revision': supply_target[1],
                    'operation_id': 'remote-supply-submission-001'}
                prepared = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 117, 'method': 'tools/call',
                    'params': {'name': 'prepare_supply_request_submission', 'arguments': supply_submit_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                supply_submit_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert supply_submit_preview['status'] == 'awaiting_confirmation'
                assert 'Synthetic draft only' not in prepared.text
                confirmation = browser.get(supply_submit_preview['confirmation_url'])
                assert confirmation.status_code == 200 and 'Synthetic draft only' in confirmation.text, confirmation.text
                assert 'No eligible approver is configured' in confirmation.text
                supply_submit_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                        for name in ('csrf', 'preview_digest')}
                supply_submit_values['confirm'] = 'yes'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT approval_status,control_number FROM supply_request WHERE id=?', (supply_target[0],)).fetchone() == ('draft', None)
                assert conn.execute('SELECT * FROM supply_sequence').fetchall() == control_before
                conn.close()
            if choose_review:
                os.environ['CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED'] = '1'
                conn = st.connect(os.environ['CSS_DB'])
                import travel
                reviewer_uid = st.create_admin_user(conn, 'reviewer@example.invalid', hashed, salt, 'viewer', active=True)
                st.mark_onboarded(conn, reviewer_uid)
                admin_unit = st.add_org_unit(conn, 'Administrative Section', 'section', 'BLHSD/ADMIN')
                reviewer_rp = st.add_rp(conn, 'Synthetic reviewer', True, admin_unit)
                conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?', (reviewer_rp, reviewer_uid)); conn.commit()
                review_filing = travel.create_filing(conn, st.get_admin_user_by_id(conn, owner), kind='reimbursement',
                    source={'source_kind':'blank','title':'Synthetic papers to review','start':'2026-10-14','end':'2026-10-16','venue':'Palo'},
                    answers={}, role='participant', dpo_no='DPO-SYNTHETIC', today='2026-10-27')
                for review_item in travel.view_items(conn, review_filing):
                    conn.execute("UPDATE travel_item SET drive_url=?,doc_url=?,state='present' WHERE filing_id=? AND item_code=?",
                        ('https://docs.google.com/document/d/private/edit', 'https://docs.google.com/document/d/private/edit', review_filing['id'], review_item['code']))
                conn.commit(); conn.close()
                current = client.post('/mcp', json={'jsonrpc':'2.0','id':121,'method':'tools/call',
                    'params':{'name':'get_my_travel_review_context','arguments':{'filing_id':review_filing['id']}}}, headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                review_context=json.loads(current.json()['result']['content'][0]['text'])
                assert review_context['ready_to_request'] and 'reviewer@example.invalid' not in current.text
                assert str(reviewer_uid) in {r['id'] for r in review_context['reviewers']}
                review_args = {'filing_id':review_filing['id'], 'reviewer_id':reviewer_uid,
                    'expected_updated_at':review_context['expected_updated_at'], 'operation_id':'remote-travel-review-001'}
                prepared = client.post('/mcp', json={'jsonrpc':'2.0','id':119,'method':'tools/call',
                    'params':{'name':'prepare_travel_review_request','arguments':review_args}}, headers=narrow_headers)
                assert prepared.status_code == 200 and not prepared.json()['result'].get('isError'), prepared.text
                review_preview = json.loads(prepared.json()['result']['content'][0]['text'])
                assert review_preview['status'] == 'awaiting_confirmation' and 'Synthetic papers to review' not in prepared.text
                confirmation = browser.get(review_preview['confirmation_url'])
                assert confirmation.status_code == 200 and 'reviewer@example.invalid' in confirmation.text, confirmation.text
                review_values = {name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                review_values['confirm']='yes'
            if choose_paper:
                os.environ['CSS_MCP_TRAVEL_SUBMISSIONS_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                import travel_review
                approved=travel_review.approve(conn,travel.get_filing(conn,review_filing['id']),'reviewer@example.invalid')
                paper_filing=travel.mark_ready(conn,approved)
                paper_items_before=conn.execute('SELECT * FROM travel_item WHERE filing_id=?',(paper_filing['id'],)).fetchall()
                mail_before=conn.execute('SELECT * FROM mcp_travel_review_mail').fetchall()
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':122,'method':'tools/call',
                    'params':{'name':'get_my_travel_submission_context','arguments':{'filing_id':paper_filing['id']}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                paper_context=json.loads(current.json()['result']['content'][0]['text'])
                assert paper_context['ready_to_record'] and 'private/edit' not in current.text
                paper_args={'filing_id':paper_filing['id'],'expected_updated_at':paper_context['expected_updated_at'],
                            'operation_id':'remote-paper-submission-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':123,'method':'tools/call',
                    'params':{'name':'prepare_travel_filing_submission','arguments':paper_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                paper_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert paper_preview['status']=='awaiting_confirmation' and paper_preview['paper_handover_attested'] is None
                confirmation=browser.get(paper_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'physically handed in' in confirmation.text,confirmation.text
                paper_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                paper_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,submitted_at FROM travel_filing WHERE id=?',(paper_filing['id'],)).fetchone()==('ready',None)
                conn.close()
            if choose_room:
                os.environ['CSS_MCP_ROOM_REQUESTS_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                room_entry=st.cal_create(conn,'Synthetic MCP room meeting','2026-10-27',kind='meeting',status='tentative',
                    audience='people',people=[owner],start_time='09:00',end_time='10:00',by='mcp@example.invalid')
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':125,'method':'tools/call',
                    'params':{'name':'get_my_room_request_context','arguments':{'entry_id':room_entry}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                room_context=json.loads(current.json()['result']['content'][0]['text'])
                assert not room_context['has_live_request'] and room_context['expected_revision']
                room_args={'entry_id':room_entry,'expected_revision':room_context['expected_revision'],
                           'from_time':'09:00','to_time':'10:00','operation_id':'remote-linked-room-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':126,'method':'tools/call',
                    'params':{'name':'prepare_room_request','arguments':room_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                room_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert room_preview['status']=='awaiting_confirmation' and 'Synthetic MCP room meeting' not in prepared.text
                confirmation=browser.get(room_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'no booking' in confirmation.text,confirmation.text
                room_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                room_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert not conn.execute('SELECT 1 FROM room_reservation WHERE calendar_entry_id=?',(room_entry,)).fetchone()
                conn.close()
            if choose_meal:
                os.environ['CSS_MCP_MEAL_REQUESTS_ENABLED']='1'
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':128,'method':'tools/call',
                    'params':{'name':'get_my_meal_request_context','arguments':{}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                assert json.loads(current.json()['result']['content'][0]['text'])['earliest_day']=='2026-10-26'
                meal_args={'title':'Synthetic private meal request','day':'2026-10-27','venue':'Synthetic location',
                           'pax':25,'special_request':'Synthetic private instruction',
                           'meals':[{'meal':'lunch','deliver_at':'12:15'}],'operation_id':'remote-meal-request-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':129,'method':'tools/call',
                    'params':{'name':'prepare_meal_request','arguments':meal_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                meal_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert meal_preview['status']=='awaiting_confirmation' and 'Synthetic private' not in prepared.text
                confirmation=browser.get(meal_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Awaiting order' in confirmation.text,confirmation.text
                meal_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                meal_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==0
                conn.close()
            if choose_wa:
                os.environ['CSS_MCP_WORK_ARRANGEMENTS_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                chief_rp=st.add_rp(conn,'Synthetic filing approver',True,unit)
                conn.execute("UPDATE resource_person SET designation='Section Head' WHERE id=?",(chief_rp,));conn.commit()
                chief=st.create_admin_user(conn,'mcp-wa-chief@example.invalid',hashed,salt,'viewer',rp_id=chief_rp,active=True)
                st.mark_onboarded(conn,chief);conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':131,'method':'tools/call',
                    'params':{'name':'get_my_work_arrangement_context','arguments':{'period_start':'2026-11-01'}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                filing_context=json.loads(current.json()['result']['content'][0]['text'])
                assert filing_context['is_open'] and filing_context['initial_notice_recipient_count']==1
                filing_args={'period_start':'2026-11-01','arrangement':'REG','note':'Synthetic private filing note','operation_id':'remote-wa-filing-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':132,'method':'tools/call',
                    'params':{'name':'prepare_work_arrangement_request','arguments':filing_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                filing_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert filing_preview['status']=='awaiting_confirmation' and 'Synthetic private filing note' not in prepared.text
                confirmation=browser.get(filing_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic private filing note' in confirmation.text and 'mcp-wa-chief@example.invalid' in confirmation.text,confirmation.text
                filing_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                filing_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM work_arrangement').fetchone()[0]==0
                assert conn.execute('SELECT COUNT(*) FROM mcp_work_arrangement_mail').fetchone()[0]==0
                conn.close()
            if choose_dates:
                os.environ['CSS_MCP_ACTIVITY_DATES_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                date_form=st.create_form_instance(conn,2,'F2','2026-10-27',topic='Synthetic private date source',lead_org_id=unit,created_by='mcp@example.invalid')
                date_event=st.create_event(conn,'Synthetic private date source','2026-10-27',lead_org_id=unit,form_instance_ids=[date_form],created_by='mcp@example.invalid')
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':134,'method':'tools/call',
                    'params':{'name':'get_activity_date_context','arguments':{'event_token':date_event['event_token']}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                date_context=json.loads(current.json()['result']['content'][0]['text'])
                assert date_context['event_date']=='2026-10-27' and 'Synthetic private date source' not in current.text
                date_args={'event_id':int(date_context['event_id']),'expected_revision':date_context['expected_revision'],
                           'event_date':'2026-11-05','operation_id':'remote-activity-date-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':135,'method':'tools/call',
                    'params':{'name':'prepare_activity_date_update','arguments':date_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                date_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert date_preview['status']=='awaiting_confirmation' and 'Synthetic private date source' not in prepared.text
                confirmation=browser.get(date_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic private date source' in confirmation.text and '2026-11-05' in confirmation.text,confirmation.text
                date_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                date_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT event_date FROM event WHERE id=?',(date_event['id'],)).fetchone()[0]=='2026-10-27'
                conn.close()
            if choose_activity_draft:
                os.environ['CSS_MCP_ACTIVITY_DRAFTS_ENABLED']='1'
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':137,'method':'tools/call',
                    'params':{'name':'get_activity_draft_context','arguments':{}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                draft_context=json.loads(current.json()['result']['content'][0]['text'])
                assert any(s['id']==str(unit) for s in draft_context['sections'])
                draft_args={'activity_name':'Synthetic private activity draft','event_date':'2026-11-03','section_id':unit,
                            'venue':'Synthetic private draft venue','operation_id':'remote-private-activity-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':138,'method':'tools/call',
                    'params':{'name':'prepare_activity_draft','arguments':draft_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                activity_draft_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert activity_draft_preview['status']=='awaiting_confirmation' and 'Synthetic private activity draft' not in prepared.text
                confirmation=browser.get(activity_draft_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic private activity draft' in confirmation.text and 'Synthetic private draft venue' in confirmation.text,confirmation.text
                activity_draft_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                activity_draft_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                before_draft_counts=[conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('event','form_instance','attendee','response','calendar_entry','room_reservation')]
                assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==0
                conn.close()
            if choose_creation:
                import activity_drafts
                from documents_storage import transaction
                from uuid import uuid4
                os.environ['CSS_MCP_ACTIVITY_CREATION_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                with transaction(conn):
                    live_draft=activity_drafts.save_in_transaction(conn,st.get_admin_user_by_id(conn,owner),
                        {'activity_name':'Synthetic unpublished conversion','event_date':'2026-11-06','section_id':unit,'venue':'Synthetic public venue'},operation_key=str(uuid4()))
                initial_live_counts=[conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('event','form_instance','attendee','response')]
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':140,'method':'tools/call',
                    'params':{'name':'get_activity_creation_context','arguments':{'draft_key':live_draft['operation_key']}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                live_context=json.loads(current.json()['result']['content'][0]['text'])
                assert live_context['form_count']==1 and live_context['initial_notice_recipient_count']==2 and 'Synthetic unpublished conversion' not in current.text
                live_args={'draft_key':live_draft['operation_key'],'expected_revision':live_context['expected_revision'],'operation_id':'remote-live-creation-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':141,'method':'tools/call',
                    'params':{'name':'prepare_activity_from_draft','arguments':live_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                live_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert live_preview['status']=='awaiting_confirmation' and live_preview['public_url'] is None and 'Synthetic unpublished conversion' not in prepared.text
                confirmation=browser.get(live_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic unpublished conversion' in confirmation.text and 'public registration/feedback' in confirmation.text,confirmation.text
                live_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                live_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert [conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('event','form_instance','attendee','response')]==initial_live_counts
                conn.close()
            if choose_announcement:
                os.environ['CSS_MCP_ACTIVITY_ANNOUNCEMENTS_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                ann_form=st.create_form_instance(conn,2,'F2','2026-11-08',topic='Synthetic update review')
                ann_event=st.create_event(conn,'Synthetic pinned update activity','2026-11-08',form_instance_ids=[ann_form],created_by='mcp@example.invalid')
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':150,'method':'tools/call',
                    'params':{'name':'get_activity_announcement_context','arguments':{'event_token':ann_event['event_token']}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                ann_context=json.loads(current.json()['result']['content'][0]['text'])
                assert ann_context['registered_count']==0 and 'Synthetic pinned update activity' not in current.text
                ann_args={'event_id':int(ann_context['event_id']),'expected_revision':ann_context['expected_revision'],
                          'announcement':'Synthetic reviewed participant update','operation_id':'remote-pinned-update-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':151,'method':'tools/call',
                    'params':{'name':'prepare_activity_announcement','arguments':ann_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                ann_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert ann_preview['status']=='awaiting_confirmation' and 'Synthetic reviewed participant update' not in prepared.text
                confirmation=browser.get(ann_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic reviewed participant update' in confirmation.text,confirmation.text
                ann_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                ann_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert st.get_event(conn,ann_event['event_token'])['announcement'] is None
                conn.close()
            if choose_accept:
                import work_tasks
                os.environ['CSS_MCP_TASK_ACCEPTANCES_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                st.set_setting(conn,'documents.enabled','1');st.set_setting(conn,'work.enabled','1')
                conn.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-24')",(manager,unit));conn.commit()
                accept_lead=st.get_admin_user_by_id(conn,owner);accept_officer=st.get_admin_user_by_id(conn,manager);accept_contributor=st.get_admin_user_by_id(conn,other)
                accept_case=work.create(conn,accept_lead,{'title':'Synthetic acceptance work','outcome':'Reviewed contribution','unit_id':unit})
                accept_case=work.confirm_lead(conn,accept_officer,accept_case['id'],accept_case['revision'],owner,'Confirmed accountable lead')
                accept_task=work_tasks.create(conn,accept_lead,accept_case['id'],{'title':'Synthetic evidence contribution','expected_output':'Validated inputs','unit_id':unit,'proposed_owner_id':other})
                accept_task=work_tasks.mutate(conn,accept_officer,accept_case['id'],accept_task['id'],accept_task['revision'],'confirm',{'owner_id':other,'reason':'Confirm owner'})
                accept_task=work_tasks.mutate(conn,accept_contributor,accept_case['id'],accept_task['id'],accept_task['revision'],'acknowledge',{'reason':'Started work'})
                accept_task=work_tasks.mutate(conn,accept_contributor,accept_case['id'],accept_task['id'],accept_task['revision'],'submit',{'reason':'Ready for exact review','submission':'Synthetic saved acceptance evidence'})
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':160,'method':'tools/call',
                    'params':{'name':'get_task_acceptance_context','arguments':{'work_item_id':accept_case['id'],'task_id':accept_task['id']}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                accept_context=json.loads(current.json()['result']['content'][0]['text'])
                assert accept_context['result_status_if_confirmed']=='done' and 'Synthetic saved acceptance evidence' not in current.text
                accept_args={'work_item_id':accept_case['id'],'task_id':accept_task['id'],'revision':accept_context['revision'],
                             'expected_revision':accept_context['expected_revision'],'reason':'Synthetic reviewed acceptance decision','operation_id':'remote-task-acceptance-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':161,'method':'tools/call',
                    'params':{'name':'prepare_task_acceptance','arguments':accept_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                accept_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert accept_preview['status']=='awaiting_confirmation' and 'Synthetic reviewed acceptance decision' not in prepared.text
                confirmation=browser.get(accept_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic saved acceptance evidence' in confirmation.text and 'For review → Done' in confirmation.text,confirmation.text
                accept_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                accept_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,revision FROM work_task WHERE id=?',(accept_task['id'],)).fetchone()==('for_review',accept_task['revision'])
                conn.close()
            if choose_supply_approval:
                import supplies_requests as supply_requests
                import supplies
                from uuid import uuid4
                os.environ['CSS_MCP_SUPPLY_APPROVALS_ENABLED']='1'
                conn=st.connect(os.environ['CSS_DB'])
                st.set_setting(conn,'supplies.enabled','1')
                # A current independent module grant, not the operator's technical role.
                conn.execute("INSERT INTO supply_role_grant(user_id,role,unit_id,granted_by,created_at) VALUES (?,'request_approver',?,?,?)",(owner,unit,manager,'2026-10-24'));conn.commit()
                approval_requester_rp=st.add_rp(conn,'Synthetic independent approval requester',True,unit)
                conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(approval_requester_rp,other));conn.commit()
                supply_actor=st.get_admin_user_by_id(conn,other)
                supply_item=conn.execute("SELECT id FROM supply_item WHERE code='MCP-LOW'").fetchone()[0]
                approval_draft=supply_requests.save_draft(conn,supply_actor,
                    {'purpose':'Synthetic full approval purpose','date_needed':'2026-11-09','lines':[{'item_id':supply_item,'requested_quantity':3}]},operation_key=str(uuid4()))
                approval_request=supply_requests.submit(conn,supply_actor,approval_draft['id'],expected_revision=approval_draft['revision'],operation_key=str(uuid4()))
                conn.close()
                current=client.post('/mcp',json={'jsonrpc':'2.0','id':170,'method':'tools/call',
                    'params':{'name':'get_supply_approval_context','arguments':{'request_id':approval_request['id']}}},headers=narrow_headers)
                assert current.status_code==200 and not current.json()['result'].get('isError'),current.text
                approval_context=json.loads(current.json()['result']['content'][0]['text'])
                assert approval_context['line_count']==1 and 'Synthetic full approval purpose' not in current.text
                approval_args={'request_id':approval_request['id'],'revision':approval_context['revision'],
                               'expected_revision':approval_context['expected_revision'],'reason':'Synthetic scoped full approval','operation_id':'remote-supply-approval-001'}
                prepared=client.post('/mcp',json={'jsonrpc':'2.0','id':171,'method':'tools/call',
                    'params':{'name':'prepare_supply_request_approval','arguments':approval_args}},headers=narrow_headers)
                assert prepared.status_code==200 and not prepared.json()['result'].get('isError'),prepared.text
                approval_preview=json.loads(prepared.json()['result']['content'][0]['text'])
                assert approval_preview['status']=='awaiting_confirmation' and 'Synthetic scoped full approval' not in prepared.text
                confirmation=browser.get(approval_preview['confirmation_url'])
                assert confirmation.status_code==200 and 'Synthetic full approval purpose' in confirmation.text and '3 / 3 pieces' in confirmation.text,confirmation.text
                approval_values={name:re.search(r'name="'+name+r'" value="([^\"]+)"',confirmation.text).group(1) for name in ('csrf','preview_digest')}
                approval_values['confirm']='yes'
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT approval_status FROM supply_request WHERE id=?',(approval_request['id'],)).fetchone()[0]=='submitted'
                approval_movements=conn.execute('SELECT * FROM supply_stock_movement').fetchall()
                conn.close()
            rotated = client.post('/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
                'refresh_token': token.json()['refresh_token'], 'resource': 'https://office.example/mcp'})
            assert rotated.status_code == 200
            assert set(rotated.json()['scope'].split()) == expected
            if choose_write:
                confirmation = browser.get(preview['confirmation_url'])
                assert confirmation.status_code == 200, confirmation.text
                assert 'Private synthetic message body' not in confirmation.text
                confirm_values = {name: re.search(r'name="' + name + r'" value="([^\"]+)"', confirmation.text).group(1)
                                  for name in ('csrf', 'preview_digest')}
                confirm_values['confirm'] = 'yes'
                confirmed = browser.post(preview['confirmation_url'], data=confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Work notice marked read' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 102, 'method': 'tools/call',
                    'params': {'name': 'get_mcp_operation', 'arguments': {'operation_id': write_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['completed_at']
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT revision FROM work_comment_read WHERE comment_id=? AND user_id=?',
                    (write_comment, owner)).fetchone()[0] == 1
                conn.close()
                for name, previous in previous_flags.items():
                    if previous is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = previous

            if choose_supply:
                confirmed = browser.post(supply_preview['confirmation_url'], data=supply_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Supply request draft saved' in confirmed.text, confirmed.text
                recovery_args = {'name': 'get_supply_draft_operation', 'arguments': {'operation_id': supply_args['operation_id']}}
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 104, 'method': 'tools/call', 'params': recovery_args},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['draft']['saved_status'] == 'draft'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == supply_count + 1
                assert conn.execute('SELECT * FROM supply_stock_movement').fetchall() == stock_before
                assert conn.execute('SELECT approval_status,requester_id FROM supply_request WHERE id=?',
                    (receipt['draft']['id'],)).fetchone() == ('draft', owner)
                conn.close()
                os.environ.pop('CSS_MCP_SUPPLY_DRAFTS_ENABLED', None)

            if choose_comment:
                confirmed = browser.post(comment_preview['confirmation_url'], data=comment_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Private task comment draft saved' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 106, 'method': 'tools/call',
                    'params': {'name': 'get_task_comment_draft_operation', 'arguments': {'operation_id': comment_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['draft_id']
                assert 'Synthetic private task draft' not in recovered.text
                source = browser.get(receipt['web_url'])
                assert source.status_code == 200 and 'Synthetic private task draft' in source.text
                compose = browser.get(f'/work/{comment_case}/discussion',
                    params={'task_id': comment_task, 'draft_id': receipt['draft_id']})
                assert compose.status_code == 200 and 'Synthetic private task draft' in compose.text
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == message_count
                assert conn.execute('SELECT COUNT(*) FROM work_notice').fetchone()[0] == notice_count
                conn.close()
                os.environ.pop('CSS_MCP_COMMENT_DRAFTS_ENABLED', None)

            if choose_view:
                confirmed = browser.post(view_preview['confirmation_url'], data=view_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Personal report view saved' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 108, 'method': 'tools/call',
                    'params': {'name': 'get_saved_report_view_operation', 'arguments': {'operation_id': view_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['view_id']
                source = browser.get(receipt['web_url'])
                assert source.status_code == 200 and 'Synthetic saved CSM selection' in source.text
                assert 'date_from=2026-09-01' in source.text and 'date_to=2026-09-30' in source.text
                collection = browser.get('/reports/saved')
                assert collection.status_code == 200 and 'Synthetic saved CSM selection' in collection.text
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == before_views + 1
                assert conn.execute('SELECT COUNT(*) FROM response').fetchone()[0] == before_responses
                conn.close()
                os.environ.pop('CSS_MCP_REPORT_VIEWS_ENABLED', None)

            if choose_personal:
                confirmed = browser.post(personal_preview['confirmation_url'], data=personal_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Personal calendar entry saved' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 110, 'method': 'tools/call',
                    'params': {'name': 'get_personal_calendar_operation', 'arguments': {'operation_id': personal_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['entry_id']
                source = browser.get(receipt['web_url'])
                assert source.status_code == 200 and 'Synthetic personal plan' in source.text, source.text
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == before_entries + 1
                assert conn.execute('SELECT COUNT(*) FROM calendar_outbox').fetchone()[0] == before_outbox
                entry = st.cal_get(conn, int(receipt['entry_id']))
                assert entry['audience'] == 'people' and entry['status'] == 'tentative'
                assert [p['user_id'] for p in entry['people']] == [owner]
                conn.close()
                os.environ.pop('CSS_MCP_PERSONAL_CALENDAR_ENABLED', None)

            if choose_travel:
                confirmed = browser.post(travel_preview['confirmation_url'], data=travel_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Reimbursement draft opened' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 112, 'method': 'tools/call',
                    'params': {'name': 'get_travel_draft_operation', 'arguments': {'operation_id': travel_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['filing_id']
                source = browser.get(receipt['web_url'])
                assert source.status_code == 200 and 'Synthetic reimbursement draft' in source.text, source.text
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == before_filings + 1
                row = conn.execute('SELECT user_id,kind,status,gen_state,review_state,advance_amount,submitted_at FROM travel_filing WHERE id=?',
                                   (receipt['filing_id'],)).fetchone()
                assert row == (owner, 'reimbursement', 'open', 'idle', '', None, None)
                conn.close()
                os.environ.pop('CSS_MCP_TRAVEL_DRAFTS_ENABLED', None)

            if choose_ack:
                confirmed = browser.post(ack_preview['confirmation_url'], data=ack_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Task acknowledged' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 114, 'method': 'tools/call',
                    'params': {'name': 'get_task_acknowledgement_operation', 'arguments': {'operation_id': ack_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['result_status'] == 'in_progress'
                assert receipt['result_revision'] == ack_revision + 1 and receipt['next_actor']['user_id'] == str(owner)
                canonical = browser.get(receipt['api_receipt_url'])
                assert canonical.status_code == 200 and canonical.json()['id'] == receipt['api_operation_id'], canonical.text
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,revision FROM work_task WHERE id=?', (ack_task,)).fetchone() == ('in_progress', ack_revision + 1)
                assert conn.execute('SELECT COUNT(*) FROM work_api_operation WHERE operation_id=?', (receipt['api_operation_id'],)).fetchone()[0] == 1
                conn.close()
                os.environ.pop('CSS_MCP_TASK_ACKNOWLEDGEMENTS_ENABLED', None)

            if choose_submit:
                confirmed = browser.post(submission_preview['confirmation_url'], data=submission_confirm_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Task submitted for review' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 116, 'method': 'tools/call',
                    'params': {'name': 'get_task_submission_operation', 'arguments': {'operation_id': submission_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['result_status'] == 'for_review'
                assert receipt['result_revision'] == submission_revision + 1
                assert receipt['next_actor'] == {'role': 'work_item_lead_or_authorized_officer', 'lead_id': None, 'unit_id': str(unit)}
                assert 'Synthetic exact output and evidence' not in recovered.text
                canonical = browser.get(receipt['api_receipt_url'])
                assert canonical.status_code == 200 and canonical.json()['id'] == receipt['api_operation_id'], canonical.text
                assert canonical.json()['action'] == 'submit' and canonical.json()['result_status'] == 'for_review'
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,revision,submission FROM work_task WHERE id=?', (submission_task,)).fetchone() == (
                    'for_review', submission_revision + 1, submission_args['submission'])
                assert conn.execute('SELECT COUNT(*) FROM work_api_operation WHERE operation_id=?', (receipt['api_operation_id'],)).fetchone()[0] == 1
                conn.close()
                os.environ.pop('CSS_MCP_TASK_SUBMISSIONS_ENABLED', None)

            if choose_supply_submit:
                confirmed = browser.post(supply_submit_preview['confirmation_url'], data=supply_submit_values,
                    headers={'Origin': 'https://office.example'})
                assert confirmed.status_code == 200 and 'Supply request submitted for approval' in confirmed.text, confirmed.text
                recovered = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 118, 'method': 'tools/call',
                    'params': {'name': 'get_supply_submission_operation', 'arguments': {'operation_id': supply_submit_args['operation_id']}}},
                    headers=dict(headers, Authorization='Bearer ' + rotated.json()['access_token']))
                assert recovered.status_code == 200 and not recovered.json()['result'].get('isError'), recovered.text
                receipt = json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status'] == 'completed' and receipt['submitted']['approval_status'] == 'submitted'
                assert receipt['submitted']['revision'] == supply_target[1] + 1
                assert receipt['submitted']['control_number'] and receipt['next_actor']['routing_warning']
                assert 'Synthetic draft only' not in recovered.text
                source = browser.get(receipt['web_url'])
                assert source.status_code == 200 and receipt['submitted']['control_number'] in source.text, source.text
                conn = st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT * FROM supply_stock_movement').fetchall() == submission_stock_before
                assert conn.execute('SELECT * FROM supply_reservation').fetchall() == submission_reservations_before
                assert conn.execute("SELECT COUNT(*) FROM supply_operation WHERE operation_key=? AND action='request_submit'", (receipt['domain_operation_id'],)).fetchone()[0] == 1
                conn.close()
                os.environ.pop('CSS_MCP_SUPPLY_SUBMISSIONS_ENABLED', None)

            if choose_review:
                confirmed=browser.post(review_preview['confirmation_url'],data=review_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Travel review requested' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':120,'method':'tools/call',
                    'params':{'name':'get_travel_review_request_operation','arguments':{'operation_id':review_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['review_state']=='requested' and receipt['review_round']==1
                assert receipt['next_actor']['user_id']==str(reviewer_uid) and receipt['notification_status']=='queued'
                assert 'private/edit' not in recovered.text
                source=browser.get(receipt['web_url']);assert source.status_code==200,source.text
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM mcp_travel_review_mail').fetchone()[0]==1
                assert conn.execute('SELECT review_state,reviewer_id,review_round,status FROM travel_filing WHERE id=?',
                    (review_filing['id'],)).fetchone()==('requested',reviewer_uid,1,'open')
                conn.close();os.environ.pop('CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED',None)

            if choose_paper:
                confirmed=browser.post(paper_preview['confirmation_url'],data=paper_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Paper submission recorded' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':124,'method':'tools/call',
                    'params':{'name':'get_travel_submission_operation','arguments':{'operation_id':paper_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['recorded_status']=='submitted' and receipt['paper_handover_attested']
                assert receipt['next_actor']['user_id']==str(owner) and receipt['submitted_at']
                source=browser.get(receipt['web_url']);assert source.status_code==200 and 'Paper submission recorded' in source.text,source.text
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,review_state FROM travel_filing WHERE id=?',(paper_filing['id'],)).fetchone()==('submitted','approved')
                assert conn.execute('SELECT * FROM travel_item WHERE filing_id=?',(paper_filing['id'],)).fetchall()==paper_items_before
                assert conn.execute('SELECT * FROM mcp_travel_review_mail').fetchall()==mail_before
                conn.close();os.environ.pop('CSS_MCP_TRAVEL_SUBMISSIONS_ENABLED',None)

            if choose_room:
                confirmed=browser.post(room_preview['confirmation_url'],data=room_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Room request recorded' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':127,'method':'tools/call',
                    'params':{'name':'get_room_request_operation','arguments':{'operation_id':room_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['requested_status']=='requested' and receipt['booking_held'] is False
                source=browser.get(receipt['web_url']);assert source.status_code==200 and receipt['reference'] in source.text,source.text
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,requester_user_id,calendar_entry_id,meals_requested,standby FROM room_reservation WHERE id=?',
                    (receipt['room_request_id'],)).fetchone()==('requested',owner,room_entry,0,0)
                assert conn.execute('SELECT SUM(is_approved) FROM room_reservation_slot WHERE reservation_id=?',(receipt['room_request_id'],)).fetchone()[0]==0
                assert conn.execute('SELECT COUNT(*) FROM mcp_room_notice').fetchone()[0]==1
                conn.close();os.environ.pop('CSS_MCP_ROOM_REQUESTS_ENABLED',None)

            if choose_meal:
                confirmed=browser.post(meal_preview['confirmation_url'],data=meal_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Meal request submitted' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':130,'method':'tools/call',
                    'params':{'name':'get_meal_request_operation','arguments':{'operation_id':meal_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['submitted_status']=='submitted' and receipt['meal_status']=='pending'
                assert receipt['notification_status']=='none_created' and 'Synthetic private' not in recovered.text
                source=browser.get(receipt['web_url']);assert source.status_code==200 and 'Synthetic private meal request' in source.text,source.text
                assert browser.post(meal_preview['confirmation_url'],data=meal_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==1
                assert conn.execute('SELECT requester_user_id,status FROM meal_request').fetchone()==(owner,'submitted')
                assert conn.execute('SELECT meal,deliver_at,status FROM meal_request_item').fetchone()==('lunch','12:15','pending')
                conn.close();os.environ.pop('CSS_MCP_MEAL_REQUESTS_ENABLED',None)

            if choose_wa:
                confirmed=browser.post(filing_preview['confirmation_url'],data=filing_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Work arrangement filed' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':133,'method':'tools/call',
                    'params':{'name':'get_work_arrangement_operation','arguments':{'operation_id':filing_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['filed_status']=='pending' and receipt['notification_status_counts']=={'queued':1}
                assert 'Synthetic private filing note' not in recovered.text
                source=browser.get(receipt['web_url']);assert source.status_code==200 and 'Synthetic private filing note' in source.text,source.text
                assert browser.post(filing_preview['confirmation_url'],data=filing_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM work_arrangement').fetchone()[0]==1
                assert conn.execute('SELECT user_id,status,supersedes_id FROM work_arrangement').fetchone()==(owner,'pending',None)
                assert conn.execute('SELECT state FROM mcp_work_arrangement_mail').fetchone()==('queued',)
                conn.close();os.environ.pop('CSS_MCP_WORK_ARRANGEMENTS_ENABLED',None)

            if choose_dates:
                confirmed=browser.post(date_preview['confirmation_url'],data=date_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Activity date updated' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':136,'method':'tools/call',
                    'params':{'name':'get_activity_date_operation','arguments':{'operation_id':date_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['change_status']=='date_updated' and receipt['updated_forms']==1
                assert receipt['old_event_date']=='2026-10-27' and receipt['event_date']=='2026-11-05'
                assert 'Synthetic private date source' not in recovered.text
                source=browser.get(receipt['web_url']);assert source.status_code==200 and '2026-11-05' in source.text,source.text
                assert browser.post(date_preview['confirmation_url'],data=date_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT event_date FROM event WHERE id=?',(date_event['id'],)).fetchone()[0]=='2026-11-05'
                assert conn.execute('SELECT event_date FROM form_instance WHERE id=?',(date_form,)).fetchone()[0]=='2026-11-05'
                conn.close();os.environ.pop('CSS_MCP_ACTIVITY_DATES_ENABLED',None)

            if choose_activity_draft:
                confirmed=browser.post(activity_draft_preview['confirmation_url'],data=activity_draft_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Private activity draft saved' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':139,'method':'tools/call',
                    'params':{'name':'get_activity_draft_operation','arguments':{'operation_id':draft_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['saved_status']=='private_draft' and receipt['notification_status']=='none_created'
                assert 'Synthetic private activity draft' not in recovered.text and 'Synthetic private draft venue' not in recovered.text
                source=browser.get(receipt['web_url']);assert source.status_code==200 and 'Synthetic private activity draft' in source.text,source.text
                draft_key=urlsplit(receipt['web_url']).path.rsplit('/',1)[-1]
                loaded=browser.get('/create',params={'activity_draft':draft_key})
                assert loaded.status_code==200 and 'Loaded a private draft for review' in loaded.text and 'Synthetic private activity draft' in loaded.text,loaded.text
                assert browser.post(activity_draft_preview['confirmation_url'],data=activity_draft_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==1
                assert conn.execute('SELECT COUNT(*) FROM activity_draft_save').fetchone()[0]==1
                assert [conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('event','form_instance','attendee','response','calendar_entry','room_reservation')]==before_draft_counts
                conn.close();os.environ.pop('CSS_MCP_ACTIVITY_DRAFTS_ENABLED',None)

            if choose_creation:
                confirmed=browser.post(live_preview['confirmation_url'],data=live_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Live activity created' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':142,'method':'tools/call',
                    'params':{'name':'get_activity_creation_operation','arguments':{'operation_id':live_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['status']=='completed' and receipt['created_status']=='live_activity' and receipt['notification_status_counts']=={'queued':2}
                assert 'Synthetic unpublished conversion' not in recovered.text and 'mcp-wa-chief@example.invalid' not in recovered.text
                source=browser.get(receipt['web_url']);assert source.status_code==200 and 'Synthetic unpublished conversion' in source.text,source.text
                public=browser.get(receipt['public_url']);assert public.status_code==200 and 'Synthetic unpublished conversion' in public.text,public.text
                assert browser.post(live_preview['confirmation_url'],data=live_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert [conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('event','form_instance','attendee','response')]==[initial_live_counts[0]+1,initial_live_counts[1]+1,*initial_live_counts[2:]]
                assert conn.execute('SELECT COUNT(*) FROM activity_draft_creation').fetchone()[0]==1
                assert conn.execute('SELECT COUNT(*) FROM mcp_activity_creation_mail').fetchone()[0]==2
                conn.close();os.environ.pop('CSS_MCP_ACTIVITY_CREATION_ENABLED',None)

            if choose_announcement:
                confirmed=browser.post(ann_preview['confirmation_url'],data=ann_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Pinned update published' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':152,'method':'tools/call',
                    'params':{'name':'get_activity_announcement_operation','arguments':{'operation_id':ann_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['publication_status']=='published' and receipt['notification_status']=='none_created'
                assert 'Synthetic reviewed participant update' not in recovered.text
                assert browser.post(ann_preview['confirmation_url'],data=ann_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert st.get_event(conn,ann_event['event_token'])['announcement']=='Synthetic reviewed participant update'
                assert conn.execute('SELECT COUNT(*) FROM activity_announcement_publication').fetchone()[0]==1
                conn.close();os.environ.pop('CSS_MCP_ACTIVITY_ANNOUNCEMENTS_ENABLED',None)

            if choose_accept:
                confirmed=browser.post(accept_preview['confirmation_url'],data=accept_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Submitted task accepted' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':162,'method':'tools/call',
                    'params':{'name':'get_task_acceptance_operation','arguments':{'operation_id':accept_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['result_status']=='done' and receipt['result_revision']==accept_task['revision']+1
                assert 'Synthetic saved acceptance evidence' not in recovered.text and 'Synthetic reviewed acceptance decision' not in recovered.text
                assert browser.post(accept_preview['confirmation_url'],data=accept_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT status,revision FROM work_task WHERE id=?',(accept_task['id'],)).fetchone()==('done',accept_task['revision']+1)
                assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_accept'").fetchone()[0]==1
                assert work.raw(conn,accept_case['id'])['status']=='open'
                conn.close();os.environ.pop('CSS_MCP_TASK_ACCEPTANCES_ENABLED',None)

            if choose_supply_approval:
                confirmed=browser.post(approval_preview['confirmation_url'],data=approval_values,headers={'Origin':'https://office.example'})
                assert confirmed.status_code==200 and 'Supply request approved' in confirmed.text,confirmed.text
                recovered=client.post('/mcp',json={'jsonrpc':'2.0','id':172,'method':'tools/call',
                    'params':{'name':'get_supply_approval_operation','arguments':{'operation_id':approval_args['operation_id']}}},
                    headers=dict(headers,Authorization='Bearer '+rotated.json()['access_token']))
                assert recovered.status_code==200 and not recovered.json()['result'].get('isError'),recovered.text
                receipt=json.loads(recovered.json()['result']['content'][0]['text'])
                assert receipt['approval_status']=='approved' and receipt['result_revision']==approval_request['revision']+1
                assert 'Synthetic full approval purpose' not in recovered.text and 'Synthetic scoped full approval' not in recovered.text
                assert browser.post(approval_preview['confirmation_url'],data=approval_values,headers={'Origin':'https://office.example'}).status_code==200
                conn=st.connect(os.environ['CSS_DB'])
                assert conn.execute('SELECT COUNT(*) FROM supply_request_decision WHERE request_id=?',(approval_request['id'],)).fetchone()[0]==1
                reservation=conn.execute('SELECT reserved_quantity FROM supply_reservation WHERE request_id=?',(approval_request['id'],)).fetchone()[0]
                assert 0<=reservation<=3
                assert conn.execute('SELECT * FROM supply_stock_movement').fetchall()==approval_movements
                conn.close();os.environ.pop('CSS_MCP_SUPPLY_APPROVALS_ENABLED',None)

        # Start a new synthetic operator session after the consent matrix.
        import ratelimit
        ratelimit.reset()
        # Legacy stored registrations must also offer choices, without changing grants.
        restricted = client.post('/register', json={
            'redirect_uris': [callback], 'client_name': 'Legacy ChatGPT', 'scope': 'work:read',
            'token_endpoint_auth_method': 'none', 'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code']})
        assert restricted.status_code == 201
        assert set(restricted.json()['scope'].split()) == scopes | {'notifications:mark_read', 'supplies:request:draft', 'work:comment:draft', 'reports:view:save', 'calendar:entry:create', 'travel:filing:draft', 'work:task:acknowledge', 'work:task:submit', 'supplies:request:submit', 'travel:review:request', 'travel:filing:submit', 'rooms:request', 'meals:request', 'work_arrangements:request', 'activities:dates:update', 'activities:draft:save', 'activities:draft:create', 'activities:announcement:publish', 'work:task:accept', 'supplies:request:approve'}
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
