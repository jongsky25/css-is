"""Own draft confirmation preserves native supply authority and atomic receipts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import re
import sqlite3
from uuid import uuid4

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import supplies as supplies
import supplies_requests as requests
import supplies_stock as stock
import supplies_corrections as corrections
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_supply_draft as draft
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_supplies import supply_env,command,key
from tests.test_telegram_brief import grant

UNCHANGED=('supply_stock_movement','supply_reservation','supply_request_revision','supply_sequence','supply_alert_event','supply_mail')


@pytest.fixture
def draft_env(supply_env,monkeypatch):
    grant(supply_env[0],draft.ACTION,monkeypatch)
    return supply_env


def fields(item,**changes):
    values={name:'' for name in draft.FIELDS['create']}
    values.update(purpose='Private supplied purpose',date_needed='2026-11-05',item_1=str(item),quantity_1='3')
    return {**values,**changes}


def prepare(env,number=10,client_key='supply-draft-operation-key',data=None):
    source,item=env;c,users,*_=source
    guide=command(env,'/supply_draft',number)['text']
    assert '?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,draft.ACTION)
    return ctx,actions.issue(c,ctx,draft.ACTION,client_key,data or fields(item),NOW)


def exact(env,result,number=11):
    text=command(env,'/supplydraft_preview '+result['operation_id'],number)['text']
    assert 'Supply draft preview' in text and 'No control number' in text
    assert draft.common.units(text)<=4096
    return re.search(r'/supplydraft_confirm [A-Za-z0-9_-]{43}',text)[0]


def unchanged(conn):return {table:list(conn.execute('SELECT * FROM '+table)) for table in UNCHANGED}


def test_exact_preview_saves_one_own_draft_then_receipts_preserve_later_edits(draft_env):
    source,item=draft_env;c,users,*_=source;before=unchanged(c)
    ctx,result=prepare(draft_env,data=fields(item,item_2=str(item),quantity_2='2'))
    assert not rows(c,'SELECT * FROM supply_request')
    text=command(draft_env,'/supplydraft_preview '+result['operation_id'],11)['text']
    assert 'Private supplied purpose' in text and 'Quantity: 5' in text and text.count('Item '+str(item)+' ·')==1
    assert users[0]['username'] not in text
    confirmation=re.search(r'/supplydraft_confirm [A-Za-z0-9_-]{43}',text)[0]
    assert 'Recorded outcome: supply draft saved.' in command(draft_env,confirmation,12)['text']
    request=rows(c,'SELECT * FROM supply_request')[0]
    assert request['requester_id']==users[0]['id'] and request['approval_status']=='draft' and request['control_number'] is None and request['current_revision']==0
    assert rows(c,'SELECT requested_quantity FROM supply_request_draft_line')[0]['requested_quantity']==5
    assert before==unchanged(c)
    for n,cmd in enumerate((confirmation,'/supplydraft_receipt '+result['operation_id']),13):
        assert 'Saved revision 1' in command(draft_env,cmd,n)['text']
    requests.save_draft(c,users[0],{'purpose':'Later native edit','date_needed':None,'lines':[{'item_id':item,'requested_quantity':1}]},request_id=request['id'],expected_revision=1,operation_key=str(uuid4()))
    text=command(draft_env,confirmation,15)['text'];assert 'Saved revision 1' in text and 'Current revision 2' in text
    assert len(rows(c,'SELECT * FROM supply_request'))==1 and requests._owned(c,users[0],request['id'])['purpose']=='Later native edit'
    p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
    assert p['fields_json'] is None and p['summary_json'] is None and p['expected_json'] is None
    assert before==unchanged(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    for row in rows(c,'SELECT projection_json FROM telegram_delivery'):assert 'Private supplied purpose' not in row['projection_json']


@pytest.mark.parametrize('change',['catalog','inactive','staff_name','staff_unit','unlinked','external','archived','availability','module','grant','read_grant','pilot','read_pilot','disconnect','restore','bot','direct','delivery','expiry'])
def test_current_native_and_private_guards_block_stale_creation(draft_env,monkeypatch,change):
    source,item=draft_env;c,users,path,_,payload=source
    ctx,result=prepare(draft_env);confirmation=exact(draft_env,result)
    if change=='catalog':c.execute('UPDATE supply_item SET description=?,revision=revision+1 WHERE id=?',('Changed catalog',item));c.commit()
    elif change=='inactive':c.execute('UPDATE supply_item SET active=0,revision=revision+1 WHERE id=?',(item,));c.commit()
    elif change=='staff_name':c.execute('UPDATE resource_person SET name=? WHERE id=?',('Changed requester',users[0]['rp_id']));c.commit()
    elif change=='staff_unit':c.execute('UPDATE resource_person SET org_unit_id=NULL WHERE id=?',(users[0]['rp_id'],));c.commit()
    elif change=='unlinked':c.execute('UPDATE admin_user SET rp_id=NULL WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='external':c.execute('UPDATE resource_person SET is_internal=0 WHERE id=?',(users[0]['rp_id'],));c.commit()
    elif change=='archived':c.execute('UPDATE resource_person SET archived_at=? WHERE id=?',(links.stamp(NOW),users[0]['rp_id']));c.commit()
    elif change=='availability':
        data={'quantity':'0','effective_date':'2026-10-20','reason':'Native stock change'}
        impact=corrections.preview(c,users[1],'stocktake',item,data)
        corrections.post_stocktake(c,users[1],item,{**data,'preview_token':impact['preview_token'],'confirmed':'yes'},operation_key=key())
    elif change=='module':st.set_setting(c,'supplies.enabled','0')
    elif change in ('grant','read_grant'):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),draft.ACTION if change=='grant' else 'supplies.read'));c.commit()
    elif change in ('pilot','read_pilot','delivery'):monkeypatch.setenv('CSS_TELEGRAM_'+{'pilot':'SUPPLIES_DRAFT','read_pilot':'SUPPLIES_READ','delivery':'DELIVERY'}[change]+'_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    else:monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    before=unchanged(c)
    response=command(draft_env,confirmation,12)
    assert 'Recorded outcome' not in response.get('text','') and not rows(c,'SELECT * FROM supply_request')
    assert before==unchanged(c)
    if change in ('grant','read_grant'):
        p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
        assert p['state']=='cancelled' and p['fields_json'] is None


@pytest.mark.parametrize('bad',[{'owner_id':1},{'request_id':1},{'status':'submitted'},{'purpose':''},{'purpose':'x'*1001},
    {'item_1':'0'},{'item_1':True},{'item_1':'1 OR 1=1'},{'quantity_1':True},{'quantity_1':'0'},{'quantity_1':'-1'},
    {'quantity_1':'1.5'},{'quantity_1':'2147483648'},{'item_1':'','quantity_1':'3'},{'item_2':'','quantity_2':'1'},
    {'date_needed':'next week'},{'date_needed':'2026-02-30'},{'item_1':'','quantity_1':''}])
def test_strict_inputs_create_no_business_draft(draft_env,bad):
    source,item=draft_env;c,users,*_=source
    ctx,_=prepare(draft_env)
    with pytest.raises(ValueError):actions.issue(c,ctx,draft.ACTION,'different-invalid-operation',fields(item,**bad),NOW)
    assert not rows(c,'SELECT * FROM supply_request')


def test_concurrent_confirmations_commit_once(draft_env):
    source,item=draft_env;c,users,path,*_=source;ctx,result=prepare(draft_env)
    token=exact(draft_env,result).split()[1]
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm_digest(conn,ctx,links.digest(token),NOW)['state']
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(confirm,range(2)))==['committed','committed']
    assert len(rows(c,'SELECT * FROM supply_request'))==1 and len(rows(c,"SELECT * FROM supply_operation WHERE action='request_save'"))==1


@pytest.mark.parametrize('failure',['audit','handoff'])
def test_atomic_domain_audit_and_webhook_handoff_failures_roll_back(draft_env,monkeypatch,failure):
    source,item=draft_env;c,users,*_=source;ctx,result=prepare(draft_env);confirmation=exact(draft_env,result)
    before=unchanged(c)
    if failure=='audit':
        original=st.audit
        def fail(*args,**kwargs):
            if len(args)>2 and args[2]=='supply_request_save':raise ValueError('Synthetic audit failure')
            return original(*args,**kwargs)
        monkeypatch.setattr(st,'audit',fail)
        assert 'Recorded outcome' not in command(draft_env,confirmation,12)['text']
        monkeypatch.setattr(st,'audit',original)
    else:
        c.executescript("CREATE TRIGGER synthetic_handoff_failure BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'Synthetic handoff failure'); END;");c.commit()
        assert submit(source[3],update(12,text=confirmation)).status_code==503
        c.execute('DROP TRIGGER synthetic_handoff_failure');c.commit()
    assert not rows(c,'SELECT * FROM supply_request') and before==unchanged(c)
    assert not rows(c,"SELECT * FROM supply_operation WHERE action='request_save'")
    assert rows(c,'SELECT state,target_id FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]=={'state':'pending','target_id':None}
    assert 'Recorded outcome: supply draft saved.' in command(draft_env,confirmation,13)['text']


def test_no_creation_from_read_only_consent_and_catalog_choices_read_no_stock(supply_env,monkeypatch):
    source,item=supply_env;c,users,*_=source
    monkeypatch.setenv('CSS_TELEGRAM_SUPPLIES_DRAFT_ENABLED','1')
    assert '?origin=' not in command(supply_env,'/supply_draft')['text']
    def deny_stock(op,table,column,*_):return sqlite3.SQLITE_DENY if op==sqlite3.SQLITE_READ and table in ('supply_stock_movement','supply_reservation') else sqlite3.SQLITE_OK
    c.set_authorizer(deny_stock)
    try:assert any(v['id']==item for v in draft.choices(c,users[0],'create',{})['catalog_items'])
    finally:c.set_authorizer(None)


def test_independent_link_consent_and_pending_pilot_changes(linking,monkeypatch):
    c,users,*_=linking
    for flag in ('SUPPLIES_DRAFT','SUPPLIES_READ'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    _,raw,confirmation=start(linking)
    with pytest.raises(ValueError):links.claim(c,linking[4],raw,[draft.ACTION],NOW)
    links.claim(c,linking[4],raw,['supplies.read',draft.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_SUPPLIES_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')



def test_deleted_request_ids_cannot_retarget_receipts(draft_env):
    source,item=draft_env;c,users,*_=source;ctx,result=prepare(draft_env);confirmation=exact(draft_env,result)
    assert 'Recorded outcome' in command(draft_env,confirmation,12)['text']
    saved=rows(c,'SELECT * FROM supply_request')[0]
    c.execute('DELETE FROM supply_request_draft_line WHERE request_id=?',(saved['id'],))
    c.execute('DELETE FROM supply_request WHERE id=?',(saved['id'],));c.commit()
    values={**saved,'purpose':'Replacement request must not appear'}
    c.execute('INSERT INTO supply_request ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',tuple(values.values()));c.commit()
    text=command(draft_env,'/supplydraft_receipt '+result['operation_id'],13)['text']
    assert 'deleted' in text and 'Replacement' not in text
    assert 'deleted' in command(draft_env,confirmation,14)['text'] and len(rows(c,'SELECT * FROM supply_request'))==1


def test_context_replay_expired_payloads_and_foreign_messages_do_not_create(draft_env):
    source,item=draft_env;c,users,*_=source;ctx,result=prepare(draft_env);confirmation=exact(draft_env,result)
    for changed in ({'generation':'a'*32},{'sender_id':102},{'topic_id':7}):
        with pytest.raises(ValueError):actions.recover(c,{**ctx,**changed},draft.ACTION,result['operation_id'])
    before=len(rows(c,'SELECT * FROM telegram_meeting_origin'))
    for n,kind in enumerate(('group','topic','sender','callback'),12):
        packet=update(n,text='/supply_draft')
        if kind=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif kind=='topic':packet['message']['message_thread_id']=1
        elif kind=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        else:packet={'update_id':n,'callback_query':{'id':'synthetic','from':{'id':101},'data':'/supply_draft'}}
        assert '?origin=' not in submit(source[3],packet).json().get('text','')
    assert before==len(rows(c,'SELECT * FROM telegram_meeting_origin'))
    with transaction(c):actions.cleanup_in_transaction(c,NOW+timedelta(minutes=6))
    p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
    assert p['state']=='cancelled' and all(p[k] is None for k in ('fields_json','summary_json','expected_json'))
    assert 'Recorded outcome' not in command(draft_env,confirmation,17).get('text','') and not rows(c,'SELECT * FROM supply_request')


def test_oversized_exact_preview_is_refused_without_truncation(draft_env):
    source,item=draft_env;c,users,*_=source;ctx,result=prepare(draft_env)
    c.execute('UPDATE supply_item SET description=? WHERE id=?',('🌿'*240,item))
    c.execute('UPDATE resource_person SET name=? WHERE id=?',('🌿'*300,users[0]['rp_id']));c.commit()
    with pytest.raises(ValueError,match='too long'):
        actions.issue(c,ctx,draft.ACTION,'oversized-exact-supply-preview',fields(item,purpose='🌿'*1000),NOW)
    assert not rows(c,'SELECT * FROM supply_request')


@pytest.mark.parametrize('source',['purpose','catalog'])
def test_ambiguous_control_text_cannot_enter_exact_private_preview(draft_env,source):
    env,item=draft_env;c,users,*_=env;ctx,_=prepare(draft_env)
    data=fields(item)
    if source=='purpose':data['purpose']='Purpose with \u202e control'
    else:c.execute('UPDATE supply_item SET description=? WHERE id=?',('Label with \u202e control',item));c.commit()
    with pytest.raises(ValueError,match='control characters'):actions.issue(c,ctx,draft.ACTION,'unsupported-private-text-key',data,NOW)
    assert not rows(c,'SELECT * FROM supply_request')
