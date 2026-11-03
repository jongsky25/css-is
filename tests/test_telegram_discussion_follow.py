"""Exact own follows preserve thread coverage, native notices and atomic recovery."""
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
import telegram_discussion_follow as manage
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_comment_manage import snapshot


@pytest.fixture
def follow_env(deadline_env,monkeypatch):
    grant(deadline_env[0],manage.ACTION,monkeypatch)
    return deadline_env


@pytest.fixture(params=[('follow',None),('unfollow',None),('follow','task'),('unfollow','task')])
def change_env(follow_env,request):
    env,item,task=follow_env;c,users,*_=env;choice,target=request.param
    task_id=task['id'] if target else None
    if choice=='unfollow':work_updates.follow(c,users[0],item['id'],task_id)
    return follow_env,{'case_id':item['id'],'task_id':task_id,'choice':choice}


def prepare(state,number=10,key='discussion-follow-operation',**changes):
    source,fields=state;env,*_=source;c,users,*_=env
    guide=command(env,'/discussion_follow',number)['text']
    assert manage.PATH+'change?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,manage.ACTION)
    return ctx,actions.issue(c,ctx,manage.ACTION,key,{**fields,**changes},NOW)


def exact(state,result,number=20):
    text=command(state[0][0],'/discussionfollow_preview '+result['operation_id'],number)['text']
    assert 'Discussion follow preview' in text and 'StoredPrivate' not in text
    assert manage.common.units(text)<=4096
    return re.search(r'/discussionfollow_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_confirmation_changes_only_own_exact_follow_and_recovers_without_replay(change_env):
    source,fields=change_env;env,item,task=source;c,users,*_=env
    work_updates.follow(c,users[3],item['id'],fields['task_id'])
    discussion.post(c,users[3],item['id'],'StoredPrivateExistingNotice',mentions=[users[0]['id']])
    before=snapshot(c);other=rows(c,'SELECT * FROM work_follow WHERE user_id<>?',(users[0]['id'],))
    ctx,result=prepare(change_env);confirmation=exact(change_env,result)
    assert before==snapshot(c)
    text=command(env,confirmation,21)['text']
    label='followed' if fields['choice']=='follow' else 'unfollowed'
    assert 'Recorded outcome: discussion '+label+'.' in text
    assert work_updates.following(c,users[0],item['id'],fields['task_id'])==(fields['choice']=='follow')
    after=snapshot(c)
    for table in before:
        if table!='work_follow':assert before[table]==after[table]
    assert other==rows(c,'SELECT * FROM work_follow WHERE user_id<>?',(users[0]['id'],))
    for number,text in ((22,confirmation),(23,'/discussionfollow_receipt '+result['operation_id'])):
        assert 'Recorded outcome:' in command(env,text,number)['text'] and after==snapshot(c)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    # Read/acknowledgement and delivery scopes are not silently granted.
    assert not links.authorized(c,users[0]['id'],'work.updates.read')
    assert not links.authorized(c,users[0]['id'],'work.updates.acknowledge')


@pytest.mark.parametrize('fields',[{'case_id':999999},{'case_id':True},{'task_id':0},{'task_id':True},{'task_id':999999},{'choice':'toggle'},{'choice':True},{'user_id':1},{'enabled':True},{'body':'text'}])
def test_strict_exact_scope_and_choice(follow_env,fields):
    env,item,task=follow_env;state=(follow_env,{'case_id':item['id'],'task_id':None,'choice':'follow'})
    before=snapshot(env[0])
    with pytest.raises(ValueError):prepare(state,**fields)
    assert before==snapshot(env[0])


def test_task_from_another_work_is_not_an_alternative_scope(follow_env):
    env,item,task=follow_env;c,users,*_=env;other=case(c,users[0],item['unit_id'])
    before=snapshot(c)
    with pytest.raises(ValueError):prepare((follow_env,{'case_id':other['id'],'task_id':task['id'],'choice':'follow'}))
    assert before==snapshot(c)


def test_already_matching_preference_requires_no_operation(change_env):
    source,fields=change_env;env,item,task=source;c,users,*_=env
    work_updates.follow(c,users[0],item['id'],fields['task_id'],fields['choice']=='follow')
    before=snapshot(c)
    with pytest.raises(ValueError,match='already'):prepare(change_env)
    assert before==snapshot(c) and not rows(c,'SELECT * FROM telegram_operation')


def test_native_future_notice_coverage_and_unfollow_preserve_other_scopes(change_env):
    source,fields=change_env;env,item,task=source;c,users,*_=env
    # A distinct task follow survives the work-wide change, and vice versa.
    other=work_tasks.create(c,users[0],item['id'],{'title':'Other scope task','expected_output':'StoredPrivateOutput','unit_id':item['unit_id']})
    work_updates.follow(c,users[0],item['id'],other['id'])
    _,result=prepare(change_env);confirmation=exact(change_env,result)
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    assert work_updates.following(c,users[0],item['id'],other['id'])
    chosen=fields['choice']=='follow'
    for task_id in (None,task['id'],other['id']):
        cid=discussion.post(c,users[3],item['id'],'StoredPrivateFuturePost',task_id=task_id)
        found=rows(c,'SELECT * FROM work_notice WHERE comment_id=? AND user_id=?',(cid,users[0]['id']))
        expected=(task_id==other['id'] or (chosen and (fields['task_id'] is None or task_id==fields['task_id'])))
        assert bool(found)==expected


def test_task_unfollow_with_work_follow_retains_effective_coverage_and_direct_notices(follow_env):
    env,item,task=follow_env;c,users,*_=env
    for target in (None,task['id']):work_updates.follow(c,users[0],item['id'],target)
    state=(follow_env,{'case_id':item['id'],'task_id':task['id'],'choice':'unfollow'})
    _,result=prepare(state);text=command(env,'/discussionfollow_preview '+result['operation_id'],20)['text']
    assert 'work-wide follow is currently on' in text and 'also covers this task' in text
    confirmation=re.search(r'/discussionfollow_confirm [A-Za-z0-9_-]{43}',text)[0]
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    cid=discussion.post(c,users[3],item['id'],'Still covered by work follow',task_id=task['id'])
    assert rows(c,'SELECT reason FROM work_notice WHERE comment_id=? AND user_id=?',(cid,users[0]['id']))==[{'reason':'following'}]
    work_updates.follow(c,users[0],item['id'],enabled=False)
    parent=discussion.post(c,users[0],item['id'],'StoredPrivateParent',task_id=task['id'])
    for why in ('mention','reply'):
        cid=discussion.post(c,users[3],item['id'],'Direct notice survives',task_id=task['id'],
                            parent_id=parent if why=='reply' else None,mentions=[users[0]['id']] if why=='mention' else [])
        assert rows(c,'SELECT reason FROM work_notice WHERE comment_id=? AND user_id=?',(cid,users[0]['id']))==[{'reason':why}]


@pytest.mark.parametrize('change',['selected','work','work_access','document_access','document_revision','work.read','work.follow','pilot','module','documents_module','expiry','disconnect','restore','account','bot','direct'])
def test_stale_source_scope_and_context_refuse_confirmation(follow_env,change,monkeypatch):
    env,item,task=follow_env;c,users,path,_,payload=env
    if change.startswith('document_'):doc=linked_document(env,item,'2026-10-30')
    state=(follow_env,{'case_id':item['id'],'task_id':task['id'],'choice':'follow'})
    _,result=prepare(state);confirmation=exact(state,result)
    if change=='selected':work_updates.follow(c,users[0],item['id'],task['id'])
    elif change=='work':c.execute('UPDATE work_case SET title=? WHERE id=?',('Changed title',item['id']));c.commit()
    elif change=='work_access':c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change=='document_revision':c.execute('UPDATE document SET revision=revision+1 WHERE id=?',(doc['id'],));c.commit()
    elif change in ('work.read',manage.ACTION):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),change));c.commit()
    elif change=='pilot':monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOW_ENABLED','0')
    elif change in ('module','documents_module'):st.set_setting(c,('work' if change=='module' else 'documents')+'.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    else:monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    before=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21).get('text','') and before==snapshot(c)
    if change in ('work.read','work.follow','disconnect'):
        assert rows(c,'SELECT state,fields_json FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]=={'state':'cancelled','fields_json':None}


def test_changed_work_wide_follow_invalidates_task_preview(follow_env):
    env,item,task=follow_env;c,users,*_=env
    state=(follow_env,{'case_id':item['id'],'task_id':task['id'],'choice':'follow'})
    _,result=prepare(state);confirmation=exact(state,result)
    work_updates.follow(c,users[0],item['id']);before=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21)['text'] and before==snapshot(c)


def test_receipt_distinguishes_recorded_change_from_later_native_follow_change(change_env):
    source,fields=change_env;env,item,task=source;c,users,*_=env
    _,result=prepare(change_env);confirmation=exact(change_env,result)
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    work_updates.follow(c,users[0],item['id'],fields['task_id'],fields['choice']!='follow');before=snapshot(c)
    text=command(env,confirmation,22)['text']
    assert 'Recorded outcome: discussion '+('followed' if fields['choice']=='follow' else 'unfollowed') in text
    assert 'Current exact follow: '+('off' if fields['choice']=='follow' else 'on') in text and before==snapshot(c)


@pytest.mark.parametrize('failure',['native','receipt','handoff'])
def test_native_follow_receipt_and_handoff_roll_back_together(change_env,monkeypatch,failure):
    env=change_env[0][0];c,*_=env;_,result=prepare(change_env);confirmation=exact(change_env,result);before=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='native':
        original=work_updates.follow_in_transaction
        def failed(*args,**kwargs):original(*args,**kwargs);fail()
        monkeypatch.setattr(work_updates,'follow_in_transaction',failed)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[manage.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_follow_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=confirmation))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert before==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmation_changes_follow_once(change_env):
    env=change_env[0][0];c,users,path,*_=env;ctx,result=prepare(change_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1] and outcomes[0]['state']=='committed'
    selected=change_env[1]
    assert work_updates.following(c,users[0],selected['case_id'],selected['task_id'])==(selected['choice']=='follow')


