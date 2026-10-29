"""S3.2 recipient/paper evidence, immutable history and print authorization/data."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_issues as issues
import supplies_acknowledgments as ack
import supplies_print as prints
import supplies_requests as requests
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing
from tests.test_supplies import supplies_db, key, hidden
from tests.test_supplies_requests import request_db, draft, submit, get, fields
from tests.test_supplies_approvals import approval_db, decide
from tests.test_supplies_backorders import ready
from tests.test_supplies_issues import issue, data
from tests.conftest import session_token


@pytest.fixture
def released(approval_db):
    c,u,units,path,item=approval_db;r=ready(c,u,item,6)
    first=issue(c,u,r,4)['id'];second=issue(c,u,r,2)['id']
    return c,u,units,path,item,r,first,second


def respond(c,u,issue_id,status='acknowledged',**kw):
    actor=kw.pop('actor',u[2])
    return ack.acknowledge_issue(c,actor,issue_id,{'status':status,'note':kw.pop('note','')},
        expected_revision=kw.pop('expected_revision',issues.get_issue(c,u[1],issue_id)['acknowledgment']['revision']),
        operation_key=kw.pop('operation_key',key()),**kw)


def paper(c,u,issue_id,**kw):
    fields={'paper_reference':'SYN-PAPER-01','paper_received_date':'2026-10-19','note':'Signed paper receipt reviewed and filed.'}
    fields.update(kw.pop('fields',{}))
    return ack.record_paper_acknowledgment(c,kw.pop('actor',u[1]),issue_id,fields,
        expected_revision=kw.pop('expected_revision',issues.get_issue(c,u[1],issue_id)['acknowledgment']['revision']),
        operation_key=kw.pop('operation_key',key()),**kw)


def unchanged_snapshot(c):
    return {table:[tuple(row) for row in c.execute(f'SELECT * FROM {table} ORDER BY id')] for table in
        ('supply_stock_movement','supply_reservation','supply_issue','supply_issue_line','supply_request')}


def test_recipient_acknowledgment_replay_and_per_release_independence(released):
    c,u,_,_,_,_,first,second=released;before=unchanged_snapshot(c)
    assert issues.get_issue(c,u[2],first)['acknowledgment']['status']=='pending'
    op=key();result=respond(c,u,first,operation_key=op)
    assert respond(c,u,first,expected_revision=0,operation_key=op)==result
    assert issues.get_issue(c,u[2],second)['acknowledgment']['status']=='pending'
    assert issues.get_issue(c,u[2],first)['acknowledgment']['method']=='recipient'
    assert before==unchanged_snapshot(c)
    with pytest.raises(Conflict):respond(c,u,first)


def test_dispute_requires_reason_then_resolution_preserves_evidence(released):
    c,u,_,_,_,_,first,_=released
    with pytest.raises(Invalid):respond(c,u,first,'disputed')
    respond(c,u,first,'disputed',note='One pack description needs verification.')
    with pytest.raises(Invalid,match='Resolving'):respond(c,u,first)
    respond(c,u,first,note='Handover and quantities verified; dispute resolved.')
    state=issues.get_issue(c,u[2],first)['acknowledgment']
    assert [event['status'] for event in state['history']]==['disputed','acknowledged']
    assert state['history'][0]['note']=='One pack description needs verification.'
    assert state['revision']==2


@pytest.mark.parametrize('who',[0,1,3,4])
def test_only_assigned_recipient_can_self_acknowledge(released,who):
    c,u,_,_,_,_,first,_=released
    with pytest.raises(Denied):respond(c,u,first,actor=u[who])
    assert not issues.get_issue(c,u[2],first)['acknowledgment']['history']


def test_request_owner_is_not_alternate_recipient_and_recipient_access_is_limited(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3)
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[4]['id']));c.commit()
    first=issue(c,u,r,fields=data(c,u,r,2,recipient_id=u[4]['id'],alternate_reason='Designated colleague'))['id']
    second=issue(c,u,r,1)['id']
    with pytest.raises(Denied):respond(c,u,first)
    respond(c,u,first,actor=u[4])
    with pytest.raises(Missing):prints.request_print(c,u[4],r)
    assigned=prints.release_print(c,u[4],first)
    assert len(assigned['releases'])==1 and assigned['releases'][0]['id']==first
    with pytest.raises(Missing):prints.release_print(c,u[4],second)
    with pytest.raises(Denied):respond(c,u,second,actor=u[4])


def test_paper_is_attributed_and_dispute_can_follow_and_be_resolved(released):
    c,u,_,_,_,_,first,_=released;before=unchanged_snapshot(c)
    paper(c,u,first)
    state=issues.get_issue(c,u[2],first)['acknowledgment']
    assert state['method']=='paper_recorded' and state['history'][0]['actor_id']==u[1]['id']
    assert state['history'][0]['actor_snapshot']==u[1]['username']
    respond(c,u,first,'disputed',note='Question about recorded paper receipt.')
    paper(c,u,first,fields={'note':'Corrected receipt verified with recipient.','paper_reference':'SYN-PAPER-02'})
    history=issues.get_issue(c,u[2],first)['acknowledgment']['history']
    assert [event['method'] for event in history]==['paper_recorded','recipient','paper_recorded']
    assert before==unchanged_snapshot(c)


@pytest.mark.parametrize('bad',[{'paper_reference':''},{'note':''},{'paper_received_date':'2099-01-01'},
                               {'paper_received_date':'2026-10-18'},{'paper_received_date':'invalid'}])
def test_paper_requires_valid_evidence_and_handover_chronology(released,bad):
    c,u,_,_,_,_,first,_=released
    with pytest.raises(Invalid):paper(c,u,first,fields=bad)
    assert issues.get_issue(c,u[2],first)['acknowledgment']['revision']==0


@pytest.mark.parametrize('who',[0,2,3,4])
def test_paper_requires_current_custodian(released,who):
    c,u,_,_,_,_,first,_=released
    with pytest.raises(Denied):paper(c,u,first,actor=u[who])


def test_stale_and_changed_payload_retries_conflict(released):
    c,u,_,_,_,_,first,_=released;op=key();respond(c,u,first,operation_key=op)
    with pytest.raises(Conflict):respond(c,u,first,'disputed',note='Different intent',expected_revision=0,operation_key=op)
    with pytest.raises(Conflict):paper(c,u,first,expected_revision=0)
    assert len(issues.get_issue(c,u[2],first)['acknowledgment']['history'])==1


def test_parallel_recipient_and_paper_response_only_one_commits(released):
    c,u,_,path,_,_,first,_=released;barrier=Barrier(2)
    def worker(method):
        conn=st.connect(path)
        try:
            barrier.wait()
            try:
                if method=='recipient':return ack.acknowledge_issue(conn,u[2],first,{'status':'acknowledged'},expected_revision=0,operation_key=key())
                return ack.record_paper_acknowledgment(conn,u[1],first,{'paper_reference':'SYN','paper_received_date':'2026-10-19','note':'Filed signed receipt'},expected_revision=0,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,['recipient','paper']))
    assert sum(isinstance(result,dict) for result in results)==1 and results.count('conflict')==1
    assert len(issues.get_issue(c,u[2],first)['acknowledgment']['history'])==1


def test_revoked_inactive_and_disabled_retry_checks(released):
    c,u,_,_,_,_,first,second=released;op=key();paper(c,u,first,operation_key=op)
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'",(u[0]['id'],u[1]['id']));c.commit()
    with pytest.raises(Denied):ack.record_paper_acknowledgment(c,u[1],first,{'paper_reference':'SYN-PAPER-01','paper_received_date':'2026-10-19','note':'Signed paper receipt reviewed and filed.'},expected_revision=0,operation_key=op)
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    assert prints.release_print(c,u[2],first)
    with pytest.raises(Disabled):ack.acknowledge_issue(c,u[2],second,{'status':'acknowledged'},expected_revision=0,operation_key=key())
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
    with pytest.raises(Denied):ack.acknowledge_issue(c,u[2],second,{'status':'acknowledged'},expected_revision=0,operation_key=key())


def test_audit_failure_rolls_back_and_history_is_immutable(released,monkeypatch):
    from supplies_storage import install
    c,u,_,_,_,_,first,_=released
    def fail(*args,**kw):raise RuntimeError('Synthetic audit failure')
    with monkeypatch.context() as patch:
        patch.setattr(st,'audit',fail)
        with pytest.raises(RuntimeError):respond(c,u,first)
    assert not issues.get_issue(c,u[2],first)['acknowledgment']['history']
    respond(c,u,first)
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_issue_acknowledgment')]
    with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM supply_issue_acknowledgment')
    c.rollback();install(c);install(c)
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_issue_acknowledgment')]
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_request_print_reconciles_partial_releases_and_preserves_separate_dates(released):
    c,u,_,_,_,r,first,second=released
    respond(c,u,first);paper(c,u,second)
    before=unchanged_snapshot(c);view=prints.request_print(c,u[2],r)
    assert view['multiple_releases'] and view['date_issued'] is None and len(view['releases'])==2
    line=view['lines'][0]
    assert (line['requested_quantity'],line['approved_quantity'],line['effective_issued_quantity'])==(6,6,6)
    assert [release['lines'][0]['issued_quantity'] for release in view['releases']]==[4,2]
    assert [release['acknowledgment']['method'] for release in view['releases']]==['recipient','paper_recorded']
    assert before==unchanged_snapshot(c)


def test_print_uses_submitted_snapshot_even_while_returned_draft_changes(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    decide(c,u,r,fields={'decision':'returned','reason':'Correct purpose'})
    requests.save_draft(c,u[2],fields(item,purpose='Private corrected purpose'),request_id=r,expected_revision=3,operation_key=key())
    view=prints.request_print(c,u[3],r)
    assert view['header']['purpose']=='Synthetic meeting supplies' and view['decision']['decision']=='returned'
    with pytest.raises(Conflict):prints.request_print(c,u[2],r,revision=99)
    other=draft(c,u,item)
    with pytest.raises(Conflict):prints.request_print(c,u[2],other)


def test_http_ack_forms_print_privacy_csrf_and_escaping(released,app_mod):
    c,u,_,path,_,r,first,_=released;old=app_mod.DB;app_mod.DB=path;target=f'/supplies/issues/{first}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            page=client.get(target);assert 'Pending' in page.text and 'Yes, I received it' in page.text and 'Report a problem' in page.text
            token=hidden(page.text,'csrf');fields={'csrf':token,'operation_key':key(),'revision':'0','status':'disputed','note':'<script>Synthetic</script>'}
            assert client.post(target+'/acknowledge',data={**fields,'csrf':'bad'}).status_code==403
            assert client.post(target+'/acknowledge',data=fields,headers={'Origin':'https://foreign.example'}).status_code==403
            assert client.post(target+'/acknowledge',data=fields,follow_redirects=False).status_code==303
            assert client.post(target+'/acknowledge',data=fields,follow_redirects=False).status_code==303
            page=client.get(target);assert '&lt;script&gt;Synthetic&lt;/script&gt;' in page.text and '<script>Synthetic</script>' not in page.text
            printable=client.get(f'/supplies/requests/{r}/print');assert printable.status_code==200
            assert 'QUANTITY' in printable.text and 'PURPOSE/DETAILS' in printable.text and 'Signature (blank)' in printable.text
            assert 'Multiple handovers' in printable.text and 'ISS-2026-00001' in printable.text and 'ISS-2026-00002' in printable.text
            assert 'csrf' not in printable.text and '<script>Synthetic</script>' not in printable.text
            assert client.get(target+'/print').status_code==200
            client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
            assert client.get(target+'/print').status_code==404
            assert client.get(f'/supplies/requests/{r}/print').status_code==404
    finally:app_mod.DB=old


def test_previous_revision_print_does_not_use_resubmitted_fields(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    decide(c,u,r,fields={'decision':'returned','reason':'Correct purpose'})
    requests.save_draft(c,u[2],fields(item,purpose='New submitted purpose'),request_id=r,expected_revision=3,operation_key=key())
    submit(c,u,r)
    assert prints.request_print(c,u[2],r)['header']['purpose']=='New submitted purpose'
    original=prints.request_print(c,u[2],r,revision=1)
    assert original['header']['purpose']=='Synthetic meeting supplies' and original['header']['revision']==1
    assert original['decision']['decision']=='returned'


def test_http_paper_attribution_and_stale_response_values(released,app_mod):
    c,u,_,path,_,_,first,_=released;old=app_mod.DB;app_mod.DB=path;target=f'/supplies/issues/{first}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            page=client.get(target);assert 'Record paper evidence' in page.text and 'Record recipient response' not in page.text
            fields={'csrf':hidden(page.text,'csrf'),'operation_key':key(),'revision':'0','paper_reference':'SYN-HTTP-PAPER',
                    'paper_received_date':'2026-10-19','note':'Signed form reviewed by custodian'}
            assert client.post(target+'/paper-acknowledgment',data=fields,follow_redirects=False).status_code==303
            page=client.get(target);assert 'Paper acknowledgment recorded by custodian' in page.text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]));page=client.get(target)
            response=client.post(target+'/acknowledge',data={'csrf':hidden(page.text,'csrf'),'operation_key':key(),
                                 'revision':'0','status':'disputed','note':'Original stale response note'})
            assert response.status_code==409 and hidden(response.text,'revision')=='0'
            assert 'Original stale response note' in response.text
            assert len(issues.get_issue(c,u[2],first)['acknowledgment']['history'])==1
    finally:app_mod.DB=old
