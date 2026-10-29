"""S2.1 owner isolation, immutable submissions, numbering and unchanged inventory."""
import sqlite3

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_requests as requests
import supplies_stock as stock
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing
from tests.test_supplies import supplies_db, setup_catalog, create, key, hidden
from tests.conftest import session_token


@pytest.fixture
def request_db(supplies_db):
    c,u,units,path=supplies_db
    setup_catalog(c,u)
    for i in (2,3,4):
        rp=st.add_rp(c,f'Synthetic requester {i}',True,units[1])
        c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,u[i]['id']));c.commit()
        u[i]=st.get_admin_user_by_id(c,u[i]['id'])
    item=create(c,u[1])['id']
    stock.post_opening(c,u[1],item,{'quantity':'10','effective_date':'2026-10-19','reason':'Synthetic opening'},expected_revision=1,operation_key=key())
    return c,u,units,path,item


def fields(item,**changes):
    return {'purpose':'Synthetic meeting supplies','date_needed':'2026-10-25',
            'lines':[{'item_id':item,'requested_quantity':'3'}],**changes}


def draft(c,u,item,**changes):
    return requests.save_draft(c,u[2],fields(item,**changes),operation_key=key())['id']


def get(c,u,r):return requests.get_request(c,u[2],r)


def submit(c,u,r,**kw):
    return requests.submit(c,u[2],r,expected_revision=kw.pop('expected_revision',get(c,u,r)['revision']),operation_key=kw.pop('operation_key',key()),**kw)


def withdraw(c,u,r,**kw):
    return requests.withdraw(c,u[2],r,reason='No longer needed',expected_revision=kw.pop('expected_revision',get(c,u,r)['revision']),operation_key=kw.pop('operation_key',key()),**kw)


def test_create_edit_combine_submit_track_and_retry_never_changes_stock(request_db):
    c,u,_,_,item=request_db
    before=[tuple(r) for r in c.execute('SELECT * FROM supply_stock_movement')]
    op=key();data=fields(item,lines=[{'item_id':item,'requested_quantity':'3'},{'item_id':str(item),'requested_quantity':'2'}])
    first=requests.save_draft(c,u[2],data,operation_key=op)
    assert requests.save_draft(c,u[2],data,operation_key=op)==first
    r=first['id'];entry=get(c,u,r)
    assert entry['control_number'] is None and entry['current_revision']==0
    assert len(entry['lines'])==1 and entry['lines'][0]['requested_quantity']==5
    line_id=entry['lines'][0]['id']
    requests.save_draft(c,u[2],fields(item),request_id=r,expected_revision=1,operation_key=key())
    assert get(c,u,r)['lines'][0]['id']==line_id
    assert not c.execute('SELECT * FROM supply_sequence').fetchall()
    op=key();result=submit(c,u,r,operation_key=op)
    assert result['control_number']=='SUP-2026-00001' and result['current_revision']==1
    assert submit(c,u,r,expected_revision=2,operation_key=op)==result
    assert get(c,u,r)['routing_warning']
    assert len(get(c,u,r)['events'])==3
    assert get(c,u,r)['lines'][0]['line_id']==line_id
    assert before==[tuple(row) for row in c.execute('SELECT * FROM supply_stock_movement')]
    assert stock.stock_totals(c,u[2],item)['on_hand']==10
    with pytest.raises(Conflict):submit(c,u,r)
    with pytest.raises(Conflict):requests.save_draft(c,u[2],fields(item),request_id=r,expected_revision=3,operation_key=key())


@pytest.mark.parametrize('user_index',[0,1,3,4])
def test_owner_only_reads_and_mutations_even_business_or_admin_roles(request_db,user_index):
    c,u,_,_,item=request_db;r=draft(c,u,item);other=u[user_index]
    with pytest.raises(Missing):requests.get_request(c,other,r)
    with pytest.raises(Missing):requests.submit(c,other,r,expected_revision=1,operation_key=key())
    with pytest.raises(Missing):requests.withdraw(c,other,r,reason='Not owner',expected_revision=1,operation_key=key())
    with pytest.raises(Denied):requests.save_draft(c,other,fields(item),request_id=r,expected_revision=1,operation_key=key())
    assert not requests.my_requests(c,other)['requests']


