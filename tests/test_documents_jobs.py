"""Durable restart/ownership contracts, using synthetic receipts and real process exit."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest
import documents as d
import documents_jobs as jobs
import documents_operations as ops
from documents_storage import rows, transaction
from documents_workspace import Unconfigured, WorkspaceError
import storage as st
import tzutil as tz
from tests.test_documents import registry, approved, register, Adapter


def job(c, operation):
    return rows(c,'SELECT * FROM document_job WHERE id=?',(operation,))[0]


def queued(registry,kind='sign'):
    c,u,unit,path=registry
    doc=approved(registry)
    if kind=='dispatch':
        doc=ops.external_signature(c,u[2],doc['id'],doc['revision'],
            'https://drive.google.com/file/d/signedfile12345/view','v1','Signed',Adapter())
        st.set_setting(c,'documents.official_sender','office@example.test')
        st.set_setting(c,'documents.sending_enabled','1');c.commit()
        values={'channel':'direct_email','recipients':['a@example.test'],'checklist':{'authority':'checked'}}
        actor=u[1]
    else:
        values={'confirmed_fingerprint':'v1'};actor=u[2]
    operation=ops.queue(c,actor,doc['id'],doc['revision'],kind,values)
    return doc,operation,actor


def age(c,operation):
    c.execute('UPDATE document_job SET updated_at=?,lease_until=CASE WHEN lease_owner IS NOT NULL THEN ? ELSE NULL END WHERE id=?',
              (jobs.later(-jobs.LEASE_SECONDS-1),jobs.later(-1),operation));c.commit()


def test_additive_migration_preserves_legacy_jobs(registry):
    c,u,unit,path=registry
    doc,operation,_=queued(registry)
    before=job(c,operation)
    for name in ('lease_owner','lease_until','attempts','next_check_at','last_checked_at','recovery_blocked','recovery_note'):
        # Remove the recovery index before simulating the previous table shape.
        c.execute('DROP INDEX IF EXISTS document_job_recovery')
        c.execute('ALTER TABLE document_job DROP COLUMN '+name)
    c.commit();st.init_db(c);st.init_db(c)
    after=job(c,operation)
    for name,value in before.items():
        assert after[name]==value
    assert after['state']=='pending' and after['attempts']==0


def test_independent_processes_claim_only_once(registry):
    c,u,unit,path=registry
    _,operation,_=queued(registry)
    code='''import sys
import storage as st, documents_jobs as jobs
import documents as d
c=st.connect(sys.argv[1])
try:
 jobs.claim(c,sys.argv[2]);print('claimed')
except d.Conflict:
 print('busy')
finally:
 c.close()
'''
    def claim():
        return subprocess.run([sys.executable,'-c',code,path,operation],check=True,capture_output=True,text=True).stdout.strip()
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:claim(),range(2)))
    assert sorted(results)==['busy','claimed']
    assert job(c,operation)['attempts']==1


@pytest.mark.parametrize('kind',['sign','dispatch'])
def test_real_worker_exit_recovers_receipt_without_repeating_effect(registry,tmp_path,kind):
    c,u,unit,path=registry
    doc,operation,_=queued(registry,kind)
    receipt=str(tmp_path/'receipt.json')
    code='''import json,os,sys
import storage as st,documents_operations as ops
from tests.test_documents import Adapter
class Crash(Adapter):
 def call(self,action,payload,operation):
  result=super().call(action,payload,operation)
  with open(sys.argv[3],'w') as f:json.dump(result,f)
  os._exit(23)
c=st.connect(sys.argv[1]);ops.execute(c,sys.argv[2],Crash())
'''
    result=subprocess.run([sys.executable,'-c',code,path,operation,receipt],capture_output=True,text=True)
    assert result.returncode==23,result.stderr
    assert job(c,operation)['state']=='running'
    assert jobs.recover_one(lambda:st.connect(path),Adapter()) is None
    age(c,operation)
    calls=[]
    class Receipt:
        def call(self,action,payload,op):
            assert not c.in_transaction
            assert op==operation and action=='status'
            assert 'signature_base64' not in payload
            calls.append(action)
            return json.loads(Path(receipt).read_text())
    assert jobs.recover_one(lambda:st.connect(path),Receipt())==operation
    assert jobs.recover_one(lambda:st.connect(path),Receipt()) is None
    assert calls==['status']
    assert job(c,operation)['state']=='confirmed'
    table='document_signature' if kind=='sign' else 'document_dispatch'
    assert c.execute('SELECT COUNT(*) FROM '+table+' WHERE operation_id=?',(operation,)).fetchone()[0]==1
    assert not job(c,operation)['lease_owner']
    assert 'signature_base64' not in '\n'.join(c.iterdump())


def test_expired_worker_cannot_save_or_overwrite_recovered_result(registry):
    c,u,unit,path=registry
    doc,operation,_=queued(registry)
    class Superseded(Adapter):
        def call(self,action,payload,op):
            # Independent database connection takes over after this worker expires.
            age(c,op)
            other=st.connect(path)
            replacement=jobs.claim(other,op,reconcile=True)
            with transaction(other):jobs.completed(other,op,replacement)
            other.close()
            return super().call(action,payload,op)
    with pytest.raises(d.Conflict,match='Another worker'):
        ops.execute(c,operation,Superseded())
    assert job(c,operation)['state']=='confirmed'
    assert not c.execute('SELECT 1 FROM document_signature WHERE operation_id=?',(operation,)).fetchone()
    assert d.raw(c,doc['id'])['current_version']==doc['current_version']


@pytest.mark.parametrize('kind',['sign','dispatch'])
def test_aged_pending_attempt_runs_once_with_fresh_checks(registry,kind):
    c,u,unit,path=registry
    _,operation,_=queued(registry,kind)
    assert jobs.recover_one(lambda:st.connect(path),Adapter()) is None
    age(c,operation)
    assert jobs.recover_one(lambda:st.connect(path),Adapter())==operation
    assert job(c,operation)['state']=='confirmed'
    assert job(c,operation)['attempts']==1
    assert jobs.recover_one(lambda:st.connect(path),Adapter()) is None


@pytest.mark.parametrize('change',['account','grant','signature','source','sending','module'])
def test_pending_recovery_rechecks_current_authority(registry,change):
    c,u,unit,path=registry
    doc,operation,actor=queued(registry,'dispatch' if change=='sending' else 'sign')
    age(c,operation)
    if change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(actor['id'],))
    elif change=='grant':c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',('2026-10-20',actor['id']))
    elif change=='signature':st.set_user_signature(c,actor['id'],b'changed','image/png')
    elif change=='source':c.execute('UPDATE document SET approved_version=NULL WHERE id=?',(doc['id'],))
    elif change=='sending':st.set_setting(c,'documents.sending_enabled','0')
    else:st.set_setting(c,'documents.enabled','0')
    c.commit()
    class NoCall:
        def call(self,*args):raise AssertionError('must not call service')
    jobs.recover_one(lambda:st.connect(path),NoCall())
    current=job(c,operation)
    assert current['state']==('pending' if change=='module' else 'failed')
    if change!='module':assert current['recovery_blocked']==1 and not current['lease_owner']


@pytest.mark.parametrize('error',[WorkspaceError('not_found','safe'),Unconfigured('safe')])
def test_missing_receipt_or_configuration_never_proves_no_effect(registry,error):
    c,u,unit,path=registry
    _,operation,_=queued(registry,'dispatch')
    c.execute("UPDATE document_job SET state='unknown' WHERE id=?",(operation,));c.commit()
    calls=[]
    class Missing:
        def call(self,action,*args):calls.append(action);raise error
    assert jobs.recover_one(lambda:st.connect(path),Missing())==operation
    current=job(c,operation)
    assert current['state']=='unknown' and current['recovery_blocked']==1
    assert jobs.describe(current)['status']=='needs_review'
    assert jobs.recover_one(lambda:st.connect(path),Missing()) is None
    assert calls==['status']


def test_unknown_backoff_limit_and_explicit_receipt_check(registry,monkeypatch):
    c,u,unit,path=registry
    _,operation,_=queued(registry,'dispatch')
    c.execute("UPDATE document_job SET state='unknown' WHERE id=?",(operation,));c.commit()
    calls=[]
    class Unknown:
        def call(self,action,*args):calls.append(action);return {'state':'unknown'}
    clock=tz.now_local()
    monkeypatch.setattr(tz,'now_local',lambda:clock)
    for attempt in range(jobs.MAX_ATTEMPTS):
        assert jobs.recover_one(lambda:st.connect(path),Unknown())==operation
        current=job(c,operation)
        assert current['attempts']==attempt+1
        assert jobs.recover_one(lambda:st.connect(path),Unknown()) is None
        clock+=timedelta(hours=2)
    assert current['recovery_blocked']==1 and not current['next_check_at']
    class Found(Adapter):
        def call(self,action,payload,op):
            assert action=='status'
            return super().call('dispatch',payload,op)
    ops.execute(c,operation,Found(),reconcile=True)
    assert job(c,operation)['state']=='confirmed'
    assert calls==['status']*jobs.MAX_ATTEMPTS


def test_manual_reconciliation_respects_other_worker_and_clears_schedule(registry):
    c,u,unit,path=registry
    _,operation,actor=queued(registry,'dispatch')
    other=st.connect(path)
    try:
        jobs.claim(other,operation)
        with pytest.raises(d.Conflict,match='still in progress'):
            ops.reconcile(c,actor,operation,'cancelled','Confirmed never started')
        age(c,operation)
        ops.reconcile(c,actor,operation,'cancelled','Confirmed never started')
        current=job(c,operation)
        assert not current['lease_owner'] and current['recovery_blocked']==1
        assert jobs.describe(current)['label']=='Cancelled'
        assert jobs.recover_one(lambda:st.connect(path),Adapter()) is None
    finally:other.close()


@pytest.mark.parametrize('state',['pending','running','unknown'])
def test_interrupted_extraction_requires_new_preview_without_replaying(registry,state):
    c,u,unit,path=registry
    doc=register(c,u[0],unit)
    operation=ops.queue(c,u[0],doc['id'],doc['revision'],'extract',{'url':'https://drive.google.com/file/d/sourcefile12345/view'})
    c.execute('UPDATE document_job SET state=? WHERE id=?',(state,operation));c.commit();age(c,operation)
    class NoCall:
        def call(self,*args):raise AssertionError('transient extraction must not replay')
    assert jobs.recover_one(lambda:st.connect(path),NoCall())==operation
    current=job(c,operation)
    assert current['state']=='failed' and current['recovery_blocked']==1
    assert 'Extract again' in jobs.describe(current)['message']


def test_status_api_is_private_minimal_and_live(app_mod,viewer,admin):
    c=app_mod.get_conn()
    try:
        st.set_setting(c,'documents.enabled','1')
        user=st.get_admin_user(c,'viewer@test.local')
        doc=d.register(c,user,{'subject':'Recovery privacy','type':'memo','direction':'OUT'})
        operation=ops.queue(c,user,doc['id'],doc['revision'],'extract',{'url':'https://drive.google.com/file/d/sourcefile12345/view'})
        url=f"/documents/{doc['id']}/operations/{operation}"
        response=viewer.get(url)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['status']=='pending'
        assert not any(x in response.text for x in ('payload_json','sourcefile12345','lease_owner','signature_hash'))
        assert admin.get(url).status_code==404
        assert viewer.get(f"/documents/{doc['id']+1}/operations/{operation}").status_code==404
        token=jobs.claim(c,operation)
        assert viewer.get(url).json()['status']=='running'
        page=viewer.get(f"/documents/{doc['id']}")
        assert 'Wait for processing to finish' in page.text
        assert 'name="operation_id"' not in page.text
        with transaction(c):jobs.completed(c,operation,token)
        assert viewer.get(url).json()['status']=='completed'
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));c.commit()
        assert viewer.get(url,follow_redirects=False).status_code!=200
    finally:c.close()


def test_worker_cancellation_does_not_swallow_shutdown(monkeypatch):
    import documents_external as external
    calls=[]
    async def run(fn,*args):calls.append(fn);raise asyncio.CancelledError()
    monkeypatch.setattr(external,'run',run)
    async def exercise():
        with pytest.raises(asyncio.CancelledError):await jobs.worker(lambda:None)
    asyncio.run(exercise())
    assert calls==[jobs.recover_one]


def test_legacy_running_waits_before_receipt_check(registry):
    c,u,unit,path=registry
    _,operation,_=queued(registry)
    c.execute("UPDATE document_job SET state='running' WHERE id=?",(operation,));c.commit()
    assert jobs.next_candidate(c) is None
    age(c,operation)
    assert jobs.next_candidate(c)['id']==operation


def test_application_recovery_startup_opt_out_and_shutdown(app_mod,monkeypatch):
    started=[]
    monkeypatch.setattr(app_mod,'_hydrate_atoms_from_pickle',lambda c:None)
    monkeypatch.setattr(app_mod.threading,'Thread',lambda **kw:type('Thread',(),{'start':lambda self:None})())
    monkeypatch.setattr(app_mod.short_links,'enabled',lambda:False)
    monkeypatch.setattr(app_mod,'PERSIST_DIR','')
    monkeypatch.setattr(app_mod,'_short_link_task',None)
    monkeypatch.setattr(app_mod,'_document_job_task',None)
    original_create=asyncio.create_task
    def capture(coroutine):
        started.append(coroutine.cr_code.co_filename)
        coroutine.close()
        return None
    async def exercise():
        with monkeypatch.context() as patch:
            patch.setattr(asyncio,'create_task',capture)
            patch.setenv('CSS_NO_SCHEDULER','1')
            await app_mod._start_scheduler()
            assert started==[]
            patch.setenv('CSS_NO_SCHEDULER','0')
            await app_mod._start_scheduler()
        assert any(path.endswith('/documents_jobs.py') for path in started)
        task=original_create(asyncio.Event().wait())
        monkeypatch.setattr(app_mod,'_document_job_task',task)
        await app_mod._stop_short_links()
        assert task.cancelled()
    asyncio.run(exercise())
