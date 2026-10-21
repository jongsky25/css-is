"""S2.2 scoped decisions, immutable revisions and serialized stock reservations."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_allocations as allocations
import supplies_stock as stock
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing
from tests.test_supplies import supplies_db, key, create, fields as item_fields, hidden
from tests.test_supplies_requests import request_db, fields, draft, submit, get, withdraw
from tests.conftest import session_token


@pytest.fixture
def approval_db(request_db):
    c,u,units,path,item=request_db
    s.grant_role(c,u[0],u[3]['id'],'request_approver',unit_id=units[0],operation_key=key())
    s.grant_role(c,u[0],u[4]['id'],'request_approver',unit_id=units[0],operation_key=key())
    stock.post_opening(c,u[1],item,{'quantity':'10','effective_date':'2026-10-19','reason':'Synthetic opening'},expected_revision=1,operation_key=key())
    return c,u,units,path,item


def decide(c,u,r,quantity=None,**kw):
    entry=get(c,u,r)
    data={'decision':'approved','reason':'', 'lines':[{'revision_line_id':line['id'],
          'approved_quantity':line['requested_quantity'] if quantity is None else quantity,
          'reason':'Reduced to match justified need' if quantity is not None and int(quantity)<line['requested_quantity'] else ''} for line in entry['lines']]}
    data.update(kw.pop('fields',{}))
    return approvals.decide_request(c,kw.pop('actor',u[3]),r,data,expected_revision=kw.pop('expected_revision',entry['revision']),
                submitted_revision=kw.pop('submitted_revision',entry['current_revision']),operation_key=kw.pop('operation_key',key()),**kw)


def test_reduced_approval_and_oldest_first_shortage_no_stock_change(approval_db):
    c,u,_,_,item=approval_db
    a=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':'8'}]);submit(c,u,a)
    b=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':'7'}]);submit(c,u,b)
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    op=key();result=decide(c,u,a,6,operation_key=op)
    assert decide(c,u,a,6,operation_key=op,expected_revision=2)==result
    decide(c,u,b)
    first=get(c,u,a)['lines'][0];second=get(c,u,b)['lines'][0]
    assert (first['requested_quantity'],first['approved_quantity'],first['reserved_quantity'],first['awaiting_stock_quantity'])==(8,6,6,0)
    assert (second['approved_quantity'],second['reserved_quantity'],second['awaiting_stock_quantity'])==(7,4,3)
    assert allocations.availability(c,item)=={'on_hand':10,'reserved_quantity':10,'available':0}
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    assert get(c,u,b)['fulfillment']=='Ready to issue'
    assert not approvals.inbox(c,u[3])['requests']
    for table in ('supply_request_decision','supply_request_decision_line'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(f'DELETE FROM {table}')
        c.rollback()


@pytest.mark.parametrize('who',[0,1,2])
def test_self_and_technical_or_custodian_roles_cannot_decide(approval_db,who):
    c,u,units,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    if who==2:s.grant_role(c,u[0],u[2]['id'],'request_approver',unit_id=units[0],operation_key=key())
    with pytest.raises(Denied):decide(c,u,r,actor=u[who])
    assert c.execute('SELECT COUNT(*) FROM supply_reservation').fetchone()[0]==0


def test_out_of_scope_and_revocation_remove_reads_inbox_and_retry(approval_db):
    c,u,units,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    decide(c,u,r)
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[3]['id']));c.commit()
    with pytest.raises(Missing):requests.get_request(c,u[3],r)
    with pytest.raises(Denied):approvals.inbox(c,u[3])
    with pytest.raises(Denied):decide(c,u,r)
    s.grant_role(c,u[0],u[3]['id'],'request_approver',unit_id=units[2],operation_key=key())
    with pytest.raises(Missing):requests.get_request(c,u[3],r)
    assert not approvals.inbox(c,u[3])['requests']


@pytest.mark.parametrize('change',['missing_line','duplicate_line','foreign_line','over_request','reduction_no_reason','negative','fraction','boolean'])
def test_invalid_approval_is_atomic(approval_db,change):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r);line=get(c,u,r)['lines'][0]
    original={'revision_line_id':line['id'],'approved_quantity':3,'reason':''}
    lines=[dict(original)]
    if change=='missing_line':lines=[]
    elif change=='duplicate_line':lines.append(dict(original))
    elif change=='foreign_line':lines[0]['revision_line_id']=999
    elif change=='over_request':lines[0]['approved_quantity']=4
    elif change=='reduction_no_reason':lines[0]['approved_quantity']=2
    elif change=='negative':lines[0]['approved_quantity']=-1
    elif change=='fraction':lines[0]['approved_quantity']='1.5'
    else:lines[0]['approved_quantity']=True
    with pytest.raises(Invalid):decide(c,u,r,fields={'lines':lines})
    assert get(c,u,r)['approval_status']=='submitted'
    assert c.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM supply_reservation').fetchone()[0]==0


def test_return_edit_remove_readd_lines_resubmit_keeps_old_evidence(approval_db):
    c,u,_,_,item=approval_db;other=create(c,u[1],code='SYN-PEN',unit='Piece')['id']
    r=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':'3'},{'item_id':other,'requested_quantity':'2'}]);submit(c,u,r)
    old=[tuple(row) for row in c.execute('SELECT * FROM supply_request_revision_line ORDER BY id')]
    old_line=get(c,u,r)['lines'][0]['line_id']
    decide(c,u,r,fields={'decision':'returned','reason':'Correct purpose and remove pens'})
    requests.save_draft(c,u[2],fields(item,purpose='Private corrected purpose',lines=[{'item_id':item,'requested_quantity':'2'}]),request_id=r,expected_revision=3,operation_key=key())
    owner=get(c,u,r);approver=requests.get_request(c,u[3],r)
    assert owner['purpose']=='Private corrected purpose' and len(owner['lines'])==1
    assert approver['purpose']=='Synthetic meeting supplies' and len(approver['lines'])==2
    assert all(e['action']!='request_save' for e in approver['events'])
    submit(c,u,r)
    entry=get(c,u,r);assert entry['control_number']=='SUP-2026-00001' and entry['current_revision']==2
    assert entry['lines'][0]['line_id']==old_line
    assert old==[tuple(row) for row in c.execute('SELECT * FROM supply_request_revision_line WHERE revision_id=1 ORDER BY id')]
    assert len(entry['history'])==2 and entry['history'][0]['decision']=='returned'
    decide(c,u,r,2)
    assert len(get(c,u,r)['lines'])==1
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('choice',['returned','rejected'])
def test_reason_required_and_no_reservations_for_nonapproval(approval_db,choice):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    with pytest.raises(Invalid):decide(c,u,r,fields={'decision':choice,'reason':''})
    decide(c,u,r,fields={'decision':choice,'reason':'Synthetic decision reason'})
    assert get(c,u,r)['approval_status']==choice
    assert c.execute('SELECT COUNT(*) FROM supply_reservation').fetchone()[0]==0
    if choice=='returned':withdraw(c,u,r);assert get(c,u,r)['approval_status']=='cancelled'
    else:
        with pytest.raises(Conflict):submit(c,u,r)
        with pytest.raises(Conflict):withdraw(c,u,r)


def test_stale_submitted_revision_and_already_decided_conflict(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    with pytest.raises(Conflict):decide(c,u,r,submitted_revision=2)
    with pytest.raises(Conflict):decide(c,u,r,expected_revision=1)
    decide(c,u,r,fields={'decision':'returned','reason':'Clarify'})
    submit(c,u,r)
    with pytest.raises(Conflict):decide(c,u,r,submitted_revision=1)
    decide(c,u,r)
    with pytest.raises(Conflict):decide(c,u,r,actor=u[4])


def test_approval_rechecks_unit_and_can_return_changed_item(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    c.execute("UPDATE supply_item SET unit='Pack',revision=revision+1 WHERE id=?",(item,));c.commit()
    with pytest.raises(Conflict,match='catalog item changed'):decide(c,u,r)
    decide(c,u,r,fields={'decision':'returned','reason':'Review new canonical unit'})
    assert get(c,u,r)['approval_status']=='returned'


def test_audit_or_allocator_failure_rolls_back_decision_and_reservation(approval_db,monkeypatch):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    def fail(*args,**kw):raise RuntimeError('Synthetic failure')
    with monkeypatch.context() as patch:
        patch.setattr(st,'audit',fail)
        with pytest.raises(RuntimeError):decide(c,u,r)
    assert c.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==0
    with monkeypatch.context() as patch:
        patch.setattr(approvals,'allocate_outstanding',fail)
        with pytest.raises(RuntimeError):decide(c,u,r)
    assert get(c,u,r)['approval_status']=='submitted'
    assert c.execute('SELECT COUNT(*) FROM supply_reservation').fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM supply_operation WHERE action='request_decide'").fetchone()[0]==0


def test_two_simultaneous_approvers_only_one_decides(approval_db):
    c,u,_,path,item=approval_db;r=draft(c,u,item);submit(c,u,r);source=get(c,u,r)['lines'][0]['id'];barrier=Barrier(2)
    def worker(actor):
        conn=st.connect(path)
        try:
            barrier.wait()
            try:return approvals.decide_request(conn,actor,r,{'decision':'approved','lines':[{'revision_line_id':source,'approved_quantity':'3'}]},expected_revision=2,submitted_revision=1,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[u[3],u[4]]))
    assert sum(isinstance(result,dict) for result in results)==1
    assert results.count('conflict')==1
    assert c.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==1
    assert allocations.availability(c,item)['reserved_quantity']==3


def test_simultaneous_requests_never_over_reserve(approval_db):
    c,u,_,path,item=approval_db;ids=[draft(c,u,item,lines=[{'item_id':item,'requested_quantity':'8'}]) for _ in range(2)]
    sources=[]
    for r in ids:submit(c,u,r);sources.append(get(c,u,r)['lines'][0]['id'])
    barrier=Barrier(2)
    def worker(pair):
        r,source=pair;conn=st.connect(path)
        try:
            barrier.wait()
            return approvals.decide_request(conn,u[3],r,{'decision':'approved','lines':[{'revision_line_id':source,'approved_quantity':'8'}]},expected_revision=2,submitted_revision=1,operation_key=key())
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert len(list(pool.map(worker,zip(ids,sources))))==2
    reserved=[row[0] for row in c.execute('SELECT reserved_quantity FROM supply_reservation')]
    assert sorted(reserved)==[2,8] and sum(reserved)==10
    assert stock.stock_totals(c,u[1],item)['on_hand']==10


def test_zero_approval_unrecorded_stock_and_allocator_repeat(approval_db):
    c,u,_,_,item=approval_db;other=create(c,u[1],code='NO-STOCK')['id']
    a=draft(c,u,other);submit(c,u,a);decide(c,u,a)
    assert get(c,u,a)['fulfillment']=='Awaiting stock'
    b=draft(c,u,item);submit(c,u,b);decide(c,u,b,0)
    assert get(c,u,b)['lines'][0]['approved_quantity']==0
    assert get(c,u,b)['fulfillment']=='No approved quantity'
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_reservation ORDER BY id')]
    c.execute('BEGIN IMMEDIATE')
    op=c.execute("SELECT operation_key FROM supply_operation WHERE action='request_decide' LIMIT 1").fetchone()[0]
    allocations.allocate_outstanding(c,u[3],[item,other],op);c.commit()
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_reservation ORDER BY id')]


def test_flag_and_custodian_auditor_read_only_and_private_drafts(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item)
    with pytest.raises(Missing):requests.get_request(c,u[3],r)
    with pytest.raises(Missing):requests.get_request(c,u[1],r)
    submit(c,u,r)
    assert requests.get_request(c,u[1],r)['is_owner'] is False
    s.grant_role(c,u[0],u[0]['id'],'auditor',operation_key=key())
    assert not requests.get_request(c,u[0],r)['can_decide']
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    assert approvals.inbox(c,u[3])['requests']
    with pytest.raises(Disabled):decide(c,u,r)


def test_http_inbox_reduced_decision_and_owner_controls(approval_db,app_mod):
    c,u,_,path,item=approval_db;r=draft(c,u,item);submit(c,u,r);old=app_mod.DB;app_mod.DB=path;target=f'/supplies/requests/{r}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
            inbox=client.get('/supplies/approvals');assert inbox.status_code==200 and 'SUP-2026-00001' in inbox.text
            page=client.get(target);assert 'Record decision' in page.text and 'Withdraw before approval' not in page.text
            assert client.get(target+'/edit').status_code==404
            source=get(c,u,r)['lines'][0]['id'];token=hidden(page.text,'csrf')
            data={'csrf':token,'operation_key':key(),'revision':'2','submitted_revision':'1','decision':'approved',f'approved_{source}':'2',f'reduction_{source}':''}
            assert client.post(target+'/decide',data={**data,'csrf':'bad'}).status_code==403
            invalid=client.post(target+'/decide',data=data);assert invalid.status_code==422 and 'requires a reason' in invalid.text
            assert 'value="2"' in invalid.text
            data[f'reduction_{source}']='Reduced for synthetic need'
            assert client.post(target+'/decide',data=data,follow_redirects=False).status_code==303
            page=client.get(target);assert 'Ready to issue' in page.text and 'Awaiting stock' in page.text
            assert client.post(target+'/decide',data=data,follow_redirects=False).status_code==303
            assert 'SUP-2026-00001' not in client.get('/supplies/approvals').text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            page=client.get(target);assert 'Reduced for synthetic need' in page.text and 'Record decision' not in page.text
            assert client.get('/supplies/approvals').status_code==403
    finally:app_mod.DB=old


def test_returned_unit_changes_do_not_leak_corrections_or_change_old_scope(approval_db):
    c,u,units,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    decide(c,u,r,fields={'decision':'returned','reason':'Update unit and purpose'})
    c.execute('UPDATE resource_person SET org_unit_id=? WHERE id=?',(units[2],u[2]['rp_id']));c.commit()
    requests.save_draft(c,u[2],fields(item,purpose='Private new-unit correction'),request_id=r,expected_revision=3,operation_key=key())
    old_scope=requests.get_request(c,u[3],r)
    assert old_scope['unit_id']==units[1] and old_scope['purpose']=='Synthetic meeting supplies'
    submit(c,u,r)
    with pytest.raises(Missing):requests.get_request(c,u[3],r)
    assert not approvals.inbox(c,u[3])['requests']


def test_revoked_approver_cannot_replay_successful_decision(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r);op=key()
    decide(c,u,r,operation_key=op)
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[3]['id']));c.commit()
    with pytest.raises(Denied):decide(c,u,r,operation_key=op,expected_revision=2)
    assert allocations.availability(c,item)['reserved_quantity']==3


def test_shared_allocator_uses_older_demand_after_receipt_on_next_approval(approval_db):
    c,u,_,_,item=approval_db
    ids=[]
    for qty in (8,7):
        r=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':qty}]);submit(c,u,r);decide(c,u,r);ids.append(r)
    stock.post_receipt(c,u[1],{'supplier':'Synthetic supplier','effective_date':'2026-10-19',
        'lines':[{'item_id':item,'expected_revision':1,'accepted_quantity':'4'}]},operation_key=key())
    last=draft(c,u,item);submit(c,u,last);decide(c,u,last)
    assert [get(c,u,r)['lines'][0]['reserved_quantity'] for r in [*ids,last]]==[8,6,0]
    assert allocations.availability(c,item)=={'on_hand':14,'reserved_quantity':14,'available':0}


def test_outstanding_approved_units_are_fixed_without_stock_history(approval_db):
    c,u,_,_,_=approval_db;item=create(c,u[1],code='UNPOSTED')['id']
    r=draft(c,u,item);submit(c,u,r);decide(c,u,r)
    with pytest.raises(Conflict,match='approved demand'):s.update_item(c,u[1],item,item_fields(code='UNPOSTED',unit='Pack'),expected_revision=1,operation_key=key())
    assert not stock.stock_totals(c,u[1],item)['recorded']


def test_additive_upgrade_preserves_preexisting_lines_and_history(approval_db):
    from supplies_storage import install
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    c.execute('ALTER TABLE supply_request_draft_line DROP COLUMN active');c.commit()
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_request_revision_line')]
    install(c);install(c)
    assert c.execute('SELECT active FROM supply_request_draft_line').fetchone()[0]==1
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_request_revision_line')]
    decide(c,u,r)
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_private_draft_cannot_be_decided_by_scoped_approver(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item)
    with pytest.raises(Missing):approvals.decide_request(c,u[3],r,{'decision':'rejected','reason':'No private draft access'},expected_revision=1,submitted_revision=1,operation_key=key())
    assert not approvals.inbox(c,u[3])['requests']
