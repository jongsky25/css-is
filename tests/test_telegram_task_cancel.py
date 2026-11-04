"""Private officer cancellation retains history and explicit completion/dependency rules."""
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
import telegram_task_cancel as cancellation
import work
import work_reads
import work_tasks
import work_blockers as blockers
import work_completion as completion
from tests.test_work import workspace,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_assign import assign_env,snapshot,link_source


@pytest.fixture
def cancel_env(assign_env,monkeypatch):
    grant(assign_env[0],cancellation.ACTION,monkeypatch)
    return assign_env


def prepare(cancel_env,number=10,key='task-cancellation-operation-key',**changes):
    env,item,task=cancel_env;c,users,*_=env
    guide=command(env,'/task_cancel',number)['text']
    assert cancellation.PATH+'cancel?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,cancellation.ACTION)
    fields={'case_id':item['id'],'task_id':task['id'],'reason':'Synthetic cancellation reason',**changes}
    return ctx,actions.issue(c,ctx,cancellation.ACTION,key,fields,NOW)


def confirmation(env,result,number=20):
    text=command(env,'/taskcancel_preview '+result['operation_id'],number)['text']
    assert 'Task cancellation preview' in text and 'New status: cancelled' in text and 'Reason:' in text
    assert 'outstanding-contribution checks' in text and 'dependent tasks requiring its acceptance remain blocked' in text
    assert 'DoNotExpose' not in text and '📌' not in text and cancellation.review.common.units(text)<=4096
    return re.search(r'/taskcancel_confirm [A-Za-z0-9_-]{43}',text)[0]


def advance(cancel_env,state='todo'):
    env,item,task=cancel_env;c,users,*_=env
    if state!='proposed':task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Source assignment'})
    if state in ('in_progress','for_review','done'):
        task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start source'})
    if state in ('for_review','done'):
        task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'submit',{'reason':'Source submission','submission':'DoNotExposeSubmission '+'📌'*7900})
    if state=='done':task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'accept',{'reason':'Source acceptance'})
    return env,item,task


@pytest.mark.parametrize('state',['proposed','todo','in_progress','for_review'])
def test_cancel_only_changes_state_revision_and_native_history(cancel_env,state):
    env,item,task=cancel_env;c,users,*_=env
    link_source(cancel_env)
    env,item,task=advance(cancel_env,state)
    before=snapshot(c)
    assert any(gap['id']==task['id'] for gap in completion.contribution_gaps(c,item['id']))
    _,result=prepare((env,item,task),reason='Cancel contribution\r\nPreserve source history')
    exact=confirmation(env,result)
    assert snapshot(c)==before
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    assert changed['status']=='cancelled' and changed['revision']==task['revision']+1
    for field in ('owner_id','due_date','submission','expected_output','title','mandatory','unit_id','proposed_owner_id'):
        assert changed[field]==task[field]
    for table in ('work_case','document','document_access','document_review','document_role_grant'):
        assert snapshot(c)[table]==before[table]
    assert not any(gap['id']==task['id'] for gap in completion.contribution_gaps(c,item['id']))
    assert rows(c,"SELECT * FROM work_event WHERE action='task_cancel'")[-1]['actor_id']==users[0]['id']
    if task['owner_id']:
        with pytest.raises(ValueError):work.get(c,users[3],item['id'])
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/taskcancel_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    assert 'reopen' not in work_tasks.actions(c,users[0],work.raw(c,item['id']),changed)


@pytest.mark.parametrize('actor_kind',['owner','lead','wrong_unit'])
def test_only_task_unit_officer_can_cancel(cancel_env,actor_kind):
    env,item,task=advance(cancel_env);c,users,*_=env
    c.execute('DELETE FROM document_role_grant WHERE user_id=?',(users[0]['id'],));c.commit()
    if actor_kind=='lead':work.confirm_lead(c,users[1],item['id'],item['revision'],users[0]['id'],'Lead alone')
    elif actor_kind=='owner':c.execute('UPDATE work_task SET owner_id=? WHERE id=?',(users[0]['id'],task['id']));c.commit()
    else:
        other=st.add_org_unit(c,'Other unit','division','OTHER/CANCEL')
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],other,links.stamp(NOW)));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError,match='contributing-unit officer'):prepare((env,item,task))
    assert snapshot(c)==saved


