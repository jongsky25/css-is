"""Confirmed blocker recording/clearing preserves native participant authority and atomicity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_blocker_manage as manage
import work
import work_reads
import work_tasks
import work_blockers as blockers
from tests.test_work import workspace,case,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_task_blockers import source_snapshot


@pytest.fixture
def manage_env(deadline_env,monkeypatch):
    for scope in manage.MODES.values():grant(deadline_env[0],scope,monkeypatch)
    return deadline_env


@pytest.fixture(params=['block','unblock'])
def action_env(manage_env,request):
    env,item,task=manage_env;c,users,*_=env
    if request.param=='unblock':
        task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',
                            {'reason':'StoredPrivateBlockerReason','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
    return env,item,task,request.param


def prepare(action_env,number=10,key='blocker-change-operation-key',**changes):
    env,item,task,mode=action_env;c,users,*_=env
    guide=command(env,'/task_'+mode,number)['text']
    assert manage.PATH+mode+'?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,manage.MODES[mode])
    fields={'case_id':item['id'],'task_id':task['id'],'reason':'Actor-entered '+mode+' reason'}
    if mode=='block':fields.update(followup_owner_id=users[3]['id'],followup_date='2026-10-30')
    fields.update(changes)
    return ctx,actions.issue(c,ctx,manage.MODES[mode],key,fields,NOW)


def confirmation(env,result,mode,number=20):
    text=command(env,'/task'+mode+'_preview '+result['operation_id'],number)['text']
    assert 'Task blocker preview: '+('record' if mode=='block' else 'clear') in text
    assert 'Actor-entered '+mode+' reason' in text and 'StoredPrivateBlockerReason' not in text
    assert manage.common.units(text)<=4096
    return re.search('/task'+mode+r'_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_exact_confirm_changes_only_recorded_blocker_and_native_history(action_env):
    env,item,task,mode=action_env;c,users,*_=env
    linked_document(env,item,'2026-10-30')
    before=source_snapshot(c)
    _,result=prepare(action_env)
    exact=confirmation(env,result,mode)
    assert source_snapshot(c)==before
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    if mode=='block':
        assert changed['blocker_reason']=='Actor-entered block reason' and changed['blocker_owner_id']==users[3]['id'] and changed['blocker_due_date']=='2026-10-30'
    else:assert changed['blocker_reason']=='' and changed['blocker_owner_id'] is None and changed['blocker_due_date'] is None
    assert changed['revision']==task['revision']+1
    for field in ('title','expected_output','owner_id','status','due_date','submission','mandatory','unit_id','proposed_owner_id'):
        assert changed[field]==task[field]
    for table in ('work_case','document','document_access','document_review','work_dependency','work_decision','work_decision_resolution'):
        assert source_snapshot(c)[table]==before[table]
    saved=source_snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/task'+mode+'_receipt '+result['operation_id'],23)['text']
    assert saved==source_snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_owner_can_record_only_self_followup(manage_env):
    env,item,task=manage_env;c,users,*_=env
    item=work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Other source lead')
    task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Actor owns source task'})
    saved=source_snapshot(c)
    with pytest.raises(ValueError,match='assign another'):prepare((env,item,task,'block'),followup_owner_id=users[2]['id'])
    assert source_snapshot(c)==saved
    _,result=prepare((env,item,task,'block'),11,followup_owner_id=users[0]['id'])
    assert 'Recorded outcome:' in command(env,confirmation(env,result,'block'),21)['text']
    assert work_reads.task(c,users[0],item['id'],task['id'])['blocker_owner_id']==users[0]['id']


def test_followup_owner_can_clear_after_lead_changes(manage_env):
    env,item,task=manage_env;c,users,*_=env
    task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'StoredPrivateBlockerReason','followup_owner_id':users[0]['id'],'followup_date':'2026-10-30'})
    item=work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Other source lead')
    assert task['owner_id']!=users[0]['id'] and not work.officer(c,users[0],task)
    _,result=prepare((env,item,task,'unblock'));exact=confirmation(env,result,'unblock')
    assert 'Recorded outcome:' in command(env,exact,21)['text']


def test_visibility_or_scope_alone_cannot_change_blocker(action_env):
    env,item,task,mode=action_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Other lead')
    saved=source_snapshot(c)
    with pytest.raises(ValueError,match='authority'):prepare(action_env)
    assert saved==source_snapshot(c)


@pytest.mark.parametrize('kind',['inactive','missing_document_access','no_work_membership'])
def test_selected_followup_must_already_have_source_access(manage_env,kind):
    env,item,task=manage_env;c,users,*_=env
    if kind=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit();selected=users[3]['id']
    elif kind=='missing_document_access':
        doc=linked_document(env,item,'2026-10-30')
        c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit();selected=users[3]['id']
    else:selected=users[2]['id']
    before=source_snapshot(c)
    with pytest.raises(ValueError):prepare((env,item,task,'block'),followup_owner_id=selected)
    assert source_snapshot(c)==before


def test_recording_never_overwrites_and_clearing_requires_recorded_blocker(manage_env):
    env,item,task=manage_env;c,users,*_=env
    with pytest.raises(ValueError,match='no recorded'):prepare((env,item,task,'unblock'))
    task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'StoredPrivateBlockerReason','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
    before=source_snapshot(c)
    with pytest.raises(ValueError,match='already recorded'):prepare((env,item,task,'block'),11)
    assert source_snapshot(c)==before


@pytest.mark.parametrize('change',['task','work','owner','authority','grant','read_grant','flag','module','expiry','disconnect','restore','cancelled','completed'])
def test_current_source_and_context_fence_stale_confirmation(action_env,monkeypatch,change):
    env,item,task,mode=action_env;c,users,path,_,payload=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    if change=='task':c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',('Changed task',task['id']));c.commit()
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Changed work',item['id']));c.commit()
    elif change=='owner':work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Changed source owner'})
    elif change=='authority':work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Lost coordinator authority')
    elif change in ('grant','read_grant'):
        scope=manage.MODES[mode] if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='cancelled':work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancelled'})
    else:c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    before=source_snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and before==source_snapshot(c)


@pytest.mark.parametrize('change',['name','inactive','document_access','work_membership'])
def test_selected_followup_changes_fence_recording(manage_env,change):
    env,item,task=manage_env;c,users,*_=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    _,result=prepare((env,item,task,'block'));exact=confirmation(env,result,'block')
    if change=='name':c.execute('UPDATE admin_user SET username=? WHERE id=?',('renamed@example.invalid',users[3]['id']));c.commit()
    elif change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    else:work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Followup no longer member'})
    before=source_snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and source_snapshot(c)==before


@pytest.mark.parametrize('bad',[{'reason':''},{'reason':'x'*501},{'reason':'unsafe\x00reason'},{'due_date':'2026-11-01'},{'submission':'replace'},{'task_id':999999}])
def test_invalid_fields_do_not_change_work(action_env,bad):
    before=source_snapshot(action_env[0][0])
    with pytest.raises(ValueError):prepare(action_env,**bad)
    assert source_snapshot(action_env[0][0])==before


@pytest.mark.parametrize('bad',[{'followup_date':''},{'followup_date':'2026-02-30'},{'followup_owner_id':''},{'followup_owner_id':999999}])
def test_recording_requires_exact_followup_person_and_date(manage_env,bad):
    before=source_snapshot(manage_env[0][0])
    with pytest.raises(ValueError):prepare((*manage_env,'block'),**bad)
    assert source_snapshot(manage_env[0][0])==before


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_source_preview_receipt_and_handoff_roll_back_together(action_env,monkeypatch,failure):
    env,item,task,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode);before=source_snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[manage.MODES[mode]],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_blocker_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert source_snapshot(c)==before
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmations_record_one_source_change(action_env):
    env,item,task,mode=action_env;c,users,path,*_=env
    ctx,result=prepare(action_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert work_reads.task(c,users[0],item['id'],task['id'])['revision']==task['revision']+1


@pytest.mark.parametrize('when',['pending','committed'])
def test_deleted_task_fences_preview_and_receipt_against_id_reuse(action_env,when):
    env,item,task,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Other output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    if when=='committed':
        text=command(env,'/task'+mode+'_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22).get('text','')
    assert work_reads.task(c,users[0],item['id'],replacement['id'])==replacement


@pytest.mark.parametrize('when',['before','after'])
def test_active_formal_review_amendments_remain_in_source_ui(action_env,when):
    env,item,task,mode=action_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Blocker target','expected_output':'Evidence','unit_id':reviewed['unit_id']})
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],reviewed['unit_id'],links.stamp(NOW)));c.commit()
    if mode=='unblock':target=blockers.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'block',{'reason':'StoredPrivateBlockerReason','followup_owner_id':users[0]['id'],'followup_date':'2026-10-30'})
    kwargs={'followup_owner_id':users[0]['id']} if mode=='block' else {}
    if when=='before':
        formal_review(c,users,request_consolidation(c,users,output,reviewed));before=source_snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,target,mode),**kwargs)
    else:
        _,result=prepare((env,reviewed,target,mode),**kwargs);exact=confirmation(env,result,mode)
        formal_review(c,users,request_consolidation(c,users,output,reviewed));before=source_snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert source_snapshot(c)==before


def test_groups_direct_and_other_action_protocols_cannot_change_blockers(action_env,monkeypatch):
    env,item,task,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode);before=source_snapshot(c)
    other='unblock' if mode=='block' else 'block'
    for number,text in enumerate(('/task'+other+'_confirm '+result['token'],'/task_confirm '+result['token'],'/deadline_confirm '+result['token']),21):
        assert 'Recorded outcome:' not in command(env,text,number).get('text','')
    packet=update(25,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,26)
    assert source_snapshot(c)==before


@pytest.mark.parametrize('mode',['block','unblock'])
def test_link_requires_separate_work_read_and_current_pilot(linking,monkeypatch,mode):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[manage.MODES[mode]],NOW)
    links.claim(c,payload,raw,['work.read',manage.MODES[mode]],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_native_caller_owned_contract_rejects_missing_transaction(manage_env):
    env,item,task=manage_env;c,users,*_=env
    assert not c.in_transaction
    with pytest.raises(RuntimeError,match='caller transaction'):
        blockers.mutate_in_transaction(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'Missing transaction'})


def test_blocker_change_does_not_resolve_prerequisites_or_changed_direction(action_env):
    env,item,task,mode=action_env;c,users,*_=env
    task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start source'})
    upstream=work_tasks.create(c,users[0],item['id'],{'title':'Pending prerequisite','expected_output':'Evidence','unit_id':item['unit_id']})
    task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'reason':'Source dependency','prerequisite_id':upstream['id']})
    import work_discussion as discussion
    import work_decisions as decisions
    message=discussion.post(c,users[0],item['id'],'StoredPrivateDecisionMessage',task_id=task['id'])
    decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'StoredPrivateDecision',
                     'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    before=source_snapshot(c)
    _,result=prepare((env,item,task,mode));exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    for table in ('work_dependency','work_decision','work_decision_task','work_decision_resolution'):
        assert source_snapshot(c)[table]==before[table]
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    with pytest.raises(ValueError,match='Resolve'):work_tasks.mutate(c,users[3],item['id'],task['id'],changed['revision'],'submit',{'reason':'Still blocked','submission':'Cannot submit'})


@pytest.mark.parametrize('state',['done','cancelled'])
def test_terminal_task_blocker_changes_are_refused(action_env,state):
    env,item,task,mode=action_env;c,*_=env
    c.execute('UPDATE work_task SET status=? WHERE id=?',(state,task['id']));c.commit()
    before=source_snapshot(c)
    with pytest.raises(ValueError):prepare(action_env)
    assert source_snapshot(c)==before


def test_receipt_reports_later_source_blocker_without_repeating_or_disclosing_it(action_env):
    env,item,task,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=work_reads.task(c,users[0],item['id'],task['id'])
    if mode=='block':blockers.mutate(c,users[0],item['id'],task['id'],current['revision'],'unblock',{'reason':'Later source resolution'})
    else:blockers.mutate(c,users[0],item['id'],task['id'],current['revision'],'block',{'reason':'StoredPrivateLaterBlocker','followup_owner_id':users[3]['id'],'followup_date':'2026-10-31'})
    before=source_snapshot(c)
    text=command(env,'/task'+mode+'_receipt '+result['operation_id'],22)['text']
    assert 'Recorded outcome:' in text and 'Current recorded blocker: '+('no' if mode=='block' else 'yes') in text
    assert 'StoredPrivate' not in text and before==source_snapshot(c)


def test_changed_blocker_record_requires_fresh_private_preview(action_env):
    env,item,task,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',
                    {'reason':'StoredPrivateChangedBlocker','followup_owner_id':users[3]['id'],'followup_date':'2026-10-31'})
    before=source_snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and before==source_snapshot(c)


def test_clearing_does_not_require_former_followup_or_task_owner_to_remain_active(manage_env):
    env,item,task=manage_env;c,users,*_=env
    task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'StoredPrivateBlockerReason','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    _,result=prepare((env,item,task,'unblock'));exact=confirmation(env,result,'unblock')
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert work_reads.task(c,users[0],item['id'],task['id'])['blocker_reason']==''
