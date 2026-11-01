"""Reopen accepted tasks without reopening a case or bypassing source review rules."""
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
import telegram_task_reopen as reopening
import work
import work_reads
import work_tasks
import work_blockers as blockers
from tests.test_work import workspace,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_task_review import review_env
from tests.test_telegram_task_assign import snapshot


@pytest.fixture
def reopen_env(review_env,monkeypatch):
    env,item,task=review_env;c,users,*_=env
    grant(env,reopening.ACTION,monkeypatch)
    task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'accept',{'reason':'Synthetic acceptance'})
    return env,item,task


def prepare(reopen_env,number=10,key='task-reopening-operation-key',**changes):
    env,item,task=reopen_env;c,users,*_=env
    guide=command(env,'/task_reopen',number)['text']
    assert reopening.PATH+'reopen?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,reopening.ACTION)
    fields={'case_id':item['id'],'task_id':task['id'],'reason':'Synthetic reopening reason',**changes}
    return ctx,actions.issue(c,ctx,reopening.ACTION,key,fields,NOW)


def confirmation(env,result,number=20):
    text=command(env,'/taskreopen_preview '+result['operation_id'],number)['text']
    assert 'Task reopening preview' in text and 'Current status: done' in text and 'New status: in progress' in text
    assert 'DoNotExposeSubmission' not in text and '📌' not in text and reopening.review.common.units(text)<=4096
    return re.search(r'/taskreopen_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_reopen_preserves_owner_long_submission_deadline_and_official_records(reopen_env):
    env,item,task=reopen_env;c,users,*_=env
    linked_document(env,item,'2026-10-30')
    before=snapshot(c)
    _,result=prepare(reopen_env,reason='Reopen task\r\nPreserve accepted evidence')
    exact=confirmation(env,result)
    assert snapshot(c)==before
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    assert changed['status']=='in_progress' and changed['revision']==task['revision']+1
    for field in ('owner_id','due_date','submission','expected_output','title','mandatory','unit_id','proposed_owner_id'):
        assert changed[field]==task[field]
    for table in ('work_case','document','document_access','document_review','document_role_grant'):
        assert snapshot(c)[table]==before[table]
    assert rows(c,"SELECT * FROM work_event WHERE action='task_reopen'")[-1]['actor_id']==users[0]['id']
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/taskreopen_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_task_owner_without_case_coordinator_authority_cannot_reopen(reopen_env):
    env,item,task=reopen_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different case lead')
    c.execute('UPDATE work_task SET owner_id=? WHERE id=?',(users[0]['id'],task['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError,match='case officer or confirmed work lead'):prepare(reopen_env)
    assert saved==snapshot(c)


@pytest.mark.parametrize('revoke',[False,True])
def test_current_case_officer_can_reopen_without_lead_status(reopen_env,revoke):
    env,item,task=reopen_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    _,result=prepare(reopen_env);exact=confirmation(env,result)
    if revoke:c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    saved=snapshot(c);text=command(env,exact,21)['text']
    if revoke:assert 'Recorded outcome:' not in text and saved==snapshot(c)
    else:assert 'Recorded outcome:' in text


@pytest.mark.parametrize('change',['task','work','owner','owner_inactive','owner_access','document','hidden_document','authority',
                                   'completed','source_reopen','revert','grant','read_grant','flag','module','expiry','disconnect','restore'])
def test_source_permissions_and_state_fence_old_reopening(reopen_env,monkeypatch,change):
    env,item,task=reopen_env;c,users,path,_,payload=env
    if change in ('owner_access','document','hidden_document'):doc=linked_document(env,item,'2026-10-30')
    _,result=prepare(reopen_env);exact=confirmation(env,result)
    if change=='task':c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',('Source changed',task['id']));c.commit()
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Different work',item['id']));c.commit()
    elif change=='owner':c.execute('UPDATE work_task SET owner_id=?,revision=revision+1 WHERE id=?',(users[2]['id'],task['id']));c.commit()
    elif change=='owner_inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif change=='owner_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    elif change=='document':c.execute("UPDATE document SET due_date='2026-10-27',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='hidden_document':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change=='authority':work.confirm_lead(c,users[1],item['id'],work.raw(c,item['id'])['revision'],users[2]['id'],'Changed lead')
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change in ('source_reopen','revert'):
        current=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'reopen',{'reason':'Other source reopening'})
        if change=='revert':
            current=work_tasks.mutate(c,users[3],item['id'],task['id'],current['revision'],'submit',{'reason':'Resubmit same','submission':task['submission']})
            work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'accept',{'reason':'Accepted again'})
    elif change in ('grant','read_grant'):
        scope=reopening.ACTION if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_REOPEN_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and saved==snapshot(c)


@pytest.mark.parametrize('state',['proposed','todo','in_progress','for_review','cancelled'])
def test_only_done_task_in_open_work_can_reopen(reopen_env,state):
    env,item,task=reopen_env;c,*_=env
    c.execute('UPDATE work_task SET status=? WHERE id=?',(state,task['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError):prepare(reopen_env)
    assert saved==snapshot(c)


@pytest.mark.parametrize('bad',[{'reason':''},{'reason':'x'*501},{'reason':'unsafe\x00reason'},{'owner_id':1},
                               {'due_date':'2026-10-29'},{'submission':'replace'},{'task_id':999999}])
def test_unsupported_fields_cannot_reopen_or_alter_source(reopen_env,bad):
    saved=snapshot(reopen_env[0][0])
    with pytest.raises(ValueError):prepare(reopen_env,**bad)
    assert saved==snapshot(reopen_env[0][0])


@pytest.mark.parametrize('kind',['missing','inactive','no_access'])
def test_existing_owner_must_still_be_eligible_before_preview(reopen_env,kind):
    env,item,task=reopen_env;c,users,*_=env
    if kind=='missing':c.execute('UPDATE work_task SET owner_id=NULL WHERE id=?',(task['id'],));c.commit()
    elif kind=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    else:
        doc=linked_document(env,item,'2026-10-30')
        c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError):prepare(reopen_env)
    assert snapshot(c)==saved


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_reopening_rolls_back_with_every_native_effect(reopen_env,monkeypatch,failure):
    env,item,task=reopen_env;c,*_=env
    _,result=prepare(reopen_env);exact=confirmation(env,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[reopening.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_reopen_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_reopening_creates_one_native_revision(reopen_env):
    env,item,task=reopen_env;c,users,path,*_=env
    ctx,result=prepare(reopen_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert work_reads.task(c,users[0],item['id'],task['id'])['revision']==task['revision']+1


@pytest.mark.parametrize('when',['pending','committed'])
def test_deleted_target_cannot_expose_or_reopen_reused_id(reopen_env,when):
    env,item,task=reopen_env;c,users,*_=env
    _,result=prepare(reopen_env);exact=confirmation(env,result)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    if when=='committed':
        text=command(env,'/taskreopen_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22)['text']
    assert work_reads.task(c,users[0],item['id'],replacement['id'])==replacement


@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_active_formal_review_blocks_reopening_without_resetting_approvals(reopen_env,when):
    env,item,task=reopen_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],reviewed['unit_id'],links.stamp(NOW)));c.commit()
    if when=='before_preview':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,accepted))
    else:
        _,result=prepare((env,reviewed,accepted));exact=confirmation(env,result)
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)


def test_group_direct_mode_and_review_protocols_cannot_reopen(reopen_env,monkeypatch):
    env,item,task=reopen_env;c,*_=env
    _,result=prepare(reopen_env);exact=confirmation(env,result);saved=snapshot(c)
    for number,text in enumerate(('/task_confirm '+result['token'],'/taskaccept_confirm '+result['token'],
                                  '/taskreturn_confirm '+result['token'],'/deadline_preview '+result['operation_id']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    packet=update(26,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,27)
    assert saved==snapshot(c)


def test_reopening_requires_its_own_scope_and_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_REOPEN_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[reopening.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',reopening.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_REOPEN_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_review_consent_cannot_reopen_or_keep_menu_hint(reopen_env):
    env,item,task=reopen_env;c,*_=env
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),reopening.ACTION));c.commit()
    text=command(env,'/menu',10)['text']
    assert '/task_reopen' not in text and '/task_accept' in text
    assert reopening.PATH not in command(env,'/task_reopen',11)['text']


def test_receipt_tracks_later_resubmission_without_replaying_reopening(reopen_env):
    env,item,task=reopen_env;c,users,*_=env
    _,result=prepare(reopen_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=work_reads.task(c,users[0],item['id'],task['id'])
    work_tasks.mutate(c,users[3],item['id'],task['id'],current['revision'],'submit',{'reason':'Later source revision','submission':'New source evidence'})
    saved=snapshot(c)
    text=command(env,'/taskreopen_receipt '+result['operation_id'],22)['text']
    assert 'task reopened' in text and 'Current status: for review' in text
    assert snapshot(c)==saved


@pytest.mark.parametrize('kind',['decision','prerequisite'])
def test_reopening_preserves_pending_direction_or_unfinished_dependency(reopen_env,kind):
    env,item,task=reopen_env;c,users,*_=env
    if kind=='decision':
        import work_discussion as discussion
        import work_decisions as decisions
        message=discussion.post(c,users[0],item['id'],'Rework the accepted source evidence',task_id=task['id'])
        decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'Changed direction requires follow-up',
                         'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    else:
        upstream=work_tasks.create(c,users[0],item['id'],{'title':'Upstream input','expected_output':'Source evidence','unit_id':item['unit_id']})
        upstream=work_tasks.mutate(c,users[1],item['id'],upstream['id'],upstream['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Source assignment'})
        upstream=work_tasks.mutate(c,users[3],item['id'],upstream['id'],upstream['revision'],'acknowledge',{'reason':'Start upstream'})
        upstream=work_tasks.mutate(c,users[3],item['id'],upstream['id'],upstream['revision'],'submit',{'reason':'Submit upstream','submission':'Upstream evidence'})
        upstream=work_tasks.mutate(c,users[0],item['id'],upstream['id'],upstream['revision'],'accept',{'reason':'Accept upstream'})
        task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'reopen',{'reason':'Record dependency'})
        task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'reason':'Source prerequisite','prerequisite_id':upstream['id']})
        task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'submit',{'reason':'Same accepted evidence','submission':task['submission']})
        task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'accept',{'reason':'Accept dependent evidence'})
        work_tasks.mutate(c,users[0],item['id'],upstream['id'],upstream['revision'],'reopen',{'reason':'Upstream rework'})
    task=work_reads.task(c,users[0],item['id'],task['id'])
    assert task['status']=='done' and blockers.waiting(c,task)
    tables=('work_dependency','work_decision','work_decision_task','work_decision_resolution')
    pending={table:list(c.execute('SELECT * FROM '+table)) for table in tables}
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    assert changed['status']=='in_progress' and blockers.waiting(c,changed)
    assert {table:list(c.execute('SELECT * FROM '+table)) for table in tables}==pending
    with pytest.raises(ValueError,match='Resolve'):work_tasks.mutate(c,users[3],item['id'],task['id'],changed['revision'],'submit',{'reason':'Blocked resubmission','submission':'Unresolved source'})
