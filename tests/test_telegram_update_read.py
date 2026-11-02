"""Own-notice acknowledgement changes only an exact native read marker."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re
import sqlite3

import pytest

import backups

from documents_storage import rows,transaction
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_update_read as manage
import work_discussion as discussion
import work_updates
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_discussion_updates import inbox_env,seed
from tests.test_telegram_comment_manage import snapshot


@pytest.fixture(params=[True,False])
def ack_env(inbox_env,monkeypatch,request):
    grant(inbox_env[0],manage.ACTION,monkeypatch)
    notice=seed(inbox_env,task_level=request.param)
    return inbox_env,{**notice,"task_id":inbox_env[2]["id"] if request.param else None}


def prepare(state,key='notice-acknowledgement-key',number=10,**changes):
    source,notice=state;env,_,_=source;c,users,*_=env
    guide=command(env,'/update_read',number)['text']
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,manage.ACTION)
    return ctx,actions.issue(c,ctx,manage.ACTION,key,{'notice_id':notice['id'],'revision':notice['revision'],**changes},NOW)


def exact(state,result,number=20):
    text=command(state[0][0],'/updateread_preview '+result['operation_id'],number)['text']
    assert 'Discussion read acknowledgement preview' in text and 'StoredPrivate' not in text
    assert manage.inbox.common.units(text)<=4096
    return re.search(r'/updateread_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_exact_ack_changes_only_own_read_marker_and_replay_is_read_only(ack_env):
    source,notice=ack_env;env,item,task=source;c,users,*_=env
    before=snapshot(c);ctx,result=prepare(ack_env);confirmation=exact(ack_env,result)
    assert snapshot(c)==before and work_updates.read_revision(c,users[0]['id'],notice['comment_id'])==0
    text=command(env,confirmation,21)['text'];assert 'Recorded outcome: notice marked read.' in text
    assert 'Recorded acknowledged revision: 1' in text and 'Current read revision: 1' in text
    after=snapshot(c)
    for table in before:
        if table!='work_comment_read':assert before[table]==after[table]
    assert work_updates.read_revision(c,users[0]['id'],notice['comment_id'])==1
    for number,text in ((22,confirmation),(23,'/updateread_receipt '+result['operation_id'])):
        assert 'Recorded outcome:' in command(env,text,number)['text'] and snapshot(c)==after
    assert 'Update '+str(notice['id'])+' ·' not in command(env,'/my_updates',24)['text']
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_ack_of_old_notice_never_marks_newer_comment_revision_read(ack_env):
    source,notice=ack_env;env,item,task=source;c,users,*_=env
    discussion.edit(c,users[3],item['id'],notice['task_id'],notice['comment_id'],1,'StoredPrivateNewerText')
    _,result=prepare(ack_env);confirmation=exact(ack_env,result)
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    assert work_updates.read_revision(c,users[0]['id'],notice['comment_id'])==1
    discussion.edit(c,users[3],item['id'],notice['task_id'],notice['comment_id'],2,'StoredPrivateLatestText')
    before=snapshot(c);text=command(env,confirmation,22)['text']
    assert 'Current revision 3' in text and 'Recorded acknowledged revision: 1' in text and before==snapshot(c)


@pytest.mark.parametrize('change',['edit','read','notice','source'])
def test_changed_preview_cannot_acknowledge(ack_env,change):
    source,notice=ack_env;env,item,task=source;c,users,*_=env
    ctx,result=prepare(ack_env);confirmation=exact(ack_env,result)
    if change=='edit':discussion.edit(c,users[3],item['id'],notice['task_id'],notice['comment_id'],1,'Changed source text')
    elif change=='read':work_updates.mark_read(c,users[0],item['id'],notice['task_id'],[(notice['comment_id'],1)])
    elif change=='notice':c.execute('UPDATE work_notice SET reason=? WHERE id=?',('following',notice['id']));c.commit()
    else:c.execute('UPDATE work_case SET title=? WHERE id=?',('Changed source title',item['id']));c.commit()
    before=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21).get('text','') and before==snapshot(c)


@pytest.mark.parametrize('fields',[{'notice_id':999999},{'notice_id':True},{'revision':2},{'revision':'01'},{'revision':0},{'revision':-1},{'body':'no text'},{'task_id':1},{'observed':[[1,1]]}])
def test_strict_one_notice_and_exact_revision_fields(ack_env,fields):
    before=snapshot(ack_env[0][0][0])
    with pytest.raises(ValueError):prepare(ack_env,**fields)
    assert before==snapshot(ack_env[0][0][0])


def test_foreign_notice_is_denied_even_for_a_work_lead(ack_env):
    source,notice=ack_env;env,item,task=source;c,users,*_=env
    other=discussion.post(c,users[3],item['id'],'StoredPrivateOtherRecipient',mentions=[users[1]['id']])
    foreign=rows(c,'SELECT id FROM work_notice WHERE comment_id=? AND user_id=?',(other,users[1]['id']))[0]['id']
    before=snapshot(c)
    with pytest.raises(ValueError,match='unavailable'):prepare(ack_env,notice_id=foreign)
    assert before==snapshot(c)


@pytest.mark.parametrize('failure',['native','receipt','handoff'])
def test_native_read_and_receipt_handoff_rollback_together(ack_env,monkeypatch,failure):
    source,notice=ack_env;env,*_=source;c,*_=env
    _,result=prepare(ack_env);confirmation=exact(ack_env,result);before=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='native':
        original=work_updates.mark_read_in_transaction
        def failed(*args,**kwargs):original(*args,**kwargs);fail()
        monkeypatch.setattr(work_updates,'mark_read_in_transaction',failed)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[manage.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_ack_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=confirmation))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert before==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmations_record_once(ack_env):
    env=ack_env[0][0];c,users,path,*_=env;ctx,result=prepare(ack_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1] and outcomes[0]['state']=='committed'
    assert work_updates.read_revision(c,users[0]['id'],ack_env[1]['comment_id'])==1


@pytest.mark.parametrize('guard',['work.read','work.updates.read',manage.ACTION,'inbox_pilot','ack_pilot','delivery','inbound','direct','module','disconnect'])
def test_current_consent_and_private_guards_prevent_stale_confirmation(ack_env,monkeypatch,guard):
    env=ack_env[0][0];c,*_=env;ctx,result=prepare(ack_env);confirmation=exact(ack_env,result)
    if guard in ('work.read','work.updates.read',manage.ACTION):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),guard));c.commit()
    elif guard=='disconnect':links.disconnect(c,env[4],NOW)
    elif guard=='module':st.set_setting(c,'work.enabled','0')
    elif guard=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    else:monkeypatch.setenv('CSS_TELEGRAM_'+{'inbox_pilot':'WORK_UPDATES_READ','ack_pilot':'WORK_UPDATES_ACKNOWLEDGE'}.get(guard,guard.upper())+'_ENABLED','0')
    before=snapshot(c);response=submit(env[3],update(21,text=confirmation))
    assert response.status_code==(503 if guard=='inbound' else 200)
    assert 'Recorded outcome:' not in response.json().get('text','') and before==snapshot(c)
    if guard in ('work.read','work.updates.read',manage.ACTION,'disconnect'):
        assert rows(c,'SELECT state,fields_json FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]=={'state':'cancelled','fields_json':None}


def test_foreign_context_groups_topics_cross_protocol_and_duplicate_update(ack_env):
    env=ack_env[0][0];c,*_=env;ctx,result=prepare(ack_env);confirmation=exact(ack_env,result);before=snapshot(c)
    for n,change in enumerate(('sender','group','topic','protocol'),21):
        packet=update(n,text=confirmation)
        if change=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        elif change=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif change=='topic':packet['message']['message_thread_id']=7
        else:packet['message']['text']='/workedit_confirm '+result['token']
        assert 'Recorded outcome:' not in submit(env[3],packet).json().get('text','')
    assert before==snapshot(c)
    packet=update(30,text=confirmation);assert 'Recorded outcome:' in submit(env[3],packet).json()['text']
    assert 'method' not in submit(env[3],packet).json()


def test_prepare_fetches_no_comment_body_or_task_submission(ack_env):
    source,notice=ack_env;env,*_=source;c,users,*_=env
    def authorize(op,table,column,*_):
        if op==sqlite3.SQLITE_READ and ((table=='work_comment_revision' and column=='body') or (table=='work_task' and column in ('submission','expected_output'))):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    c.set_authorizer(authorize)
    try:summary=manage.Adapter('read').prepare(c,users[0],{'notice_id':notice['id'],'revision':1})[1]
    finally:c.set_authorizer(None)
    assert 'StoredPrivate' not in str(summary)


def test_retention_removes_source_routing(ack_env):
    env=ack_env[0][0];c,*_=env;_,result=prepare(ack_env);confirmation=exact(ack_env,result)
    command(env,confirmation,21)
    with transaction(c):actions.cleanup_in_transaction(c,NOW+timedelta(days=181))
    op=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]
    assert op['result_code']=='retained_key' and all(op[k] is None for k in ('target_id','comment_id','comment_revision','expected_revision','context_json'))


def test_link_requires_separate_read_consents_and_all_pilots(linking,monkeypatch):
    c,users,path,client,payload=linking;_,raw,code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_ACKNOWLEDGE_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_READ_ENABLED','1')
    for scopes in ([manage.ACTION],['work.read',manage.ACTION],['work.updates.read',manage.ACTION]):
        with pytest.raises(ValueError):links.claim(c,payload,raw,scopes,NOW)
    links.claim(c,payload,raw,['work.read','work.updates.read',manage.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


@pytest.mark.parametrize('phase',['prepare','confirm','receipt'])
@pytest.mark.parametrize('change',['work_access','document_access'])
def test_consents_never_grant_source_or_linked_document_access(ack_env,phase,change):
    source,notice=ack_env;env,item,task=source;c,users,*_=env
    doc=linked_document(env,item,'2026-10-30') if change=='document_access' else None
    if phase!='prepare':
        _,result=prepare(ack_env);confirmation=exact(ack_env,result)
        if phase=='receipt':assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    if change=='work_access':c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']))
    else:c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']))
    c.commit();before=snapshot(c)
    if phase=='prepare':
        with pytest.raises(ValueError):prepare(ack_env)
    else:
        text=command(env,confirmation if phase=='confirm' else '/updateread_receipt '+result['operation_id'],22).get('text','')
        assert 'Recorded outcome:' not in text and item['title'] not in text
    assert before==snapshot(c)


@pytest.mark.parametrize('change',['restore','account','bot','expiry','documents_module'])
def test_current_identity_source_module_and_expiry(ack_env,change,monkeypatch):
    env=ack_env[0][0];c,users,path,*_=env;_,result=prepare(ack_env);confirmation=exact(ack_env,result)
    if change=='restore':backups.clear_restored_sessions(path)
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    else:st.set_setting(c,'documents.enabled','0')
    before=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21).get('text','') and before==snapshot(c)


def test_read_marker_never_decreases_and_already_read_notice_cannot_be_prepared(ack_env):
    source,notice=ack_env;env,item,task=source;c,users,*_=env
    discussion.edit(c,users[3],item['id'],notice['task_id'],notice['comment_id'],1,'StoredPrivateNewerText')
    work_updates.mark_read(c,users[0],item['id'],notice['task_id'],[(notice['comment_id'],2)])
    before=snapshot(c)
    with pytest.raises(ValueError,match='already read'):prepare(ack_env)
    assert work_updates.read_revision(c,users[0]['id'],notice['comment_id'])==2 and before==snapshot(c)


@pytest.mark.parametrize('status',['done','cancelled','completed'])
def test_native_terminal_source_visibility_allows_own_read_acknowledgement(ack_env,status):
    source,notice=ack_env;env,item,task=source;c,*_=env
    if status=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],))
    else:c.execute('UPDATE work_task SET status=? WHERE id=?',(status,task['id']))
    c.commit();before=snapshot(c);_,result=prepare(ack_env);confirmation=exact(ack_env,result)
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    after=snapshot(c)
    for table in before:
        if table!='work_comment_read':assert before[table]==after[table]
