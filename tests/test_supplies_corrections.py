"""S3.3 correction arithmetic, stale previews, authorization, audit and HTTP workflows."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies_corrections as corrections
import supplies_stock as stock
import supplies_allocations as allocations
import supplies_requests as requests
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing, install
from tests.test_supplies import supplies_db, key, create, hidden
from tests.test_supplies_requests import request_db, get
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_backorders import ready, cancel, receipt
from tests.test_supplies_issues import issue
from tests.conftest import session_token


def correction(c,u,kind,parent,quantity,*,actor=None,fields=None,**kw):
    data={'quantity':str(quantity),'effective_date':'2026-10-20','reason':'Synthetic correction evidence'}
    if kind!='stocktake':
        data['source_line_id']=corrections.form_context(c,u[1],kind,parent)['source_lines'][0]['id']
    if kind=='return':data['condition']='usable'
    if kind=='issue_reversal':data['reopen_demand']='yes'
    data.update(fields or {})
    impact=corrections.preview(c,u[1],kind,parent,data)
    return corrections._post(c,actor or u[1],kind,parent,{**data,'preview_token':impact['preview_token'],'confirmed':'yes'},
                             operation_key=kw.pop('operation_key',key()),**kw)


def released(c,u,item,quantity=6):
    r=ready(c,u,item,quantity)
    return r,issue(c,u,r,quantity)['id']


def test_genuine_usable_and_unusable_returns_never_reopen_demand(approval_db):
    c,u,_,_,item=approval_db;r,release=released(c,u,item)
    correction(c,u,'return',release,2)
    correction(c,u,'return',release,1,fields={'condition':'unusable'})
    assert stock.stock_totals(c,u[1],item)['on_hand']==6
    assert get(c,u,r)['fulfillment']=='Fully issued'
    assert get(c,u,r)['lines'][0]['effective_issued_quantity']==6
    assert c.execute('SELECT COUNT(*) FROM supply_correction').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==3
    with pytest.raises(Conflict):correction(c,u,'issue_reversal',release,4)
    correction(c,u,'issue_reversal',release,3)
    assert stock.stock_totals(c,u[1],item)['on_hand']==9
    assert get(c,u,r)['lines'][0]['outstanding_quantity']==3


@pytest.mark.parametrize('reopen',['yes','no'])
def test_issue_reversal_preserves_cancelled_remainder_and_explicit_choice(approval_db,reopen):
    c,u,_,_,item=approval_db;r=ready(c,u,item,6);release=issue(c,u,r,4)['id'];cancel(c,u,r)
    correction(c,u,'issue_reversal',release,2,fields={'reopen_demand':reopen})
    line=get(c,u,r)['lines'][0]
    assert line['effective_issued_quantity']==2
    assert line['cancelled_quantity']==(2 if reopen=='yes' else 4)
    assert line['outstanding_quantity']==(2 if reopen=='yes' else 0)
    assert get(c,u,r)['approval_status']=='approved'
    assert stock.stock_totals(c,u[1],item)['on_hand']==8
    evidence=c.execute("SELECT m.reverses_movement_id FROM supply_stock_movement m WHERE kind='reversal'").fetchone()[0]
    assert evidence==c.execute('SELECT movement_id FROM supply_issue_line').fetchone()[0]


@pytest.mark.usefixtures('unlimited_requests')
def test_stocktake_loss_preview_releases_newest_reserved_demand_first(approval_db):
    c,u,_,_,item=approval_db;a=ready(c,u,item,4);b=ready(c,u,item,4);d=ready(c,u,item,4)
    fields={'quantity':'3','effective_date':'2026-10-20','reason':'Synthetic missing supplies'}
    preview=corrections.preview(c,u[1],'stocktake',item,fields)
    assert [(x['request_id'],x['reserved']) for x in preview['affected_requests']]==[(a,3),(b,0),(d,0)]
    assert allocations.availability(c,item)['on_hand']==10
    correction(c,u,'stocktake',item,3)
    assert [get(c,u,r)['lines'][0]['reserved_quantity'] for r in (a,b,d)]==[3,0,0]
    assert [row[0] for row in c.execute("SELECT entity_id FROM supply_event WHERE action='stocktake_reservation_release' ORDER BY id")]==[d,b,a]
    correction(c,u,'stocktake',item,8)
    assert [get(c,u,r)['lines'][0]['reserved_quantity'] for r in (a,b,d)]==[4,4,0]
    assert allocations.availability(c,item)=={'on_hand':8,'reserved_quantity':8,'available':0}


def test_receipt_reversal_blocks_consumed_and_reserved_stock_without_deallocation(approval_db):
    c,u,_,_,item=approval_db;rec=receipt(c,u,item,5);r=ready(c,u,item,15);release=issue(c,u,r,12)['id']
    before=[tuple(row) for row in c.execute('SELECT * FROM supply_reservation')]
    with pytest.raises(Conflict,match='free to reverse'):correction(c,u,'receipt_reversal',rec['id'],1)
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_reservation')]
    cancel(c,u,r)
    correction(c,u,'receipt_reversal',rec['id'],3)
    with pytest.raises(Conflict,match='free to reverse'):correction(c,u,'receipt_reversal',rec['id'],1)
    correction(c,u,'issue_reversal',release,2,fields={'reopen_demand':'no'})
    correction(c,u,'receipt_reversal',rec['id'],2)
    assert stock.stock_totals(c,u[1],item)['on_hand']==0
    assert stock.get_receipt(c,u[1],rec['id'])['lines'][0]['net_accepted_quantity']==0
    with pytest.raises(Conflict):correction(c,u,'receipt_reversal',rec['id'],1)


@pytest.mark.parametrize('bad',['zero','negative','fraction','bool','over','condition','choice','reason','future','before_original','foreign'])
def test_invalid_input_cannot_create_correction(approval_db,bad):
    c,u,_,_,item=approval_db;r,release=released(c,u,item)
    kind='return';data={'source_line_id':1,'quantity':'1','effective_date':'2026-10-20','reason':'Evidence','condition':'usable'}
    if bad=='zero':data['quantity']=0
    elif bad=='negative':data['quantity']=-1
    elif bad=='fraction':data['quantity']='1.5'
    elif bad=='bool':data['quantity']=True
    elif bad=='over':data['quantity']=7
    elif bad=='condition':data['condition']=''
    elif bad=='choice':kind='issue_reversal'
    elif bad=='reason':data['reason']=' '
    elif bad=='future':data['effective_date']='2099-01-01'
    elif bad=='before_original':data['effective_date']='2026-10-18'
    else:data['source_line_id']=9999
    with pytest.raises((Invalid,Conflict)):corrections.preview(c,u[1],kind,release,data)
    assert c.execute('SELECT COUNT(*) FROM supply_correction').fetchone()[0]==0


def test_preview_stales_on_stock_reservation_and_original_changes_replay_is_harmless(approval_db):
    c,u,_,_,item=approval_db;r,release=released(c,u,item)
    fields={'source_line_id':1,'quantity':'1','effective_date':'2026-10-20','reason':'Evidence','condition':'usable'}
    impact=corrections.preview(c,u[1],'return',release,fields)
    fields.update(preview_token=impact['preview_token'],confirmed='yes');op=key()
    ready(c,u,item,1)
    with pytest.raises(Conflict,match='changed'):corrections.post_return(c,u[1],release,fields,operation_key=op)
    fields['preview_token']=corrections.preview(c,u[1],'return',release,fields)['preview_token']
    result=corrections.post_return(c,u[1],release,fields,operation_key=op)
    assert corrections.post_return(c,u[1],release,fields,operation_key=op)==result
    with pytest.raises(Conflict):corrections.post_return(c,u[1],release,{**fields,'reason':'Different'},operation_key=op)
    assert c.execute('SELECT COUNT(*) FROM supply_correction').fetchone()[0]==1
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    with pytest.raises(Disabled):corrections.post_return(c,u[1],release,fields,operation_key=op)
    assert corrections.history(c,u[2],'issues',release)['corrections']


@pytest.mark.parametrize('who',[0,2,3,4])
def test_only_current_custodian_can_preview_or_post(approval_db,who):
    c,u,_,_,item=approval_db;r,release=released(c,u,item)
    with pytest.raises(Denied):corrections.preview(c,u[who],'stocktake',item,{'quantity':3})
    with pytest.raises(Denied):corrections.post_return(c,u[who],release,{},operation_key=key())


@pytest.mark.parametrize('failure',['audit','allocator'])
def test_mid_correction_failure_rolls_back_stock_reservations_history_and_operation(approval_db,monkeypatch,failure):
    c,u,_,_,item=approval_db;r=ready(c,u,item,10)
    def fail(*args,**kw):raise RuntimeError('Synthetic correction failure')
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    else:monkeypatch.setattr(corrections,'allocate_outstanding',fail)
    with pytest.raises(RuntimeError):correction(c,u,'stocktake',item,3)
    assert allocations.availability(c,item)=={'on_hand':10,'reserved_quantity':10,'available':0}
    assert not c.execute('SELECT * FROM supply_correction').fetchall()
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==1


def test_competing_returns_cannot_exceed_original_and_same_key_has_single_result(approval_db):
    c,u,_,path,item=approval_db;r,release=released(c,u,item,2)
    data={'source_line_id':1,'quantity':'2','effective_date':'2026-10-20','reason':'Evidence','condition':'usable','confirmed':'yes'}
    data['preview_token']=corrections.preview(c,u[1],'return',release,data)['preview_token'];op=key();barrier=Barrier(2)
    def worker(_):
        conn=st.connect(path)
        try:
            barrier.wait()
            return corrections.post_return(conn,u[1],release,data,operation_key=op)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
    assert results[0]==results[1]
    assert c.execute('SELECT COUNT(*) FROM supply_correction').fetchone()[0]==1
    with pytest.raises(Conflict):correction(c,u,'return',release,1)


def test_immutable_history_install_and_inactive_item_correction(approval_db):
    c,u,_,_,item=approval_db;r,release=released(c,u,item)
    c.execute('UPDATE supply_item SET active=0 WHERE id=?',(item,));c.commit()
    result=correction(c,u,'issue_reversal',release,1)
    for sql in ('UPDATE supply_correction SET quantity=2','DELETE FROM supply_correction'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(sql)
        c.rollback()
    install(c);install(c)
    assert corrections.history(c,u[2],'issues',release)['corrections'][0]['id']==result['id']
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    with pytest.raises(Denied):corrections.history(c,u[2],'items',item)


def test_stocktake_requires_recorded_changed_count(approval_db):
    c,u,_,_,item=approval_db
    with pytest.raises(Invalid):correction(c,u,'stocktake',item,10)
    other=create(c,u[1],code='UNRECORDED')['id']
    with pytest.raises(Conflict):correction(c,u,'stocktake',other,1)


@pytest.mark.parametrize('kind',['return','stocktake','issue_reversal','receipt_reversal'])
def test_http_review_post_replay_csrf_and_recipient_read(approval_db,app_mod,kind):
    c,u,_,path,item=approval_db;r,release=released(c,u,item,4);rec=receipt(c,u,item,3)
    target=(f'/supplies/items/{item}/stocktake' if kind=='stocktake' else
            f"/supplies/receipts/{rec['id']}/reverse" if kind=='receipt_reversal' else
            f'/supplies/issues/{release}/'+('returns' if kind=='return' else 'reverse'))
    old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]));page=client.get(target)
            assert page.status_code==200
            fields={'csrf':hidden(page.text,'csrf'),'operation_key':key(),'quantity':'2' if kind!='stocktake' else '8',
                    'effective_date':'2026-10-20','reason':'Synthetic HTTP evidence <script>bad()</script>'}
            if kind!='stocktake':fields['source_line_id']=str(corrections.form_context(c,u[1],kind,rec['id'] if kind=='receipt_reversal' else release)['source_lines'][0]['id'])
            if kind=='return':fields['condition']='unusable'
            if kind=='issue_reversal':fields['reopen_demand']='no'
            assert client.post(target+'/preview',data={**fields,'csrf':'bad'}).status_code==403
            assert client.post(target+'/preview',data=fields,headers={'Origin':'https://foreign.example'}).status_code==403
            assert client.post(target,data={**fields,'confirmed':'yes'}).status_code==422
            before=[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
            response=client.post(target+'/preview',data=fields)
            assert response.status_code==200 and 'Review the change' in response.text
            assert '<script>bad()</script>' not in response.text
            assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
            final={**fields,'preview_token':hidden(response.text,'preview_token'),'confirmed':'yes'}
            assert client.post(target,data={**final,'preview_token':'f'*64}).status_code==409
            response=client.post(target,data=final,follow_redirects=False)
            assert response.status_code==303
            location=response.headers['location']
            assert client.post(target,data=final,follow_redirects=False).headers['location']==location
            assert client.get(location).status_code==200
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            assert client.get(target).status_code==403
            assert client.post(target,data=final).status_code==403
            assert client.get(location).status_code==(200 if kind in ('return','issue_reversal') else 403)
            if kind in ('return','issue_reversal'):
                history=client.get(f'/supplies/issues/{release}/corrections')
                assert history.status_code==200 and 'Synthetic HTTP evidence' in history.text
                assert 'Correction summary' in client.get(f'/supplies/issues/{release}/print').text
                assert client.get(f'/supplies/requests/{r}/print').status_code==200
    finally:app_mod.DB=old


def test_different_keys_compete_and_revoked_custodian_cannot_replay(approval_db):
    c,u,_,path,item=approval_db;r,release=released(c,u,item,2)
    data={'source_line_id':1,'quantity':'2','effective_date':'2026-10-20','reason':'Evidence','condition':'usable','confirmed':'yes'}
    data['preview_token']=corrections.preview(c,u[1],'return',release,data)['preview_token'];barrier=Barrier(2)
    def worker(_):
        conn=st.connect(path)
        try:
            barrier.wait()
            try:return corrections.post_return(conn,u[1],release,data,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
    assert sum(isinstance(result,dict) for result in results)==1 and results.count('conflict')==1
    correction_key=c.execute('SELECT operation_key FROM supply_correction').fetchone()[0]
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'",(u[0]['id'],u[1]['id']));c.commit()
    with pytest.raises(Denied):corrections.post_return(c,u[1],release,data,operation_key=correction_key)


def test_correction_history_pagination_and_stable_old_evidence_link(approval_db):
    c,u,_,_,item=approval_db;correction(c,u,'stocktake',item,100)
    r,release=released(c,u,item,30)
    ids=[correction(c,u,'return',release,1)['id'] for _ in range(26)]
    first=corrections.history(c,u[2],'issues',release);second=corrections.history(c,u[2],'issues',release,page=2)
    assert len(first['corrections'])==25 and first['has_next'] and len(second['corrections'])==1
    assert corrections.get_correction(c,u[2],ids[0])['corrections'][0]['id']==ids[0]
    with pytest.raises(Missing):corrections.get_correction(c,u[2],9999)


@pytest.mark.usefixtures('unlimited_requests')
def test_return_to_stock_allocates_older_other_request_without_leaking_it(approval_db):
    from tests.test_supplies_requests import draft, submit, fields
    from tests.test_supplies_approvals import decide
    c,u,units,_,item=approval_db;r,release=released(c,u,item,10)
    other=requests.save_draft(c,u[4],fields(item),operation_key=key())['id']
    requests.submit(c,u[4],other,expected_revision=1,operation_key=key())
    current=requests.get_request(c,u[3],other)
    import supplies_approvals as approvals
    approvals.decide_request(c,u[3],other,{'decision':'approved','lines':[{'revision_line_id':current['lines'][0]['id'],'approved_quantity':3}]},expected_revision=2,submitted_revision=1,operation_key=key())
    # The original requester has no approver grant and cannot view the other request.
    result=correction(c,u,'return',release,2)
    assert requests.get_request(c,u[4],other)['lines'][0]['reserved_quantity']==2
    own=corrections.get_correction(c,u[2],result['id'])['corrections'][0]
    privileged=corrections.get_correction(c,u[1],result['id'])['corrections'][0]
    assert own['impact']['affected_requests']==[]
    assert privileged['impact']['affected_requests'][0]['request_id']==other


def test_acknowledgment_and_original_snapshots_survive_corrections(approval_db):
    import supplies_acknowledgments as acknowledgments
    import supplies_issues as issues
    c,u,_,_,item=approval_db;r,release=released(c,u,item,6)
    acknowledgments.acknowledge_issue(c,u[2],release,{'status':'acknowledged','note':''},expected_revision=0,operation_key=key())
    original=[tuple(row) for row in c.execute('SELECT * FROM supply_issue_line')]
    correction(c,u,'issue_reversal',release,2,fields={'reopen_demand':'no'})
    correction(c,u,'return',release,1)
    detail=issues.get_issue(c,u[2],release)
    assert detail['acknowledgment']['status']=='acknowledged'
    assert detail['lines'][0]['net_issued_quantity']==4 and detail['lines'][0]['usable_returned']==1
    assert original==[tuple(row) for row in c.execute('SELECT * FROM supply_issue_line')]


def test_negative_receipt_reversal_does_not_reverse_another_reversal(approval_db):
    c,u,_,_,item=approval_db;rec=receipt(c,u,item,3)
    first=correction(c,u,'receipt_reversal',rec['id'],1)
    fields={'quantity':1,'source_line_id':first['movement_id'],'effective_date':'2026-10-20','reason':'Wrong source'}
    with pytest.raises((Invalid,Missing)):corrections.preview(c,u[1],'receipt_reversal',first['movement_id'],fields)
    with pytest.raises(sqlite3.IntegrityError,match='original issue or receipt'):
        c.execute('''INSERT INTO supply_stock_movement
          (item_id,kind,quantity_delta,effective_date,posted_at,posted_by,actor_snapshot,source_type,source_id,
           reason,code_snapshot,description_snapshot,unit_snapshot,operation_key,reverses_movement_id)
          SELECT item_id,'reversal',1,effective_date,posted_at,posted_by,actor_snapshot,'reversal',1,
           reason,code_snapshot,description_snapshot,unit_snapshot,operation_key,id
          FROM supply_stock_movement WHERE id=?''',(first['movement_id'],))
    c.rollback()


def test_zero_count_and_concurrent_issue_cannot_leave_over_reserved_stock(approval_db):
    from tests.test_supplies_issues import data
    import supplies_issues as issues
    c,u,_,path,item=approval_db;r=ready(c,u,item,10);issue_fields=data(c,u,r,2)
    count={'quantity':'0','effective_date':'2026-10-20','reason':'Synthetic empty physical count','confirmed':'yes'}
    count['preview_token']=corrections.preview(c,u[1],'stocktake',item,count)['preview_token'];barrier=Barrier(2)
    def worker(action):
        conn=st.connect(path)
        try:
            barrier.wait()
            try:
                if action=='count':return corrections.post_stocktake(conn,u[1],item,count,operation_key=key())
                return issues.post_issue(conn,u[1],r,issue_fields,expected_revision=3,operation_key=key())
            except Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,['count','issue']))
    assert sum(isinstance(result,dict) for result in results)==1 and results.count('conflict')==1
    totals=allocations.availability(c,item)
    assert totals['on_hand']>=totals['reserved_quantity']>=0
    if totals['on_hand']!=0:correction(c,u,'stocktake',item,0)
    assert allocations.availability(c,item)=={'on_hand':0,'reserved_quantity':0,'available':0}
    assert get(c,u,r)['lines'][0]['awaiting_stock_quantity']>0


def test_correction_evidence_retains_posting_item_name_after_catalog_changes(approval_db):
    c,u,_,_,item=approval_db;r,release=released(c,u,item)
    result=correction(c,u,'return',release,1)
    c.execute("UPDATE supply_item SET code='LATER-CODE',description='Later name' WHERE id=?",(item,));c.commit()
    evidence=corrections.get_correction(c,u[2],result['id'])['corrections'][0]
    assert evidence['code']=='TEST-PAPER' and evidence['impact']['item']['description']=='Synthetic paper'
