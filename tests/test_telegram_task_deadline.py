"""Internal deadline edits preserve coordinator rights and native source state."""
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
import telegram_task_deadline as deadlines
import work
import work_tasks
from tests.test_work import workspace, document, consolidation_fixture, request_consolidation, formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_work import seed
from tests.test_telegram_brief import grant


@pytest.fixture
def deadline_env(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'work.read',monkeypatch);grant(env,deadlines.ACTION,monkeypatch)
    item,task=seed(env,owner=3)
    item=work.confirm_lead(c,users[1],item['id'],item['revision'],users[0]['id'],'Synthetic lead confirmation')
    task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'milestone',
                           {'due_date':'2026-10-28','reason':'Synthetic initial target'})
    return env,item,task


def fields(item,task,**changes):
    return {'case_id':item['id'],'task_id':task['id'],'deadline_mode':'set',
            'due_date':'2026-10-29','reason':'Synthetic revised internal target',**changes}


def prepare(deadline_env,number=10,key='deadline-operation-key',**changes):
    env,item,task=deadline_env;c,users,*_=env
    guide=command(env,'/task_deadline',number)['text']
    assert deadlines.PATH+'change?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,deadlines.ACTION)
    return ctx,actions.issue(c,ctx,deadlines.ACTION,key,fields(item,task,**changes),NOW)


def confirmation(env,result,number=20):
    text=command(env,'/deadline_preview '+result['operation_id'],number)['text']
    assert 'Task deadline preview' in text and '2026-10-28' in text and 'Reason:' in text
    assert deadlines.common.units(text)<=4096
    return re.search(r'/deadline_confirm [A-Za-z0-9_-]{43}',text)[0]


def snapshot(c):
    return {table:list(c.execute('SELECT * FROM '+table)) for table in
            ('work_case','work_task','work_event','audit_log','document','document_notice',
             'document_review','work_review_packet','work_review_invalidation')}


def linked_document(env,item,due):
    c,users,*_=env
    doc=document(c,users[0],item['unit_id'])
    doc=docs.mutate(c,users[1],doc['id'],doc['revision'],'access',
                    {'visibility':'restricted','viewers':[users[0]['id'],users[3]['id']],'reason':'Authorize both contributors'})
    c.execute('UPDATE document SET due_date=? WHERE id=?',(due,doc['id']));c.commit()
    work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
    return doc


@pytest.mark.parametrize('mode',['set','clear'])
def test_exact_confirmation_changes_only_due_revision_and_native_history(deadline_env,mode):
    env,item,task=deadline_env;c,*_=env
    _,result=prepare(deadline_env,deadline_mode=mode,due_date='2026-10-29' if mode=='set' else '')
    exact=confirmation(env,result)
    assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
    text=command(env,exact,21)['text']
    changed=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
    assert changed['due_date']==('2026-10-29' if mode=='set' else None)
    assert changed['revision']==task['revision']+1
    for key in ('title','expected_output','owner_id','proposed_owner_id','status','submission','mandatory'):
        assert changed[key]==task[key]
    assert 'Recorded outcome: internal task deadline' in text and '/work_status '+str(item['id']) in text
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/deadline_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_task_owner_without_coordinator_rights_cannot_change_deadline(deadline_env):
    env,item,task=deadline_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different accountable lead')
    task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',
                          {'owner_id':users[0]['id'],'reason':'Owner is not coordinator'})
    saved=snapshot(c)
    with pytest.raises(ValueError,match='officer or confirmed work lead'):prepare((env,item,task))
    assert saved==snapshot(c)


def test_concerned_officer_can_change_deadline_without_being_owner_or_lead(deadline_env):
    env,item,task=deadline_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    _,result=prepare(deadline_env);exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert rows(c,'SELECT due_date FROM work_task WHERE id=?',(task['id'],))[0]['due_date']=='2026-10-29'


def test_officer_grant_revoked_after_preview_removes_deadline_authority(deadline_env):
    env,item,task=deadline_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    _,result=prepare(deadline_env);exact=confirmation(env,result)
    c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and saved==snapshot(c)