@pytest.mark.parametrize('mutation',['no_link','external','archived','no_unit','inactive','forged_cookie'])
def test_directory_linkage_is_reloaded_at_submission(request_db,mutation):
    c,u,_,_,item=request_db;r=draft(c,u,item);rp=u[2]['rp_id']
    if mutation=='no_link':c.execute('UPDATE admin_user SET rp_id=NULL WHERE id=?',(u[2]['id'],))
    elif mutation=='external':c.execute('UPDATE resource_person SET is_internal=0 WHERE id=?',(rp,))
    elif mutation=='archived':c.execute("UPDATE resource_person SET archived_at='2026-10-20' WHERE id=?",(rp,))
    elif mutation=='no_unit':c.execute('UPDATE resource_person SET org_unit_id=NULL WHERE id=?',(rp,))
    elif mutation=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],))
    else:
        c.execute('UPDATE admin_user SET rp_id=NULL WHERE id=?',(u[2]['id'],))
        u[2]={**u[2],'rp_id':u[3]['rp_id'],'role':'admin'}
    c.commit()
    with pytest.raises(Denied):requests.submit(c,u[2],r,expected_revision=1,operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_request_revision').fetchone()[0]==0
    assert not c.execute('SELECT * FROM supply_sequence').fetchall()


def test_current_directory_at_submit_and_immutable_item_unit_snapshots(request_db):
    c,u,units,_,item=request_db;r=draft(c,u,item)
    c.execute("UPDATE resource_person SET name='Changed synthetic name',org_unit_id=? WHERE id=?",(units[2],u[2]['rp_id']));c.commit()
    submit(c,u,r);entry=get(c,u,r)
    assert entry['unit_id']==units[2] and entry['requester_snapshot']=='Changed synthetic name'
    c.execute("UPDATE resource_person SET name='Later name',org_unit_id=? WHERE id=?",(units[0],u[2]['rp_id']))
    c.execute("UPDATE supply_item SET description='Later description',unit='Pack',revision=revision+1 WHERE id=?",(item,));c.commit()
    entry=get(c,u,r)
    assert entry['unit_id']==units[2] and entry['lines'][0]['unit_snapshot']=='Ream'
    assert entry['lines'][0]['description_snapshot']=='Synthetic paper'
    for table in ('supply_request_revision','supply_request_revision_line'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(f'DELETE FROM {table}')
        c.rollback()


@pytest.mark.parametrize('bad',[{'purpose':''},{'date_needed':'2026-02-30'},{'lines':[]},
    {'lines':[{'item_id':1,'requested_quantity':'0'}]}, {'lines':[{'item_id':1,'requested_quantity':'1.5'}]},
    {'lines':[{'item_id':1,'requested_quantity':True}]},
    {'lines':[{'item_id':1,'requested_quantity':'2147483647'},{'item_id':1,'requested_quantity':'1'}]}])
def test_invalid_requests_leave_no_draft_or_audit(request_db,bad):
    c,u,_,_,item=request_db
    with pytest.raises(Invalid):requests.save_draft(c,u[2],fields(item,**bad),operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM supply_event WHERE entity_type='request'").fetchone()[0]==0


def test_inactive_and_changed_units_require_review(request_db):
    c,u,_,_,item=request_db;r=draft(c,u,item)
    c.execute("UPDATE supply_item SET unit='Pack',revision=revision+1 WHERE id=?",(item,));c.commit()
    with pytest.raises(Conflict,match='unit changed'):submit(c,u,r)
    requests.save_draft(c,u[2],fields(item),request_id=r,expected_revision=1,operation_key=key())
    s.deactivate_item(c,u[1],item,expected_revision=2,operation_key=key(),reason='Synthetic inactive item')
    with pytest.raises(Conflict,match='inactive'):submit(c,u,r)
    with pytest.raises(Conflict):requests.save_draft(c,u[2],fields(item),operation_key=key())


def test_open_obligation_blocks_deactivation_withdrawal_releases_guard(request_db):
    c,u,_,_,item=request_db;r=draft(c,u,item);submit(c,u,r)
    with pytest.raises(Conflict,match='open supply request'):s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='Try deactivation')
    op=key();result=withdraw(c,u,r,operation_key=op)
    assert withdraw(c,u,r,expected_revision=2,operation_key=op)==result
    assert get(c,u,r)['approval_status']=='cancelled'
    assert get(c,u,r)['control_number']=='SUP-2026-00001'
    s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='Obligation closed')
    with pytest.raises(Conflict):submit(c,u,r)
    with pytest.raises(Conflict):withdraw(c,u,r)
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==1


def test_draft_withdraw_and_stale_submission_do_not_consume_numbers(request_db):
    c,u,_,_,item=request_db;r=draft(c,u,item)
    requests.save_draft(c,u[2],fields(item,purpose='Edited'),request_id=r,expected_revision=1,operation_key=key())
    with pytest.raises(Conflict):submit(c,u,r,expected_revision=1)
    withdraw(c,u,r)
    assert get(c,u,r)['control_number'] is None
    assert not c.execute('SELECT * FROM supply_sequence').fetchall()
    new=draft(c,u,item);assert submit(c,u,new)['control_number']=='SUP-2026-00001'


def test_routing_current_scopes_self_approval_and_revocation(request_db):
    c,u,units,_,item=request_db;r=draft(c,u,item);submit(c,u,r)
    assert get(c,u,r)['routing_warning']
    s.grant_role(c,u[0],u[2]['id'],'request_approver',unit_id=units[0],operation_key=key())
    s.grant_role(c,u[0],u[3]['id'],'request_approver',unit_id=units[2],operation_key=key())
    assert get(c,u,r)['routing_warning']  # self and neighboring TEST/D10 excluded
    grant=s.grant_role(c,u[0],u[4]['id'],'request_approver',unit_id=units[0],operation_key=key())
    assert not get(c,u,r)['routing_warning']
    s.revoke_role(c,u[0],grant['id'],expected_revision=1,operation_key=key())
    assert get(c,u,r)['routing_warning']


def test_number_exhaustion_and_audit_failure_rollback(request_db,monkeypatch):
    c,u,_,_,item=request_db;r=draft(c,u,item)
    c.execute("INSERT INTO supply_sequence VALUES ('SUP',2026,99999)");c.commit()
    with pytest.raises(Conflict,match='limit'):submit(c,u,r)
    assert get(c,u,r)['approval_status']=='draft'
    c.execute("DELETE FROM supply_sequence WHERE kind='SUP'");c.commit()
    def fail(*args,**kwargs):raise RuntimeError('Synthetic audit failure')
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):submit(c,u,r)
    assert not c.execute('SELECT * FROM supply_sequence').fetchall()
    assert c.execute('SELECT COUNT(*) FROM supply_request_revision_line').fetchone()[0]==0
    assert get(c,u,r)['revision']==1


