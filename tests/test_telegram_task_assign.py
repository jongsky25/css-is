"""Initial assignment retains officer scope, source access and atomic receipt semantics."""
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
import telegram_task_assign as assignment
import work
import work_reads
import work_tasks
from tests.test_work import workspace,case,document,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant


@pytest.fixture
def assign_env(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'work.read',monkeypatch);grant(env,assignment.ACTION,monkeypatch)
    unit=c.execute("SELECT id FROM org_unit WHERE path='WORK/D1'").fetchone()[0]
    item=case(c,users[0],unit)
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],unit,links.stamp(NOW)));c.commit()
    task=work_tasks.create(c,users[0],item['id'],{'title':'Synthetic proposed task','expected_output':'DoNotExposeCriteria',
                                               'unit_id':unit,'proposed_owner_id':users[2]['id'],'due_date':'2026-10-28'})
    return env,item,task


def prepare(assign_env,number=10,key='task-assignment-operation-key',**changes):
    env,item,task=assign_env;c,users,*_=env
    guide=command(env,'/task_assign',number)['text']
    assert assignment.PATH+'assign?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,assignment.ACTION)
    fields={'case_id':item['id'],'task_id':task['id'],'owner_id':users[3]['id'],'reason':'Synthetic officer assignment',**changes}
    return ctx,actions.issue(c,ctx,assignment.ACTION,key,fields,NOW)


def confirmation(env,result,number=20):
    text=command(env,'/taskassign_preview '+result['operation_id'],number)['text']
    assert 'Task assignment preview' in text and 'proposed' in text and 'to do' in text and '2026-10-28' in text
    assert 'DoNotExposeCriteria' not in text and assignment.common.units(text)<=4096
    return re.search(r'/taskassign_confirm [A-Za-z0-9_-]{43}',text)[0]


def snapshot(c):
    return {table:list(c.execute('SELECT * FROM '+table)) for table in
            ('work_case','work_task','work_event','audit_log','document','document_access','document_notice',
             'document_review','work_review_packet','work_review_invalidation','document_role_grant')}


def link_source(assign_env, *, owner_access=True):
    env,item,task=assign_env;c,users,*_=env
    doc=document(c,users[0],item['unit_id'])
    doc=docs.mutate(c,users[1],doc['id'],doc['revision'],'access',
                    {'visibility':'restricted','viewers':[users[0]['id']]+([users[3]['id']] if owner_access else []),
                     'reason':'Synthetic contributor access'})
    c.execute("UPDATE document SET due_date='2026-10-30' WHERE id=?",(doc['id'],));c.commit()
    work.link_document(c,users[0],item['id'],work.raw(c,item['id'])['revision'],doc['id'])
    return doc


