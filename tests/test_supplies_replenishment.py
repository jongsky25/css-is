"""S5.1 calculations and draft obligations."""
import pytest
from starlette.testclient import TestClient
import auth

import supplies as s
import supplies_replenishment as rep
import supplies_stock as stock
import supplies_issues as issues
from supplies_storage import Conflict, Denied, Invalid, Missing
from tests.test_supplies import supplies_db, key, create, hidden
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_requests import request_db
from tests.test_supplies_backorders import ready
from tests.test_supplies_issues import issue
from tests.conftest import session_token


def line(item, quantity, target=20, reason=''):
    return {'item_id':item,'requested_quantity':quantity,'intended_target':target,
            'estimated_unit_cost':'12.3456','override_reason':reason}


def fields(*lines):
    return {'purpose':'Synthetic restocking need','expected_need_date':'2026-11-01',
            'procurement_reference':'APR-SYN-1','lines':list(lines)}


@pytest.mark.usefixtures('unlimited_requests')
def test_plan_scenario_suggestion_counts_outstanding_once_and_incoming_once(approval_db):
    c,u,_,_,item=approval_db
    s.update_item(c,u[1],item,{'code':'PAPER','description':'Synthetic paper','unit':'Ream',
        'critical_level':'5','target_level':'20'},expected_revision=1,operation_key=key())
    a=ready(c,u,item,6); b=ready(c,u,item,7)
    issue(c,u,a,4)
    # Cancel A's two unissued units so B inherits the remaining reservations.
    from tests.test_supplies_backorders import cancel
    cancel(c,u,a)
    snap=rep.suggest_replenishment(c,u[1],item)
    assert (snap['on_hand'],snap['reserved'],snap['available'],snap['outstanding'],snap['incoming'],snap['suggested'])==(6,6,0,7,0,21)
    draft=rep.save_replenishment(c,u[1],fields(line(item,21)),operation_key=key())
    assert rep.get_replenishment(c,u[1],draft['id'])['lines'][0]['suggested_quantity']==21
    assert rep.suggest_replenishment(c,u[1],item)['suggested']==21
    assert rep.suggest_replenishment(c,u[1],item)['open_records'][0]['id']==draft['id']
    assert c.execute('SELECT COUNT(*) FROM supply_replenishment_commitment').fetchone()[0]==0
    # S5.2 commitment shape: approved incoming is net of accepted and cancelled units.
    c.execute("UPDATE supply_replenishment SET status='approved' WHERE id=?",(draft['id'],))
    line_id=c.execute('SELECT id FROM supply_replenishment_line WHERE replenishment_id=?',(draft['id'],)).fetchone()[0]
    c.execute('INSERT INTO supply_replenishment_commitment(line_id,approved_quantity) VALUES (?,21)',(line_id,));c.commit()
    snap=rep.suggest_replenishment(c,u[1],item)
    assert snap['incoming']==21 and snap['suggested']==0
    assert 'incoming' in snap['explanation']
    c.execute('UPDATE supply_replenishment_commitment SET received_quantity=10 WHERE line_id=?',(line_id,));c.commit()
    snap=rep.suggest_replenishment(c,u[1],item)
    assert snap['incoming']==11 and snap['suggested']==10  # Stock receipt itself belongs to S5.3.


def test_missing_target_requires_manual_input_and_override_requires_reason(approval_db):
    c,u,_,_,item=approval_db
    s.update_item(c,u[1],item,{'code':'PAPER','description':'Synthetic paper','unit':'Ream',
        'critical_level':'5','target_level':''},expected_revision=1,operation_key=key())
    snap=rep.suggest_replenishment(c,u[1],item)
    assert snap['suggested'] is None and snap['explanation']=='Set target or enter quantity'
    with pytest.raises(Invalid):rep.save_replenishment(c,u[1],fields(line(item,10,target=5)),operation_key=key())
    result=rep.save_replenishment(c,u[1],fields(line(item,10,target=5,reason='One extra case')),operation_key=key())
    assert rep.get_replenishment(c,u[1],result['id'])['lines'][0]['intended_target']==5
    assert s._item(c,item)['target_level'] is None