def test_number_uniqueness_and_competing_connections(request_db):
    c,u,_,path,item=request_db;r=draft(c,u,item);op=key();other=st.connect(path)
    try:
        first=submit(c,u,r,operation_key=op)
        assert requests.submit(other,u[2],r,expected_revision=1,operation_key=op)==first
        with pytest.raises(Conflict):requests.submit(other,u[2],r,expected_revision=1,operation_key=key())
        second=draft(c,u,item);assert submit(c,u,second)['control_number']=='SUP-2026-00002'
        assert c.execute('SELECT COUNT(*) FROM supply_request_revision').fetchone()[0]==2
    finally:other.close()


def test_flag_current_account_and_readonly_history(request_db):
    c,u,_,_,item=request_db;r=draft(c,u,item)
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    assert get(c,u,r)['approval_status']=='draft'
    for call in (lambda:submit(c,u,r),lambda:withdraw(c,u,r),lambda:draft(c,u,item)):
        with pytest.raises(Disabled):call()
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
    with pytest.raises(Denied):get(c,u,r)


def test_http_create_edit_submit_withdraw_and_owner_isolation(request_db,app_mod):
    c,u,_,path,item=request_db;old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            page=client.get('/supplies/requests/new?view=list');assert page.status_code==200
            token=hidden(page.text,'csrf');op=key()
            data={'csrf':token,'operation_key':op,'purpose':'HTTP synthetic purpose','date_needed':'',
                  'item_0':str(item),'quantity_0':'3','item_1':str(item),'quantity_1':'2',
                  'requester_id':str(u[3]['id']),'unit_id':'999'}
            assert client.post('/supplies/requests',data={**data,'csrf':'bad'}).status_code==403
            assert client.post('/supplies/requests',data=data,headers={'Origin':'https://foreign.example'}).status_code==403
            result=client.post('/supplies/requests',data=data,follow_redirects=False);assert result.status_code==303
            target=result.headers['location'];r=int(target.rsplit('/',1)[1])
            assert client.post('/supplies/requests',data=data,follow_redirects=False).headers['location']==target
            assert get(c,u,r)['requester_id']==u[2]['id']
            page=client.get(target);assert 'Draft saved' in page.text and '5</td>' in page.text
            assert client.get(target+'/edit').status_code==200
            submit_data={'csrf':token,'operation_key':key(),'revision':'1'}
            result=client.post(target+'/submit',data=submit_data,follow_redirects=False);assert result.status_code==303
            page=client.get(target);assert 'SUP-2026-00001' in page.text and 'No eligible approver' in page.text
            assert 'Submitted for approval' in page.text
            assert client.post(target+'/submit',data=submit_data,follow_redirects=False).status_code==303
            assert client.get(target+'/edit').status_code==409
            client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
            assert client.get(target).status_code==404
            assert 'HTTP synthetic purpose' not in client.get('/supplies/requests').text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            token=hidden(client.get(target).text,'csrf')
            assert client.post(target+'/withdraw',data={'csrf':token,'operation_key':key(),'revision':'2','reason':'Meeting cancelled'},follow_redirects=False).status_code==303
            page=client.get(target);assert 'Withdrawn by requester' in page.text and 'Submit for approval' not in page.text
            assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==1
    finally:app_mod.DB=old