def test_task_unit_officer_can_cancel_without_case_unit_or_lead_authority(cancel_env):
    env,item,task=cancel_env;c,users,*_=env
    other=st.add_org_unit(c,'Contributing unit','division','OTHER/CONTRIBUTION')
    c.execute('DELETE FROM document_role_grant WHERE user_id=?',(users[0]['id'],))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],other,links.stamp(NOW)))
    c.execute('UPDATE work_task SET unit_id=? WHERE id=?',(other,task['id']));c.commit()
    assert not work.officer(c,users[0],item) and item['lead_id']!=users[0]['id']
    _,result=prepare(cancel_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']


@pytest.mark.parametrize('change',['task','work','owner','document','hidden_document','authority','completed','assigned','cancelled',
                                   'grant','read_grant','flag','module','expiry','disconnect','restore'])
def test_stale_source_or_lost_authority_blocks_cancellation(cancel_env,monkeypatch,change):
    env,item,task=cancel_env;c,users,path,_,payload=env
    if change in ('document','hidden_document'):doc=link_source(cancel_env)
    _,result=prepare(cancel_env);exact=confirmation(env,result)
    if change=='task':c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',('Changed source',task['id']));c.commit()
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Different work',item['id']));c.commit()
    elif change=='owner':c.execute('UPDATE work_task SET proposed_owner_id=?,revision=revision+1 WHERE id=?',(users[3]['id'],task['id']));c.commit()
    elif change=='document':c.execute("UPDATE document SET due_date='2026-10-27',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='hidden_document':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change=='authority':c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change=='assigned':work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Changed source assignment'})
    elif change=='cancelled':work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancelled'})
    elif change in ('grant','read_grant'):
        scope=cancellation.ACTION if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_CANCEL_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and saved==snapshot(c)


@pytest.mark.parametrize('state',['done','cancelled'])
def test_terminal_tasks_cannot_cancel_again(cancel_env,state):
    env,item,task=advance(cancel_env,'done' if state=='done' else 'proposed');c,users,*_=env
    if state=='cancelled':task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancelled'})
    saved=snapshot(c)
    with pytest.raises(ValueError):prepare((env,item,task))
    assert snapshot(c)==saved


@pytest.mark.parametrize('kind',['inactive','no_access'])
def test_native_cancellation_can_close_task_with_ineligible_owner_without_granting_access(cancel_env,kind):
    env,item,task=cancel_env;c,users,*_=env
    doc=link_source(cancel_env)
    env,item,task=advance(cancel_env)
    if kind=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    else:c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    access=list(c.execute('SELECT * FROM document_access'))
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert list(c.execute('SELECT * FROM document_access'))==access


@pytest.mark.parametrize('bad',[{'reason':''},{'reason':'x'*501},{'reason':'unsafe\x00reason'},{'owner_id':1},
                               {'due_date':'2026-10-29'},{'submission':'replace'},{'task_id':999999}])
def test_unsupported_fields_cannot_cancel_or_modify_source(cancel_env,bad):
    saved=snapshot(cancel_env[0][0])
    with pytest.raises(ValueError):prepare(cancel_env,**bad)
    assert saved==snapshot(cancel_env[0][0])


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_cancellation_rolls_back_with_source_receipt_and_handoff(cancel_env,monkeypatch,failure):
    env,item,task=cancel_env;c,*_=env
    _,result=prepare(cancel_env);exact=confirmation(env,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[cancellation.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_cancel_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_cancellation_records_one_revision(cancel_env):
    env,item,task=cancel_env;c,users,path,*_=env
    ctx,result=prepare(cancel_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert work_reads.task(c,users[0],item['id'],task['id'])['revision']==task['revision']+1


@pytest.mark.parametrize('when',['pending','committed'])
def test_deleted_target_cannot_expose_or_cancel_reused_id(cancel_env,when):
    env,item,task=cancel_env;c,users,*_=env
    _,result=prepare(cancel_env);exact=confirmation(env,result)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    if when=='committed':
        text=command(env,'/taskcancel_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22)['text']
    assert work_reads.task(c,users[0],item['id'],replacement['id'])==replacement


@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_formal_review_blocks_cancellation_without_resetting_approvals(cancel_env,when):
    env,item,task=cancel_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Cancel target','expected_output':'Evidence','unit_id':reviewed['unit_id']})
    if when=='before_preview':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,target))
    else:
        _,result=prepare((env,reviewed,target));exact=confirmation(env,result)
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert snapshot(c)==saved


def test_group_direct_mode_and_other_task_protocols_cannot_cancel(cancel_env,monkeypatch):
    env,item,task=cancel_env;c,*_=env
    for scope in ('tasks.accept','tasks.return','tasks.reopen'):grant(env,scope,monkeypatch)
    _,result=prepare(cancel_env);exact=confirmation(env,result);saved=snapshot(c)
    for number,text in enumerate(('/task_confirm '+result['token'],'/taskreopen_confirm '+result['token'],
                                  '/taskreturn_confirm '+result['token'],'/taskassign_preview '+result['operation_id']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    packet=update(26,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,27)
    assert saved==snapshot(c)


def test_cancellation_requires_its_own_scope_and_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_CANCEL_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[cancellation.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',cancellation.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_CANCEL_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_other_task_consent_cannot_cancel_or_keep_menu_hint(cancel_env):
    env,item,task=cancel_env;c,*_=env
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),cancellation.ACTION));c.commit()
    text=command(env,'/menu',10)['text']
    assert '/task_cancel' not in text and '/task_assign' in text
    assert cancellation.PATH not in command(env,'/task_cancel',11)['text']


def test_cancelled_prerequisite_does_not_satisfy_dependent_acceptance(cancel_env):
    env,item,task=advance(cancel_env,'in_progress');c,users,*_=env
    dependent=work_tasks.create(c,users[0],item['id'],{'title':'Dependent contribution','expected_output':'Combined evidence','unit_id':item['unit_id']})
    dependent=work_tasks.mutate(c,users[0],item['id'],dependent['id'],dependent['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Dependent assignment'})
    dependent=work_tasks.mutate(c,users[3],item['id'],dependent['id'],dependent['revision'],'acknowledge',{'reason':'Start dependent'})
    dependent=blockers.mutate(c,users[0],item['id'],dependent['id'],dependent['revision'],'dependency_add',{'reason':'Requires source acceptance','prerequisite_id':task['id']})
    edges=list(c.execute('SELECT * FROM work_dependency'))
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert list(c.execute('SELECT * FROM work_dependency'))==edges and blockers.waiting(c,dependent)
    with pytest.raises(ValueError,match='Resolve'):work_tasks.mutate(c,users[3],item['id'],dependent['id'],dependent['revision'],'submit',{'reason':'Dependency unresolved','submission':'Cannot submit'})
    assert any(gap['id']==dependent['id'] for gap in completion.contribution_gaps(c,item['id']))


@pytest.mark.parametrize('kind',['blocker','decision'])
def test_cancellation_preserves_blocker_and_direction_history(cancel_env,kind):
    env,item,task=advance(cancel_env,'in_progress');c,users,*_=env
    if kind=='blocker':blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'No longer needed input','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
    else:
        import work_discussion as discussion
        import work_decisions as decisions
        message=discussion.post(c,users[0],item['id'],'Changed source direction',task_id=task['id'])
        decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'Review changed direction',
                         'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    task=work_reads.task(c,users[0],item['id'],task['id'])
    tables=('work_decision','work_decision_task','work_decision_resolution')
    direction={table:list(c.execute('SELECT * FROM '+table)) for table in tables}
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    for field in ('blocker_reason','blocker_owner_id','blocker_due_date'):assert changed[field]==task[field]
    assert {table:list(c.execute('SELECT * FROM '+table)) for table in tables}==direction


def test_optional_contribution_is_identified_before_cancellation(cancel_env):
    env,item,task=cancel_env;c,*_=env
    c.execute('UPDATE work_task SET mandatory=0 WHERE id=?',(task['id'],));c.commit()
    _,result=prepare(cancel_env)
    text=command(env,'/taskcancel_preview '+result['operation_id'],20)['text']
    assert 'Contribution: optional' in text and 'New status: cancelled' in text
    exact=re.search(r'/taskcancel_confirm [A-Za-z0-9_-]{43}',text)[0]
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert work_reads.task(c,env[1][0],item['id'],task['id'])['mandatory']==0


def test_changed_submission_blocks_prepared_cancellation(cancel_env):
    env,item,task=advance(cancel_env,'for_review');c,users,*_=env
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'return',{'reason':'Source revision'})
    work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'submit',{'reason':'Revised source','submission':'Different evidence'})
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and snapshot(c)==saved