def test_combined_draft_edit_idempotency_and_deactivation_obligation(approval_db):
    c,u,_,_,item=approval_db
    other=create(c,u[1],code='OTHER')['id']
    payload=fields(line(item,10,reason='Synthetic extra stock'),line(other,3,reason='Synthetic backup'))
    op=key();created=rep.save_replenishment(c,u[1],payload,operation_key=op)
    assert rep.save_replenishment(c,u[1],payload,operation_key=op)==created
    assert len(rep.get_replenishment(c,u[1],created['id'])['lines'])==2
    with pytest.raises(Conflict):rep.save_replenishment(c,u[1],fields(line(item,11,reason='Changed')),
                                                        operation_key=op)
    with pytest.raises(Conflict):s.deactivate_item(c,u[1],item,expected_revision=1,reason='Synthetic cleanup',operation_key=key())
    changed=rep.save_replenishment(c,u[1],fields(line(other,4,reason='Adjusted')),
             replenishment_id=created['id'],expected_revision=1,operation_key=key())
    assert changed['revision']==2
    assert [l['item_id'] for l in rep.get_replenishment(c,u[1],created['id'])['lines']]==[other]
    with pytest.raises(Conflict):rep.save_replenishment(c,u[1],payload,replenishment_id=created['id'],expected_revision=1,operation_key=key())
    assert s.deactivate_item(c,u[1],item,expected_revision=1,reason='Synthetic cleanup',operation_key=key())['active']==0


def test_roles_and_disabled_mode_keep_draft_private(approval_db):
    c,u,_,_,item=approval_db
    created=rep.save_replenishment(c,u[1],fields(line(item,10,reason='Synthetic restocking')),
                                   operation_key=key())
    with pytest.raises(Denied):rep.suggest_replenishment(c,u[2],item)
    with pytest.raises(Missing):rep.get_replenishment(c,u[3],created['id'])
    with pytest.raises(Denied):rep.save_replenishment(c,u[3],fields(line(item,10,reason='No grant')),operation_key=key())
    assert rep.list_replenishments(c,u[1])[0]['id']==created['id']
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    assert rep.get_replenishment(c,u[1],created['id'])['id']==created['id']
    with pytest.raises(Conflict):rep.save_replenishment(c,u[1],fields(line(item,10,reason='Disabled')),operation_key=key())


def test_invalid_lines_and_target_override_leave_no_partial_draft(approval_db):
    c,u,_,_,item=approval_db
    for payload in (fields(line(item,10,target=30)), fields(line(item,10),line(item,11)),
                    fields({**line(item,10),'estimated_unit_cost':'1.12345'}),
                    fields(line(item,1,target=4,reason='Too low'))):
        with pytest.raises(Invalid):rep.save_replenishment(c,u[1],payload,operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_replenishment').fetchone()[0]==0


def test_replenishment_http_form_save_and_read_scope(approval_db,app_mod):
    c,u,_,path,item=approval_db;old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            page=client.get('/supplies/replenishments/new?item='+str(item))
            assert page.status_code==200 and 'Prepare replenishment draft' in page.text
            assert 'name="target_0" value="20"' in page.text
            data={'csrf':hidden(page.text,'csrf'),'operation_key':key(),'purpose':'Synthetic needs',
                  'expected_need_date':'2026-11-01','procurement_reference':'APR-TEST',
                  'item_id_0':str(item),'quantity_0':'10','target_0':'20','cost_0':'2.5000',
                  'reason_0':'Extra contingency'}
            for i in range(1,20):
                data.update({f'item_id_{i}':'',f'quantity_{i}':'',f'target_{i}':'',
                             f'cost_{i}':'',f'reason_{i}':''})
            result=client.post('/supplies/replenishments',data=data,follow_redirects=False)
            assert result.status_code==303
            detail=client.get(result.headers['location'])
            assert detail.status_code==200 and 'APR-TEST' in detail.text and 'Extra contingency' in detail.text
            assert client.get('/supplies/replenishments').status_code==200
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            assert client.get(result.headers['location']).status_code==404
            assert client.get('/supplies/replenishments').status_code==403
    finally:app_mod.DB=old
