"""A20 delegated metadata reads never acquire browser or task-write authority."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import sqlite3
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

import auth
import documents as docs
import documents_permissions as permissions
import integration_access as access
import storage as st
from tests.conftest import PW,session_token
from tests.test_integration_read_api import api
from tests.test_work import workspace,case,document,propose,advance


@pytest.fixture
def connected(api):
    c,u,unit,clients,app = api
    hashed,salt=auth.hash_password(PW)
    for user,client in zip(u,clients):
        c.execute('UPDATE admin_user SET pw_hash=?,salt=? WHERE id=?',(hashed,salt,user['id']))
    c.commit()
    for i,client in enumerate(clients):
        u[i]=st.get_admin_user_by_id(c,u[i]['id'])
        client.cookies.set(auth.COOKIE_NAME,session_token(u[i]))
    return api


def mint(data,owner=0,scopes=('documents:read','work:read'),days=7,audience=None):
    c,u,unit,clients,app=data
    return access.issue(c,auth.parse_token(clients[owner].cookies.get(auth.COOKIE_NAME)),u[owner]['pw_hash'],
                        'Example tracker',list(scopes),days,audience or '["http","testserver",80,"/api/v1"]')


@contextmanager
def tool(data,token):
    client=TestClient(data[4].app,raise_server_exceptions=False)
    try:
        client.headers['Authorization']='Bearer '+token
        yield client
    finally:
        client.close()


def form(client):
    page=client.get('/account/integrations')
    assert page.status_code==200,page.text[:500]
    return re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]


def test_browser_consent_one_time_secret_hashed_storage_and_revocation(connected):
    c,u,unit,clients,app=connected
    client=clients[0]
    response=client.post('/account/integrations',data={'csrf':form(client),'name':'Tracker <private>',
        'scopes':['documents:read','work:read'],'days':'7','password':PW,'consent':'yes'})
    assert response.status_code==200,response.text[:600]
    assert response.headers['referrer-policy']=='same-origin' and 'no-store' in response.headers['cache-control']
    token=re.search(access.TOKEN_PATTERN,response.text)[0]; key=token[8:40]
    assert 'Tracker &lt;private&gt;' in response.text
    assert PW not in response.text and 'Set-Cookie' not in response.headers
    assert c.execute('SELECT secret_hash FROM integration_credential').fetchone()[0]==hashlib.sha256(token.encode()).hexdigest()
    assert token not in '\n'.join(c.iterdump())
    page=client.get('/account/integrations')
    assert token not in page.text and key in page.text and 'Active' in page.text
    with tool(connected,token) as reader:
        info=reader.get('/api/v1/').json()
        assert info['read_only'] and info['authentication']=='scoped_read_credential'
        assert reader.get('/api/v1/documents').status_code==200
        result=client.post(f'/account/integrations/{key}/revoke',data={'csrf':form(client)},follow_redirects=False)
        assert result.status_code==303
        assert reader.get('/api/v1/documents').status_code==401
    assert st.verify_audit_chain(c)==(True,None)


@pytest.mark.parametrize('scopes,allowed,denied',[(('documents:read',),'/documents','/work-items'),(('work:read',),'/work-items','/documents')])
def test_scopes_are_enforced_even_when_owner_can_read_both(connected,scopes,allowed,denied):
    token=mint(connected,scopes=scopes)
    c,u,unit,clients,app=connected
    document(c,u[0],unit); case(c,u[0],unit)
    with tool(connected,token) as reader:
        assert reader.get('/api/v1'+allowed).json()['data']
        response=reader.get('/api/v1'+denied)
        assert response.status_code==403 and response.json()['error']['code']=='insufficient_scope'
        assert reader.get('/api/v1/openapi.json').status_code==200


def test_current_linked_document_and_assignment_permissions_apply(connected):
    c,u,unit,clients,app=connected
    doc=document(c,u[0],unit)
    doc=docs.mutate(c,u[1],doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Checked'})
    item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[2]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[2]['id'])
    token=mint(connected,owner=2)
    with tool(connected,token) as reader:
        for path in (f"/documents/{doc['id']}",f"/work-items/{item['id']}/tasks/{task['id']}"):
            assert reader.get('/api/v1'+path).status_code==200
        docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Narrow'})
        for path in (f"/documents/{doc['id']}",f"/work-items/{item['id']}",f"/work-items/{item['id']}/tasks/{task['id']}"):
            response=reader.get('/api/v1'+path)
            assert response.status_code==404 and 'Correspondence' not in response.text
        assert not reader.get('/api/v1/work-items').json()['data']


def test_revoked_officer_grant_and_technical_admin_do_not_bypass_domain_rules(connected):
    c,u,unit,clients,app=connected
    item=case(c,u[0],unit)
    token=mint(connected,owner=1)
    with tool(connected,token) as reader:
        assert reader.get('/api/v1/work-items').json()['data']
        c.execute("UPDATE document_role_grant SET revoked_at='2026-10-22' WHERE user_id=?",(u[1]['id'],));c.commit()
        assert not reader.get('/api/v1/work-items').json()['data']
    with tool(connected,mint(connected,owner=4)) as admin_tool:
        assert admin_tool.get(f"/api/v1/work-items/{item['id']}").status_code==404


@pytest.mark.parametrize('field,value',[('username','renamed@example.test'),('pw_hash','changed'),('salt','changed'),
    ('role','encoder'),('active',0),('must_change',1),('bureau_access','read')])
def test_account_changes_permanently_revoke_credentials(connected,field,value):
    c,u,unit,clients,app=connected
    token=mint(connected)
    original=u[0][field]
    c.execute(f'UPDATE admin_user SET {field}=? WHERE id=?',(value,u[0]['id']));c.commit()
    with tool(connected,token) as reader:
        assert reader.get('/api/v1/').status_code==401
        c.execute(f'UPDATE admin_user SET {field}=? WHERE id=?',(original,u[0]['id']));c.commit()
        assert reader.get('/api/v1/').status_code==401
    assert c.execute('SELECT revoked_at FROM integration_credential').fetchone()[0] is not None


def test_directory_link_change_also_revokes_and_invalid_role_is_refused(connected):
    c,u,unit,clients,app=connected
    token=mint(connected)
    rp=c.execute("INSERT INTO resource_person(name,is_internal,org_unit_id) VALUES('Moved account',1,?)",(unit,)).lastrowid
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,u[0]['id']));c.commit()
    with tool(connected,token) as reader:
        assert reader.get('/api/v1/').status_code==401


def test_expiry_and_wrong_audience_refused_without_cookie_fallback(connected,monkeypatch):
    token=mint(connected)
    with tool(connected,token) as reader:
        assert reader.get('/api/v1/').status_code==200
        monkeypatch.setenv('CSS_BASE_URL','https://other.example')
        assert reader.get('/api/v1/').status_code==401
        monkeypatch.delenv('CSS_BASE_URL')
        issued=connected[0].execute('SELECT issued_at FROM integration_credential').fetchone()[0]
        monkeypatch.setattr(access.time,'time',lambda:issued+7*86400)
        assert reader.get('/api/v1/').status_code==401


@pytest.mark.parametrize('header',['Bearer bad','Basic user:password','Bearer oc_read_'+'a'*32+'.'+'b'*64,'Bearer x\u00e9'])
def test_invalid_authorization_never_uses_a_valid_browser_cookie(connected,header):
    response=connected[3][0].get('/api/v1/documents',headers={'Authorization':header}) if header.isascii() else None
    if response is not None:
        assert response.status_code==401 and 'no-store' in response.headers['cache-control']
    else:
        # ASGI can carry Latin-1 bytes which HTTP client header encoders disallow.
        from starlette.requests import Request
        request=Request({'type':'http','headers':[(b'authorization',header.encode('latin-1'))],'scheme':'http','server':('testserver',80),'path':'/'})
        with pytest.raises(access.InvalidCredential):access.authenticate(connected[0],request)


def test_valid_mixed_and_duplicate_identities_are_refused(connected):
    token=mint(connected)
    assert connected[3][0].get('/api/v1/',headers={'Authorization':'Bearer '+token}).status_code==401
    with tool(connected,token) as reader:
        assert reader.get('/api/v1/',headers=[('Authorization','Bearer '+token),('Authorization','Bearer '+token)]).status_code==401


def test_no_browser_api_write_context_or_receipt_authority_and_no_business_effects(connected):
    c,u,unit,clients,app=connected
    item=case(c,u[0],unit)
    task=propose(c,u[0],item,unit,u[2]['id']); task=advance(c,u[1],task,'confirm',owner_id=u[2]['id'])
    before=c.execute('SELECT COUNT(*) FROM work_event').fetchone()[0]
    with tool(connected,mint(connected,owner=2)) as reader:
        assert reader.get('/account/integrations',follow_redirects=False).status_code==303
        assert reader.get('/admin/integrations',follow_redirects=False).status_code==303
        for path in ('/write-context','/operations/'+str(uuid4()),'/unknown'):
            assert reader.get('/api/v1'+path).status_code==403
        for action in ('acknowledge','submit','accept','return','cancel'):
            response=reader.post(f"/api/v1/work-items/{item['id']}/tasks/{task['id']}/{action}",json={'revision':task['revision'],'reason':'Must not change'})
            assert response.status_code==403
        for method in ('HEAD','OPTIONS','PATCH','PUT','DELETE'):
            assert reader.request(method,'/api/v1/documents').status_code==403
    assert c.execute('SELECT status,revision FROM work_task WHERE id=?',(task['id'],)).fetchone()==('todo',task['revision'])
    assert c.execute('SELECT COUNT(*) FROM work_event').fetchone()[0]==before
    assert c.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM audit_log WHERE action="integration_read"').fetchone()[0]>=10


def test_audit_is_attributed_minimized_and_read_fails_closed_when_audit_fails(connected):
    c,u,unit,clients,app=connected
    doc=document(c,u[0],unit,subject='Very private subject')
    token=mint(connected,scopes=('documents:read',)); key=token[8:40]
    with tool(connected,token) as reader:
        assert reader.get('/api/v1/documents?q=Very%20private%20subject').status_code==200
        log=c.execute("SELECT actor,target_id,summary FROM audit_log WHERE action='integration_read'").fetchone()
        assert log[0]==u[0]['username'] and log[1]==key
        assert json.loads(log[2])=={'resource':'documents','method':'GET','status':200}
        assert token not in '\n'.join(c.iterdump())
        assert c.execute('SELECT last_used_at FROM integration_credential').fetchone()[0]
        c.execute("CREATE TRIGGER fail_integration_audit BEFORE INSERT ON audit_log WHEN NEW.action='integration_read' BEGIN SELECT RAISE(ABORT,'blocked audit'); END");c.commit()
        response=reader.get('/api/v1/documents')
        assert response.status_code==500 and doc['subject'] not in response.text
    assert st.verify_audit_chain(c)==(True,None)


def test_owner_and_admin_revocation_boundaries_and_rotation(connected):
    c,u,unit,clients,app=connected
    first=mint(connected); second=mint(connected); key=first[8:40]
    assert key not in clients[3].get('/account/integrations').text
    assert clients[3].post(f'/account/integrations/{key}/revoke',data={'csrf':form(clients[3])}).status_code==404
    assert clients[3].get('/admin/integrations').status_code==403
    admin_page=clients[4].get('/admin/integrations')
    assert key in admin_page.text and first not in admin_page.text
    csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',admin_page.text)[1]
    assert clients[4].post(f'/admin/integrations/{key}/revoke',data={'csrf':csrf},follow_redirects=False).status_code==303
    with tool(connected,first) as old, tool(connected,second) as replacement:
        assert old.get('/api/v1/').status_code==401
        assert replacement.get('/api/v1/').status_code==200
        # Ordinary logout does not silently turn a scheduled tool off.
        clients[0].post('/logout')
        assert replacement.get('/api/v1/').status_code==200
    assert st.verify_audit_chain(c)==(True,None)


@pytest.mark.parametrize('changes',[{'csrf':''},{'csrf':'é'},{'password':'wrong'},{'consent':''},{'scopes':['admin:write']},
    {'scopes':[]},{'scopes':['work:read','work:read']},{'days':'0'},{'days':'91'},{'name':' '},{'name':'x'*81},{'name':'a\nb'}])
def test_invalid_or_unconsented_issuance_never_mints_or_echoes_password(connected,changes):
    c,u,unit,clients,app=connected
    data={'csrf':form(clients[0]),'name':'Tracker','scopes':['work:read'],'days':'7','password':PW,'consent':'yes',**changes}
    response=clients[0].post('/account/integrations',data=data)
    assert response.status_code==400,response.text[:300]
    assert not c.execute('SELECT COUNT(*) FROM integration_credential').fetchone()[0]
    assert PW not in response.text


def test_hostile_origin_expired_session_body_limit_and_duplicate_fields_do_not_mint(connected):
    c,u,unit,clients,app=connected
    data={'csrf':form(clients[0]),'name':'Tracker','scopes':'work:read','days':'7','password':PW,'consent':'yes'}
    assert clients[0].post('/account/integrations',data=data,headers={'Origin':'https://hostile.example'}).status_code==403
    assert clients[0].post('/account/integrations',content=b'x'*8193).status_code==400
    assert clients[0].post('/account/integrations',content='csrf=x&csrf=y',headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==400
    st.revoke_login_session(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))['sid'])
    assert clients[0].post('/account/integrations',data=data).status_code==401
    assert c.execute('SELECT COUNT(*) FROM integration_credential').fetchone()[0]==0


def test_issue_rechecks_verified_password_session_and_limits_under_writer_lock(connected):
    c,u,unit,clients,app=connected
    for i in range(20):mint(connected)
    with pytest.raises(ValueError,match='20 active'):mint(connected)
    key=c.execute('SELECT id FROM integration_credential LIMIT 1').fetchone()[0]
    access.revoke(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)),key)
    mint(connected)
    with pytest.raises(access.InvalidCredential):
        access.issue(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)),'wrong','New',['work:read'],7,'audience')


def test_read_and_password_attempt_limits_and_no_audit_amplification(connected,monkeypatch):
    c,u,unit,clients,app=connected
    monkeypatch.setenv('CSS_RL_INTEGRATION_READ','1/60')
    with tool(connected,mint(connected)) as reader:
        assert reader.get('/api/v1/write-context').status_code==403
        for _ in range(3):
            response=reader.get('/api/v1/')
            assert response.status_code==429 and response.headers['retry-after']=='60'
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_read'").fetchone()[0]==1
    monkeypatch.setenv('CSS_RL_INTEGRATION_ISSUE','1/900')
    data={'csrf':form(clients[0]),'name':'Tracker','scopes':'work:read','days':'7','password':'bad','consent':'yes'}
    assert clients[0].post('/account/integrations',data=data).status_code==400
    assert clients[0].post('/account/integrations',data=data).status_code==429


def test_repeat_install_preserves_hashes_grants_revocation_and_audit(connected):
    c,u,unit,clients,app=connected
    token=mint(connected); key=token[8:40]
    original=c.execute('SELECT * FROM integration_credential').fetchone()
    st.init_db(c); st.init_db(c)
    assert c.execute('SELECT * FROM integration_credential').fetchone()==original
    with pytest.raises(sqlite3.IntegrityError):c.execute('UPDATE integration_credential SET scopes_json=? WHERE id=?',('["work:read"]',key))
    c.rollback()
    access.revoke(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)),key)
    with pytest.raises(sqlite3.IntegrityError):c.execute('UPDATE integration_credential SET revoked_at=NULL WHERE id=?',(key,))
    c.rollback()
    st.init_db(c)
    with tool(connected,token) as reader:assert reader.get('/api/v1/').status_code==401
    assert st.verify_audit_chain(c)==(True,None)


def test_issuance_and_revocation_roll_back_if_audit_storage_fails(connected):
    c,u,unit,clients,app=connected
    token=mint(connected); key=token[8:40]
    c.execute("CREATE TRIGGER fail_credential_audit BEFORE INSERT ON audit_log WHEN NEW.action IN ('integration_issue','integration_revoke') BEGIN SELECT RAISE(ABORT,'blocked audit'); END");c.commit()
    with pytest.raises(sqlite3.IntegrityError):mint(connected)
    with pytest.raises(sqlite3.IntegrityError):access.revoke(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)),key)
    assert c.execute('SELECT COUNT(*) FROM integration_credential').fetchone()[0]==1
    assert c.execute('SELECT revoked_at FROM integration_credential').fetchone()[0] is None


def test_paginated_credential_history_never_exposes_another_owner(connected):
    c,u,unit,clients,app=connected
    token=mint(connected); key=token[8:40]
    row=c.execute('SELECT owner_id,name,secret_hash,scopes_json,audience,issued_at,expires_at FROM integration_credential').fetchone()
    c.executemany('INSERT INTO integration_credential(id,owner_id,name,secret_hash,scopes_json,audience,issued_at,expires_at,revoked_at) VALUES(?,?,?,?,?,?,?,?,1)',
                  [(f'{i:032x}',*row) for i in range(105)]);c.commit()
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    page,before=access.listing(c,payload)
    next_page,last=access.listing(c,payload,before=before)
    assert len(page)==100 and len(next_page)==6 and last is None
    assert len({x['id'] for x in page+next_page})==106
    with pytest.raises(access.InvalidCredential):access.listing(c,auth.parse_token(clients[3].cookies.get(auth.COOKIE_NAME)),before=key)


def test_concurrent_reads_and_revocation_keep_audit_chain_and_next_request_denial(connected):
    c,u,unit,clients,app=connected
    token=mint(connected); key=token[8:40]
    def read(_):
        with tool(connected,token) as reader:return reader.get('/api/v1/').status_code
    with ThreadPoolExecutor(max_workers=3) as pool:assert list(pool.map(read,range(6)))==[200]*6
    access.revoke(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)),key)
    with tool(connected,token) as reader:assert reader.get('/api/v1/').status_code==401
    assert st.verify_audit_chain(c)==(True,None)


def test_boot_recovery_keeps_tool_grants_but_historical_restore_revokes_them(connected,tmp_path,monkeypatch):
    import backups as bk
    c,u,unit,clients,app=connected
    token=mint(connected);key=token[8:40]
    path=c.execute('PRAGMA database_list').fetchone()[2]
    bk.clear_restored_sessions(path)
    with tool(connected,token) as reader:assert reader.get('/api/v1/').status_code==200
    # Snapshot an active credential, then revoke it in live state. Restoring
    # that historical snapshot must not make the credential usable again.
    monkeypatch.setattr(bk,'SCHED_DIR',str(tmp_path/'snapshots'))
    snap=bk.make_backup(path,kind='manual')
    c.execute('UPDATE integration_credential SET revoked_at=1 WHERE id=?',(key,));c.commit()
    bk.restore_backup(snap['name'],path)
    with tool(connected,token) as reader:assert reader.get('/api/v1/').status_code==401
    assert c.execute('SELECT revoked_at FROM integration_credential WHERE id=?',(key,)).fetchone()[0] is not None


def test_secret_cannot_be_supplied_as_a_query_parameter(connected):
    token=mint(connected)
    with TestClient(connected[4].app,raise_server_exceptions=False) as client:
        response=client.get('/api/v1/documents',params={'access_token':token})
        assert response.status_code==401 and token not in response.text


def test_parallel_issuance_cannot_exceed_active_limit_and_old_sessions_cannot_issue(connected):
    c,u,unit,clients,app=connected
    for _ in range(19):mint(connected)
    path=c.execute('PRAGMA database_list').fetchone()[2]
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    def create(_):
        conn=st.connect(path)
        try:
            access.issue(conn,payload,u[0]['pw_hash'],'Concurrent tracker',['work:read'],7,'audience')
            return 'created'
        except ValueError:
            return 'refused'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(create,range(2)))==['created','refused']
    assert c.execute('SELECT COUNT(*) FROM integration_credential').fetchone()[0]==20
    st.revoke_login_session(c,payload['sid'])
    with pytest.raises(access.InvalidCredential):access.issue(c,payload,u[0]['pw_hash'],'No session',['work:read'],7,'audience')