def test_preview_never_reads_discussion_bodies_or_task_submissions(follow_env):
    env,item,task=follow_env;c,users,*_=env
    def authorize(op,table,column,*_):
        if op==sqlite3.SQLITE_READ and ((table=='work_comment_revision' and column=='body') or (table=='work_task' and column in ('submission','expected_output'))):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    c.set_authorizer(authorize)
    try:clean,summary,expected=manage.Adapter('change').prepare(c,users[0],{'case_id':item['id'],'task_id':task['id'],'choice':'follow'})
    finally:c.set_authorizer(None)
    assert 'StoredPrivate' not in str(summary)


def test_groups_topics_cross_protocol_and_duplicate_updates(change_env):
    env=change_env[0][0];c,*_=env;ctx,result=prepare(change_env);confirmation=exact(change_env,result);before=snapshot(c)
    for n,change in enumerate(('sender','group','topic','protocol'),21):
        packet=update(n,text=confirmation)
        if change=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        elif change=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif change=='topic':packet['message']['message_thread_id']=7
        else:packet['message']['text']='/updateread_confirm '+result['token']
        assert 'Recorded outcome:' not in submit(env[3],packet).json().get('text','')
    assert before==snapshot(c)
    packet=update(30,text=confirmation);assert 'Recorded outcome:' in submit(env[3],packet).json()['text']
    assert 'method' not in submit(env[3],packet).json()


