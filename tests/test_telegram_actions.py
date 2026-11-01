"""Dormant confirmation contract with a test-only real calendar adapter."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json

import pytest

import backups
import calendar_actions as calendar
from documents_storage import rows,transaction
import office_calendar as oc
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,activate
from tests.test_telegram_groups import registered


FORM={'title':'Synthetic meeting','kind':'meeting','status':'confirmed','start_date':'2026-10-26',
      'end_date':'','start_time':'09:00','end_time':'10:00','time_note':'','venue':'Synthetic venue',
      'modality':'f2f','meeting_url':'','note':'','owner_org_id':'','extra_org_ids':[],
      'audience':'bureau','people':[],'tags':'','repeat':'none','until':''}


class CalendarFixture:
    """Only tests install this adapter. T3.2 must implement the actual bot policy."""
    def __init__(self):
        self.calls=0;self.fail=False;self.anchor=None

    def prepare(self,c,user,form):
        fields,people,tags=calendar.prepare(c,user,form)
        clean={'fields':fields,'people':people,'tags':tags}
        summary={'fields':fields,'people':people,'timezone':'Asia/Manila','duration_minutes':60,'room':'No request'}
        expected={}
        if self.anchor:
            e=st.cal_get(c,self.anchor);expected={'sequence':e['sequence'],'updated_at':e['updated_at']}
        return clean,summary,expected

    def revalidate(self,c,user,clean,expected):
        if self.anchor:
            e=st.cal_get(c,self.anchor)
            if not e or expected!={'sequence':e['sequence'],'updated_at':e['updated_at']}:
                raise actions.Unavailable('Source changed.')
        # The shared service rechecks actor and active participants at commit.

    def apply(self,c,user,clean,operation_id):
        self.calls+=1
        eid=calendar.create_in_transaction(c,user,clean['fields'],clean['people'],clean['tags'])
        if self.fail:
            raise RuntimeError('Synthetic failure before receipt')
        return {'state':'committed','result_entry_id':eid,'result_code':'calendar_created'}

    def check_receipt(self,c,user,operation):
        if operation['result_entry_id'] and not oc.viewable_entry(c,user,operation['result_entry_id']):
            raise actions.Unavailable('Receipt unavailable.')


@pytest.fixture
def action_env(linking,monkeypatch):
    c,users,path,client,payload=linking
    activate(linking)
    for switch in ('CALENDAR_CREATE','CALENDAR_READ'):
        monkeypatch.setenv('CSS_TELEGRAM_'+switch+'_ENABLED','1')
    connection=rows(c,'SELECT * FROM telegram_connection')[0]
    c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
        VALUES (?,?,'calendar.create',?,?,?,?)''',(connection['id'],users[0]['id'],connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    context={'connection_id':connection['id'],'generation':connection['generation'],'sender_id':101,'chat_id':101,
             'topic_id':None,'registration_id':None,'registration_generation':None}
    adapter=CalendarFixture();monkeypatch.setitem(actions.ADAPTERS,'calendar.create',adapter)
    return linking,context,adapter


def issue(env,key='synthetic-action-key',**fields):
    linking,context,_=env
    return actions.issue(linking[0],context,'calendar.create',key,{**FORM,**fields},NOW)


def test_exact_preview_hash_only_token_and_one_atomic_receipt(action_env):
    linking,ctx,adapter=action_env;c,users,_,_,_=linking
    p=issue(action_env,people=[str(users[1]['id'])],note='Private normalized detail')
    assert p['preview']['timezone']=='Asia/Manila' and p['preview']['duration_minutes']==60
    assert p['preview']['fields']['title']=='Synthetic meeting'
    assert len(p['token'])==43 and p['token'] not in str(rows(c,'SELECT * FROM telegram_preview'))
    result=actions.confirm(c,ctx,p['token'],NOW)
    eid=result['result_entry_id']
    assert result['state']=='committed' and adapter.calls==1
    assert st.cal_get(c,eid)['source']=='app'
    assert c.execute('SELECT count(*) FROM calendar_entry_revision WHERE entry_id=?',(eid,)).fetchone()[0]==1
    assert c.execute('SELECT count(*) FROM calendar_outbox WHERE entry_id=?',(eid,)).fetchone()[0]>=1
    assert rows(c,'SELECT * FROM telegram_preview')[0]['fields_json'] is None
    assert actions.confirm(c,ctx,p['token'],NOW+timedelta(minutes=10))==result
    assert actions.recover(c,ctx,'calendar.create',p['operation_id'])==result
    assert adapter.calls==1
    assert issue(action_env,people=[str(users[1]['id'])],note='Private normalized detail')['token'] is None
    with pytest.raises(actions.Unavailable):
        issue(action_env,title='Other content')


@pytest.mark.parametrize('change',['expiry','sender','destination','generation','token','fields','source','inactive','participant','write_grant','read_grant','flag','restore','disconnect','rotation'])
def test_stale_foreign_or_revoked_confirmation_never_mutates(action_env,monkeypatch,change):
    linking,ctx,adapter=action_env;c,users,path,_,payload=linking
    anchor=st.cal_create(c,'Synthetic anchor','2026-10-26',audience='bureau',by='fixture')
    adapter.anchor=anchor
    p=issue(action_env,people=[str(users[1]['id'])]);when=NOW;context=dict(ctx);token=p['token']
    if change=='expiry':when+=timedelta(seconds=actions.TTL)
    elif change=='sender':context['sender_id']=999
    elif change=='destination':context['chat_id']=999
    elif change=='generation':context['generation']='f'*32
    elif change=='token':token='X'*43
    elif change=='fields':
        c.execute("UPDATE telegram_preview SET fields_json='{}'");c.commit()
    elif change=='source':st.cal_update(c,anchor,start_date='2026-10-27',by='fixture')
    elif change=='inactive':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='participant':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[1]['id'],));c.commit()
    elif change in ('write_grant','read_grant'):
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),'calendar.create' if change=='write_grant' else 'calendar.read'));c.commit()
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','0')
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    with pytest.raises(ValueError):actions.confirm(c,context,token,when)
    assert c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    assert not rows(c,"SELECT * FROM telegram_operation WHERE state='committed'")


def test_atomic_rollback_clears_business_audit_outbox_and_receipt(action_env):
    linking,ctx,adapter=action_env;c=linking[0];p=issue(action_env)
    before=c.execute('SELECT count(*) FROM audit_log').fetchone()[0]
    adapter.fail=True
    with pytest.raises(RuntimeError):actions.confirm(c,ctx,p['token'],NOW)
    assert not rows(c,'SELECT * FROM calendar_entry')
    assert c.execute('SELECT count(*) FROM audit_log').fetchone()[0]==before
    assert rows(c,'SELECT * FROM telegram_preview')[0]['state']=='pending'
    assert rows(c,'SELECT * FROM telegram_operation')[0]['state']=='pending'
    adapter.fail=False
    assert actions.confirm(c,ctx,p['token'],NOW)['state']=='committed'


def test_two_clients_race_and_timeout_after_commit_recover_original_receipt(action_env):
    linking,ctx,adapter=action_env;c,_,path,_,_=linking;p=issue(action_env)
    def confirm():
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,p['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:confirm(),range(2)))
    assert results[0]==results[1] and adapter.calls==1
    def lost_response():
        confirm()
        raise TimeoutError('Synthetic response lost after commit')
    with pytest.raises(TimeoutError):lost_response()
    assert actions.recover(c,ctx,'calendar.create',p['operation_id'])==results[0]
    assert adapter.calls==1 and c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1


def test_restart_preserves_preview_and_receipt_but_recovery_rechecks_access(action_env):
    linking,ctx,_=action_env;c,_,path,_,_=linking;p=issue(action_env)
    restarted=st.connect(path)
    try:
        st.init_db(restarted);result=actions.confirm(restarted,ctx,p['token'],NOW)
    finally:restarted.close()
    c.execute("UPDATE calendar_entry SET created_by='somebodyelse',audience='people' WHERE id=?",(result['result_entry_id'],));c.commit()
    with pytest.raises(actions.Unavailable):actions.recover(c,ctx,'calendar.create',p['operation_id'])
    with pytest.raises(actions.Unavailable):actions.confirm(c,ctx,p['token'],NOW)


def test_expiry_scrubbing_and_key_tombstone(action_env):
    linking,ctx,_=action_env;c=linking[0];p=issue(action_env)
    bot.cleanup(c,NOW+timedelta(seconds=301))
    preview=rows(c,'SELECT * FROM telegram_preview')[0]
    assert preview['fields_json'] is None and preview['summary_json'] is None and preview['state']=='cancelled'
    bot.cleanup(c,NOW+timedelta(days=2))
    assert not rows(c,'SELECT * FROM telegram_preview')
    # The cancellation trigger stamps real DB time, independently of NOW.
    cancelled_at=datetime.fromisoformat(rows(c,'SELECT * FROM telegram_operation')[0]['updated_at'].replace('Z','+00:00'))
    bot.cleanup(c,cancelled_at+timedelta(days=179))
    assert rows(c,'SELECT * FROM telegram_operation')[0]['result_code']=='preview_cancelled'
    bot.cleanup(c,cancelled_at+timedelta(days=181))
    assert rows(c,'SELECT * FROM telegram_operation')[0]['result_code']=='retained_key'
    with pytest.raises(actions.Unavailable):issue(action_env)


def test_unconsented_actions_remain_unavailable(linking,monkeypatch):
    assert set(actions.ADAPTERS)=={'calendar.create','rooms.request','tasks.acknowledge','tasks.submit','calendar.reschedule','calendar.cancel','rooms.withdraw','rooms.move','tasks.create','tasks.deadline'}
    c,_,_,client,payload=linking
    activate(linking)
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','1')
    assert bot.normalize(update(text='/meeting'))['command']=='/meeting'
    assert bot.normalize(update(text='/confirm_action '+'x'*43))['command'] is None
    assert 'rooms.request' in links.SCOPES
    assert submit(client,update(10,text='/meeting')).status_code==200
    assert not rows(c,'SELECT * FROM telegram_operation')
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_foreign_linked_actor_and_action_cannot_consume_or_recover(action_env):
    from tests.test_telegram_groups import bind
    linking,ctx,_=action_env;c,users,_,_,_=linking
    p=issue(action_env)
    bind(c,users[1],102)
    connection=rows(c,'SELECT * FROM telegram_connection WHERE telegram_user_id=102')[0]
    for scope in ('calendar.read','calendar.create'):
        c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],connection['account_id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()
    other={**ctx,'connection_id':connection['id'],'generation':connection['generation'],'sender_id':102,'chat_id':102}
    with pytest.raises(actions.Unavailable):actions.confirm(c,other,p['token'],NOW)
    with pytest.raises(actions.Unavailable):actions.recover(c,other,'calendar.create',p['operation_id'])
    assert rows(c,'SELECT * FROM telegram_preview')[0]['state']=='pending'
    assert not rows(c,'SELECT * FROM calendar_entry')


@pytest.mark.parametrize('change',['group_pause','topic_changed','provider_failure','proof_race','wrong_topic','success'])
def test_group_context_generation_and_fresh_membership_are_required(registered,monkeypatch,change):
    from tests.test_telegram_groups import register
    import telegram_groups as groups
    c,users,path,client,payload=registered
    group=register(registered,topic=7)
    connection=groups.linked(c,users[4]['id'])
    for switch in ('CALENDAR_CREATE','CALENDAR_READ'):
        monkeypatch.setenv('CSS_TELEGRAM_'+switch+'_ENABLED','1')
    for scope in ('calendar.read','calendar.create'):
        c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],connection['account_id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()
    context={'connection_id':connection['id'],'generation':connection['generation'],'sender_id':101,'chat_id':-100,
             'topic_id':7,'registration_id':group['id'],'registration_generation':group['generation']}
    adapter=CalendarFixture();monkeypatch.setitem(actions.ADAPTERS,'calendar.create',adapter)
    p=actions.issue(c,context,'calendar.create','group-test-operation',FORM,NOW)
    # Same actor/key in another destination cannot retrieve or replace this preview.
    private={**context,'chat_id':101,'topic_id':None,'registration_id':None,'registration_generation':None}
    with pytest.raises(actions.Unavailable):actions.issue(c,private,'calendar.create','group-test-operation',FORM,NOW)
    with pytest.raises(actions.Unavailable):actions.recover(c,private,'calendar.create',p['operation_id'])
    if change=='group_pause':groups.manage(c,payload,group['id'],group['generation'],'pause')
    elif change=='topic_changed':
        with transaction(c):groups.pause(c,-100,7,reason='topic_changed')
    elif change=='provider_failure':monkeypatch.setattr(bot.transport,'member_status',lambda *a:None)
    elif change=='wrong_topic':context={**context,'topic_id':8}
    elif change=='proof_race':
        def proof(*args):
            with transaction(c):groups.pause(c,-100,7,reason='changed_during_proof')
            return 'administrator'
        monkeypatch.setattr(bot.transport,'member_status',proof)
    if change=='success':
        assert actions.confirm(c,context,p['token'],NOW)['state']=='committed'
        assert adapter.calls==1
        return
    with pytest.raises(actions.Unavailable):actions.confirm(c,context,p['token'],NOW)
    assert adapter.calls==0 and not rows(c,'SELECT * FROM calendar_entry')


def test_pending_payloads_are_scrubbed_on_revoke_and_restore(action_env):
    linking,ctx,_=action_env;c,_,path,_,_=linking
    p=issue(action_env,note='Synthetic private payload')
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    preview=rows(c,'SELECT * FROM telegram_preview')[0]
    assert preview['state']=='cancelled' and preview['fields_json'] is None and preview['summary_json'] is None
    assert rows(c,'SELECT * FROM telegram_operation')[0]['state']=='cancelled'
    backups.clear_restored_sessions(path)
    assert actions.digest(p['token'])==preview['token_hash']


def test_upgrade_adds_preview_schema_without_altering_old_operations(action_env):
    linking,ctx,_=action_env;c,_,path,_,_=linking
    p=issue(action_env)
    for name in ('telegram_preview_connection','telegram_preview_group','telegram_preview_grant','telegram_room_calendar_grant','telegram_combined_room_grant','telegram_task_proposal_delete'):
        c.execute('DROP TRIGGER '+name)
    c.execute('DROP TABLE telegram_preview')
    c.execute('ALTER TABLE telegram_operation DROP COLUMN context_hash');c.commit()
    st.init_db(c)
    assert not rows(c,'SELECT * FROM telegram_preview')
    operation=rows(c,'SELECT * FROM telegram_operation')[0]
    assert operation['operation_id']==p['operation_id'] and operation['state']=='pending'
    assert operation['context_hash'] is None
    with pytest.raises(actions.Unavailable):actions.recover(c,ctx,'calendar.create',p['operation_id'])


@pytest.mark.parametrize('fields',[{'title':'x'*17000},[],{'title':float('nan')}])
def test_unbounded_or_unstructured_preview_is_rejected_before_storage(action_env,fields):
    linking,ctx,_=action_env;c=linking[0]
    with pytest.raises(actions.Unavailable):actions.issue(c,ctx,'calendar.create','invalid-fields-key',fields,NOW)
    assert not rows(c,'SELECT * FROM telegram_preview')


def test_failed_receipts_are_consumed_once(action_env,monkeypatch):
    linking,ctx,adapter=action_env;c=linking[0]
    def apply(c,user,clean,operation):
        adapter.calls+=1
        return {'state':'failed','result_code':'domain_declined'}
    monkeypatch.setattr(adapter,'apply',apply)
    p=issue(action_env)
    result=actions.confirm(c,ctx,p['token'],NOW)
    assert result['state']=='failed'
    assert actions.confirm(c,ctx,p['token'],NOW)==result and adapter.calls==1
    assert issue(action_env)['receipt']==result
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_atomic_receipt_failure_rolls_back_a_completed_domain_mutation(action_env):
    linking,ctx,adapter=action_env;c=linking[0];p=issue(action_env)
    c.execute("CREATE TRIGGER synthetic_receipt_failure BEFORE UPDATE OF state ON telegram_operation WHEN NEW.state='committed' BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END");c.commit()
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):actions.confirm(c,ctx,p['token'],NOW)
    assert not rows(c,'SELECT * FROM calendar_entry')
    assert rows(c,'SELECT * FROM telegram_preview')[0]['state']=='pending'
    c.execute('DROP TRIGGER synthetic_receipt_failure');c.commit()
    assert actions.confirm(c,ctx,p['token'],NOW)['state']=='committed'


def test_bounded_expiry_never_deletes_a_pending_preview_before_cancelling_its_operation(action_env):
    linking,ctx,_=action_env;c=linking[0]
    for i in range(25):issue(action_env,key='expiry-batch-key-'+str(i))
    bot.cleanup(c,NOW+timedelta(days=2))
    pending=rows(c,"SELECT operation_id FROM telegram_operation WHERE state='pending'")
    previews=rows(c,"SELECT operation_id FROM telegram_preview WHERE state='pending'")
    assert len(pending)==5 and {p['operation_id'] for p in pending}=={p['operation_id'] for p in previews}
    bot.cleanup(c,NOW+timedelta(days=2))
    assert not rows(c,'SELECT * FROM telegram_preview')
    assert not rows(c,"SELECT * FROM telegram_operation WHERE state='pending'")
    assert c.execute('SELECT count(*) FROM telegram_operation').fetchone()[0]==25
