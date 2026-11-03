"""Officer transfer preserves submissions and blockers while returning to To do."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re

import pytest

import backups
import documents as docs
from documents_storage import rows,transaction
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_task_reassign as reassignment
import work
import work_reads
import work_tasks
import work_blockers as blockers
from tests.test_work import workspace,document,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_assign import assign_env,snapshot


@pytest.fixture
def reassign_env(assign_env,monkeypatch):
    env,item,task=assign_env;c,users,*_=env
    grant(env,reassignment.ACTION,monkeypatch)
    task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'confirm',
                           {'owner_id':users[2]['id'],'reason':'Synthetic initial owner'})
    return env,item,task


def prepare(reassign_env,number=10,key='task-reassignment-operation-key',**changes):
    env,item,task=reassign_env;c,users,*_=env
    guide=command(env,'/task_reassign',number)['text']
    assert reassignment.PATH+'reassign?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,reassignment.ACTION)
    fields={'case_id':item['id'],'task_id':task['id'],'owner_id':users[3]['id'],'reason':'Synthetic officer transfer',**changes}
    return ctx,actions.issue(c,ctx,reassignment.ACTION,key,fields,NOW)


def confirmation(env,result,number=20):
    text=command(env,'/taskreassign_preview '+result['operation_id'],number)['text']
    assert 'Task reassignment preview' in text and 'Current owner account:' in text and 'New status: to do' in text
    assert '2026-10-28' in text and 'returns the task to To do' in text
    assert 'DoNotExpose' not in text and '📌' not in text and reassignment.assignment.common.units(text)<=4096
    return re.search(r'/taskreassign_confirm [A-Za-z0-9_-]{43}',text)[0]


def link_source(reassign_env,owner_access=True):
    env,item,task=reassign_env;c,users,*_=env
    doc=document(c,users[0],item['unit_id'])
    doc=docs.mutate(c,users[1],doc['id'],doc['revision'],'access',
                    {'visibility':'restricted','viewers':[users[0]['id'],users[2]['id']]+([users[3]['id']] if owner_access else []),
                     'reason':'Synthetic existing contributor access'})
    c.execute("UPDATE document SET due_date='2026-10-30' WHERE id=?",(doc['id'],));c.commit()
    work.link_document(c,users[0],item['id'],work.raw(c,item['id'])['revision'],doc['id'])
    return doc


@pytest.mark.parametrize('state',['todo','in_progress','for_review'])
def test_transfer_shows_reset_and_preserves_source_submission_dates_and_document_permissions(reassign_env,state):
    env,item,task=reassign_env;c,users,*_=env
    doc=link_source(reassign_env)
    if state!='todo':task=work_tasks.mutate(c,users[2],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start work'})
    if state=='for_review':task=work_tasks.mutate(c,users[2],item['id'],task['id'],task['revision'],'submit',
                                                {'reason':'Submit evidence','submission':'DoNotExposeSubmission '+'📌'*7900})
    before=snapshot(c)
    _,result=prepare((env,item,task),reason='Officer transfer\r\nSecond line')
    exact=confirmation(env,result)
    assert snapshot(c)==before
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    assert changed['owner_id']==users[3]['id'] and changed['status']=='todo' and changed['revision']==task['revision']+1
    for key in ('title','expected_output','proposed_owner_id','due_date','submission','mandatory','unit_id'):
        assert changed[key]==task[key]
    for table in ('document','document_access','document_review','document_role_grant','work_case'):
        assert snapshot(c)[table]==before[table]
    assert work.get(c,users[3],item['id'])['id']==item['id']
    with pytest.raises(ValueError):work.get(c,users[2],item['id'])
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/taskreassign_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('kind',['blocker','prerequisite','decision'])
def test_transfer_does_not_resolve_existing_blockers_or_decision_reviews(reassign_env,kind):
    env,item,task=reassign_env;c,users,*_=env
    if kind=='blocker':
        blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',
                        {'reason':'Waiting on evidence','followup_owner_id':users[2]['id'],'followup_date':'2026-10-30'})
    elif kind=='prerequisite':
        upstream=work_tasks.create(c,users[0],item['id'],{'title':'Pending upstream','expected_output':'Evidence','unit_id':item['unit_id']})
        blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'reason':'Source prerequisite','prerequisite_id':upstream['id']})
    else:
        import work_discussion as discussion
        import work_decisions as decisions
        message=discussion.post(c,users[0],item['id'],'Source changed decision',task_id=task['id'])
        decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'Review source direction',
                         'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    task=work_reads.task(c,users[0],item['id'],task['id'])
    dependencies=list(c.execute('SELECT * FROM work_dependency'))
    decision_rows={table:list(c.execute('SELECT * FROM '+table)) for table in ('work_decision','work_decision_task','work_decision_resolution')}
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    for field in ('blocker_reason','blocker_owner_id','blocker_due_date'):assert changed[field]==task[field]
    assert blockers.waiting(c,changed) and list(c.execute('SELECT * FROM work_dependency'))==dependencies
    assert {table:list(c.execute('SELECT * FROM '+table)) for table in decision_rows}==decision_rows


@pytest.mark.parametrize('actor_kind',['owner','lead','wrong_unit'])
def test_owner_lead_or_wrong_unit_officer_cannot_transfer(reassign_env,actor_kind):
    env,item,task=reassign_env;c,users,*_=env
    c.execute('DELETE FROM document_role_grant WHERE user_id=?',(users[0]['id'],));c.commit()
    if actor_kind=='lead':work.confirm_lead(c,users[1],item['id'],item['revision'],users[0]['id'],'Confirmed lead alone')
    elif actor_kind=='owner':c.execute('UPDATE work_task SET owner_id=? WHERE id=?',(users[0]['id'],task['id']));c.commit()
    else:
        other=st.add_org_unit(c,'Unrelated unit','division','UNRELATED/TRANSFER')
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],other,links.stamp(NOW)));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError,match='contributing-unit officer'):prepare(reassign_env)
    assert saved==snapshot(c)


@pytest.mark.parametrize('change',['task','revert','work','owner_name','owner_role','owner_inactive','owner_access','document',
                                   'hidden_document','authority','completed','cancelled','accepted','source_transfer','grant',
                                   'read_grant','flag','module','expiry','disconnect','restore'])
def test_current_source_authority_and_contributor_access_fence_old_transfer(reassign_env,monkeypatch,change):
    env,item,task=reassign_env;c,users,path,_,payload=env
    if change in ('owner_access','document','hidden_document'):doc=link_source(reassign_env)
    _,result=prepare(reassign_env);exact=confirmation(env,result)
    if change in ('task','revert'):
        current=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'milestone',{'due_date':'2026-10-27','reason':'Source date'})
        if change=='revert':work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'milestone',{'due_date':task['due_date'],'reason':'Source reverted'})
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Different work',item['id']));c.commit()
    elif change=='owner_name':c.execute('UPDATE admin_user SET username=? WHERE id=?',('renamed@example.invalid',users[3]['id']));c.commit()
    elif change=='owner_role':c.execute("UPDATE admin_user SET role='encoder' WHERE id=?",(users[3]['id'],));c.commit()
    elif change=='owner_inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif change=='owner_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    elif change=='document':c.execute("UPDATE document SET due_date='2026-10-27',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='hidden_document':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change=='authority':c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change=='cancelled':work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancellation'})
    elif change=='accepted':c.execute("UPDATE work_task SET status='done',revision=revision+1 WHERE id=?",(task['id'],));c.commit()
    elif change=='source_transfer':work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Different source transfer'})
    elif change in ('grant','read_grant'):
        scope=reassignment.ACTION if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_REASSIGN_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and saved==snapshot(c)


@pytest.mark.parametrize('bad',[{'owner_id':''},{'owner_id':999999},{'reason':''},{'reason':'x'*501},
                               {'reason':'unsafe\x00reason'},{'due_date':'2026-10-29'},{'status':'in_progress'},
                               {'submission':'replace'},{'task_id':999999}])
def test_invalid_fields_cannot_transfer(reassign_env,bad):
    saved=snapshot(reassign_env[0][0])
    with pytest.raises(ValueError):prepare(reassign_env,**bad)
    assert saved==snapshot(reassign_env[0][0])


def test_same_owner_is_not_a_reassignment(reassign_env):
    env,item,task=reassign_env;c,*_=env
    saved=snapshot(c)
    with pytest.raises(ValueError,match='different owner'):prepare(reassign_env,owner_id=task['owner_id'])
    assert saved==snapshot(c)


@pytest.mark.parametrize('state',['proposed','done','cancelled'])
def test_nonactive_task_cannot_transfer(reassign_env,state):
    env,item,task=reassign_env;c,*_=env
    c.execute('UPDATE work_task SET status=? WHERE id=?',(state,task['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError):prepare(reassign_env)
    assert saved==snapshot(c)


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_transfer_rolls_back_with_source_receipt_and_handoff(reassign_env,monkeypatch,failure):
    env,item,task=reassign_env;c,*_=env
    _,result=prepare(reassign_env);exact=confirmation(env,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[reassignment.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_reassign_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_transfer_records_one_revision(reassign_env):
    env,item,task=reassign_env;c,users,path,*_=env
    ctx,result=prepare(reassign_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert work_reads.task(c,users[0],item['id'],task['id'])['revision']==task['revision']+1


def test_competing_owner_preview_cannot_transfer_again(reassign_env):
    env,item,task=reassign_env;c,users,*_=env
    _,chosen=prepare(reassign_env)
    _,other=prepare(reassign_env,11,'other-transfer-choice-key',owner_id=users[0]['id'])
    exact=confirmation(env,chosen);obsolete=confirmation(env,other,19)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,obsolete,22)['text'] and saved==snapshot(c)


@pytest.mark.parametrize('when',['pending','committed'])
def test_deleted_target_cannot_expose_or_transfer_reused_id(reassign_env,when):
    env,item,task=reassign_env;c,users,*_=env
    _,result=prepare(reassign_env);exact=confirmation(env,result)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    if when=='committed':
        text=command(env,'/taskreassign_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22)['text']
    assert work_reads.task(c,users[0],item['id'],replacement['id'])==replacement


@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_formal_review_blocks_transfer_without_changing_approvals(reassign_env,when):
    env,item,task=reassign_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Transfer target','expected_output':'Evidence','unit_id':reviewed['unit_id'],'due_date':'2026-10-28'})
    target=work_tasks.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'confirm',{'owner_id':users[0]['id'],'reason':'Initial source owner'})
    # Source officer 1 already has document access; transfer to them needs no access change.
    if when=='before_preview':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,target),owner_id=users[1]['id'])
    else:
        _,result=prepare((env,reviewed,target),owner_id=users[1]['id']);exact=confirmation(env,result)
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)


def test_group_direct_mode_and_assignment_protocols_cannot_transfer(reassign_env,monkeypatch):
    env,item,task=reassign_env;c,*_=env
    _,result=prepare(reassign_env);exact=confirmation(env,result);saved=snapshot(c)
    for number,text in enumerate(('/task_confirm '+result['token'],'/taskassign_confirm '+result['token'],
                                  '/taskassign_preview '+result['operation_id'],'/newtask_preview '+result['operation_id']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    packet=update(26,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,27)
    assert saved==snapshot(c)


def test_transfer_requires_its_own_scope_and_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_REASSIGN_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[reassignment.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',reassignment.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_REASSIGN_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_initial_assignment_scope_cannot_transfer_or_keep_menu_hint(reassign_env):
    env,item,task=reassign_env;c,*_=env
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),reassignment.ACTION));c.commit()
    text=command(env,'/menu',10)['text']
    assert '/task_reassign' not in text and '/task_assign' in text
    assert reassignment.PATH not in command(env,'/task_reassign',11)['text']


def test_recovery_reports_later_owner_and_state_without_replaying(reassign_env):
    env,item,task=reassign_env;c,users,*_=env
    _,result=prepare(reassign_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=work_reads.task(c,users[0],item['id'],task['id'])
    current=work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Later source owner'})
    work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'acknowledge',{'reason':'Later progress'})
    saved=snapshot(c)
    text=command(env,'/taskreassign_receipt '+result['operation_id'],22)['text']
    assert 'task reassigned' in text and 'Current owner account: '+str(users[0]['id']) in text and 'in progress' in text
    assert saved==snapshot(c)


def test_changed_submission_requires_fresh_transfer_preview(reassign_env):
    env,item,task=reassign_env;c,users,*_=env
    task=work_tasks.mutate(c,users[2],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start source'})
    task=work_tasks.mutate(c,users[2],item['id'],task['id'],task['revision'],'submit',{'reason':'Original evidence','submission':'DoNotExposeOriginal'})
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'return',{'reason':'Update source evidence'})
    work_tasks.mutate(c,users[2],item['id'],task['id'],task['revision'],'submit',{'reason':'Revised source','submission':'DoNotExposeNew'})
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and snapshot(c)==saved


def test_new_owner_access_is_required_before_transfer_preview(reassign_env):
    env,item,task=reassign_env;c,*_=env
    link_source(reassign_env,owner_access=False)
    saved=snapshot(c)
    with pytest.raises(ValueError,match='access to every linked document'):prepare(reassign_env)
    assert snapshot(c)==saved


def test_task_unit_officer_can_transfer_without_case_unit_or_lead_authority(reassign_env):
    env,item,task=reassign_env;c,users,*_=env
    other=st.add_org_unit(c,'Contributing unit','division','OTHER/TRANSFER')
    c.execute('DELETE FROM document_role_grant WHERE user_id=?',(users[0]['id'],))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],other,links.stamp(NOW)))
    c.execute('UPDATE work_task SET unit_id=? WHERE id=?',(other,task['id']));c.commit()
    assert not work.officer(c,users[0],item) and item['lead_id']!=users[0]['id']
    _,result=prepare(reassign_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
