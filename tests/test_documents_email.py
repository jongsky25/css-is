"""Synthetic intake tests: no Gmail or Drive connection required."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import documents as d
import documents_email as email
import storage as st


@pytest.fixture
def setup(tmp_path,monkeypatch):
    path = str(tmp_path/'intake.db')
    conn = st.connect(path); st.init_db(conn)
    uid = st.create_admin_user(conn,'records@example.test','hash','salt','viewer',active=True)
    conn.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','2026-01-01')",(uid,))
    conn.commit()
    for key,value in [('enabled','1'),('gmail_intake_enabled','1'),('gmail_mailbox','office@example.test'),('gmail_actor_id',str(uid))]:
        st.set_setting(conn,'documents.'+key,value)
    monkeypatch.setenv('CSS_GMAIL_INTAKE_SECRET','test-only-secret-with-at-least-32-characters')
    app = FastAPI(); app.include_router(email.make_router(lambda:st.connect(path)))
    with TestClient(app) as client:
        yield conn,path,uid,client
    conn.close()


def payload():
    return {'mailbox':'office@example.test','message_id':'19abc123','subject':'Incoming memo',
            'sender':'Sender <sender@example.test>','received_at':'2026-10-17T10:00:00+08:00',
            'attachments':[{'attachment_id':'attachment1','drive_url':'https://drive.google.com/file/d/sourcefile12345/view'},
                           {'attachment_id':'attachment2','drive_url':'https://drive.google.com/file/d/sourcefile67890/view'}]}


def signed(client,data=None,ts=None,body=None):
    body = body if body is not None else json.dumps(data if data is not None else payload()).encode()
    ts = str(int(time.time()) if ts is None else ts)
    sig = hmac.new(b'test-only-secret-with-at-least-32-characters',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
    return client.post(email.PATH,content=body,headers={'x-css-timestamp':ts,'x-css-signature':sig})


def test_registration_replay_and_conflict(setup):
    c,path,uid,client = setup
    first = signed(client); assert first.status_code==201,first.text
    doc = d.raw(c,first.json()['document_id'])
    assert (doc['direction'],doc['verification'],doc['visibility'])==('IN','pending','preverification')
    assert doc['creator_id']==uid and doc['lead_id'] is None and doc['due_date'] is None
    assert c.execute('SELECT count(*) FROM document_file_version').fetchone()[0]==2
    assert signed(client).json()=={'document_id':doc['id'],'duplicate':True}
    changed=payload(); changed['subject']='Changed'
    assert signed(client,changed).status_code==409
    assert c.execute('SELECT count(*) FROM document').fetchone()[0]==1
    assert c.execute("SELECT count(*) FROM document_event WHERE action='gmail_imported'").fetchone()[0]==1


def test_concurrent_replay(setup):
    c,path,uid,client=setup
    def run(_):
        other=st.connect(path)
        try:return email.ingest(other,payload())
        finally:other.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run,range(4)))
    assert sum(not r['duplicate'] for r in results)==1
    assert len({r['document_id'] for r in results})==1


def test_authentication_and_bounds(setup,monkeypatch):
    c,path,uid,client=setup
    assert client.post(email.PATH,json=payload()).status_code==401
    assert signed(client,ts=int(time.time())-301).status_code==401
    assert signed(client,ts=int(time.time())+301).status_code==401
    assert signed(client,body=b'x'*(email.MAX_BODY+1)).status_code==413
    assert signed(client,body=b'{').status_code==400
    monkeypatch.delenv('CSS_GMAIL_INTAKE_SECRET')
    assert signed(client).status_code==401
    assert c.execute('SELECT count(*) FROM document').fetchone()[0]==0


@pytest.mark.parametrize('change',[
    {'attachments':[]},{'received_at':'2026-10-17T10:00:00'}, {'subject':''},
    {'actor_id':123},{'attachments':[{'attachment_id':'x','drive_url':'https://evil.test/file'}]},
    {'mailbox':'another@example.test'}])
def test_invalid_payloads_leave_no_records(setup,change):
    c,path,uid,client=setup
    data=payload();data.update(change)
    assert signed(client,data).status_code in (400,403)
    assert c.execute('SELECT count(*) FROM document').fetchone()[0]==0
    assert c.execute('SELECT count(*) FROM document_email_import').fetchone()[0]==0


def test_switches_and_revoked_account(setup):
    c,path,uid,client=setup
    st.set_setting(c,'documents.gmail_intake_enabled','0');st.init_db(c)
    assert signed(client).status_code==403
    st.set_setting(c,'documents.gmail_intake_enabled','1')
    st.set_setting(c,'documents.enabled','0');assert signed(client).status_code==400
    st.set_setting(c,'documents.enabled','1')
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(uid,));c.commit()
    assert signed(client).status_code==403
    c.execute('UPDATE admin_user SET active=1 WHERE id=?',(uid,))
    c.execute("UPDATE document_role_grant SET revoked_at='2026-10-17' WHERE user_id=?",(uid,));c.commit()
    assert signed(client).status_code==403


def test_atomic_failure_and_disabled_defaults(setup,monkeypatch,tmp_path):
    c,path,uid,client=setup
    def fail(*args,**kwargs):raise RuntimeError('Simulated failure after registration')
    monkeypatch.setattr(email,'event',fail)
    with pytest.raises(RuntimeError):email.ingest(c,payload())
    for table in ('document','document_email_import','document_file_version','document_sequence','document_event'):
        assert c.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
    other=st.connect(str(tmp_path/'fresh.db'));st.init_db(other);st.init_db(other)
    assert st.get_setting(other,'documents.gmail_intake_enabled')=='0'
    other.close()


def test_rules_cannot_route_imports_before_review(setup):
    c,path,uid,client=setup
    c.execute("INSERT INTO document_rule_version(name,body_json,state,actor_id,created_at) VALUES (?,?, 'active',?,'2026-01-01')",
              ('Automatic rule',json.dumps({'field':'subject','keywords':['memo'],'mode':'any','lead_id':uid,
               'policy':{'default_days':2,'anchor':'receipt'}}),uid));c.commit()
    result=signed(client); assert result.status_code==201,result.text
    doc=d.raw(c,result.json()['document_id'])
    assert doc['due_date'] is None and doc['lead_id'] is None
    assert c.execute('SELECT count(*) FROM document_assignment').fetchone()[0]==0


def test_real_app_auth_gate(setup,monkeypatch,tmp_path):
    import app
    import monitoring
    c,path,uid,_=setup
    monkeypatch.setattr(app,'DB',path)
    monkeypatch.setattr(monitoring,'LOG_PATH',str(tmp_path/'requests.log'))
    with TestClient(app.app) as client:
        assert client.post(email.PATH,json=payload()).status_code==401
        response=signed(client)
        assert response.status_code==201,response.text
        assert client.get('/documents',follow_redirects=False).status_code==303
        assert client.post(email.PATH+'/extra',json=payload()).status_code==401


def test_signature_is_bound_to_body(setup):
    c,path,uid,client=setup
    ts=str(int(time.time()))
    signature=hmac.new(b'test-only-secret-with-at-least-32-characters',ts.encode()+b'.{}',hashlib.sha256).hexdigest()
    assert client.post(email.PATH,json=payload(),headers={
        'x-css-timestamp':ts,'x-css-signature':signature}).status_code==401
    assert not email.authenticate(b'{}',ts,'é'*64)
