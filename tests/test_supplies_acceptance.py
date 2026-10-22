"""S6.2 integrated synthetic request-to-report and recovery acceptance."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from starlette.testclient import TestClient

import app
import auth
import backups
import storage as st
import supplies as s
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_issues as issues
import supplies_acknowledgments as ack
import supplies_replenishment as rep
import supplies_replenishment_flow as flow
import supplies_deliveries as deliveries
import supplies_reports as reports
import supplies_stock as stock
import supplies_corrections as corrections
from supplies_storage import Conflict, Denied, Disabled
from tests.test_supplies import supplies_db, key
from tests.test_supplies_requests import request_db, fields
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_replenishment_flow import flow_db
from tests.test_supplies_backorders import cancel
from tests.test_supplies_corrections import correction
from tests.test_supplies_deliveries import payload, post
from tests.conftest import session_token


def _state(c, custodian, item):
    item_row=rep.suggest_replenishment(c,custodian,item)
    return tuple(item_row[name] for name in ('on_hand','reserved','available','outstanding','incoming'))


def _request(c,u,item,owner,requested,approved):
    rid=requests.save_draft(c,u[owner],fields(item,lines=[{'item_id':item,'requested_quantity':requested}]),operation_key=key())['id']
    requests.submit(c,u[owner],rid,expected_revision=1,operation_key=key())
    line=requests.get_request(c,u[owner],rid)['lines'][0]
    result=approvals.decide_request(c,u[3],rid,{'decision':'approved','lines':[
        {'revision_line_id':line['id'],'approved_quantity':approved,
         'reason':'Synthetic reduction after need review' if approved<requested else ''}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    return rid,result


def _issue(c,u,rid,recipient,quantity,op=None):
    entry=requests.get_request(c,u[1],rid)
    line=entry['lines'][0]
    fields={'recipient_id':recipient['id'],'effective_date':'2026-10-20','confirmed':'yes',
            'lines':[{'line_id':line['line_id'],'version':line['reservation_version'],
                      'issued_quantity':quantity}]}
    return issues.post_issue(c,u[1],rid,fields,expected_revision=entry['revision'],operation_key=op or key()),fields,entry['revision']


def _complete(c,u,item):
    assert _state(c,u[1],item)==(10,0,10,0,0)
    a,_=_request(c,u,item,2,8,6)
    assert _state(c,u[1],item)==(10,6,4,6,0)
    assert requests.get_request(c,u[2],a)['approval_status']=='approved'
    b,_=_request(c,u,item,4,7,7)
    assert _state(c,u[1],item)==(10,10,0,13,0)
    assert requests.get_request(c,u[4],b)['lines'][0]['awaiting_stock_quantity']==3
    op=key();first,fields,revision=_issue(c,u,a,u[2],4,op)
    assert issues.post_issue(c,u[1],a,fields,expected_revision=revision,operation_key=op)==first
    assert _state(c,u[1],item)==(6,6,0,9,0)
    cancel(c,u,a)
    assert _state(c,u[1],item)==(6,6,0,7,0)
    assert requests.get_request(c,u[4],b)['lines'][0]['awaiting_stock_quantity']==1
    assert rep.suggest_replenishment(c,u[1],item)['suggested']==21
    rid=rep.save_replenishment(c,u[1],{'purpose':'Synthetic replenishment','procurement_reference':'APR-SYN',
        'lines':[{'item_id':item,'requested_quantity':21,'intended_target':20,
                  'estimated_unit_cost':'2.5000','override_reason':''}]},operation_key=key())['id']
    flow.submit_replenishment(c,u[1],rid,expected_revision=1,operation_key=key())
    submitted=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]
    flow.decide_replenishment(c,u[4],rid,{'decision':'approved','reason':'Synthetic need reviewed',
        'lines':[{'revision_line_id':submitted['id'],'approved_quantity':21,'reason':''}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    assert _state(c,u[1],item)==(6,6,0,7,21)
    first_delivery=post(c,u,rid,payload(c,u,rid,10,dr_number='DR-SYN-1'))
    assert _state(c,u[1],item)==(16,7,9,7,11)
    second,_,_=_issue(c,u,b,u[4],7)
    assert _state(c,u[1],item)==(9,0,9,0,11)
    ack.acknowledge_issue(c,u[4],second['id'],{'status':'acknowledged','note':''},
                          expected_revision=0,operation_key=key())
    final_delivery=post(c,u,rid,payload(c,u,rid,11,dr_number='DR-SYN-2'))
    assert _state(c,u[1],item)==(20,0,20,0,0)
    correction(c,u,'return',second['id'],1)
    assert _state(c,u[1],item)==(21,0,21,0,0)
    assert requests.get_request(c,u[4],b)['fulfillment']=='Fully issued'
    assert [r['balance'] for r in reports.report(c,u[1],'stock-card',item_id=item)['rows']]==[10,6,16,9,20,21]
    inventory=next(r for r in reports.report(c,u[1],'inventory')['rows'] if r['item_id']==item)
    assert (inventory['on_hand'],inventory['reserved'],inventory['available'],inventory['incoming'])==(21,0,21,0)
    assert reports.report(c,u[1],'consumption')['summary'][0]['net_issued']==11
    assert reports.report(c,u[1],'consumption')['summary'][0]['usable_returned']==1
    assert not reports.report(c,u[1],'replenishment')['rows']
    assert [r['issued'] for r in reports.report(c,u[1],'fulfillment')['rows']]==[4,7]
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    return a,b,rid,first,second,first_delivery,final_delivery


def test_full_scenario_reconciles_and_backup_restores_with_other_app_records(flow_db,tmp_path,monkeypatch):
    c,u,_,path,item=flow_db
    a,b,rid,first,second,first_delivery,final_delivery=_complete(c,u,item)
    st.set_setting(c,'other_module_recovery_probe','before backup')
    tables=('admin_user','resource_person','org_unit','app_setting','supply_item','supply_request','supply_issue',
            'supply_delivery','supply_receipt','supply_stock_movement','supply_reservation',
            'supply_event','supply_operation')
    before={name:c.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in tables}
    keys=[r[0] for r in c.execute('SELECT operation_key FROM supply_operation ORDER BY operation_key')]
    events=[tuple(r) for r in c.execute('SELECT entity_type,entity_id,action,operation_key FROM supply_event ORDER BY id')]
    monkeypatch.setattr(backups,'SCHED_DIR',str(tmp_path/'backups'))
    saved=backups.make_backup(path,kind='manual')
    st.set_setting(c,'other_module_recovery_probe','after backup')
    s.create_item(c,u[1],{'code':'AFTER-BACKUP','description':'Synthetic post-snapshot item',
        'unit':'Piece','critical_level':'0','target_level':'1'},operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0]==before['supply_item']+1
    c.close()
    safety=backups.restore_backup(saved['name'],path)
    restored=st.connect(path)
    try:
        assert safety['kind']=='pre_restore'
        assert {name:restored.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in tables}==before
        assert [r[0] for r in restored.execute('SELECT operation_key FROM supply_operation ORDER BY operation_key')]==keys
        assert [tuple(r) for r in restored.execute('SELECT entity_type,entity_id,action,operation_key FROM supply_event ORDER BY id')]==events
        assert st.get_setting(restored,'other_module_recovery_probe')=='before backup'
        assert _state(restored,u[1],item)==(21,0,21,0,0)
        assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert restored.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:restored.close()


def test_delivery_failure_and_independent_connection_contention_are_atomic(flow_db,monkeypatch):
    c,u,_,path,item=flow_db
    rid=rep.save_replenishment(c,u[1],{'purpose':'Synthetic replenishment',
        'lines':[{'item_id':item,'requested_quantity':10,'intended_target':20,
                  'estimated_unit_cost':'2.5000','override_reason':''}]},operation_key=key())['id']
    flow.submit_replenishment(c,u[1],rid,expected_revision=1,operation_key=key())
    submitted=rep.get_replenishment(c,u[1],rid)['submitted_lines'][0]
    flow.decide_replenishment(c,u[4],rid,{'decision':'approved','reason':'',
        'lines':[{'revision_line_id':submitted['id'],'approved_quantity':10,'reason':''}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    before=c.execute('SELECT COUNT(*) FROM supply_operation').fetchone()[0]
    def fail(*args,**kwargs):raise RuntimeError('Synthetic allocator failure')
    original=deliveries.allocate_outstanding
    monkeypatch.setattr(deliveries,'allocate_outstanding',fail)
    with pytest.raises(RuntimeError):post(c,u,rid,payload(c,u,rid,4))
    assert _state(c,u[1],item)==(10,0,10,0,10)
    assert c.execute('SELECT COUNT(*) FROM supply_delivery').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM supply_receipt').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM supply_operation').fetchone()[0]==before
    monkeypatch.setattr(deliveries,'allocate_outstanding',original)
    barrier=Barrier(2)
    def worker():
        conn=st.connect(path)
        try:
            fields=payload(conn,u,rid,8)
            barrier.wait()
            try:return deliveries.receive_delivery(conn,u[1],rid,fields,expected_revision=3,operation_key=key())['id']
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:worker(),range(2)))
    assert len([x for x in outcomes if type(x) is int])==1 and outcomes.count('conflict')==1
    assert _state(c,u[1],item)==(18,0,18,0,2)
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==2


def test_csrf_stale_approval_revocation_and_write_disable_with_report_reads(flow_db):
    c,u,_,path,item=flow_db
    rid=requests.save_draft(c,u[2],fields(item),operation_key=key())['id']
    requests.submit(c,u[2],rid,expected_revision=1,operation_key=key())
    line=requests.get_request(c,u[2],rid)['lines'][0]
    data={'decision':'approved','lines':[{'revision_line_id':line['id'],
                                         'approved_quantity':line['requested_quantity']}]}
    previous=app.DB;app.DB=path
    try:
        client=TestClient(app.app,raise_server_exceptions=True)
        client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
        response=client.post(f'/supplies/requests/{rid}/decide',data={
            'csrf':'invalid','operation_key':key(),'revision':2,'submitted_revision':1,
            'decision':'approved','approved_'+str(line['id']):line['requested_quantity']})
        assert response.status_code==403
        assert c.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==0
    finally:app.DB=previous
    grant=c.execute("SELECT id,revision FROM supply_role_grant WHERE user_id=? AND role='request_approver' AND revoked_at IS NULL",
                    (u[3]['id'],)).fetchone()
    s.revoke_role(c,u[0],grant[0],expected_revision=grant[1],operation_key=key())
    with pytest.raises(Denied):approvals.decide_request(c,u[3],rid,data,
        expected_revision=2,submitted_revision=1,operation_key=key())
    with pytest.raises(Conflict):approvals.decide_request(c,u[4],rid,data,
        expected_revision=1,submitted_revision=1,operation_key=key())
    approvals.decide_request(c,u[4],rid,data,expected_revision=2,submitted_revision=1,operation_key=key())
    assert _state(c,u[1],item)==(10,3,7,3,0)
    s.set_enabled(c,u[0],'0',expected_revision=1,operation_key=key())
    with pytest.raises(Disabled):stock.post_receipt(c,u[1],{'supplier':'Synthetic vendor',
        'effective_date':'2026-10-20','lines':[{'item_id':item,'expected_revision':1,
                                               'accepted_quantity':1}]},operation_key=key())
    assert reports.report(c,u[1],'inventory')['rows'][0]['on_hand']==10
    assert reports.report(c,u[1],'fulfillment')['rows'][0]['approved']==3
    assert _state(c,u[1],item)==(10,3,7,3,0)
