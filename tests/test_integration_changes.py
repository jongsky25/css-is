"""A21 atomic notices, private current authorization and durable resume behavior."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import pytest

import auth
import backups as bk
import documents as docs
import integration_access as access
import integration_changes as changes
import storage as st
from tests.test_integration_access import connected,api,workspace,mint,tool
from tests.test_work import case,document,propose,advance


def feed(client,resource='work-items',cursor='',limit=25,expected=200):
    response=client.get('/api/v1/changes',params={'resource':resource,'cursor':cursor,'limit':limit})
    assert response.status_code==expected,response.text
    assert 'no-store' in response.headers['cache-control']
    return response.json()


def test_start_now_then_replay_and_resume_atomic_domain_changes(connected):
    c,u,unit,clients,app=connected
    old=case(c,u[0],unit)
    client=clients[0]
    initial=feed(client)
    assert initial['initialized'] and not initial['data'] and not initial['has_more']
    checkpoint=initial['next_cursor']
    item=case(c,u[0],unit)
    task=propose(c,u[0],item,unit,u[2]['id'])
    page=feed(client,cursor=checkpoint)
    assert not page['initialized'] and not page['has_more']
    assert {x['type'] for x in page['data']}=={'work_item.changed','task.changed'}
    assert all(x['schema_version']=='1' and len(x['id'])==32 for x in page['data'])
    assert all(x['work_item_id']==str(item['id']) for x in page['data'])
    assert 'Consolidate' not in json.dumps(page) and 'expected_output' not in json.dumps(page)
    assert all(x['resource_id']!=str(old['id']) or x['type']=='task.changed' for x in page['data'])
    replay=feed(client,cursor=checkpoint)
    assert replay['data']==page['data']
    assert feed(client,cursor=page['next_cursor'])['data']==[]
    for notice in page['data']:
        current=client.get(notice['resource_url'])
        assert current.status_code==200 and current.json()['revision']>=notice['revision']
    assert len(checkpoint)==64 and checkpoint.isalnum()


def test_visible_pagination_skips_large_hidden_population_without_skips(connected):
    c,u,unit,clients,app=connected
    start=feed(clients[0])['next_cursor']
    first=case(c,u[0],unit)
    for _ in range(120):case(c,u[3],unit,title='Hidden private work')
    last=case(c,u[0],unit)
    page=feed(clients[0],cursor=start,limit=1)
    assert page['has_more'] and page['data'][0]['resource_id']==str(first['id'])
    next_page=feed(clients[0],cursor=page['next_cursor'],limit=1)
    assert not next_page['has_more'] and next_page['data'][0]['resource_id']==str(last['id'])
    assert 'Hidden' not in json.dumps(page)+json.dumps(next_page)
    after=next_page['next_cursor']
    case(c,u[3],unit)
    hidden_only=feed(clients[0],cursor=after)
    assert hidden_only['data']==[] and hidden_only['next_cursor']==after


def test_current_restricted_document_access_and_canonical_aliases_never_leak(connected):
    c,u,unit,clients,app=connected
    checkpoint=feed(clients[3],'documents')['next_cursor']
    doc=document(c,u[0],unit,subject='Confidential earlier subject')
    doc=docs.mutate(c,u[1],doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Verify'})
    visible=feed(clients[3],'documents',checkpoint)
    assert visible['data'] and all(x['resource_id']==str(doc['id']) for x in visible['data'])
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
    assert not feed(clients[3],'documents',checkpoint)['data']
    alias=document(c,u[0],unit,subject='Hidden obsolete receipt')
    c.execute('UPDATE document SET canonical_id=?,revision=revision+1 WHERE id=?',(doc['id'],alias['id']));c.commit()
    assert not feed(clients[3],'documents',checkpoint)['data']
    officer=feed(clients[1],'documents')['next_cursor']
    docs.mutate(c,u[1],doc['id'],doc['revision']+1,'access',{'visibility':'bureau','viewers':[],'reason':'Restore'})
    notices=feed(clients[1],'documents',officer)['data']
    assert notices and str(alias['id']) not in [x['resource_id'] for x in notices]


def test_linked_case_revocation_and_technical_admin_boundaries(connected):
    c,u,unit,clients,app=connected
    start=feed(clients[2])['next_cursor']
    doc=document(c,u[0],unit)
    doc=docs.mutate(c,u[1],doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Verify'})
    item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[2]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[2]['id'])
    assert feed(clients[2],cursor=start)['data']
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
    assert not feed(clients[2],cursor=start)['data']
    admin_start=feed(clients[4])['next_cursor']
    case(c,u[0],unit)
    assert not feed(clients[4],cursor=admin_start)['data']


def test_scoped_credentials_binding_revocation_and_current_audit(connected):
    c,u,unit,clients,app=connected
    token=mint(connected,scopes=('work:read',));replacement=mint(connected,scopes=('work:read',))
    with tool(connected,token) as reader,tool(connected,replacement) as other:
        checkpoint=feed(reader)['next_cursor']
        feed(reader,'documents',expected=403)
        assert reader.post('/api/v1/changes').status_code==403
        case(c,u[0],unit)
        assert feed(reader,cursor=checkpoint)['data']
        feed(other,cursor=checkpoint,expected=410)
        feed(clients[0],cursor=checkpoint,expected=410)
        log=c.execute("SELECT summary FROM audit_log WHERE action='integration_read' ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert json.loads(log)['resource']=='changes' and checkpoint not in log
        access.revoke(c,auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)),token[8:40])
        feed(reader,cursor=checkpoint,expected=401)


def test_owner_family_audience_expiry_and_malformed_checkpoints(connected,monkeypatch):
    c,u,unit,clients,app=connected
    key=feed(clients[0])['next_cursor']
    feed(clients[3],cursor=key,expected=410)
    feed(clients[0],'documents',key,expected=410)
    feed(clients[0],cursor='a'*64,expected=410)
    feed(clients[0],cursor='malformed-secret',expected=400)
    c.execute('UPDATE integration_checkpoint SET expires_at=0 WHERE id=?',(key,));c.commit()
    feed(clients[0],cursor=key,expected=410)
    key=feed(clients[0])['next_cursor']
    monkeypatch.setenv('CSS_BASE_URL','https://new.example')
    feed(clients[0],cursor=key,expected=410)


def test_notices_rollback_with_the_business_transaction_and_install_is_repeatable(connected):
    c,u,unit,clients,app=connected
    item=case(c,u[0],unit)
    before=c.execute('SELECT COUNT(*) FROM integration_change').fetchone()[0]
    c.execute('BEGIN IMMEDIATE')
    c.execute('UPDATE work_case SET revision=revision+1 WHERE id=?',(item['id'],))
    assert c.execute('SELECT COUNT(*) FROM integration_change').fetchone()[0]==before+1
    c.rollback()
    assert c.execute('SELECT COUNT(*) FROM integration_change').fetchone()[0]==before
    st.init_db(c);st.init_db(c)
    assert c.execute('SELECT COUNT(*) FROM integration_change').fetchone()[0]==before
    for sql in ('DELETE FROM integration_change','UPDATE integration_change SET revision=999'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(sql)
        c.rollback()


def test_failed_notice_storage_refuses_domain_write_and_failed_checkpoint_is_retryable(connected):
    c,u,unit,clients,app=connected
    checkpoint=feed(clients[0])['next_cursor']
    before=c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0]
    c.execute("CREATE TRIGGER fail_change BEFORE INSERT ON integration_change BEGIN SELECT RAISE(ABORT,'no notice'); END");c.commit()
    with pytest.raises(sqlite3.IntegrityError):case(c,u[0],unit)
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0]==before
    c.execute('DROP TRIGGER fail_change');c.commit()
    case(c,u[0],unit)
    c.execute("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON integration_checkpoint BEGIN SELECT RAISE(ABORT,'no checkpoint'); END");c.commit()
    feed(clients[0],cursor=checkpoint,expected=500)
    c.execute('DROP TRIGGER fail_checkpoint');c.commit()
    assert feed(clients[0],cursor=checkpoint)['data']


def test_normal_boot_preserves_checkpoint_historical_restore_invalidates_it(connected,tmp_path,monkeypatch):
    c,u,unit,clients,app=connected
    key=feed(clients[0])['next_cursor'];payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    path=c.execute('PRAGMA database_list').fetchone()[2]
    before=c.execute('SELECT epoch FROM integration_stream').fetchone()[0]
    # Routine boot preserves checkpoints, independently of browser re-login.
    bk.clear_restored_sessions(path)
    from tests.conftest import session_token
    clients[0].cookies.set(auth.COOKIE_NAME,session_token(u[0]))
    assert not feed(clients[0],cursor=key)['data']
    monkeypatch.setattr(bk,'SCHED_DIR',str(tmp_path/'backups'))
    snap=bk.make_backup(path,kind='manual');case(c,u[0],unit)
    bk.restore_backup(snap['name'],path)
    assert c.execute('SELECT epoch FROM integration_stream').fetchone()[0]!=before
    clients[0].cookies.set(auth.COOKIE_NAME,session_token(u[0]))
    feed(clients[0],cursor=key,expected=410)
    assert bk.db_marker(path)['integration_change']==0


@pytest.mark.parametrize('suffix',['?resource=unknown','?resource=work-items&limit=0','?resource=work-items&extra=private',
    '?resource=documents&resource=work-items','?resource=work-items&cursor='+('a'*65)])
def test_invalid_queries_are_generic_private_errors(connected,suffix):
    response=connected[3][0].get('/api/v1/changes'+suffix)
    assert response.status_code==400 and 'private' not in response.text


def test_rate_limit_and_concurrent_independent_checkpoints(connected,monkeypatch):
    c,u,unit,clients,app=connected
    monkeypatch.setenv('CSS_RL_INTEGRATION_READ','1/60')
    feed(clients[0]);feed(clients[0],expected=429)
    monkeypatch.setenv('CSS_RL_INTEGRATION_READ','120/60')
    token=mint(connected)
    with tool(connected,token) as reader:key=feed(reader)['next_cursor']
    case(c,u[0],unit)
    def consume(_):
        with tool(connected,token) as reader:return feed(reader,cursor=key)
    with ThreadPoolExecutor(max_workers=2) as pool:pages=list(pool.map(consume,range(2)))
    assert pages[0]['data']==pages[1]['data'] and pages[0]['next_cursor']==pages[1]['next_cursor']
    assert st.verify_audit_chain(c)==(True,None)


def test_independent_http_client_recovers_a_lost_response_with_the_saved_checkpoint(connected):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    from starlette.testclient import TestClient
    from examples.read_api import ReadClient,ApiFailure
    c,u,unit,clients,app=connected
    adapter=TestClient(app.app,raise_server_exceptions=False)
    state={'lose':False,'requests':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            state['requests']+=1
            response=adapter.get(base+self.path,headers={'Authorization':self.headers.get('Authorization','')},follow_redirects=False)
            if state['lose']:
                state['lose']=False
                self.send_response(502);self.end_headers();return
            self.send_response(response.status_code)
            for k,v in response.headers.items():
                if k.lower() not in ('content-length','content-encoding','connection','transfer-encoding'):
                    self.send_header(k,v)
            self.send_header('Content-Length',str(len(response.content)));self.end_headers();self.wfile.write(response.content)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    base=f'http://127.0.0.1:{server.server_port}'
    worker=Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);worker.start()
    token=mint(connected,audience=json.dumps(['http','127.0.0.1',server.server_port,'/api/v1'],separators=(',',':')))
    client=ReadClient(base+'/api/v1',credential=token)
    try:
        baseline=client.changes('work-items')['next_cursor']
        case(c,u[0],unit)
        state['lose']=True
        with pytest.raises(ApiFailure,match='HTTP 502'):client.changes('work-items',cursor=baseline)
        assert state['requests']==2
        first=client.changes('work-items',cursor=baseline)
        replay=client.changes('work-items',cursor=baseline)
        assert first['data'] and first['data']==replay['data']
        assert not client.changes('work-items',cursor=first['next_cursor'])['data']
    finally:
        server.shutdown();server.server_close();worker.join(timeout=2);adapter.close()


def test_local_inbox_commits_notices_and_checkpoint_together_and_deduplicates(connected,tmp_path):
    from examples.change_inbox import collect
    from examples.read_api import ReadClient
    c,u,unit,clients,app=connected
    token=mint(connected)
    with tool(connected,token) as reader:
        client=ReadClient('http://localhost/api/v1',credential=token)
        client.changes=lambda resource,**kw:feed(reader,resource,kw.get('cursor',''),kw.get('limit',25))
        path=str(tmp_path/'inbox.sqlite')
        assert collect(client,path,'work-items')['initialized']
        case(c,u[0],unit)
        local=sqlite3.connect(path)
        old=local.execute('SELECT cursor FROM state').fetchone()[0]
        local.execute("CREATE TRIGGER fail_save BEFORE INSERT ON state BEGIN SELECT RAISE(ABORT,'fail checkpoint'); END");local.commit()
        with pytest.raises(sqlite3.Error):collect(client,path,'work-items')
        assert local.execute('SELECT COUNT(*) FROM notice').fetchone()[0]==0
        assert local.execute('SELECT cursor FROM state').fetchone()[0]==old
        local.execute('DROP TRIGGER fail_save');local.commit()
        assert collect(client,path,'work-items')['received']>0
        count=local.execute('SELECT COUNT(*) FROM notice').fetchone()[0]
        local.execute('UPDATE state SET cursor=?',(old,));local.commit()
        collect(client,path,'work-items')
        assert local.execute('SELECT COUNT(*) FROM notice').fetchone()[0]==count
        assert not collect(client,path,'work-items')['received']
        with pytest.raises(ValueError):collect(client,path,'documents')
        local.close()
