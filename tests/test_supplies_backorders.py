"""S2.3 allocation on receipts, safe remainder cancellation and scoped shortages."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3
import hashlib
import hmac

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_stock as stock
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_allocations as allocations
import supplies_backorders as backorders
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing, record, operation, transaction
from tests.test_supplies import supplies_db, key, create, hidden
from tests.test_supplies_requests import request_db, fields, draft, submit, get
from tests.test_supplies_approvals import approval_db, decide
from tests.conftest import session_token


def ready(c,u,item,quantity,owner=2):
    r=requests.save_draft(c,u[owner],fields(item,lines=[{'item_id':item,'requested_quantity':quantity}]),operation_key=key())['id']
    requests.submit(c,u[owner],r,expected_revision=1,operation_key=key())
    entry=requests.get_request(c,u[owner],r)
    approvals.decide_request(c,u[3] if owner!=3 else u[4],r,{'decision':'approved','lines':[
        {'revision_line_id':line['id'],'approved_quantity':line['requested_quantity']} for line in entry['lines']]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    return r


def cancel_fields(c,u,r,selected=None):
    entry=requests.get_request(c,u[1],r)
    return {'reason':'Synthetic demand no longer needed','lines':[
        {'line_id':line['line_id'],'version':line['reservation_version']} for line in entry['lines']
        if line['outstanding_quantity'] and (selected is None or line['item_id'] in selected)]}


def cancel(c,u,r,**kw):
    actor=kw.pop('actor',u[2]);entry=requests.get_request(c,u[1],r)
    data=kw.pop('fields',cancel_fields(c,u,r))
    return backorders.cancel_remainder(c,actor,r,data,expected_revision=kw.pop('expected_revision',entry['revision']),
                                      operation_key=kw.pop('operation_key',key()),**kw)


def receipt(c,u,item,quantity,op=None):
    return stock.post_receipt(c,u[1],{'supplier':'Synthetic supplier','effective_date':'2026-10-19',
        'lines':[{'item_id':item,'expected_revision':1,'accepted_quantity':quantity}]},operation_key=op or key())


@pytest.mark.usefixtures('unlimited_requests')
def test_receipt_refills_older_demand_atomically_and_replay_no_extra_stock(approval_db):
    c,u,_,_,item=approval_db;a=ready(c,u,item,8);b=ready(c,u,item,7)
    assert [get(c,u,r)['lines'][0]['reserved_quantity'] for r in (a,b)]==[8,2]
    op=key();first=receipt(c,u,item,4,op)
    assert receipt(c,u,item,4,op)==first
    assert [get(c,u,r)['lines'][0]['reserved_quantity'] for r in (a,b)]==[8,6]
    assert allocations.availability(c,item)=={'on_hand':14,'reserved_quantity':14,'available':0}
    shortages=backorders.awaiting_stock(c,u[1])['shortages']
    assert len(shortages)==1 and shortages[0]['request_id']==b and shortages[0]['awaiting_stock_quantity']==1
    assert shortages[0]['request_unit_snapshot']=='Synthetic section'


@pytest.mark.usefixtures('unlimited_requests')
def test_cancel_releases_reservations_to_next_and_preserves_approval(approval_db):
    c,u,_,_,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7)
    original=[tuple(row) for row in c.execute('SELECT * FROM supply_request_decision ORDER BY id')]
    movements=[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    data=cancel_fields(c,u,a);op=key();first=cancel(c,u,a,fields=data,operation_key=op)
    assert cancel(c,u,a,fields=data,expected_revision=3,operation_key=op)==first
    entry=get(c,u,a);line=entry['lines'][0]
    assert entry['approval_status']=='approved' and entry['fulfillment']=='Cancelled before issue'
    assert (line['approved_quantity'],line['cancelled_quantity'],line['reserved_quantity'],line['awaiting_stock_quantity'])==(6,6,0,0)
    assert get(c,u,b)['lines'][0]['reserved_quantity']==7
    assert allocations.availability(c,item)=={'on_hand':10,'reserved_quantity':7,'available':3}
    assert not backorders.awaiting_stock(c,u[1])['shortages']
    assert original==[tuple(row) for row in c.execute('SELECT * FROM supply_request_decision ORDER BY id')]
    assert movements==[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    assert entry['cancellations'][0]['reason']==data['reason']
    assert c.execute('SELECT COUNT(*) FROM supply_request_cancellation').fetchone()[0]==1


@pytest.mark.usefixtures('unlimited_requests')
def test_mixed_item_cancel_only_selected_full_remainder(approval_db):
    c,u,_,_,item=approval_db;other=create(c,u[1],code='NO-STOCK')['id']
    r=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':3},{'item_id':other,'requested_quantity':5}]);submit(c,u,r);decide(c,u,r)
    assert get(c,u,r)['fulfillment']=='Ready to issue'
    cancel(c,u,r,fields=cancel_fields(c,u,r,{item}))
    entry=get(c,u,r)
    assert entry['fulfillment']=='Awaiting stock'
    assert [line['cancelled_quantity'] for line in entry['lines']]==[3,0]
    assert entry['lines'][1]['awaiting_stock_quantity']==5
    cancel(c,u,r,fields=cancel_fields(c,u,r,{other}))
    assert get(c,u,r)['fulfillment']=='Cancelled before issue'


@pytest.mark.usefixtures('unlimited_requests')
def test_opening_stock_also_refills_preexisting_demand(approval_db):
    c,u,_,_,_=approval_db;item=create(c,u[1],code='UNPOSTED')['id'];r=ready(c,u,item,7)
    stock.post_opening(c,u[1],item,{'quantity':5,'effective_date':'2026-10-19','reason':'Synthetic count'},expected_revision=1,operation_key=key())
    line=get(c,u,r)['lines'][0]
    assert (line['reserved_quantity'],line['awaiting_stock_quantity'])==(5,2)


@pytest.mark.parametrize('change',['empty','duplicate','foreign','version','partial','reason','request_revision'])
def test_invalid_or_stale_cancellation_has_no_partial_effects(approval_db,change):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);data=cancel_fields(c,u,r);revision=3
    if change=='empty':data['lines']=[]
    elif change=='duplicate':data['lines']*=2
    elif change=='foreign':data['lines'][0]['line_id']=999
    elif change=='version':data['lines'][0]['version']=999
    elif change=='partial':data['lines'][0]['quantity']=1
    elif change=='reason':data['reason']=''
    else:revision=2
    with pytest.raises((Invalid,Conflict)):cancel(c,u,r,fields=data,expected_revision=revision)
    assert get(c,u,r)['lines'][0]['cancelled_quantity']==0
    assert c.execute('SELECT COUNT(*) FROM supply_request_cancellation').fetchone()[0]==0


@pytest.mark.parametrize('who',[0,3,4])
def test_only_owner_or_custodian_can_cancel(approval_db,who):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3)
    with pytest.raises(Denied):cancel(c,u,r,actor=u[who])
    cancel(c,u,r,actor=u[1])
    assert get(c,u,r)['fulfillment']=='Cancelled before issue'


@pytest.mark.usefixtures('unlimited_requests')
def test_queue_owner_scope_global_read_and_revocation(approval_db):
    c,u,units,_,item=approval_db;a=ready(c,u,item,15);b=ready(c,u,item,8,owner=4)
    assert [line['request_id'] for line in backorders.awaiting_stock(c,u[2])['shortages']]==[a]
    assert [line['request_id'] for line in backorders.awaiting_stock(c,u[3])['shortages']]==[a,b]
    assert not backorders.awaiting_stock(c,u[0])['shortages']
    s.grant_role(c,u[0],u[0]['id'],'auditor',operation_key=key())
    assert len(backorders.awaiting_stock(c,u[0])['shortages'])==2
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[3]['id']));c.commit()
    assert not backorders.awaiting_stock(c,u[3])['shortages']
    s.grant_role(c,u[0],u[3]['id'],'request_approver',unit_id=units[2],operation_key=key())
    assert not backorders.awaiting_stock(c,u[3])['shortages']


@pytest.mark.usefixtures('unlimited_requests')
def test_refresh_is_safe_idempotent_and_current_custodian_only(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,15)
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_reservation')]
    events=c.execute("SELECT COUNT(*) FROM supply_event WHERE action='reservation_allocate'").fetchone()[0]
    op=key();first=backorders.refresh_reservations(c,u[1],operation_key=op)
    assert backorders.refresh_reservations(c,u[1],operation_key=op)==first
    backorders.refresh_reservations(c,u[1],operation_key=key())
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_reservation')]
    assert c.execute("SELECT COUNT(*) FROM supply_event WHERE action='reservation_allocate'").fetchone()[0]==events
    with pytest.raises(Denied):backorders.refresh_reservations(c,u[2],operation_key=key())
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'",(u[0]['id'],u[1]['id']));c.commit()
    with pytest.raises(Denied):backorders.refresh_reservations(c,u[1],operation_key=op)


@pytest.mark.usefixtures('unlimited_requests')
def test_cancellation_after_issue_preserves_issue_projection_and_movements(approval_db):
    c,u,_,_,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7)
    # Model S3.1's future posted issue without adding an issuance feature to S2.3.
    with transaction(c):
        op,digest,_=operation(c,u[1],key(),'synthetic_issue',{})
        stock._add_movement(c,u[1],s._item(c,item),kind='issue',quantity=-4,effective_date='2026-10-19',key=op,source_id=1,reason='Synthetic historical issue')
        c.execute('UPDATE supply_reservation SET effective_issued_quantity=4,reserved_quantity=2,version=version+1 WHERE request_id=?',(a,))
        record(c,u[1],op,digest,'synthetic_issue','request',{'id':a},{})
        allocations.allocate_outstanding(c,u[1],[item],op)
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    cancel(c,u,a)
    line=get(c,u,a)['lines'][0]
    assert (line['approved_quantity'],line['effective_issued_quantity'],line['cancelled_quantity'],line['reserved_quantity'])==(6,4,2,0)
    assert get(c,u,a)['fulfillment']=='Closed with remainder cancelled'
    assert get(c,u,b)['lines'][0]['reserved_quantity']==6
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]


@pytest.mark.usefixtures('unlimited_requests')
def test_failure_in_refill_rolls_back_receipt_and_cancellation(approval_db,monkeypatch):
    c,u,_,_,item=approval_db;r=ready(c,u,item,15)
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_reservation')]
    def fail(*args,**kw):raise RuntimeError('Synthetic allocation failure')
    with monkeypatch.context() as patch:
        patch.setattr(allocations,'allocate_outstanding',fail)
        with pytest.raises(RuntimeError):receipt(c,u,item,5)
    assert stock.stock_totals(c,u[1],item)['on_hand']==10
    assert c.execute('SELECT COUNT(*) FROM supply_receipt').fetchone()[0]==0
    with monkeypatch.context() as patch:
        patch.setattr(backorders,'allocate_outstanding',fail)
        with pytest.raises(RuntimeError):cancel(c,u,r)
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_reservation')]
    assert c.execute('SELECT COUNT(*) FROM supply_request_cancellation').fetchone()[0]==0
    assert get(c,u,r)['revision']==3


@pytest.mark.usefixtures('unlimited_requests')
def test_cancelled_demand_allows_deactivation_but_other_obligations_block(approval_db):
    c,u,_,_,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7)
    cancel(c,u,a)
    with pytest.raises(Conflict):s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='Another obligation')
    cancel(c,u,b)
    s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='All obligations resolved')
    assert get(c,u,a)['approval_status']=='approved'


@pytest.mark.usefixtures('unlimited_requests')
def test_parallel_cancellations_apply_once(approval_db):
    c,u,_,path,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7);data=cancel_fields(c,u,a);barrier=Barrier(2)
    def worker(actor):
        conn=st.connect(path)
        try:
            barrier.wait()
            try:return backorders.cancel_remainder(conn,actor,a,data,expected_revision=3,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[u[1],u[2]]))
    assert sum(isinstance(result,dict) for result in results)==1 and results.count('conflict')==1
    assert get(c,u,b)['lines'][0]['reserved_quantity']==7
    assert c.execute('SELECT COUNT(*) FROM supply_request_cancellation').fetchone()[0]==1


@pytest.mark.usefixtures('unlimited_requests')
def test_receipt_invalidates_stale_line_version_even_without_header_change(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,15);data=cancel_fields(c,u,r)
    receipt(c,u,item,2)
    with pytest.raises(Conflict,match='Reservations changed'):cancel(c,u,r,fields=data)
    assert get(c,u,r)['revision']==3 and get(c,u,r)['lines'][0]['cancelled_quantity']==0


def test_immutable_cancellation_and_repeat_install(approval_db):
    from supplies_storage import install
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);cancel(c,u,r)
    for table in ('supply_request_cancellation','supply_request_cancellation_line'):
        before=[tuple(row) for row in c.execute(f'SELECT * FROM {table}')]
        with pytest.raises(sqlite3.IntegrityError):c.execute(f'DELETE FROM {table}')
        c.rollback();install(c);install(c)
        assert before==[tuple(row) for row in c.execute(f'SELECT * FROM {table}')]
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.usefixtures('unlimited_requests')
def test_disabled_changes_retain_queue_and_history(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,15)
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    assert backorders.awaiting_stock(c,u[2])['shortages']
    with pytest.raises(Disabled):cancel(c,u,r)
    with pytest.raises(Disabled):backorders.refresh_reservations(c,u[1],operation_key=key())


@pytest.mark.usefixtures('unlimited_requests')
def test_http_queue_cancellation_csrf_and_controls(approval_db,app_mod):
    c,u,_,path,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7);old=app_mod.DB;app_mod.DB=path;target=f'/supplies/requests/{a}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            queue=client.get('/supplies/awaiting-stock');assert queue.status_code==200 and 'SUP-2026-00002' in queue.text
            page=client.get(target);assert 'Cancel remaining demand' in page.text
            token=hidden(page.text,'csrf');line=get(c,u,a)['lines'][0]
            data={'csrf':token,'operation_key':key(),'revision':'3','reason':'Meeting no longer needs supplies',f"cancel_{line['line_id']}":str(line['reservation_version'])}
            assert client.post(target+'/cancel-remainder',data={**data,'csrf':'bad'}).status_code==403
            assert client.post(target+'/cancel-remainder',data=data,headers={'Origin':'https://foreign.example'}).status_code==403
            invalid=client.post(target+'/cancel-remainder',data={**data,'reason':''});assert invalid.status_code==422 and 'checked' in invalid.text
            assert client.post(target+'/cancel-remainder',data=data,follow_redirects=False).status_code==303
            assert client.post(target+'/cancel-remainder',data=data,follow_redirects=False).status_code==303
            page=client.get(target);assert 'Cancelled before issue' in page.text and 'Meeting no longer needs supplies' in page.text
            assert 'Cancel selected remainders' not in page.text
            queue=client.get('/supplies/awaiting-stock',follow_redirects=False)      # Supplies 4.1: a requester is sent to My requests
            assert queue.status_code==303 and queue.headers['location']=='/supplies/requests?status=active'
            client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
            assert 'Cancel selected remainders' not in client.get(f'/supplies/requests/{b}').text
            assert client.post('/supplies/allocations/refresh',data={'csrf':hmac.new(auth._secret(),('supplies:'+client.cookies.get(auth.COOKIE_NAME)).encode(),hashlib.sha256).hexdigest(),'operation_key':key()}).status_code==403
    finally:app_mod.DB=old


@pytest.mark.usefixtures('unlimited_requests')
def test_imported_opening_refills_existing_approved_demand(approval_db):
    from tests.test_supplies_import_review import stage, save, finish, apply, include
    c,u,_,_,_=approval_db;item=create(c,u[1],code='UNPOSTED')['id'];r=ready(c,u,item,15)
    batch=stage(c,u)
    save(c,u,batch,{**include(),'item_choice':f'{item}:1'})
    finish(c,u,batch);apply(c,u,batch)
    assert (get(c,u,r)['lines'][0]['reserved_quantity'],get(c,u,r)['lines'][0]['awaiting_stock_quantity'])==(13,2)
    assert allocations.availability(c,item)=={'on_hand':13,'reserved_quantity':13,'available':0}


@pytest.mark.usefixtures('unlimited_requests')
def test_cancellation_audit_failure_rolls_back_evidence_and_projection(approval_db,monkeypatch):
    c,u,_,_,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7)
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_reservation ORDER BY id')]
    def fail(*args,**kwargs):raise RuntimeError('Synthetic audit failure')
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):cancel(c,u,a)
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_reservation ORDER BY id')]
    assert c.execute('SELECT COUNT(*) FROM supply_request_cancellation_line').fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM supply_operation WHERE action='request_cancel_remainder'").fetchone()[0]==0
    assert get(c,u,a)['revision']==3


@pytest.mark.usefixtures('unlimited_requests')
def test_shortage_queue_pagination_and_no_private_draft_or_submitted_demand(approval_db):
    c,u,_,_,_=approval_db;item=create(c,u[1],code='EMPTY')['id']
    private=draft(c,u,item);pending=draft(c,u,item);submit(c,u,pending)
    for _ in range(26):ready(c,u,item,1)
    page1=backorders.awaiting_stock(c,u[1]);page2=backorders.awaiting_stock(c,u[1],page=2)
    assert len(page1['shortages'])==25 and page1['has_next']
    assert len(page2['shortages'])==1 and not page2['has_next']
    ids=[row['request_id'] for row in page1['shortages']+page2['shortages']]
    assert len(set(ids))==26 and private not in ids and pending not in ids


def test_revoked_custodian_and_disabled_flag_block_cancellation_replay(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);data=cancel_fields(c,u,r);op=key()
    cancel(c,u,r,actor=u[1],fields=data,operation_key=op)
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    with pytest.raises(Disabled):cancel(c,u,r,actor=u[1],fields=data,operation_key=op,expected_revision=3)
    c.execute("UPDATE app_setting SET value='1' WHERE key='supplies.enabled'")
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'",(u[0]['id'],u[1]['id']));c.commit()
    with pytest.raises(Denied):backorders.cancel_remainder(c,u[1],r,data,expected_revision=3,operation_key=op)
    assert c.execute('SELECT COUNT(*) FROM supply_request_cancellation').fetchone()[0]==1


@pytest.mark.usefixtures('unlimited_requests')
def test_parallel_receipt_and_cancellation_preserve_stock_and_demand_equations(approval_db):
    c,u,_,path,item=approval_db;a=ready(c,u,item,15);b=ready(c,u,item,7);data=cancel_fields(c,u,a);barrier=Barrier(2)
    def worker(action):
        conn=st.connect(path)
        try:
            barrier.wait()
            if action=='receipt':return receipt(conn,u,item,2)
            try:return backorders.cancel_remainder(conn,u[2],a,data,expected_revision=3,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,['receipt','cancel']))
    assert stock.stock_totals(c,u[1],item)['on_hand']==12
    for r in (a,b):
        line=get(c,u,r)['lines'][0]
        assert line['effective_issued_quantity']+line['cancelled_quantity']+line['reserved_quantity']+line['awaiting_stock_quantity']==line['approved_quantity']
        assert line['reserved_quantity']>=0 and line['awaiting_stock_quantity']>=0
    totals=allocations.availability(c,item)
    assert totals['available']+totals['reserved_quantity']==12
    if results[1]=='conflict':assert get(c,u,a)['lines'][0]['cancelled_quantity']==0
    else:assert get(c,u,b)['lines'][0]['reserved_quantity']==7


def test_mixed_issue_and_cancellation_fulfillment_precedence():
    lines=[{'approved_quantity':6,'effective_issued_quantity':4,'cancelled_quantity':2,'reserved_quantity':0},
           {'approved_quantity':7,'effective_issued_quantity':0,'cancelled_quantity':0,'reserved_quantity':3}]
    assert allocations.fulfillment(lines)=='Partially issued'
    lines[1].update(cancelled_quantity=7,reserved_quantity=0)
    assert allocations.fulfillment(lines)=='Closed with remainder cancelled'
    for line in lines:line.update(effective_issued_quantity=line['approved_quantity'],cancelled_quantity=0,reserved_quantity=0)
    assert allocations.fulfillment(lines)=='Fully issued'