def test_independent_link_consent_and_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking;_,raw,code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOW_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[manage.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',manage.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOW_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_native_helper_requires_caller_transaction_and_existing_wrapper_is_atomic(follow_env):
    env,item,task=follow_env;c,users,*_=env;before=snapshot(c)
    with pytest.raises(RuntimeError,match='active transaction'):work_updates.follow_in_transaction(c,users[0],item['id'])
    assert before==snapshot(c)
    with pytest.raises(ValueError):
        with transaction(c):
            work_updates.follow_in_transaction(c,users[0],item['id']);raise ValueError('Caller rolls back')
    assert before==snapshot(c)


def test_retention_clears_source_identifiers(change_env):
    env=change_env[0][0];c,*_=env;_,result=prepare(change_env);confirmation=exact(change_env,result)
    command(env,confirmation,21)
    with transaction(c):actions.cleanup_in_transaction(c,NOW+timedelta(days=181))
    op=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]
    assert op['result_code']=='retained_key' and all(op[k] is None for k in ('target_id','expected_revision','context_json'))


@pytest.mark.parametrize('phase',['prepare','receipt'])
@pytest.mark.parametrize('change',['work_access','document_access'])
def test_consent_never_grants_source_access_at_prepare_or_receipt(follow_env,phase,change):
    env,item,task=follow_env;c,users,*_=env
    doc=linked_document(env,item,'2026-10-30') if change=='document_access' else None
    state=(follow_env,{'case_id':item['id'],'task_id':None,'choice':'follow'})
    if phase=='receipt':
        _,result=prepare(state);confirmation=exact(state,result)
        assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    if change=='work_access':c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']))
    else:c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']))
    c.commit();before=snapshot(c)
    if phase=='prepare':
        with pytest.raises(ValueError):prepare(state)
    else:
        text=command(env,'/discussionfollow_receipt '+result['operation_id'],22).get('text','')
        assert 'Recorded outcome:' not in text and item['title'] not in text
    assert before==snapshot(c)


def test_unrelated_account_follow_does_not_invalidate_own_preview(change_env):
    source,fields=change_env;env,item,task=source;c,users,*_=env
    _,result=prepare(change_env);confirmation=exact(change_env,result)
    work_updates.follow(c,users[3],item['id'],fields['task_id'])
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    assert work_updates.following(c,users[3],item['id'],fields['task_id'])


@pytest.mark.parametrize('status',['done','cancelled','completed'])
def test_native_terminal_discussions_remain_followable(follow_env,status):
    env,item,task=follow_env;c,*_=env
    if status=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],))
    else:c.execute('UPDATE work_task SET status=? WHERE id=?',(status,task['id']))
    c.commit();state=(follow_env,{'case_id':item['id'],'task_id':task['id'],'choice':'follow'})
    _,result=prepare(state);confirmation=exact(state,result)
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']


def test_disconnect_does_not_silently_erase_existing_native_follows(follow_env):
    env,item,task=follow_env;c,users,_,_,payload=env
    state=(follow_env,{'case_id':item['id'],'task_id':None,'choice':'follow'})
    _,result=prepare(state);confirmation=exact(state,result)
    assert 'Recorded outcome:' in command(env,confirmation,21)['text']
    before=snapshot(c);links.disconnect(c,payload,NOW);after=snapshot(c)
    for table in before:
        if table!='audit_log':assert before[table]==after[table]
    assert after['audit_log'][:-1]==before['audit_log'] and len(after['audit_log'])==len(before['audit_log'])+1
    assert rows(c,'SELECT actor,action FROM audit_log ORDER BY id DESC LIMIT 1')==[{'actor':users[0]['username'],'action':'telegram_disconnect'}]
