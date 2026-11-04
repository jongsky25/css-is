"""Own submission preserves native numbering, approval routing and immutable receipts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import json
from uuid import uuid4

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import supplies
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_corrections as corrections
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_supply_submit as submitter
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_supplies import supply_env,command,key
from tests.test_telegram_brief import grant

TABLES=('supply_request','supply_request_draft_line','supply_request_revision','supply_request_revision_line',
        'supply_sequence','supply_stock_movement','supply_reservation','supply_mail','supply_operation','supply_event')


@pytest.fixture
def submit_env(supply_env,monkeypatch):
    source,item=supply_env;c,users,*_=source
    grant(source,submitter.ACTION,monkeypatch)
    result=requests.save_draft(c,users[0],{'purpose':'Own private submission purpose','date_needed':'2026-11-06',
        'lines':[{'item_id':item,'requested_quantity':3}]},operation_key=key())
    return supply_env,result['id']


def fields(state):
    env,rid=state;c,users,*_=env[0]
    return {'request_id':rid,'revision':requests._owned(c,users[0],rid)['revision']}


def prepare(state,number=10,client_key='own-supply-submit-operation',data=None):
    env,rid=state;source,item=env;c,users,*_=source
    guide=command(env,'/supply_submit',number)['text'];assert '?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,submitter.ACTION)
    return ctx,actions.issue(c,ctx,submitter.ACTION,client_key,data or fields(state),NOW)


def exact(state,result,number=11):
    text=command(state[0],'/supplysubmit_preview '+result['operation_id'],number)['text']
    assert 'Supply submission preview' in text and 'Own private' in text and 'No approval' in text
    assert submitter.common.units(text)<=4096
    return reparse(text),text


def reparse(text):
    import re
    return re.search(r'/supplysubmit_confirm [A-Za-z0-9_-]{43}',text)[0]


def native(conn):return {table:list(conn.execute('SELECT * FROM '+table)) for table in TABLES}


def test_exact_submission_allocates_one_number_version_and_native_mail_then_recovers(submit_env):
    env,rid=submit_env;c,users,*_=env[0];before=native(c)
    ctx,result=prepare(submit_env);confirmation,text=exact(submit_env,result)
    assert 'Quantity: 3' in text and 'Eligible unit approvers (excluding you): 1' in text
    assert 'assigned only on confirmation' in text and native(c)==before
    receipt=command(env,confirmation,12)['text'];assert 'Recorded outcome: supply request submitted for approval.' in receipt
    saved=requests._owned(c,users[0],rid)
    assert saved['approval_status']=='submitted' and saved['current_revision']==1 and saved['revision']==2
    assert saved['control_number'].startswith('SUP-') and len(rows(c,'SELECT * FROM supply_request_revision'))==1
    for table in ('supply_stock_movement','supply_reservation'):assert before[table]==native(c)[table]
    mail=rows(c,"SELECT * FROM supply_mail WHERE kind='supplies_request_pending'")
    assert len(mail)==1 and mail[0]['recipient_id']==users[2]['id']
    after=native(c)
    for n,cmd in enumerate((confirmation,'/supplysubmit_receipt '+result['operation_id']),13):
        assert 'Recorded submitted version 1' in command(env,cmd,n)['text'] and native(c)==after
    assert rows(c,'SELECT fields_json,summary_json,expected_json FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]==dict(fields_json=None,summary_json=None,expected_json=None)
    for row in rows(c,'SELECT projection_json FROM telegram_delivery'):assert 'Own private' not in row['projection_json']
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_returned_request_resubmission_keeps_number_and_old_receipt(submit_env):
    env,rid=submit_env;c,users,*_=env[0];ctx,first=prepare(submit_env);old,_=exact(submit_env,first)
    command(env,old,12);saved=requests._owned(c,users[0],rid);number=saved['control_number']
    approvals.decide_request(c,users[2],rid,{'decision':'returned','reason':'Clarify purpose'},expected_revision=saved['revision'],submitted_revision=saved['current_revision'],operation_key=key())
    current=requests._owned(c,users[0],rid)
    requests.save_draft(c,users[0],{'purpose':'Own private revised purpose','date_needed':None,'lines':[{'item_id':env[1],'requested_quantity':2}]},request_id=rid,expected_revision=current['revision'],operation_key=key())
    ctx,second=prepare(submit_env,13,'returned-submit-new-operation');new,text=exact(submit_env,second,14)
    assert number+' (retained)' in text and 'New submitted version: 2' in text
    assert 'Recorded submitted version 2' in command(env,new,15)['text']
    assert requests._owned(c,users[0],rid)['control_number']==number and len(rows(c,'SELECT * FROM supply_request_revision'))==2
    after=native(c)
    assert 'Recorded submitted version 1' in command(env,old,16)['text'] and native(c)==after
    assert c.execute('SELECT last_value FROM supply_sequence').fetchone()[0]==1


@pytest.mark.parametrize('change',['request','catalog','inactive','directory','routing','same_count_routing','availability','year','capacity',
    'module','grant','read_grant','pilot','read_pilot','disconnect','restore','direct','delivery','expiry'])
def test_stale_native_context_and_grants_block_submission(submit_env,monkeypatch,change):
    env,rid=submit_env;c,users,path,_,payload=env[0];item=env[1]
    ctx,result=prepare(submit_env);confirmation,_=exact(submit_env,result)
    if change=='request':requests.save_draft(c,users[0],{'purpose':'Changed native purpose','date_needed':None,'lines':[{'item_id':item,'requested_quantity':2}]},request_id=rid,expected_revision=1,operation_key=key())
    elif change=='catalog':c.execute('UPDATE supply_item SET revision=revision+1 WHERE id=?',(item,));c.commit()
    elif change=='inactive':c.execute('UPDATE supply_item SET active=0,revision=revision+1 WHERE id=?',(item,));c.commit()
    elif change=='directory':c.execute('UPDATE resource_person SET name=? WHERE id=?',('Changed identity',users[0]['rp_id']));c.commit()
    elif change in ('routing','same_count_routing'):
        for role in rows(c,"SELECT * FROM supply_role_grant WHERE role='request_approver' AND revoked_at IS NULL"):
            supplies.revoke_role(c,users[4],role['id'],expected_revision=role['revision'],operation_key=key())
        if change=='same_count_routing':supplies.grant_role(c,users[4],users[3]['id'],'request_approver',unit_id=requests._owned(c,users[0],rid)['unit_id'],operation_key=key())
    elif change=='availability':
        data={'quantity':'0','effective_date':'2026-10-20','reason':'Native stocktake'}
        preview=corrections.preview(c,users[1],'stocktake',item,data)
        corrections.post_stocktake(c,users[1],item,{**data,'confirmed':'yes','preview_token':preview['preview_token']},operation_key=key())
    elif change=='year':monkeypatch.setattr(submitter.tz,'today_local',lambda:date(2027,1,1))
    elif change=='capacity':c.execute("INSERT INTO supply_sequence(kind,year,last_value) VALUES ('SUP',?,99999)",(submitter.tz.today_local().year,));c.commit()
    elif change=='module':st.set_setting(c,'supplies.enabled','0')
    elif change in ('grant','read_grant'):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),submitter.ACTION if change=='grant' else 'supplies.read'));c.commit()
    elif change in ('pilot','read_pilot','delivery'):monkeypatch.setenv('CSS_TELEGRAM_'+{'pilot':'SUPPLIES_SUBMIT','read_pilot':'SUPPLIES_READ','delivery':'DELIVERY'}[change]+'_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    else:monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    before=native(c)
    assert 'Recorded outcome' not in command(env,confirmation,12).get('text','') and native(c)==before
    if change in ('grant','read_grant'):
        p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
        assert p['state']=='cancelled' and p['fields_json'] is None


@pytest.mark.parametrize('bad',[{'owner_id':1},{'purpose':'New purpose'},{'quantity':5},{'decision':'approved'},
    {'request_id':True},{'request_id':0},{'request_id':999999},{'revision':True},{'revision':0},{'revision':2},{'revision':2147483647}])
def test_strict_fields_and_exact_current_revision(submit_env,bad):
    env,rid=submit_env;c,users,*_=env[0];ctx,result=prepare(submit_env);before=native(c)
    with pytest.raises(ValueError):actions.issue(c,ctx,submitter.ACTION,'different-invalid-submit-key',{**fields(submit_env),**bad},NOW)
    assert before==native(c)


def test_owner_only_and_draft_consent_does_not_authorize_submission(supply_env,monkeypatch):
    env,item=supply_env;c,users,*_=env
    grant(env,'supplies.draft',monkeypatch);monkeypatch.setenv('CSS_TELEGRAM_SUPPLIES_SUBMIT_ENABLED','1')
    assert '?origin=' not in command(supply_env,'/supply_submit')['text']
    grant(env,submitter.ACTION,monkeypatch)
    other=requests.save_draft(c,users[3],{'purpose':'Foreign request','date_needed':None,'lines':[{'item_id':item,'requested_quantity':1}]},operation_key=key())
    guide=command(supply_env,'/supply_submit',11)['text'];ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,submitter.ACTION)
    with pytest.raises(ValueError):actions.issue(c,ctx,submitter.ACTION,'foreign-owner-submit-key',{'request_id':other['id'],'revision':1},NOW)
    assert requests._owned(c,users[3],other['id'])['approval_status']=='draft'


def test_zero_approvers_warns_and_preserves_native_submission_policy(submit_env):
    env,rid=submit_env;c,users,*_=env[0]
    for role in rows(c,"SELECT * FROM supply_role_grant WHERE role='request_approver' AND revoked_at IS NULL"):
        supplies.revoke_role(c,users[4],role['id'],expected_revision=role['revision'],operation_key=key())
    ctx,result=prepare(submit_env);confirmation,text=exact(submit_env,result)
    assert 'WARNING: No eligible approver' in text
    receipt=command(env,confirmation,12)['text'];assert 'WARNING: No eligible approver' in receipt
    assert requests._owned(c,users[0],rid)['approval_status']=='submitted' and not rows(c,'SELECT * FROM supply_mail')


@pytest.mark.parametrize('failure',['audit','handoff'])
def test_late_failure_rolls_back_number_immutable_snapshot_mail_and_outcome(submit_env,monkeypatch,failure):
    env,rid=submit_env;c,users,*_=env[0];ctx,result=prepare(submit_env);confirmation,_=exact(submit_env,result);before=native(c)
    if failure=='audit':
        original=st.audit
        def fail(*args,**kwargs):
            if len(args)>2 and args[2]=='supply_request_submit':raise ValueError('Synthetic audit failure')
            return original(*args,**kwargs)
        monkeypatch.setattr(st,'audit',fail)
        assert 'Recorded outcome' not in command(env,confirmation,12)['text']
        monkeypatch.setattr(st,'audit',original)
    else:
        c.executescript("CREATE TRIGGER synthetic_submit_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'Synthetic handoff failure'); END;");c.commit()
        assert submit(env[0][3],update(12,text=confirmation)).status_code==503
        c.execute('DROP TRIGGER synthetic_submit_handoff');c.commit()
    assert before==native(c)
    assert rows(c,'SELECT state,expected_revision FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]=={'state':'pending','expected_revision':None}
    assert 'Recorded outcome' in command(env,confirmation,13)['text']


def test_two_independent_previews_on_one_revision_submit_at_most_once(submit_env):
    env,rid=submit_env;c,users,path,*_=env[0];ctx,one=prepare(submit_env)
    _,two=prepare(submit_env,11,'second-independently-keyed-submit')
    def confirm(result):
        conn=st.connect(path)
        try:
            try:actions.confirm(conn,ctx,result['token'],NOW);return 'committed'
            except ValueError:return 'stale'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(confirm,(one,two)))==['committed','stale']
    assert len(rows(c,'SELECT * FROM supply_request_revision'))==1 and c.execute('SELECT last_value FROM supply_sequence').fetchone()[0]==1


def test_deleted_pending_request_and_expired_payload_cannot_retarget(submit_env):
    env,rid=submit_env;c,users,*_=env[0];ctx,result=prepare(submit_env);confirmation,_=exact(submit_env,result)
    saved=requests._owned(c,users[0],rid)
    c.execute('DELETE FROM supply_request_draft_line WHERE request_id=?',(rid,));c.execute('DELETE FROM supply_request WHERE id=?',(rid,));c.commit()
    c.execute('INSERT INTO supply_request ('+','.join(saved)+') VALUES ('+','.join('?' for _ in saved)+')',tuple(saved.values()));c.commit()
    p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
    assert p['state']=='cancelled' and p['fields_json'] is None
    assert 'Recorded outcome' not in command(env,confirmation,12)['text'] and requests._owned(c,users[0],rid)['approval_status']=='draft'


def test_submission_is_independent_of_draft_grant_and_pending_link_requires_read(linking,monkeypatch):
    for flag in ('SUPPLIES_SUBMIT','SUPPLIES_READ'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    c,users,*_=linking;_,raw,_=start(linking)
    with pytest.raises(ValueError):links.claim(c,linking[4],raw,[submitter.ACTION],NOW)
    links.claim(c,linking[4],raw,['supplies.read',submitter.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_SUPPLIES_SUBMIT_ENABLED','0')
    challenge=rows(c,'SELECT * FROM telegram_link_challenge')[0]
    with transaction(c):assert links.confirm(c,101,challenge['confirm_hash'],bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_draft_revocation_does_not_cancel_independent_submission(submit_env,monkeypatch):
    env,rid=submit_env;c,users,*_=env[0]
    grant(env[0],'supplies.draft',monkeypatch)
    ctx,result=prepare(submit_env);confirmation,_=exact(submit_env,result)
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='supplies.draft'",(links.stamp(NOW),));c.commit()
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'
    assert 'Recorded outcome' in command(env,confirmation,12)['text']


@pytest.mark.parametrize('bad_text',['🌿'*2000,'Purpose with \u202e control'])
def test_complete_unrenderable_source_is_refused_without_truncation(submit_env,bad_text):
    env,rid=submit_env;c,users,*_=env[0]
    requests.save_draft(c,users[0],{'purpose':bad_text,'date_needed':None,'lines':[{'item_id':env[1],'requested_quantity':2}]},request_id=rid,expected_revision=1,operation_key=key())
    before=native(c)
    with pytest.raises(ValueError):prepare(submit_env)
    assert before==native(c) and not rows(c,'SELECT * FROM telegram_operation')


def test_expiry_scrubs_source_projection_and_foreign_contexts_cannot_start(submit_env):
    env,rid=submit_env;c,users,*_=env[0];ctx,result=prepare(submit_env)
    confirmation,_=exact(submit_env,result)
    for changed in ({'generation':'a'*32},{'sender_id':102},{'topic_id':1}):
        with pytest.raises(ValueError):actions.recover(c,{**ctx,**changed},submitter.ACTION,result['operation_id'])
    before=len(rows(c,'SELECT * FROM telegram_meeting_origin'))
    for n,kind in enumerate(('group','topic','sender','callback'),12):
        packet=update(n,text='/supply_submit')
        if kind=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif kind=='topic':packet['message']['message_thread_id']=1
        elif kind=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        else:packet={'update_id':n,'callback_query':{'id':'synthetic','from':{'id':101},'data':'/supply_submit'}}
        assert '?origin=' not in submit(env[0][3],packet).json().get('text','')
    assert before==len(rows(c,'SELECT * FROM telegram_meeting_origin'))
    with transaction(c):actions.cleanup_in_transaction(c,NOW+timedelta(minutes=6))
    p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
    assert p['state']=='cancelled' and all(p[key] is None for key in ('fields_json','summary_json','expected_json'))
    assert 'Recorded outcome' not in command(env,confirmation,17).get('text','')
    assert requests._owned(c,users[0],rid)['approval_status']=='draft'
