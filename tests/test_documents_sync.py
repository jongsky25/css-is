"""Background admission, cross-process ownership and durable Drive retry contracts."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
import documents as d
import documents_external as external
import documents_intake as intake
import documents_jobs as jobs
import documents_sync as sync
from documents_storage import rows
from documents_workspace import WorkspaceError
import storage as st
import tzutil as tz
from tests.test_documents import registry
from tests.test_documents_intake import seed,fields,Drive
from tests.test_documents_routes import token


def filing(registry,count=1):
    c,u,unit,path=registry
    seed(registry,count)
    item=intake.claim(c,u[1],1,1)
    doc=intake.register(c,u[1],1,item['revision'],fields(),[(i,1) for i in range(2,count+1)],Drive())
    return doc


def item(c,i=1):
    return rows(c,'SELECT * FROM document_intake WHERE id=?',(i,))[0]


def expire(c):
    c.execute('UPDATE document_intake_sync SET lease_until=? WHERE id=1',(sync.later(-1),))
    c.execute("UPDATE document_intake SET filing_next_at=? WHERE filing_state='running'",(sync.later(-1),));c.commit()


def test_migration_preserves_registered_payloads_and_operations(registry):
    c,u,unit,path=registry;filing(registry)
    previous=item(c)
    c.execute('DROP INDEX document_intake_retry')
    for name in ('filing_attempts','filing_next_at','filing_last_at','filing_blocked'):
        c.execute('ALTER TABLE document_intake DROP COLUMN '+name)
    c.execute('DROP TABLE document_intake_sync');c.commit()
    st.init_db(c);st.init_db(c)
    assert item(c)==previous
    assert sync.state(c)['failures']==0


def test_separate_processes_share_one_discovery_filing_lease(registry):
    c,u,unit,path=registry;seed(registry)
    code='''import sys
import storage as st, documents_sync as sync
c=st.connect(sys.argv[1])
try:print('claimed' if sync.claim(c,manual=True) else 'busy')
finally:c.close()
'''
    def run(_):return subprocess.run([sys.executable,'-c',code,path],check=True,capture_output=True,text=True).stdout.strip()
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(results)==['busy','claimed']


def test_manual_requests_coalesce_and_do_not_overlap_automatic_work(registry):
    c,u,unit,path=registry;filing(registry)
    entered,release=threading.Event(),threading.Event()
    class Slow(Drive):
        def call(self,*args):
            entered.set();assert release.wait(5)
            return super().call(*args)
    def run():
        other=st.connect(path)
        try:return sync.sync(other,Slow(),manual=False)
        finally:other.close()
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(run)
        try:
            assert entered.wait(3)
            assert sync.sync(c,Drive(),manual=False) is False
            assert sync.request_check(c,u[1])=='running'
            assert sync.claim(c,manual=True,filing_only=True) is None
            with pytest.raises(d.Conflict):sync.retry_file(c,u[1],1)
            with pytest.raises(d.Conflict):intake.configure(c,u[1],{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
        finally:release.set()
        assert future.result(5)
    assert item(c)['filing_state']=='complete'


def test_stale_listing_cannot_replace_a_new_cursor_or_diagnostic(registry):
    c,u,unit,path=registry;seed(registry)
    class Superseded(Drive):
        def call(self,action,*args):
            assert action=='intake_list' and not c.in_transaction
            other=st.connect(path)
            try:
                expire(other)
                class Fresh(Drive):
                    def call(self,*args):return {'inbox':'inbox_folder_123','files':[],'next_cursor':'new-cursor'}
                sync.sync(other,Fresh())
            finally:other.close()
            return {'inbox':'inbox_folder_123','files':[],'next_cursor':'old-cursor'}
    with pytest.raises(d.Conflict):sync.sync(c,Superseded())
    assert intake.settings(c)['cursor']=='new-cursor'
    assert intake.settings(c)['sync_error']==''
    assert sync.state(c)['state']=='idle'


@pytest.mark.parametrize('late_error',[False,True])
def test_stale_filing_success_and_failure_cannot_overwrite_recovered_result(registry,late_error):
    c,u,unit,path=registry;doc=filing(registry)
    class Superseded(Drive):
        def call(self,action,payload,operation):
            assert action=='intake_file' and not c.in_transaction
            other=st.connect(path)
            try:
                expire(other)
                sync.sync(other,Drive(),filing_only=True)
            finally:other.close()
            if late_error:raise TimeoutError('private provider text')
            return super().call(action,payload,operation)
    with pytest.raises(d.Conflict):sync.sync(c,Superseded(),filing_only=True)
    assert item(c)['filing_state']=='complete' and not item(c)['error']
    assert c.execute("SELECT COUNT(*) FROM document_event WHERE document_id=? AND action='drive_filed'",(doc['id'],)).fetchone()[0]==1
    assert sync.state(c)['state']=='idle'


def test_actual_process_exit_after_remote_filing_reuses_exact_marker(registry,tmp_path):
    c,u,unit,path=registry;doc=filing(registry)
    receipt=tmp_path/'drive-receipt.json'
    code='''import json,os,sys
import storage as st,documents_sync as sync
class Crash:
 def call(self,action,payload,operation):
  assert action=='intake_file'
  with open(sys.argv[2],'w') as f:json.dump({'payload':payload,'operation':operation,'moves':1},f)
  os._exit(23)
c=st.connect(sys.argv[1]);sync.sync(c,Crash(),filing_only=True)
'''
    result=subprocess.run([sys.executable,'-c',code,path,str(receipt)],capture_output=True,text=True)
    assert result.returncode==23,result.stderr
    before=item(c)
    assert before['filing_state']=='running' and before['filing_attempts']==1
    assert sync.sync(c,Drive(),manual=False) is False
    expire(c)
    class Receipt(Drive):
        def call(self,action,payload,operation):
            assert not c.in_transaction
            record=json.loads(receipt.read_text())
            assert record['operation']==operation and record['payload']==payload and record['moves']==1
            return super().call(action,payload,operation)
    other=st.connect(path)
    try:assert sync.sync(other,Receipt(),manual=False,filing_only=True)
    finally:other.close()
    assert item(c)['filing_state']=='complete'
    assert item(c)['filing_operation']==before['filing_operation']
    assert item(c)['filing_payload']==before['filing_payload']
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1
    assert c.execute("SELECT COUNT(*) FROM document_event WHERE action='drive_filed'").fetchone()[0]==1
    assert json.loads(receipt.read_text())['moves']==1


def test_listing_backoff_limit_and_explicit_request_restart(registry,monkeypatch):
    c,u,unit,path=registry;seed(registry)
    clock=tz.now_local();monkeypatch.setattr(tz,'now_local',lambda:clock)
    class Down(Drive):
        def call(self,*args):self.calls.append(args);raise TimeoutError('private URL / token')
    drive=Down()
    for attempt in range(sync.MAX_ATTEMPTS):
        assert sync.sync(c,drive,manual=False)
        current=sync.state(c)
        assert current['failures']==attempt+1 and not current['lease_owner']
        assert not sync.sync(c,drive,manual=False)
        assert len(drive.calls)==attempt+1
        clock+=timedelta(hours=2)
    assert current['blocked']==1 and not current['next_check_at']
    assert 'private' not in intake.settings(c)['sync_error']
    assert sync.progress(c)['status']=='needs_review'
    sync.request_check(c,u[1]);assert sync.progress(c)['status']=='pending'
    sync.sync(c,Drive(),manual=False)
    assert sync.progress(c)['status']=='idle' and not intake.settings(c)['sync_error']


def test_filing_retry_backoff_limit_and_identity_survive_manual_retry(registry,monkeypatch):
    c,u,unit,path=registry;filing(registry)
    before=item(c);clock=tz.now_local();monkeypatch.setattr(tz,'now_local',lambda:clock)
    c.execute('UPDATE document_intake_sync SET next_check_at=?',(sync.later(86400),));c.commit()
    class Down(Drive):
        def call(self,*args):self.calls.append(args);raise TimeoutError('private')
    drive=Down()
    for attempt in range(sync.MAX_ATTEMPTS):
        sync.sync(c,drive,manual=False,filing_only=True)
        current=item(c)
        assert current['filing_attempts']==attempt+1
        assert not sync.sync(c,drive,manual=False,filing_only=True)
        clock+=timedelta(hours=2)
    assert len(drive.calls)==6 and current['filing_blocked']==1
    sync.retry_file(c,u[1],1)
    assert item(c)['filing_operation']==before['filing_operation']
    assert item(c)['filing_payload']==before['filing_payload']
    sync.sync(c,Drive(),manual=False)
    assert item(c)['filing_state']=='complete'
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1


@pytest.mark.parametrize('code',['version_changed','operation_conflict','bad_folder'])
def test_known_filing_conflict_requires_review_without_resetting_identity(registry,code):
    c,u,unit,path=registry;filing(registry)
    before=item(c)
    class Conflict(Drive):
        def call(self,*args):raise WorkspaceError(code,'provider credential text')
    sync.sync(c,Conflict(),filing_only=True)
    after=item(c)
    assert after['filing_state']=='error' and after['filing_blocked']==1
    assert after['filing_operation']==before['filing_operation']
    assert after['filing_payload']==before['filing_payload']
    assert 'credential' not in after['error']
    assert sync.due_file(c) is None


def test_automatic_turn_files_one_item_and_does_not_repeat_listing(registry):
    c,u,unit,path=registry;filing(registry,3)
    drive=Drive()
    for n in range(3):sync.sync(c,drive,manual=False)
    assert [x[0] for x in drive.calls]==['intake_list','intake_file','intake_file','intake_file']
    assert c.execute("SELECT COUNT(*) FROM document_intake WHERE filing_state='complete'").fetchone()[0]==3
    assert not sync.sync(c,drive,manual=False)


@pytest.mark.parametrize('when',['before','after'])
def test_original_actor_revocation_stops_filing_and_keeps_record(registry,when):
    c,u,unit,path=registry;filing(registry)
    # Keep the configured sync account distinct from the original filing actor.
    c.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','now')",(u[0]['id'],))
    value=item(c);payload=json.loads(value['filing_payload']);payload['actor_id']=u[0]['id']
    c.execute('UPDATE document_intake SET filing_payload=?',(json.dumps(payload),));c.commit()
    def revoke():
        c.execute("UPDATE document_role_grant SET revoked_at='now' WHERE user_id=? AND role='records'",(u[0]['id'],));c.commit()
    if when=='before':revoke()
    class Revoking(Drive):
        def call(self,*args):
            assert when=='after'
            revoke();return super().call(*args)
    sync.sync(c,Revoking(),filing_only=True)
    assert item(c)['filing_blocked']==1 and item(c)['filing_state']=='error'
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1


@pytest.mark.parametrize('kind',['request','settings','filing_retry'])
def test_expired_owner_is_fenced_when_an_authorized_user_requests_new_work(registry,kind):
    c,u,unit,path=registry;filing(registry)
    owner,_=sync.claim(c,manual=True);expire(c)
    if kind=='request':sync.request_check(c,u[1])
    elif kind=='settings':intake.configure(c,u[1],{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
    else:sync.retry_file(c,u[1],1)
    with pytest.raises(d.Conflict):sync.owned(c,owner)


@pytest.mark.parametrize('cancel',[False,True])
def test_background_timeout_or_cancellation_retains_capacity_for_actual_worker(cancel):
    runner=external.Runner(wait_seconds=.05)
    entered,release,finished=threading.Event(),threading.Event(),threading.Event()
    def slow():
        try:entered.set();assert release.wait(5)
        finally:finished.set()
    async def exercise():
        task=asyncio.create_task(runner.run(slow,background=True))
        assert await asyncio.to_thread(entered.wait,3)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        else:
            with pytest.raises(external.Unconfirmed):await task
        with pytest.raises(external.Busy):await runner.run(lambda:None,background=True)
        assert await runner.run(lambda:'interactive')=='interactive'
        release.set();assert await asyncio.to_thread(finished.wait,3)
    try:asyncio.run(exercise())
    finally:release.set();runner._pool.shutdown(wait=True)


def test_unified_scheduler_alternates_recovery_and_intake_without_starvation(registry,monkeypatch):
    c,u,unit,path=registry;seed(registry)
    called=[]
    monkeypatch.setattr(jobs,'recover_one',lambda factory:called.append('recovery') or 'operation')
    monkeypatch.setattr(sync,'sync',lambda conn,**kw:called.append('intake') or True)
    async def run(fn,*args):fn(*args)
    async def pause(seconds):
        assert seconds==sync.TICK_SECONDS
        if len(called)==4:raise asyncio.CancelledError()
    monkeypatch.setattr(external,'run_background',run)
    monkeypatch.setattr(asyncio,'sleep',pause)
    async def exercise():
        with pytest.raises(asyncio.CancelledError):await sync.worker(lambda:st.connect(path))
    asyncio.run(exercise())
    assert called==['recovery','intake','recovery','intake']


def test_sync_route_queues_durably_without_provider_io_and_checks_csrf(app_mod,viewer,admin,monkeypatch):
    c=app_mod.get_conn()
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)',(user['id'],role,'now'))
        c.commit()
        intake.configure(c,user,{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
        monkeypatch.setattr(intake.ops,'get_adapter',lambda:pytest.fail('request must not call provider'))
        page=viewer.get('/documents/intake');csrf=token(page)
        assert viewer.post('/documents/intake/sync',data={},follow_redirects=False).status_code==403
        assert admin.post('/documents/intake/sync',data={'csrf':token(admin.get('/documents/new'))},follow_redirects=False).status_code==403
        response=viewer.post('/documents/intake/sync',data={'csrf':csrf},follow_redirects=False)
        assert response.status_code==303
        assert sync.state(c)['state']=='pending' and not sync.state(c)['lease_owner']
        assert 'Drive check queued' in viewer.get('/documents/intake').text
    finally:c.close()


def test_filing_retry_route_requires_records_access_and_preserves_operation(app_mod,viewer,admin):
    c=app_mod.get_conn()
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)',(user['id'],role,'now'))
        c.commit()
        intake.configure(c,user,{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
        intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':[{'id':'sourcefile12345','name':'scan.pdf','fingerprint':'v1','content_key':'hash','mime_type':'application/pdf','size':10}]})
        claimed=intake.claim(c,user,1,1)
        doc=intake.register(c,user,1,claimed['revision'],fields(),adapter=Drive())
        c.execute("UPDATE document_intake SET filing_state='error',filing_blocked=1,filing_attempts=6");c.commit()
        before=item(c)
        page=viewer.get('/documents/intake?state=registered');csrf=token(page)
        assert 'Retry filing check' in page.text and 'needs review' in page.text
        url='/documents/intake/1/filing/retry'
        assert viewer.post(url,data={},follow_redirects=False).status_code==403
        assert admin.post(url,data={'csrf':token(admin.get('/documents/new'))},follow_redirects=False).status_code==403
        response=viewer.post(url,data={'csrf':csrf},follow_redirects=False)
        assert response.status_code==303
        assert item(c)['filing_operation']==before['filing_operation'] and item(c)['filing_payload']==before['filing_payload']
        assert item(c)['filing_attempts']==0 and item(c)['filing_blocked']==0
        assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1
    finally:c.close()


def test_shared_turn_budget_stops_additional_provider_calls(registry,monkeypatch):
    from types import SimpleNamespace
    import documents_workspace as workspace
    c,u,unit,path=registry;filing(registry)
    clock=[0]
    monkeypatch.setattr(workspace,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    class SlowListing(Drive):
        def call(self,action,*args):
            assert action=='intake_list'
            clock[0]=workspace.CALL_SECONDS+1
            return super().call(action,*args)
    drive=SlowListing()
    sync.sync(c,drive,manual=False)
    assert [x[0] for x in drive.calls]==['intake_list']
    assert item(c)['filing_state']=='pending' and item(c)['filing_attempts']==0
    assert sync.due_file(c)['id']==1
    assert workspace._CALL_DEADLINE.get() is None


def test_shared_budget_is_applied_to_real_workspace_transport(monkeypatch):
    from types import SimpleNamespace
    import httpx
    import documents_workspace as workspace
    clock=[10.0];budgets=[]
    monkeypatch.setattr(workspace,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setenv('CSS_DOCS_RELAY_URL','https://script.google.com/macros/s/synthetic/exec')
    monkeypatch.setenv('CSS_DOCS_RELAY_SECRET','synthetic-test-secret')
    def response(client,method,url,*,deadline,**kw):
        budgets.append(deadline-clock[0]);clock[0]+=50
        return httpx.Response(200,json={'operation_id':'operation','state':'confirmed'},request=httpx.Request('POST',url))
    monkeypatch.setattr(workspace,'_request',response)
    adapter=workspace.BudgetAdapter(workspace.WorkspaceRelay())
    adapter.call('intake_list',{},'operation');adapter.call('intake_list',{},'operation')
    assert budgets==[120,70]
    assert workspace._CALL_DEADLINE.get() is None


def test_registration_checks_share_a_budget_before_allocating_a_number(registry,monkeypatch):
    from types import SimpleNamespace
    import documents_workspace as workspace
    c,u,unit,path=registry;seed(registry,2)
    claimed=intake.claim(c,u[1],1,1)
    clock=[0];monkeypatch.setattr(workspace,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    class SlowCheck(Drive):
        def call(self,*args):
            clock[0]=workspace.CALL_SECONDS+1
            return super().call(*args)
    drive=SlowCheck()
    with pytest.raises(WorkspaceError,match='not confirm'):
        intake.register(c,u[1],1,claimed['revision'],fields(),[(2,1)],drive)
    assert len(drive.calls)==1
    assert not c.execute('SELECT 1 FROM document').fetchone()
    assert not c.execute('SELECT 1 FROM document_sequence').fetchone()


@pytest.mark.parametrize('action',['background','registration'])
def test_background_or_registration_stall_leaves_http_navigation_responsive(app_mod,viewer,monkeypatch,action):
    import httpx
    import time
    c=app_mod.get_conn()
    entered=threading.Event()
    runner=external.Runner()
    monkeypatch.setattr(external,'RUNNER',runner)
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        for role in ('records','workflow_admin'):
            c.execute('INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)',(user['id'],role,'now'))
        c.commit()
        intake.configure(c,user,{'enabled':'yes','inbox':'inbox_folder_123','filed':'filed_folder_123'})
        intake.discover(c,intake.settings(c),{'inbox':'inbox_folder_123','files':[{'id':'sourcefile12345','name':'scan.pdf','fingerprint':'v1','content_key':'hash','mime_type':'application/pdf','size':10}]})
        claimed=intake.claim(c,user,1,1)
        csrf=token(viewer.get('/documents/intake/1'))
        class Slow(Drive):
            def call(self,*args):
                entered.set();time.sleep(2)
                return super().call(*args)
        monkeypatch.setattr(intake.ops,'get_adapter',lambda:Slow())
        def background():
            other=app_mod.get_conn()
            try:sync.sync(other,Slow(),manual=False)
            finally:other.close()
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_mod.app),base_url='http://testserver',cookies=viewer.cookies,headers={'Origin':'http://testserver'}) as http:
                pending=asyncio.create_task(external.run_background(background) if action=='background' else
                    http.post('/documents/intake/1',data={'csrf':csrf,'action':'register','revision':claimed['revision'],**fields()}))
                try:
                    assert await asyncio.to_thread(entered.wait,3)
                    started=time.monotonic()
                    for url in ('/health','/documents/new'):
                        response=await asyncio.wait_for(http.get(url),1.5)
                        assert response.status_code==200
                    assert time.monotonic()-started<1.5 and not pending.done()
                    if action=='background':
                        assert await external.run(lambda:'interactive')=='interactive'
                        with pytest.raises(external.Busy):await external.run_background(lambda:None)
                finally:await asyncio.wait_for(pending,6)
        asyncio.run(exercise())
    finally:runner._pool.shutdown(wait=True);c.close()