@pytest.mark.usefixtures('unlimited_requests')
def test_multipart_twenty_line_form_and_validation_preserve_input(request_db,app_mod):
    c,u,_,path,item=request_db;old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            page=client.get('/supplies/requests/new?view=list');token=hidden(page.text,'csrf')
            assert page.text.count('<fieldset')==20
            data={'csrf':token,'operation_key':key(),'purpose':'<script>synthetic input</script>','date_needed':'',
                  'item_0':str(item),'quantity_0':'0'}
            invalid=client.post('/supplies/requests',data=data)
            assert invalid.status_code==422 and '&lt;script&gt;synthetic input&lt;/script&gt;' in invalid.text
            assert '<script>synthetic input</script>' not in invalid.text
            assert 'value="0"' in invalid.text and 'selected' in invalid.text
            data['operation_key']=key()
            for i in range(20):data.update({f'item_{i}':str(item),f'quantity_{i}':'1'})
            result=client.post('/supplies/requests',files={k:(None,v) for k,v in data.items()},follow_redirects=False)
            assert result.status_code==303
            r=int(result.headers['location'].rsplit('/',1)[1]);assert get(c,u,r)['lines'][0]['requested_quantity']==20
            page=client.get(result.headers['location']);assert '<script>synthetic input</script>' not in page.text
            with pytest.raises(Invalid):draft(c,u,item,lines=[{'item_id':item,'requested_quantity':'1'}]*21)
    finally:app_mod.DB=old


def test_saved_revision_conflicts_preserve_expected_revision(request_db,app_mod):
    c,u,_,path,item=request_db;r=draft(c,u,item)
    requests.save_draft(c,u[2],fields(item,purpose='Latest saved purpose'),request_id=r,expected_revision=1,operation_key=key())
    old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            token=hidden(client.get(f'/supplies/requests/{r}/edit').text,'csrf')
            response=client.post(f'/supplies/requests/{r}/save',data={'csrf':token,'operation_key':key(),'revision':'1',
                                  'purpose':'Stale form purpose','date_needed':'','item_0':str(item),'quantity_0':'4'})
            assert response.status_code==409 and 'Stale form purpose' in response.text
            assert hidden(response.text,'revision')=='1'
            assert get(c,u,r)['purpose']=='Latest saved purpose'
    finally:app_mod.DB=old


def test_my_requests_pagination_and_repeated_install(request_db):
    from supplies_storage import install
    c,u,_,_,item=request_db
    for i in range(26):draft(c,u,item,purpose=f'Synthetic request {i}')
    first=requests.my_requests(c,u[2]);second=requests.my_requests(c,u[2],page=2)
    assert len(first['requests'])==25 and first['has_next']
    assert len(second['requests'])==1 and not second['has_next']
    assert not {r['id'] for r in first['requests']} & {r['id'] for r in second['requests']}
    r=first['requests'][0]['id'];submit(c,u,r)
    before=[tuple(x) for x in c.execute('SELECT * FROM supply_request_revision_line')]
    install(c);install(c)
    assert [tuple(x) for x in c.execute('SELECT * FROM supply_request_revision_line')]==before
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_changed_operation_payload_and_failed_withdrawal_preserve_obligation(request_db,monkeypatch):
    c,u,_,_,item=request_db;op=key()
    r=requests.save_draft(c,u[2],fields(item),operation_key=op)['id']
    with pytest.raises(Conflict):requests.save_draft(c,u[2],fields(item,purpose='Different intent'),operation_key=op)
    submit(c,u,r)
    def fail(*args,**kwargs):raise RuntimeError('Synthetic withdrawal audit failure')
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):withdraw(c,u,r)
    assert get(c,u,r)['approval_status']=='submitted'
    assert len(get(c,u,r)['events'])==2
    with pytest.raises(Conflict,match='open supply request'):s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='Still obligated')


def test_approved_requests_cannot_be_withdrawn_before_approval(request_db):
    c,u,_,_,item=request_db;r=draft(c,u,item);submit(c,u,r)
    import supplies_approvals as approvals
    s.grant_role(c,u[0],u[3]['id'],'request_approver',unit_id=get(c,u,r)['unit_id'],operation_key=key())
    line=get(c,u,r)['lines'][0]
    approvals.decide_request(c,u[3],r,{'decision':'approved','lines':[
        {'revision_line_id':line['id'],'approved_quantity':line['requested_quantity']}]},
        expected_revision=2,submitted_revision=1,operation_key=key())
    with pytest.raises(Conflict,match='can no longer'):withdraw(c,u,r)
    with pytest.raises(Conflict,match='open supply request'):s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='Pending fulfillment')
