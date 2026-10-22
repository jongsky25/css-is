"""S5.2 immutable submissions, independent approval and incoming accounting."""
import pytest
from starlette.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import auth
import storage as st
import supplies as s
import supplies_replenishment as rep
import supplies_replenishment_flow as flow
from supplies_storage import Conflict, Denied, Invalid, Missing
from tests.test_supplies import key, hidden, supplies_db
from tests.test_supplies_requests import request_db
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_replenishment import line,fields
from tests.conftest import session_token


def prepared(c,u,item,quantity=10,reason=''):
    return rep.save_replenishment(c,u[1],fields(line(item,quantity,reason=reason)),operation_key=key())['id']


def submitted(c,u,item,quantity=10,reason='',review_reason=''):
    rid=prepared(c,u,item,quantity,reason)
    flow.submit_replenishment(c,u[1],rid,expected_revision=1,operation_key=key(),review_reason=review_reason)
    return rid


def approve(c,u,rid,quantity=10,reason='',line_reason=''):
    line_id=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]['id']
    return flow.decide_replenishment(c,u[4],rid,{'decision':'approved','reason':reason,
        'lines':[{'revision_line_id':line_id,'approved_quantity':quantity,'reason':line_reason}]},
        expected_revision=2,submitted_revision=1,operation_key=key())


@pytest.fixture
def flow_db(approval_db):
    c,u,units,path,item=approval_db
    s.grant_role(c,u[0],u[4]['id'],'replenishment_approver',operation_key=key())
    return c,u,units,path,item


