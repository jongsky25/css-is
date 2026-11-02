"""Own-only supply metadata lookup with source approval/handover/receipt stages."""
from uuid import uuid4

import pytest
import auth

from documents_storage import rows
import storage as st
import supplies as s
import supplies_requests as requests
import supplies_stock as stock
import supplies_approvals as approvals
import supplies_issues as issues
import supplies_acknowledgments as acknowledgments
import telegram_bot as bot
import telegram_links as links
import telegram_supplies as reads
from tests.test_work import workspace
from tests.test_telegram_bot import setup,update,submit,NOW
from tests.test_telegram_links import linking,claimed
from tests.test_supplies import fields as item_fields


def key():return str(uuid4())


@pytest.fixture
def supply_env(linking,monkeypatch):
    c,users,path,client,_=linking
    # Establish a genuine fresh admin link; role changes correctly revoke old links.
    c.execute("UPDATE admin_user SET role='admin' WHERE id=?",(users[0]['id'],));c.commit()
    users[0]=st.get_admin_user_by_id(c,users[0]['id'])
    payload=auth.parse_token(auth.make_token(users[0]))
    st.register_login_session(c,payload);c.commit()
    linking=(c,users,path,client,payload)
    monkeypatch.setenv('CSS_TELEGRAM_SUPPLIES_READ_ENABLED','1')
    _,_,code=claimed(linking,scopes=['supplies.read'])
    submit(client,update(2,text='/confirm '+code));bot.process_updates(c,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing provider call'))
    unit=c.execute("SELECT id FROM org_unit WHERE path='WORK/D1'").fetchone()[0]
    s.grant_role(c,users[4],users[1]['id'],'custodian',operation_key=key())
    s.grant_role(c,users[4],users[2]['id'],'request_approver',unit_id=unit,operation_key=key())
    s.set_enabled(c,users[4],'1',expected_revision=0,operation_key=key())
    for index in (0,3,4):
        rp=st.add_rp(c,'Synthetic supply requester '+str(index),True,unit)
        c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,users[index]['id']));c.commit()
        users[index]=st.get_admin_user_by_id(c,users[index]['id'])
    item=s.create_item(c,users[1],item_fields(description='DoNotExposeItemDescription'),operation_key=key())['id']
    stock.post_opening(c,users[1],item,{'quantity':'100','effective_date':'2026-10-19','reason':'Synthetic opening'},expected_revision=1,operation_key=key())
    return linking,item


def seed(env,owner=0,submitted=False):
    linking,item=env;c,users,*_=linking
    result=requests.save_draft(c,users[owner],{'purpose':'DoNotExposePurpose','date_needed':'2026-10-25',
        'lines':[{'item_id':item,'requested_quantity':2}]},operation_key=key())
    if submitted:
        result=requests.submit(c,users[owner],result['id'],expected_revision=result['revision'],operation_key=key())
    return result['id']


def command(env,text='/my_supplies',number=10):
    response=submit(env[0][3],update(number,text=text))
    assert response.status_code==200
    return response.json()


def test_source_lifecycle_matches_approval_collection_and_received(supply_env):
    c,users,*_=supply_env[0]
    rid=seed(supply_env,submitted=True)
    assert 'Approval: submitted' in command(supply_env,f'/supply_status {rid}')['text']
    entry=requests.get_request(c,users[0],rid)
    approvals.decide_request(c,users[2],rid,{'decision':'approved','reason':'',
        'lines':[{'revision_line_id':row['id'],'approved_quantity':row['requested_quantity'],'reason':''} for row in entry['lines']]},
        expected_revision=entry['revision'],submitted_revision=entry['current_revision'],operation_key=key())
    assert 'Ready for pickup' in command(supply_env,f'/supply_status {rid}',11)['text']
    entry=requests.get_request(c,users[1],rid)
    issued=issues.post_issue(c,users[1],rid,{'recipient_id':users[0]['id'],'effective_date':'2026-10-19','confirmed':'yes',
        'lines':[{'line_id':entry['lines'][0]['line_id'],'version':entry['lines'][0]['reservation_version'],'issued_quantity':2}]},
        expected_revision=entry['revision'],operation_key=key())
    assert 'Please confirm receipt' in command(supply_env,f'/supply_status {rid}',12)['text']
    acknowledgments.acknowledge_issue(c,users[0],issued['id'],{'status':'acknowledged','note':''},expected_revision=0,operation_key=key())
    assert 'Collection: Received' in command(supply_env,f'/supply_status {rid}',13)['text']