@pytest.mark.parametrize('state',['proposed','todo','in_progress','for_review'])
def test_native_nonterminal_states_and_outputs_are_preserved(deadline_env,state):
    env,item,task=deadline_env;c,users,*_=env
    if state=='proposed':
        task=work_tasks.create(c,users[0],item['id'],{'title':'Proposed deadline target','expected_output':'Pending output',
                                                   'unit_id':item['unit_id'],'due_date':'2026-10-28'})
    elif state in ('in_progress','for_review'):
        task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start source task'})
        if state=='for_review':
            task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'submit',
                                  {'reason':'Submit native output','submission':'DoNotExposeSubmission '+'📌'*7900})
    _,result=prepare((env,item,task));exact=confirmation(env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    updated=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
    assert updated['status']==state and updated['owner_id']==task['owner_id'] and updated['submission']==task['submission']


@pytest.mark.parametrize('change',['task','revert','work','owner','completed','done','cancelled','deadline',
                                   'hidden_document','authority','grant','read_grant','flag','module','expiry','disconnect','restore'])
def test_changed_source_or_current_authority_blocks_old_preview(deadline_env,monkeypatch,change):
    env,item,task=deadline_env;c,users,path,_,payload=env
    if change in ('deadline','hidden_document'):
        doc=linked_document(env,item,'2026-10-30')
    _,result=prepare(deadline_env);exact=confirmation(env,result)
    if change in ('task','revert'):
        work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'milestone',
                          {'due_date':'2026-10-27','reason':'Changed source'})
        if change=='revert':
            current=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
            work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'milestone',
                              {'due_date':task['due_date'],'reason':'Restored date'})
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Changed work',item['id']));c.commit()
    elif change=='owner':c.execute('UPDATE work_task SET owner_id=?,revision=revision+1 WHERE id=?',(users[2]['id'],task['id']));c.commit()
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change in ('done','cancelled'):c.execute('UPDATE work_task SET status=?,revision=revision+1 WHERE id=?',(change,task['id']));c.commit()
    elif change=='deadline':c.execute("UPDATE document SET due_date='2026-10-28',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='hidden_document':
        c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
        c.execute('DELETE FROM document_access WHERE document_id=?',(doc['id'],));c.commit()
    elif change=='authority':work.confirm_lead(c,users[1],item['id'],work.raw(c,item['id'])['revision'],users[2]['id'],'Coordinator changed')
    elif change in ('grant','read_grant'):
        scope=deadlines.ACTION if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_DEADLINE_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','')
    assert saved==snapshot(c)


@pytest.mark.parametrize('bad',[{'deadline_mode':'other'},{'due_date':''},{'due_date':'2026-02-30'},
                               {'deadline_mode':'clear'},{'reason':''},{'due_date':'2026-10-28'},
                               {'owner_id':1},{'reason':'x'*501}])
def test_invalid_noop_and_ambiguous_clearing_are_refused(deadline_env,bad):
    env,item,task=deadline_env;c,*_=env
    saved=snapshot(c)
    with pytest.raises(ValueError):prepare(deadline_env,**bad)
    assert saved==snapshot(c)


def test_official_deadline_is_never_extended_or_cleared_with_internal_target(deadline_env):
    env,item,task=deadline_env;c,users,*_=env
    doc=linked_document(env,item,'2026-10-28')
    with pytest.raises(ValueError):prepare(deadline_env)
    before=rows(c,'SELECT * FROM document WHERE id=?',(doc['id'],))[0]
    _,result=prepare(deadline_env,11,'clear-internal-deadline',deadline_mode='clear',due_date='')
    exact=confirmation(env,result)
    command(env,exact,21)
    assert rows(c,'SELECT * FROM document WHERE id=?',(doc['id'],))[0]==before
    assert rows(c,'SELECT due_date FROM work_task WHERE id=?',(task['id'],))[0]['due_date'] is None


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_failed_audit_late_receipt_and_handoff_roll_back_every_source_effect(deadline_env,monkeypatch,failure):
    env,item,task=deadline_env;c,*_=env
    _,result=prepare(deadline_env);exact=confirmation(env,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[deadlines.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_deadline_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmations_record_one_milestone(deadline_env):
    env,item,task=deadline_env;c,users,path,*_=env
    ctx,result=prepare(deadline_env)
    before=c.execute("SELECT count(*) FROM work_event WHERE action='task_milestone'").fetchone()[0]
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert c.execute("SELECT count(*) FROM work_event WHERE action='task_milestone'").fetchone()[0]==before+1


@pytest.mark.parametrize('when',['pending','committed'])
def test_task_deletion_fences_old_operation_against_id_reuse(deadline_env,when):
    env,item,task=deadline_env;c,users,*_=env
    _,result=prepare(deadline_env);exact=confirmation(env,result)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    if when=='committed':
        text=command(env,'/deadline_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22)['text']
    assert rows(c,'SELECT due_date FROM work_task WHERE id=?',(replacement['id'],))[0]['due_date'] is None


@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_active_formal_review_prevents_approval_invalidation(deadline_env,when):
    env,item,task=deadline_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Task deadline target','expected_output':'Pending evidence',
                                                    'unit_id':reviewed['unit_id'],'due_date':'2026-10-28'})
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],reviewed['unit_id'],links.stamp(NOW)));c.commit()
    if when=='before_preview':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,target))
    else:
        _,result=prepare((env,reviewed,target));exact=confirmation(env,result)
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)


def test_groups_direct_mode_and_old_task_protocol_cannot_apply_deadline_tokens(deadline_env,monkeypatch):
    env,item,task=deadline_env;c,*_=env
    _,result=prepare(deadline_env);exact=confirmation(env,result);saved=snapshot(c)
    for number,text in enumerate(('/task_preview '+result['operation_id'],'/task_confirm '+result['token'],'/newtask_preview '+result['operation_id']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    packet=update(24,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,25)
    assert saved==snapshot(c)


def test_deadline_scope_requires_read_consent_and_current_pilot(linking,monkeypatch):
    c,users,_,_,payload=linking
    ch,raw,confirmation=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_DEADLINE_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[deadlines.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',deadlines.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_DEADLINE_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')
