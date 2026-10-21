"""S3.1 atomic partial handovers, immutable release evidence and current permissions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_stock as stock
import supplies_requests as requests
import supplies_issues as issues
import supplies_allocations as allocations
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing
from tests.test_supplies import supplies_db, key, create, hidden
from tests.test_supplies_requests import request_db, draft, submit, get
from tests.test_supplies_approvals import approval_db, decide
from tests.test_supplies_backorders import ready, cancel, receipt
from tests.conftest import session_token


def data(c,u,r,quantity=1,**changes):
    entry=requests.get_request(c,u[1],r)
    return {'recipient_id':u[2]['id'],'effective_date':'2026-10-19','confirmed':'yes',
            'lines':[{'line_id':entry['lines'][0]['line_id'],'version':entry['lines'][0]['reservation_version'],
                      'issued_quantity':quantity}],**changes}


def issue(c,u,r,quantity=1,**kw):
    entry=requests.get_request(c,u[1],r)
    return issues.post_issue(c,kw.pop('actor',u[1]),r,kw.pop('fields',data(c,u,r,quantity)),
        expected_revision=kw.pop('expected_revision',entry['revision']),operation_key=kw.pop('operation_key',key()),**kw)


def test_two_partial_releases_stock_and_request_totals_replay(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,6)
    original=[tuple(row) for row in c.execute('SELECT * FROM supply_request_decision_line')]
    fields=data(c,u,r,4);op=key();first=issue(c,u,r,fields=fields,operation_key=op)
    assert first['release_number']=='ISS-2026-00001'
    assert issue(c,u,r,fields=fields,expected_revision=3,operation_key=op)==first
    line=get(c,u,r)['lines'][0]
    assert (line['approved_quantity'],line['effective_issued_quantity'],line['reserved_quantity'],line['outstanding_quantity'])==(6,4,2,2)
    assert get(c,u,r)['fulfillment']=='Partially issued'
    second=issue(c,u,r,2)
    assert second['release_number']=='ISS-2026-00002'
    assert get(c,u,r)['fulfillment']=='Fully issued' and get(c,u,r)['approval_status']=='approved'
    assert stock.stock_totals(c,u[1],item)['on_hand']==4
    assert allocations.availability(c,item)['reserved_quantity']==0
    assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==3
    assert original==[tuple(row) for row in c.execute('SELECT * FROM supply_request_decision_line')]
    assert not issues.issuance_queue(c,u[1])['requests']


@pytest.mark.parametrize('bad',['zero','negative','fraction','boolean','over_reserved','foreign','duplicate','stale_version','stale_request','future_date','unconfirmed'])
def test_invalid_issue_leaves_no_release_movement_or_number(approval_db,bad):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);fields=data(c,u,r,2);revision=3
    if bad=='zero':fields['lines'][0]['issued_quantity']=0
    elif bad=='negative':fields['lines'][0]['issued_quantity']=-1
    elif bad=='fraction':fields['lines'][0]['issued_quantity']='1.5'
    elif bad=='boolean':fields['lines'][0]['issued_quantity']=True
    elif bad=='over_reserved':fields['lines'][0]['issued_quantity']=4
    elif bad=='foreign':fields['lines'][0]['line_id']=999
    elif bad=='duplicate':fields['lines']*=2
    elif bad=='stale_version':fields['lines'][0]['version']=999
    elif bad=='stale_request':revision=2
    elif bad=='future_date':fields['effective_date']='2099-01-01'
    else:fields['confirmed']=''
    with pytest.raises((Invalid,Conflict)):issue(c,u,r,fields=fields,expected_revision=revision)
    assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM supply_sequence WHERE kind='ISS'").fetchone()[0]==0
    assert stock.stock_totals(c,u[1],item)['on_hand']==10


@pytest.mark.parametrize('who',[0,2,3,4])
def test_only_current_custodian_can_issue(approval_db,who):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3)
    with pytest.raises(Denied):issue(c,u,r,actor=u[who])
    with pytest.raises(Denied):issues.issuance_queue(c,u[who])


def test_unapproved_unreserved_and_cancelled_demand_cannot_be_issued(approval_db):
    c,u,_,_,item=approval_db;r=draft(c,u,item);submit(c,u,r)
    with pytest.raises(Conflict):issue(c,u,r,fields={'recipient_id':u[2]['id'],'effective_date':'2026-10-19','confirmed':'yes',
        'lines':[{'line_id':get(c,u,r)['lines'][0]['line_id'],'version':1,'issued_quantity':1}]})
    a=ready(c,u,item,10);b=ready(c,u,item,3)
    with pytest.raises(Conflict):issue(c,u,b)
    cancel(c,u,a)
    cancel(c,u,b)
    with pytest.raises(Conflict):issue(c,u,b)


def test_alternate_recipient_requires_reason_and_gets_only_assigned_release(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3)
    # Remove the alternate's independent approval rights to test only recipient access.
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[4]['id']));c.commit()
    with pytest.raises(Invalid,match='alternate recipient'):issue(c,u,r,fields=data(c,u,r,2,recipient_id=u[4]['id']))
    first=issue(c,u,r,fields=data(c,u,r,2,recipient_id=u[4]['id'],alternate_reason='Collected by designated colleague'))
    second=issue(c,u,r,1)
    assert issues.get_issue(c,u[4],first['id'])['recipient_id']==u[4]['id']
    assert [entry['id'] for entry in issues.list_issues(c,u[4])['releases']]==[first['id']]
    with pytest.raises(Missing):requests.get_request(c,u[4],r)
    with pytest.raises(Missing):issues.get_issue(c,u[4],second['id'])
    assert issues.get_issue(c,u[2],first['id'])['recipient_snapshot']=='Synthetic requester 4'


@pytest.mark.parametrize('change',['inactive','external','archived','unitless','unlinked'])
def test_recipient_linkage_reloaded_before_posting(approval_db,change):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);rp=u[2]['rp_id']
    if change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],))
    elif change=='external':c.execute('UPDATE resource_person SET is_internal=0 WHERE id=?',(rp,))
    elif change=='archived':c.execute("UPDATE resource_person SET archived_at='2026-10-20' WHERE id=?",(rp,))
    elif change=='unitless':c.execute('UPDATE resource_person SET org_unit_id=NULL WHERE id=?',(rp,))
    else:c.execute('UPDATE admin_user SET rp_id=NULL WHERE id=?',(u[2]['id'],))
    c.commit()
    with pytest.raises(Invalid,match='active internal staff'):issue(c,u,r)
    assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==0


def test_posted_snapshots_immutable_and_role_read_revocation(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);result=issue(c,u,r,2)
    c.execute("UPDATE resource_person SET name='Later directory name' WHERE id=?",(u[2]['rp_id'],))
    c.execute("UPDATE supply_item SET description='Later catalog description' WHERE id=?",(item,));c.commit()
    posted=issues.get_issue(c,u[2],result['id'])
    assert posted['recipient_snapshot']=='Synthetic requester 2' and posted['lines'][0]['description_snapshot']=='Synthetic paper'
    for table in ('supply_issue','supply_issue_line'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(f'DELETE FROM {table}')
        c.rollback()
    assert issues.get_issue(c,u[3],result['id'])
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",(u[0]['id'],u[3]['id']));c.commit()
    with pytest.raises(Missing):issues.get_issue(c,u[3],result['id'])
    assert not issues.list_issues(c,u[3])['releases']


def test_number_exhaustion_and_mid_issue_failure_roll_back_all(approval_db,monkeypatch):
    c,u,_,_,item=approval_db;other=create(c,u[1],code='SECOND')['id']
    stock.post_opening(c,u[1],other,{'quantity':5,'effective_date':'2026-10-19','reason':'Synthetic count'},expected_revision=1,operation_key=key())
    r=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':2},{'item_id':other,'requested_quantity':2}]);submit(c,u,r);decide(c,u,r)
    c.execute("INSERT INTO supply_sequence VALUES ('ISS',2026,99999)");c.commit()
    with pytest.raises(Conflict,match='limit'):issue(c,u,r)
    c.execute("DELETE FROM supply_sequence WHERE kind='ISS'");c.commit()
    fields=data(c,u,r);fields['lines']=[{'line_id':line['line_id'],'version':line['reservation_version'],'issued_quantity':2} for line in get(c,u,r)['lines']]
    original=stock._add_movement
    def fail(conn,user,item,**kw):
        if item['id']==other:raise RuntimeError('Synthetic second line failure')
        return original(conn,user,item,**kw)
    monkeypatch.setattr(stock,'_add_movement',fail)
    with pytest.raises(RuntimeError):issue(c,u,r,fields=fields)
    assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==2
    assert c.execute("SELECT COUNT(*) FROM supply_sequence WHERE kind='ISS'").fetchone()[0]==0
    assert all(line['effective_issued_quantity']==0 for line in get(c,u,r)['lines'])


def test_two_connections_compete_for_last_reserved_units(approval_db):
    c,u,_,path,item=approval_db;r=ready(c,u,item,10);fields=data(c,u,r,10);barrier=Barrier(2)
    def worker(_):
        conn=st.connect(path)
        try:
            barrier.wait()
            try:return issues.post_issue(conn,u[1],r,fields,expected_revision=3,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
    assert sum(isinstance(result,dict) for result in results)==1 and results.count('conflict')==1
    assert allocations.availability(c,item)=={'on_hand':0,'reserved_quantity':0,'available':0}
    assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==1


def test_receipt_stales_form_then_issue_and_cancel_reconcile(approval_db):
    c,u,_,_,item=approval_db;a=ready(c,u,item,6);b=ready(c,u,item,7);old=data(c,u,b,2)
    receipt(c,u,item,2)
    with pytest.raises(Conflict,match='Reservations changed'):issue(c,u,b,fields=old)
    issue(c,u,a,4);cancel(c,u,a)
    assert get(c,u,a)['fulfillment']=='Closed with remainder cancelled'
    issue(c,u,b,7)
    assert get(c,u,b)['fulfillment']=='Fully issued'
    assert stock.stock_totals(c,u[1],item)['on_hand']==1
    assert not allocations.availability(c,item)['reserved_quantity']


def test_audit_and_allocator_failure_rollback_and_disabled_retry(approval_db,monkeypatch):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3)
    def fail(*args,**kwargs):raise RuntimeError('Synthetic failure')
    for target in ('audit','allocator'):
        with monkeypatch.context() as patch:
            patch.setattr(st if target=='audit' else issues,'audit' if target=='audit' else 'allocate_outstanding',fail)
            with pytest.raises(RuntimeError):issue(c,u,r,2)
        assert stock.stock_totals(c,u[1],item)['on_hand']==10
        assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==0
    fields=data(c,u,r,2);op=key();issue(c,u,r,fields=fields,operation_key=op)
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    assert issues.get_issue(c,u[2],1)
    with pytest.raises(Disabled):issue(c,u,r,fields=fields,expected_revision=3,operation_key=op)


def test_http_post_and_recipient_read_csrf_and_no_owner_write(approval_db,app_mod):
    c,u,_,path,item=approval_db;r=ready(c,u,item,6);old=app_mod.DB;app_mod.DB=path;target=f'/supplies/requests/{r}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            assert 'SUP-2026-00001' in client.get('/supplies/issuance').text
            page=client.get(target+'/issues/new');assert page.status_code==200
            line=get(c,u,r)['lines'][0];token=hidden(page.text,'csrf')
            fields={'csrf':token,'operation_key':key(),'revision':'3','recipient_id':str(u[2]['id']),
                'effective_date':'2026-10-19','confirmed':'yes',f"issue_quantity_{line['line_id']}":'4',f"version_{line['line_id']}":str(line['reservation_version'])}
            assert client.post(target+'/issues',data={**fields,'csrf':'bad'}).status_code==403
            assert client.post(target+'/issues',data=fields,headers={'Origin':'https://foreign.example'}).status_code==403
            response=client.post(target+'/issues',data=fields,follow_redirects=False);assert response.status_code==303
            assert client.post(target+'/issues',data=fields,follow_redirects=False).headers['location']==response.headers['location']
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            page=client.get(response.headers['location']);assert 'ISS-2026-00001' in page.text and 'Synthetic requester 2' in page.text
            assert client.get(target+'/issues/new').status_code==403
            assert 'ISS-2026-00001' in client.get(target).text
    finally:app_mod.DB=old


def test_multiline_handover_and_movement_match_guard(approval_db):
    c,u,_,_,item=approval_db;other=create(c,u[1],code='SECOND')['id']
    stock.post_opening(c,u[1],other,{'quantity':5,'effective_date':'2026-10-19','reason':'Synthetic count'},expected_revision=1,operation_key=key())
    r=draft(c,u,item,lines=[{'item_id':item,'requested_quantity':2},{'item_id':other,'requested_quantity':3}]);submit(c,u,r);decide(c,u,r)
    fields=data(c,u,r);fields['lines']=[{'line_id':line['line_id'],'version':line['reservation_version'],
        'issued_quantity':line['reserved_quantity']} for line in get(c,u,r)['lines']]
    result=issue(c,u,r,fields=fields);release=issues.get_issue(c,u[2],result['id'])
    assert len(release['lines'])==2 and get(c,u,r)['fulfillment']=='Fully issued'
    assert stock.stock_totals(c,u[1],item)['on_hand']==8 and stock.stock_totals(c,u[1],other)['on_hand']==2
    source=release['lines'][0]
    with pytest.raises(sqlite3.IntegrityError,match='match its stock movement'):
        c.execute('''INSERT INTO supply_issue_line
          (id,issue_id,line_id,revision_line_id,reservation_id,item_id,issued_quantity,code_snapshot,description_snapshot,unit_snapshot,movement_id)
          VALUES (999,?,?,?,?,?,?,?,?,?,?)''',(source['issue_id'],source['line_id'],source['revision_line_id'],source['reservation_id'],source['item_id'],
          source['issued_quantity']+1,source['code_snapshot'],source['description_snapshot'],source['unit_snapshot'],source['movement_id']))
    c.rollback()
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_revoked_custodian_cannot_replay_and_changed_payload_conflicts(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,3);fields=data(c,u,r,2);op=key()
    issue(c,u,r,fields=fields,operation_key=op)
    with pytest.raises(Conflict):issue(c,u,r,fields={**fields,'note':'Different intent'},expected_revision=3,operation_key=op)
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'",(u[0]['id'],u[1]['id']));c.commit()
    with pytest.raises(Denied):issues.post_issue(c,u[1],r,fields,expected_revision=3,operation_key=op)
    assert stock.stock_totals(c,u[2],item)['on_hand']==8


def test_issuance_and_release_pagination_and_repeated_install(approval_db):
    from supplies_storage import install
    c,u,_,_,item=approval_db;receipt(c,u,item,30)
    ids=[ready(c,u,item,1) for _ in range(26)]
    first=issues.issuance_queue(c,u[1]);second=issues.issuance_queue(c,u[1],page=2)
    assert len(first['requests'])==25 and first['has_next'] and len(second['requests'])==1
    for r in ids:issue(c,u,r,1)
    first=issues.list_issues(c,u[2]);second=issues.list_issues(c,u[2],page=2)
    assert len(first['releases'])==25 and first['has_next'] and len(second['releases'])==1
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_issue_line ORDER BY id')]
    install(c);install(c)
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_issue_line ORDER BY id')]
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_http_stale_issue_preserves_submitted_quantity_and_versions(approval_db,app_mod):
    c,u,_,path,item=approval_db;r=ready(c,u,item,3);old=app_mod.DB;app_mod.DB=path;target=f'/supplies/requests/{r}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]));page=client.get(target+'/issues/new');line=get(c,u,r)['lines'][0]
            fields={'csrf':hidden(page.text,'csrf'),'operation_key':key(),'revision':'3','recipient_id':str(u[2]['id']),
              'effective_date':'2026-10-19','confirmed':'yes',f"issue_quantity_{line['line_id']}":'2',f"version_{line['line_id']}":str(line['reservation_version'])}
            issue(c,u,r,1)
            response=client.post(target+'/issues',data=fields)
            assert response.status_code==409 and 'value="2"' in response.text
            assert hidden(response.text,'revision')=='3'
            assert hidden(response.text,f"version_{line['line_id']}")==str(line['reservation_version'])
            assert c.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==1
    finally:app_mod.DB=old
