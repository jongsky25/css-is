"""S5.3 linked partial deliveries, stock allocation and reversal accounting."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_stock as stock
import supplies_deliveries as deliveries
import supplies_replenishment as rep
import supplies_replenishment_flow as flow
import supplies_corrections as corrections
import supplies_notify as notify
from supplies_storage import Conflict, Invalid
from tests.test_supplies import supplies_db,key,hidden
from tests.test_supplies_requests import request_db
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_replenishment import line,fields
from tests.test_supplies_replenishment_flow import flow_db
from tests.test_supplies_backorders import ready,cancel
from tests.test_supplies_issues import issue
from tests.conftest import session_token


def approved(c,u,item,quantity=10):
    draft=rep.save_replenishment(c,u[1],fields(line(item,quantity,reason='Synthetic replenishment need')),
                                 operation_key=key())['id']
    flow.submit_replenishment(c,u[1],draft,expected_revision=1,operation_key=key(),
                              review_reason='Synthetic need reviewed')
    submitted_line=rep.get_replenishment(c,u[1],draft)['submitted_lines'][0]['id']
    flow.decide_replenishment(c,u[4],draft,{'decision':'approved','reason':'Synthetic need confirmed',
        'lines':[{'revision_line_id':submitted_line,'approved_quantity':quantity,'reason':''}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    return draft


def payload(c,u,rid,delivered,accepted=None,rejected=0,reason='',**extra):
    detail=rep.get_replenishment(c,u[1],rid)
    source=detail['lines'][0]
    return {'supplier':'Synthetic supplier','dr_number':'DR-SYN-1','apr_number':'APR-SYN-1',
            'effective_date':'2026-10-20','lines':[{'replenishment_line_id':source['id'],
                'expected_item_revision':s._item(c,source['item_id'])['revision'],
                'delivered_quantity':delivered,'accepted_quantity':delivered-rejected if accepted is None else accepted,
                'rejected_quantity':rejected,'rejection_reason':reason,'unit_cost':'3.2500'}],**extra}


def post(c,u,rid,fields,revision=None,op=None):
    return deliveries.receive_delivery(c,u[1],rid,fields,
        expected_revision=revision or rep.get_replenishment(c,u[1],rid)['revision'],operation_key=op or key())


@pytest.mark.usefixtures('unlimited_requests')
def test_two_partial_deliveries_reconcile_incoming_stock_allocations_and_warnings(flow_db):
    c,u,_,_,item=flow_db
    a=ready(c,u,item,6);b=ready(c,u,item,7)
    issue(c,u,a,4);cancel(c,u,a)
    assert notify.status(c,u[1],item)['availability_state']=='fully_reserved'
    rid=approved(c,u,item,21)
    before=rep.suggest_replenishment(c,u[1],item)
    assert (before['on_hand'],before['reserved'],before['outstanding'],before['incoming'],before['suggested'])==(6,6,7,21,0)
    first=post(c,u,rid,payload(c,u,rid,10))
    assert first['receipt_id'] and first['status']=='partially_received'
    mid=rep.suggest_replenishment(c,u[1],item)
    assert (mid['on_hand'],mid['reserved'],mid['available'],mid['outstanding'],mid['incoming'])==(16,7,9,7,11)
    assert notify.status(c,u[1],item)['availability_state']=='available'
    second=post(c,u,rid,payload(c,u,rid,11,dr_number='DR-SYN-2'))
    assert second['status']=='received' and second['remaining_incoming']==0
    end=rep.suggest_replenishment(c,u[1],item)
    assert (end['on_hand'],end['reserved'],end['incoming'])==(27,7,0)
    assert len(rep.get_replenishment(c,u[1],rid)['deliveries'])==2
    assert stock.get_receipt(c,u[1],first['receipt_id'])['replenishment_id']==rid


def test_rejected_delivery_records_evidence_without_stock_or_incoming(flow_db):
    c,u,_,_,item=flow_db;rid=approved(c,u,item)
    before=rep.suggest_replenishment(c,u[1],item)
    result=post(c,u,rid,payload(c,u,rid,4,accepted=0,rejected=4,reason='Damaged packaging'))
    assert result['receipt_id'] is None and result['status']=='approved'
    assert rep.suggest_replenishment(c,u[1],item)['on_hand']==before['on_hand']
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==before['incoming']
    assert deliveries.get_delivery(c,u[1],rid,result['id'])['lines'][0]['rejection_reason']=='Damaged packaging'
    assert c.execute('SELECT COUNT(*) FROM supply_receipt WHERE delivery_id=?',(result['id'],)).fetchone()[0]==0


def test_invalid_quantities_generic_bypass_and_replay_leave_balances_unchanged(flow_db):
    c,u,_,_,item=flow_db;rid=approved(c,u,item)
    generic={'supplier':'Unlinked supplier','effective_date':'2026-10-20',
             'lines':[{'item_id':item,'expected_revision':1,'accepted_quantity':3}]}
    with pytest.raises(Conflict):stock.post_receipt(c,u[1],generic,operation_key=key())
    for fields in (payload(c,u,rid,11),payload(c,u,rid,4,accepted=3,rejected=0),
                   payload(c,u,rid,4,accepted=2,rejected=2,reason='')):
        with pytest.raises((Conflict,Invalid)):post(c,u,rid,fields)
    assert rep.suggest_replenishment(c,u[1],item)['on_hand']==10
    op=key();fields=payload(c,u,rid,6)
    first=post(c,u,rid,fields,op=op)
    assert post(c,u,rid,fields,revision=3,op=op)==first
    with pytest.raises(Conflict):post(c,u,rid,payload(c,u,rid,5))
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==4
    assert rep.suggest_replenishment(c,u[1],item)['on_hand']==16


def test_linked_receipt_reversal_requires_choice_and_reconciles_incoming(flow_db):
    c,u,_,_,item=flow_db;rid=approved(c,u,item)
    result=post(c,u,rid,payload(c,u,rid,6))
    receipt=stock.get_receipt(c,u[1],result['receipt_id']);source=receipt['lines'][0]['id']
    base={'source_line_id':source,'quantity':2,'effective_date':'2026-10-20','reason':'Synthetic count correction'}
    with pytest.raises(Invalid):corrections.preview(c,u[1],'receipt_reversal',receipt['id'],base)
    fields={**base,'reopen_incoming':'yes'}
    preview=corrections.preview(c,u[1],'receipt_reversal',receipt['id'],fields)
    assert preview['incoming_after']==6
    corrected=corrections.reverse_receipt(c,u[1],receipt['id'],{**fields,
        'preview_token':preview['preview_token'],'confirmed':'yes'},operation_key=key())
    assert corrected['quantity_delta']==-2
    current=rep.suggest_replenishment(c,u[1],item)
    assert (current['on_hand'],current['incoming'])==(14,6)
    assert rep.get_replenishment(c,u[1],rid)['status']=='partially_received'
    fields={**base,'quantity':1,'reopen_incoming':'no'}
    preview=corrections.preview(c,u[1],'receipt_reversal',receipt['id'],fields)
    assert preview['incoming_after']==6
    corrections.reverse_receipt(c,u[1],receipt['id'],{**fields,
        'preview_token':preview['preview_token'],'confirmed':'yes'},operation_key=key())
    current=rep.suggest_replenishment(c,u[1],item)
    assert (current['on_hand'],current['incoming'])==(13,6)
    commitment=c.execute('SELECT received_quantity,cancelled_quantity FROM supply_replenishment_commitment').fetchone()
    assert tuple(commitment)==(3,1)
    assert c.execute('SELECT COUNT(*) FROM supply_replenishment_receipt_reversal').fetchone()[0]==2


def test_competing_deliveries_cannot_receive_same_remainder_twice(flow_db):
    c,u,_,path,item=flow_db;rid=approved(c,u,item)
    fields=payload(c,u,rid,10);barrier=Barrier(2)
    def attempt():
        db=st.connect(path)
        try:
            barrier.wait()
            return deliveries.receive_delivery(db,u[1],rid,fields,expected_revision=3,operation_key=key())['status']
        except Conflict:return 'conflict'
        finally:db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(lambda _:attempt(),range(2)))
    assert sorted(outcomes)==['conflict','received']
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==0
    assert rep.suggest_replenishment(c,u[1],item)['on_hand']==20
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement WHERE kind="receipt"').fetchone()[0]==1


def test_http_delivery_forms_and_scoped_detail(flow_db,app_mod):
    c,u,_,path,item=flow_db;rid=approved(c,u,item);old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            form=client.get(f'/supplies/replenishments/{rid}/deliveries/new')
            assert form.status_code==200 and 'Record delivery' in form.text
            line_id=rep.get_replenishment(c,u[1],rid)['lines'][0]['id']
            response=client.post(f'/supplies/replenishments/{rid}/deliveries',data={
                'csrf':hidden(form.text,'csrf'),'operation_key':key(),'revision':'3',
                'supplier':'Synthetic supplier','dr_number':'DR-HTTP','effective_date':'2026-10-20',
                f'item_revision_{line_id}':'1',f'delivered_{line_id}':'4',
                f'accepted_{line_id}':'3',f'rejected_{line_id}':'1',
                f'rejection_reason_{line_id}':'Damaged'},follow_redirects=False)
            assert response.status_code==303
            detail=client.get(response.headers['location'])
            assert detail.status_code==200 and 'Damaged' in detail.text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            assert client.get(response.headers['location']).status_code==404
    finally:app_mod.DB=old