def test_exact_initial_assignment_preserves_dates_outputs_proposal_and_document_access(assign_env):
    env,item,task=assign_env;c,users,*_=env
    doc=link_source(assign_env)
    before=snapshot(c)
    _,result=prepare(assign_env,reason='Officer confirms\r\nSelected contributor')
    exact=confirmation(env,result)
    assert snapshot(c)==before
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    assert changed['owner_id']==users[3]['id'] and changed['status']=='todo'
    assert changed['revision']==task['revision']+1
    for key in ('title','expected_output','proposed_owner_id','due_date','submission','mandatory','unit_id'):
        assert changed[key]==task[key]
    for table in ('document','document_access','document_review','document_role_grant','work_case'):
        assert snapshot(c)[table]==before[table]
    assert work.get(c,users[3],item['id'])['id']==item['id']  # Normal confirmed ownership establishes work membership.
    assert rows(c,"SELECT * FROM work_event WHERE action='task_confirm'")[-1]['actor_id']==users[0]['id']
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/taskassign_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('actor_kind',['proposer','lead','suggested_owner','admin_role','case_unit_officer'])
def test_assignment_requires_contributing_unit_officer_scope(assign_env,actor_kind):
    env,item,task=assign_env;c,users,*_=env
    c.execute('DELETE FROM document_role_grant WHERE user_id=?',(users[0]['id'],));c.commit()
    if actor_kind=='lead':item=work.confirm_lead(c,users[1],item['id'],item['revision'],users[0]['id'],'Confirmed lead alone')
    elif actor_kind=='suggested_owner':c.execute('UPDATE work_task SET proposed_owner_id=? WHERE id=?',(users[0]['id'],task['id']));c.commit()
    elif actor_kind=='admin_role':c.execute("UPDATE admin_user SET role='admin' WHERE id=?",(users[0]['id'],));c.commit()
    elif actor_kind=='case_unit_officer':
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
                  (users[0]['id'],item['unit_id'],links.stamp(NOW)))
        other=st.add_org_unit(c,'Other contributing unit','division','OTHER/CONTRIBUTOR')
        c.execute('UPDATE work_task SET unit_id=? WHERE id=?',(other,task['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError):
        if actor_kind=='admin_role':
            # Changing the account role also revokes Telegram context; test source authority directly.
            assignment.Adapter().prepare(c,st.get_admin_user_by_id(c,users[0]['id']),
                                         {'case_id':item['id'],'task_id':task['id'],'owner_id':users[3]['id'],'reason':'Source role test'})
        else:prepare((env,item,task))
    assert saved==snapshot(c)


def test_proposed_owner_without_document_access_is_refused_before_preview(assign_env):
    env,item,task=assign_env;c,users,*_=env
    doc=link_source(assign_env,owner_access=False)
    saved=snapshot(c)
    with pytest.raises(ValueError,match='access to every linked document'):prepare(assign_env)
    assert saved==snapshot(c)
    with pytest.raises(ValueError):work.get(c,users[3],item['id'])


@pytest.mark.parametrize('change',['task','revert','work','owner_name','owner_role','owner_inactive','owner_access','document',
                                   'hidden_document','authority','completed','already_assigned','cancelled','grant','read_grant',
                                   'flag','module','expiry','disconnect','restore'])
def test_stale_source_or_current_permissions_block_assignment(assign_env,monkeypatch,change):
    env,item,task=assign_env;c,users,path,_,payload=env
    if change in ('owner_access','document','hidden_document'):doc=link_source(assign_env)
    _,result=prepare(assign_env);exact=confirmation(env,result)
    if change in ('task','revert'):
        c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',('Changed source',task['id']));c.commit()
        if change=='revert':c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',(task['title'],task['id']));c.commit()
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Different work',item['id']));c.commit()
    elif change=='owner_name':c.execute('UPDATE admin_user SET username=? WHERE id=?',('renamed@example.invalid',users[3]['id']));c.commit()
    elif change=='owner_role':c.execute("UPDATE admin_user SET role='encoder' WHERE id=?",(users[3]['id'],));c.commit()
    elif change=='owner_inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif change=='owner_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    elif change=='document':c.execute("UPDATE document SET due_date='2026-10-27',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='hidden_document':
        c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change=='authority':c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change=='already_assigned':work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'confirm',{'owner_id':users[2]['id'],'reason':'Another source assignment'})
    elif change=='cancelled':work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancelled'})
    elif change in ('grant','read_grant'):
        scope=assignment.ACTION if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_ASSIGN_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and saved==snapshot(c)


@pytest.mark.parametrize('bad',[{'owner_id':''},{'owner_id':999999},{'reason':''},{'reason':'x'*501},
                               {'reason':'unsafe\x00reason'},{'due_date':'2026-10-29'},{'status':'in_progress'},
                               {'submission':'replace'},{'task_id':999999}])
def test_invalid_fields_never_assign_a_task(assign_env,bad):
    saved=snapshot(assign_env[0][0])
    with pytest.raises(ValueError):prepare(assign_env,**bad)
    assert saved==snapshot(assign_env[0][0])


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_assignment_rolls_back_with_every_native_effect(assign_env,monkeypatch,failure):
    env,item,task=assign_env;c,*_=env
    _,result=prepare(assign_env);exact=confirmation(env,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[assignment.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_assignment_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_duplicate_concurrent_assignments_record_one_initial_owner(assign_env):
    env,item,task=assign_env;c,users,path,*_=env
    ctx,result=prepare(assign_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert work_reads.task(c,users[0],item['id'],task['id'])['revision']==task['revision']+1


def test_other_pending_owner_choice_cannot_reassign_confirmed_task(assign_env):
    env,item,task=assign_env;c,users,*_=env
    _,chosen=prepare(assign_env)
    _,other=prepare(assign_env,11,'other-initial-owner-key',owner_id=users[2]['id'])
    exact=confirmation(env,chosen);obsolete=confirmation(env,other,19)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,obsolete,22)['text'] and saved==snapshot(c)


@pytest.mark.parametrize('when',['pending','committed'])
def test_deleted_target_cannot_expose_or_assign_reused_id(assign_env,when):
    env,item,task=assign_env;c,users,*_=env
    _,result=prepare(assign_env);exact=confirmation(env,result)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    if when=='committed':
        text=command(env,'/taskassign_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22)['text']
    assert work_reads.task(c,users[0],item['id'],replacement['id'])==replacement


@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_formal_review_blocks_assignment_without_resetting_approvals(assign_env,when):
    env,item,task=assign_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Pending assignment','expected_output':'Evidence',
                                                    'unit_id':reviewed['unit_id'],'due_date':'2026-10-28'})
    # The source creator already has document access; no new access is granted by assignment.
    if when=='before_preview':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,target),owner_id=users[0]['id'])
    else:
        _,result=prepare((env,reviewed,target),owner_id=users[0]['id']);exact=confirmation(env,result)
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)


def test_group_direct_mode_and_other_action_protocols_cannot_assign(assign_env,monkeypatch):
    env,item,task=assign_env;c,*_=env
    for scope in ('tasks.accept','tasks.return','tasks.deadline','tasks.create'):grant(env,scope,monkeypatch)
    _,result=prepare(assign_env);exact=confirmation(env,result);saved=snapshot(c)
    for number,text in enumerate(('/task_confirm '+result['token'],'/taskaccept_confirm '+result['token'],
                                  '/deadline_confirm '+result['token'],'/newtask_preview '+result['operation_id']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    packet=update(26,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,27)
    assert saved==snapshot(c)


def test_assignment_consent_requires_read_and_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_ASSIGN_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[assignment.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',assignment.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_ASSIGN_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_assignment_scope_is_independent_of_other_task_grants(assign_env,monkeypatch):
    env,item,task=assign_env;c,*_=env
    for scope in ('tasks.create','tasks.deadline','tasks.accept','tasks.return','tasks.acknowledge','tasks.submit'):grant(env,scope,monkeypatch)
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),assignment.ACTION));c.commit()
    assert '/task_assign' not in command(env,'/menu',10)['text']
    assert assignment.PATH not in command(env,'/task_assign',11)['text']
    assert work_reads.task(c,env[1][0],item['id'],task['id'])==task


def test_receipt_reports_current_state_without_repeating_assignment(assign_env):
    env,item,task=assign_env;c,users,*_=env
    _,result=prepare(assign_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=work_reads.task(c,users[0],item['id'],task['id'])
    work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'reassign',
                      {'owner_id':users[2]['id'],'reason':'Later source reassignment'})
    saved=snapshot(c)
    text=command(env,'/taskassign_receipt '+result['operation_id'],22)['text']
    assert 'initial task assignment confirmed' in text and 'Current owner account: '+str(users[2]['id']) in text
    assert saved==snapshot(c)


@pytest.mark.parametrize('state',['todo','in_progress','for_review','done','cancelled'])
def test_initial_assignment_is_not_reassignment_or_reopening(assign_env,state):
    env,item,task=assign_env;c,users,*_=env
    c.execute('UPDATE work_task SET status=?,owner_id=? WHERE id=?',(state,users[2]['id'],task['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError,match='proposed task assignment'):prepare(assign_env)
    assert saved==snapshot(c)


def test_selected_owner_needs_access_to_every_linked_document(assign_env):
    env,item,task=assign_env;c,*_=env
    link_source(assign_env,owner_access=True)
    link_source(assign_env,owner_access=False)
    saved=snapshot(c)
    with pytest.raises(ValueError,match='access to every linked document'):prepare(assign_env)
    assert saved==snapshot(c)


def test_officer_for_contributing_unit_can_assign_without_case_officer_or_lead(assign_env):
    env,item,task=assign_env;c,users,*_=env
    other=st.add_org_unit(c,'Contributing unit','division','OTHER/ASSIGNMENT')
    c.execute('DELETE FROM document_role_grant WHERE user_id=?',(users[0]['id'],))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],other,links.stamp(NOW)))
    c.execute('UPDATE work_task SET unit_id=? WHERE id=?',(other,task['id']));c.commit()
    assert not work.officer(c,users[0],item) and item['lead_id']!=users[0]['id']
    _,result=prepare(assign_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert work_reads.task(c,users[0],item['id'],task['id'])['owner_id']==users[3]['id']