def test_submit_approve_order_cancel_counts_incoming_once_without_stock_change(flow_db):
    c,u,_,_,item=flow_db;rid=prepared(c,u,item)
    stock_before=[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    op=key();first=flow.submit_replenishment(c,u[1],rid,expected_revision=1,operation_key=op)
    assert flow.submit_replenishment(c,u[1],rid,expected_revision=1,operation_key=op)==first
    assert first['control_number'].startswith('REP-') and first['current_revision']==1
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==0
    decision=approve(c,u,rid)
    assert decision['status']=='approved' and rep.suggest_replenishment(c,u[1],item)['incoming']==10
    assert rep.suggest_replenishment(c,u[1],item)['suggested']==0
    detail=rep.get_replenishment(c,u[1],rid)
    line_id=detail['lines'][0]['id']
    order_fields={'order_reference':'PO-SYN-1','expected_delivery_date':'2026-11-05',
        'responsible_custodian_id':u[1]['id'],'lines':[{'line_id':line_id,'ordered_quantity':7}]}
    order_key=key()
    order=flow.record_order(c,u[1],rid,order_fields,expected_revision=3,operation_key=order_key)
    assert flow.record_order(c,u[1],rid,order_fields,expected_revision=3,operation_key=order_key)==order
    assert order['status']=='ordered' and rep.suggest_replenishment(c,u[1],item)['incoming']==10
    cancel_fields={'reason':'Supplier shortage','lines':[{'line_id':line_id,'cancelled_quantity':4}]}
    cancel_key=key()
    partial=flow.cancel_replenishment_remainder(c,u[1],rid,cancel_fields,expected_revision=4,operation_key=cancel_key)
    assert flow.cancel_replenishment_remainder(c,u[1],rid,cancel_fields,expected_revision=4,operation_key=cancel_key)==partial
    assert partial['remaining_incoming']==6 and rep.suggest_replenishment(c,u[1],item)['incoming']==6
    final=flow.cancel_replenishment_remainder(c,u[1],rid,{'reason':'Alternative source closed need',
        'lines':[{'line_id':line_id,'cancelled_quantity':6}]},expected_revision=5,operation_key=key())
    assert final['status']=='cancelled' and final['remaining_incoming']==0
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==0
    assert stock_before==[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    assert len(rep.get_replenishment(c,u[1],rid)['cancellations'])==2


def test_return_edit_resubmit_preserves_old_revision_and_decision(flow_db):
    c,u,_,_,item=flow_db;rid=submitted(c,u,item)
    returned=flow.decide_replenishment(c,u[4],rid,{'decision':'returned','reason':'Explain one extra ream'},
        expected_revision=2,submitted_revision=1,operation_key=key())
    assert returned['status']=='returned' and rep.suggest_replenishment(c,u[1],item)['incoming']==0
    old_lines=[tuple(row) for row in c.execute('SELECT * FROM supply_replenishment_revision_line')]
    private=fields(line(item,11,reason='Extra contingency'))
    private['purpose']='Private returned draft correction'
    edited=rep.save_replenishment(c,u[1],private,
        replenishment_id=rid,expected_revision=3,operation_key=key())
    assert edited['revision']==4
    assert rep.get_replenishment(c,u[4],rid)['purpose']=='Synthetic restocking need'
    assert 'Private returned draft correction' not in str(rep.list_replenishments(c,u[4]))
    with pytest.raises(Invalid):flow.submit_replenishment(c,u[1],rid,expected_revision=4,operation_key=key())
    resubmitted=flow.submit_replenishment(c,u[1],rid,expected_revision=4,operation_key=key(),review_reason='Need extra contingency')
    assert resubmitted['current_revision']==2 and resubmitted['control_number']==rep.get_replenishment(c,u[1],rid)['control_number']
    assert old_lines==[tuple(row) for row in c.execute('SELECT * FROM supply_replenishment_revision_line WHERE revision_id=1')]
    with pytest.raises(Conflict):flow.decide_replenishment(c,u[4],rid,{'decision':'rejected','reason':'Old form'},
        expected_revision=2,submitted_revision=1,operation_key=key())
    new_line=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]['id']
    approved=flow.decide_replenishment(c,u[4],rid,{'decision':'approved','reason':'Reviewed extra need',
        'lines':[{'revision_line_id':new_line,'approved_quantity':11,'reason':''}]},
        expected_revision=5,submitted_revision=2,operation_key=key())
    assert approved['status']=='approved' and rep.suggest_replenishment(c,u[1],item)['incoming']==11
    assert len(rep.get_replenishment(c,u[1],rid)['decisions'])==2


def test_overlap_requires_reason_at_submission_and_decision(flow_db):
    c,u,_,_,item=flow_db;first=submitted(c,u,item);approve(c,u,first)
    second=prepared(c,u,item,5,reason='Additional emergency stock')
    with pytest.raises(Invalid):flow.submit_replenishment(c,u[1],second,expected_revision=1,operation_key=key())
    flow.submit_replenishment(c,u[1],second,expected_revision=1,operation_key=key(),review_reason='Separate urgent order')
    line_id=rep.get_replenishment(c,u[1],second)['submitted_lines'][0]['id']
    decision={'decision':'approved','lines':[{'revision_line_id':line_id,'approved_quantity':5,'reason':''}]}
    with pytest.raises(Invalid):flow.decide_replenishment(c,u[4],second,decision,
        expected_revision=2,submitted_revision=1,operation_key=key())
    decision['reason']='Reviewed overlap with first approved replenishment'
    flow.decide_replenishment(c,u[4],second,decision,expected_revision=2,submitted_revision=1,operation_key=key())
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==15


def test_independent_grant_self_approval_and_invalid_actions(flow_db):
    c,u,_,_,item=flow_db;rid=submitted(c,u,item)
    line_id=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]['id']
    decision={'decision':'approved','lines':[{'revision_line_id':line_id,'approved_quantity':10,'reason':''}]}
    with pytest.raises(Denied):flow.decide_replenishment(c,u[3],rid,decision,
        expected_revision=2,submitted_revision=1,operation_key=key())
    s.grant_role(c,u[0],u[1]['id'],'replenishment_approver',operation_key=key())
    with pytest.raises(Denied):flow.decide_replenishment(c,u[1],rid,decision,
        expected_revision=2,submitted_revision=1,operation_key=key())
    with pytest.raises(Invalid):flow.decide_replenishment(c,u[4],rid,
        {'decision':'approved','lines':[{'revision_line_id':line_id,'approved_quantity':9,'reason':''}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==0
    approve(c,u,rid)
    with pytest.raises(Invalid):flow.record_order(c,u[1],rid,{'order_reference':'PO-SYN','expected_delivery_date':'2026-11-05','responsible_custodian_id':u[3]['id'],
        'lines':[{'line_id':rep.get_replenishment(c,u[1],rid)['lines'][0]['id'],'ordered_quantity':10}]},
        expected_revision=3,operation_key=key())
    with pytest.raises(Invalid):flow.cancel_replenishment_remainder(c,u[1],rid,{'reason':'Too many',
        'lines':[{'line_id':rep.get_replenishment(c,u[1],rid)['lines'][0]['id'],'cancelled_quantity':11}]},
        expected_revision=3,operation_key=key())
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==10


def test_reduced_approval_and_rejection_keep_separate_evidence(flow_db):
    c,u,_,_,item=flow_db;first=submitted(c,u,item)
    line_id=rep.get_replenishment(c,u[1],first)['submitted_lines'][0]['id']
    reduced=flow.decide_replenishment(c,u[4],first,{'decision':'approved','reason':'Only six needed now',
        'lines':[{'revision_line_id':line_id,'approved_quantity':6,'reason':'Reduced after count'}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    assert reduced['status']=='approved' and rep.suggest_replenishment(c,u[1],item)['incoming']==6
    second=prepared(c,u,item,4,reason='Separate anticipated need')
    flow.submit_replenishment(c,u[1],second,expected_revision=1,operation_key=key(),review_reason='Reviewing overlap')
    rejected=flow.decide_replenishment(c,u[4],second,{'decision':'rejected','reason':'Existing approval covers need'},
        expected_revision=2,submitted_revision=1,operation_key=key())
    assert rejected['status']=='rejected' and rep.suggest_replenishment(c,u[1],item)['incoming']==6
    assert c.execute("SELECT COUNT(*) FROM supply_replenishment_decision WHERE decision='rejected'").fetchone()[0]==1


def test_competing_decisions_commit_only_one_incoming_projection(flow_db):
    c,u,_,path,item=flow_db;rid=submitted(c,u,item)
    line_id=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]['id']
    barrier=Barrier(2)
    def attempt():
        db=st.connect(path)
        try:
            barrier.wait()
            return flow.decide_replenishment(db,u[4],rid,{'decision':'approved','reason':'',
                'lines':[{'revision_line_id':line_id,'approved_quantity':10,'reason':''}]},
                expected_revision=2,submitted_revision=1,operation_key=key())['status']
        except Conflict:return 'conflict'
        finally:db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:attempt(),range(2)))
    assert sorted(outcomes)==['approved','conflict']
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==10
    assert c.execute('SELECT COUNT(*) FROM supply_replenishment_decision').fetchone()[0]==1


def test_revoked_approver_and_disabled_mode_block_decision_but_keep_owner_read(flow_db):
    c,u,_,_,item=flow_db;rid=submitted(c,u,item)
    line_id=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]['id']
    decision={'decision':'approved','lines':[{'revision_line_id':line_id,'approved_quantity':10,'reason':''}]}
    grant=c.execute("SELECT id FROM supply_role_grant WHERE user_id=? AND role='replenishment_approver' AND revoked_at IS NULL",(u[4]['id'],)).fetchone()[0]
    s.revoke_role(c,u[0],grant,expected_revision=1,operation_key=key())
    with pytest.raises(Denied):flow.decide_replenishment(c,u[4],rid,decision,
        expected_revision=2,submitted_revision=1,operation_key=key())
    with pytest.raises(Missing):rep.get_replenishment(c,u[4],rid)
    s.grant_role(c,u[0],u[4]['id'],'replenishment_approver',operation_key=key())
    s.set_enabled(c,u[0],'0',expected_revision=1,operation_key=key())
    assert rep.get_replenishment(c,u[1],rid)['status']=='submitted'
    with pytest.raises(Conflict):flow.decide_replenishment(c,u[4],rid,decision,
        expected_revision=2,submitted_revision=1,operation_key=key())
    assert rep.suggest_replenishment(c,u[1],item)['incoming']==0


def test_http_submit_decide_and_current_scopes(flow_db,app_mod):
    c,u,_,path,item=flow_db;rid=prepared(c,u,item);old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            detail=client.get(f'/supplies/replenishments/{rid}')
            assert detail.status_code==200 and 'Submit replenishment' in detail.text
            submit=client.post(f'/supplies/replenishments/{rid}/submit',data={
                'csrf':hidden(detail.text,'csrf'),'operation_key':key(),'revision':'1','review_reason':''},follow_redirects=False)
            assert submit.status_code==303
            client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
            assert 'Record replenishment decision' not in client.get(f'/supplies/replenishments/{rid}').text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
            detail=client.get(f'/supplies/replenishments/{rid}')
            assert detail.status_code==200 and 'Record replenishment decision' in detail.text
            line_id=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]['id']
            decided=client.post(f'/supplies/replenishments/{rid}/decide',data={
                'csrf':hidden(detail.text,'csrf'),'operation_key':key(),'revision':'2','submitted_revision':'1',
                'decision':'approved','reason':'',f'approved_{line_id}':'10',f'line_reason_{line_id}':''},follow_redirects=False)
            assert decided.status_code==303
            assert rep.suggest_replenishment(c,u[1],item)['incoming']==10
    finally:app_mod.DB=old