def test_lookup_is_read_only_and_excludes_purpose_people_items_and_quantities(supply_env):
    c,users,*_=supply_env[0]
    rid=seed(supply_env,submitted=True)
    tables=('supply_request','supply_reservation','supply_stock_movement','supply_issue','supply_event')
    before={t:list(c.execute('SELECT * FROM '+t)) for t in tables}
    text=command(supply_env)['text']
    assert str(rid) in text and '/supplies/requests/'+str(rid) in text
    assert 'DoNotExpose' not in text and users[2]['username'] not in text
    assert 'quantity' not in text.lower()
    assert {t:list(c.execute('SELECT * FROM '+t)) for t in tables}==before
    assert all('DoNotExpose' not in (row[0] or '') for row in c.execute('SELECT projection_json FROM telegram_delivery'))


def test_owner_filter_precedes_paging_even_when_technical_admin(supply_env):
    c,users,*_=supply_env[0]
    own=[seed(supply_env) for _ in range(6)]
    other=[seed(supply_env,owner=3) for _ in range(6)]
    for role in ('custodian','auditor','request_approver'):
        unit=c.execute("SELECT id FROM org_unit WHERE path='WORK/D1'").fetchone()[0]
        s.grant_role(c,users[4],users[0]['id'],role,unit_id=unit if role=='request_approver' else None,operation_key=key())
    text=command(supply_env)['text']
    assert 'Next page: /my_supplies all 2' in text
    assert all('Request '+str(i)+' ·' not in text for i in other)
    text2=command(supply_env,'/my_supplies all 2',11)['text']
    assert 'Request '+str(own[0])+' ·' in text2 and 'Next page:' not in text2
    denied=command(supply_env,'/supply_status '+str(other[0]),12)['text']
    assert denied==command(supply_env,'/supply_status 2147483647',13)['text']


@pytest.mark.parametrize('filter_',['active','needs_action','completed'])
def test_filters_match_source_requester_queue(supply_env,filter_):
    from supplies_dashboard import queue
    c,users,*_=supply_env[0]
    rid=seed(supply_env,submitted=True);draft=seed(supply_env)
    text=command(supply_env,'/my_supplies '+filter_)['text']
    expected=queue(c,users[0],'requests',state=filter_,limit=5)['requests']
    for id_ in (rid,draft):
        assert ('Request '+str(id_)+' ·' in text)==any(row['id']==id_ for row in expected)


@pytest.mark.parametrize('change',['flag','grant','module','disconnect','account'])
def test_revocation_blocks_source_reads(supply_env,monkeypatch,change):
    c,users,_,_,payload=supply_env[0]
    seed(supply_env)
    if change=='flag':monkeypatch.setenv('CSS_TELEGRAM_SUPPLIES_READ_ENABLED','0')
    elif change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='supplies.read'",(links.stamp(NOW),));c.commit()
    elif change=='module':st.set_setting(c,'supplies.enabled','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    monkeypatch.setattr(reads.dashboard,'queue',lambda *a,**k:pytest.fail('Revoked source read'))
    assert 'method' not in command(supply_env)


@pytest.mark.parametrize('text',['/my_supplies -1','/my_supplies active 10001','/my_supplies banana','/supply_status','/supply_status 2147483648'])
def test_invalid_input_never_reads_source(supply_env,monkeypatch,text):
    monkeypatch.setattr(reads.dashboard,'queue',lambda *a,**k:pytest.fail('Invalid source read'))
    assert command(supply_env,text)['text']==reads.USAGE


def test_module_independence_duplicates_and_group_direct_denial(supply_env,monkeypatch):
    c,*_=supply_env[0]
    seed(supply_env)
    st.set_setting(c,'documents.enabled','0');st.set_setting(c,'work.enabled','0')
    assert 'Request ' in command(supply_env)['text']
    assert 'method' not in command(supply_env)
    message=update(11,text='/my_supplies');message['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(supply_env[0][3],message).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(supply_env,number=12)
    assert bot.deliver(c,NOW)==0


def test_unrelated_grant_and_final_reply_revocation(supply_env,monkeypatch):
    c,*_=supply_env[0]
    seed(supply_env)
    render=reads.render
    def revoked(*args):
        text=render(*args)
        args[0].execute("UPDATE telegram_grant SET revoked_at=? WHERE action='supplies.read'",(links.stamp(NOW),))
        return text
    monkeypatch.setattr(reads,'render',revoked)
    assert 'method' not in command(supply_env)
    c.execute("UPDATE telegram_grant SET action='work.read',revoked_at=NULL");c.commit()
    monkeypatch.setattr(reads,'render',render)
    assert 'method' not in command(supply_env,number=11)
