"""Dependency direction, current coordinator authority, cycle and atomic private confirmations."""
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
import telegram_dependency_manage as manage
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
def dependency_env(deadline_env,monkeypatch):
    for scope in manage.MODES.values():grant(deadline_env[0],scope,monkeypatch)
    env,item,task=deadline_env;c,users,*_=env
    prerequisite=work_tasks.create(c,users[0],item['id'],{'title':'Synthetic prerequisite','expected_output':'PrivatePrerequisiteOutput','unit_id':item['unit_id']})
    return env,item,task,prerequisite


@pytest.fixture(params=['add','remove'])
def action_env(dependency_env,request):
    env,item,task,prerequisite=dependency_env;c,users,*_=env
    if request.param=='remove':
        task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'prerequisite_id':prerequisite['id'],'reason':'Source dependency'})
    return env,item,task,prerequisite,request.param


def prepare(action_env,number=10,key='dependency-operation-key',**changes):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    guide=command(env,'/task_dependency_'+mode,number)['text']
    assert manage.PATH+mode+'?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,manage.MODES[mode])
    fields={'case_id':item['id'],'task_id':task['id'],'prerequisite_id':prerequisite['id'],'reason':'Actor-entered '+mode+' reason'}
    return ctx,actions.issue(c,ctx,manage.MODES[mode],key,{**fields,**changes},NOW)


def confirmation(env,result,mode,number=20):
    text=command(env,'/taskdep'+mode+'_preview '+result['operation_id'],number)['text']
    assert 'Task dependency preview: '+mode in text and 'Actor-entered '+mode+' reason' in text
    assert 'PrivatePrerequisiteOutput' not in text and manage.common.units(text)<=4096
    return re.search('/taskdep'+mode+r'_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_exact_confirmation_changes_one_edge_and_native_history(action_env):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    linked_document(env,item,'2026-10-30')
    before=source_snapshot(c);_,result=prepare(action_env);exact=confirmation(env,result,mode)
    text=command(env,'/taskdep'+mode+'_preview '+result['operation_id'],19)['text']
    assert f"task {task['id']} depends on task {prerequisite['id']}" in text
    assert before==source_snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=work_reads.task(c,users[0],item['id'],task['id'])
    assert changed['revision']==task['revision']+1
    for field in task:
        if field not in ('revision','updated_at'):assert changed[field]==task[field]
    assert rows(c,'SELECT * FROM work_task WHERE id=?',(prerequisite['id'],))[0]==prerequisite
    exists=c.execute('SELECT 1 FROM work_dependency WHERE task_id=? AND prerequisite_id=?',(task['id'],prerequisite['id'])).fetchone()
    assert bool(exists)==(mode=='add')
    event=rows(c,'SELECT * FROM work_event ORDER BY id DESC LIMIT 1')[0]
    assert event['action']=='task_dependency_'+mode
    for table in ('work_case','document','document_access','document_review','work_decision','work_decision_resolution'):
        assert source_snapshot(c)[table]==before[table]
    saved=source_snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Current link: '+('present' if mode=='add' else 'absent') in command(env,'/taskdep'+mode+'_receipt '+result['operation_id'],23)['text']
    assert saved==source_snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('role',['reader','owner','followup'])
def test_visibility_task_owner_or_followup_alone_is_insufficient(action_env,role):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Other lead')
    if role=='owner':task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Task ownership only'})
    if role=='followup':task=blockers.mutate(c,users[1],item['id'],task['id'],task['revision'],'block',{'reason':'Private blocker','followup_owner_id':users[0]['id'],'followup_date':'2026-10-30'})
    before=source_snapshot(c)
    with pytest.raises(ValueError,match='authority'):prepare(action_env)
    assert source_snapshot(c)==before


def test_concerned_officer_can_change_without_being_lead(action_env):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Other lead')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    _,result=prepare(action_env)
    assert 'Recorded outcome:' in command(env,confirmation(env,result,mode),21)['text']


@pytest.mark.parametrize('bad',[{'reason':''},{'reason':'x'*501},{'reason':'unsafe\x00reason'},{'due_date':'2026-11-01'},{'submission':'replace'},{'task_id':999999},{'prerequisite_id':999999},{'prerequisite_id':True}])
def test_strict_fields_do_not_change_source(action_env,bad):
    before=source_snapshot(action_env[0][0])
    with pytest.raises(ValueError):prepare(action_env,**bad)
    assert source_snapshot(action_env[0][0])==before


@pytest.mark.parametrize('kind',['self','other_work','duplicate','cancelled','cycle','long_cycle'])
def test_add_refuses_invalid_graph(dependency_env,kind):
    env,item,task,prerequisite=dependency_env;c,users,*_=env
    chosen=prerequisite['id']
    if kind=='self':chosen=task['id']
    elif kind=='other_work':
        other=case(c,users[0],item['unit_id'])
        chosen=work_tasks.create(c,users[0],other['id'],{'title':'Other work task','expected_output':'Other work output','unit_id':item['unit_id']})['id']
    elif kind=='duplicate':blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'prerequisite_id':chosen,'reason':'Existing source link'})
    elif kind=='cancelled':c.execute("UPDATE work_task SET status='cancelled' WHERE id=?",(chosen,));c.commit()
    elif kind=='cycle':blockers.mutate(c,users[0],item['id'],chosen,prerequisite['revision'],'dependency_add',{'prerequisite_id':task['id'],'reason':'Opposite source link'})
    else:
        middle=work_tasks.create(c,users[0],item['id'],{'title':'Middle task','expected_output':'Middle output','unit_id':item['unit_id']})
        blockers.mutate(c,users[0],item['id'],chosen,prerequisite['revision'],'dependency_add',{'prerequisite_id':middle['id'],'reason':'First link'})
        blockers.mutate(c,users[0],item['id'],middle['id'],middle['revision'],'dependency_add',{'prerequisite_id':task['id'],'reason':'Second link'})
    before=source_snapshot(c)
    with pytest.raises(ValueError):prepare((*dependency_env,'add'),prerequisite_id=chosen)
    assert source_snapshot(c)==before


def test_remove_requires_existing_link(dependency_env):
    with pytest.raises(ValueError,match='no longer present'):prepare((*dependency_env,'remove'))


@pytest.mark.parametrize('state',['done','cancelled'])
def test_terminal_dependent_task_is_refused(action_env,state):
    env,item,task,prerequisite,mode=action_env;c,*_=env
    c.execute('UPDATE work_task SET status=? WHERE id=?',(state,task['id']));c.commit()
    before=source_snapshot(c)
    with pytest.raises(ValueError):prepare(action_env)
    assert source_snapshot(c)==before


@pytest.mark.parametrize('state',['done','cancelled'])
def test_prerequisite_done_can_be_added_and_cancelled_can_be_removed(dependency_env,state):
    env,item,task,prerequisite=dependency_env;c,users,*_=env
    mode='add' if state=='done' else 'remove'
    if mode=='remove':task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'prerequisite_id':prerequisite['id'],'reason':'Original link'})
    c.execute('UPDATE work_task SET status=? WHERE id=?',(state,prerequisite['id']));c.commit()
    _,result=prepare((env,item,task,prerequisite,mode));exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']


@pytest.mark.parametrize('change',['task','work','prerequisite','graph','cycle','authority','grant','read_grant','flag','module','documents_module','expiry','disconnect','restore','cancelled','completed','document_access'])
def test_changed_source_or_context_refuses_stale_confirmation(action_env,monkeypatch,change):
    env,item,task,prerequisite,mode=action_env;c,users,path,_,payload=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    if change=='task':c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',('Changed task',task['id']));c.commit()
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Changed work',item['id']));c.commit()
    elif change=='prerequisite':c.execute('UPDATE work_task SET title=?,revision=revision+1 WHERE id=?',('Changed prerequisite',prerequisite['id']));c.commit()
    elif change in ('graph','cycle'):
        if mode=='remove' or change=='graph':c.execute('DELETE FROM work_dependency WHERE task_id=?',(task['id'],))
        else:c.execute('INSERT INTO work_dependency VALUES (?,?,?,?)',(prerequisite['id'],task['id'],users[0]['id'],links.stamp(NOW)))
        c.commit()
        if mode=='add' and change=='graph':
            # A graph change without source revision/event changes must also fence the preview.
            c.execute('INSERT INTO work_dependency VALUES (?,?,?,?)',(task['id'],prerequisite['id'],users[0]['id'],links.stamp(NOW)));c.commit()
    elif change=='authority':work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Lost authority')
    elif change in ('grant','read_grant'):
        scope=manage.MODES[mode] if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_DEPENDENCY_'+mode.upper()+'_ENABLED','0')
    elif change in ('module','documents_module'):st.set_setting(c,('work' if change=='module' else 'documents')+'.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='cancelled':work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancellation'})
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE user_id=? AND document_id=?',(users[0]['id'],doc['id']));c.commit()
    else:c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    before=source_snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and before==source_snapshot(c)


@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_atomic_source_receipt_preview_handoff_rollback(action_env,monkeypatch,failure):
    env,item,task,prerequisite,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode);before=source_snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[manage.MODES[mode]],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_dependency_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert source_snapshot(c)==before
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmations_change_once(action_env):
    env,item,task,prerequisite,mode=action_env;c,users,path,*_=env
    ctx,result=prepare(action_env)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert work_reads.task(c,users[0],item['id'],task['id'])['revision']==task['revision']+1


@pytest.mark.parametrize('which',['target','prerequisite'])
@pytest.mark.parametrize('when',['pending','committed'])
def test_deletion_fences_both_task_numbers_from_reuse(action_env,which,when):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    if when=='committed':assert 'Recorded outcome:' in command(env,exact,21)['text']
    deleted=task if which=='target' else prerequisite
    c.execute('DELETE FROM work_dependency WHERE task_id=? OR prerequisite_id=?',(deleted['id'],deleted['id']))
    c.execute('DELETE FROM work_task WHERE id=?',(deleted['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Replacement output','unit_id':item['unit_id']})
    c.execute('UPDATE work_task SET id=? WHERE id=?',(deleted['id'],replacement['id']));c.commit()
    before=source_snapshot(c)
    if when=='committed':
        text=command(env,'/taskdep'+mode+'_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22).get('text','')
    assert source_snapshot(c)==before


@pytest.mark.parametrize('when',['before','after'])
def test_active_formal_review_amendments_stay_in_source(action_env,when):
    env,item,task,prerequisite,mode=action_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Dependency target','expected_output':'Evidence','unit_id':reviewed['unit_id']})
    upstream=work_tasks.create(c,users[0],reviewed['id'],{'title':'Dependency upstream','expected_output':'Evidence','unit_id':reviewed['unit_id']})
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],reviewed['unit_id'],links.stamp(NOW)));c.commit()
    if mode=='remove':target=blockers.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'dependency_add',{'prerequisite_id':upstream['id'],'reason':'Existing source link'})
    state=(env,reviewed,target,upstream,mode)
    if when=='before':
        formal_review(c,users,request_consolidation(c,users,output,reviewed));before=source_snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare(state)
    else:
        _,result=prepare(state);exact=confirmation(env,result,mode)
        formal_review(c,users,request_consolidation(c,users,output,reviewed));before=source_snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert source_snapshot(c)==before


def test_groups_direct_and_other_protocols_cannot_amend(action_env,monkeypatch):
    env,item,task,prerequisite,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode);before=source_snapshot(c)
    other='remove' if mode=='add' else 'add'
    for number,text in enumerate(('/taskdep'+other+'_confirm '+result['token'],'/taskblock_confirm '+result['token'],'/deadline_confirm '+result['token']),21):
        assert 'Recorded outcome:' not in command(env,text,number).get('text','')
    packet=update(25,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,26)
    assert source_snapshot(c)==before


@pytest.mark.parametrize('mode',['add','remove'])
def test_link_requires_independent_scope_work_read_and_pilot(linking,monkeypatch,mode):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_DEPENDENCY_'+mode.upper()+'_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[manage.MODES[mode]],NOW)
    links.claim(c,payload,raw,['work.read',manage.MODES[mode]],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_DEPENDENCY_'+mode.upper()+'_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_later_receipt_reports_current_edge_without_replay(action_env):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=work_reads.task(c,users[0],item['id'],task['id'])
    opposite='remove' if mode=='add' else 'add'
    blockers.mutate(c,users[0],item['id'],task['id'],current['revision'],'dependency_'+opposite,{'prerequisite_id':prerequisite['id'],'reason':'Later source change'})
    before=source_snapshot(c)
    text=command(env,'/taskdep'+mode+'_receipt '+result['operation_id'],22)['text']
    assert 'Current link: '+('absent' if mode=='add' else 'present') in text
    assert 'Recorded outcome: dependency '+('added' if mode=='add' else 'removed') in text
    assert before==source_snapshot(c)


@pytest.mark.parametrize('extra_blocker',[False,True])
def test_dependency_removal_preserves_other_submission_gates(action_env,extra_blocker):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start source task'})
    if extra_blocker:
        task=blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'StoredPrivateBlocker','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
        import work_discussion as discussion
        import work_decisions as decisions
        message=discussion.post(c,users[0],item['id'],'StoredPrivateDiscussion',task_id=task['id'])
        decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'StoredPrivateDecision',
                         'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    before=source_snapshot(c)
    _,result=prepare((env,item,task,prerequisite,mode));exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=work_reads.task(c,users[0],item['id'],task['id'])
    for field in ('blocker_reason','blocker_owner_id','blocker_due_date','status','submission','owner_id','due_date'):assert current[field]==task[field]
    for table in ('work_decision','work_decision_task','work_decision_resolution'):assert source_snapshot(c)[table]==before[table]
    if mode=='add' or extra_blocker:
        with pytest.raises(ValueError,match='Resolve'):work_tasks.mutate(c,users[3],item['id'],task['id'],current['revision'],'submit',{'reason':'Still waiting','submission':'Cannot bypass'})
    else:
        changed=work_tasks.mutate(c,users[3],item['id'],task['id'],current['revision'],'submit',{'reason':'Explicit source submission','submission':'Independent source output'})
        assert changed['status']=='for_review'


def test_unrelated_graph_change_without_task_revision_or_event_refuses_confirmation(action_env):
    env,item,task,prerequisite,mode=action_env;c,users,*_=env
    others=[work_tasks.create(c,users[0],item['id'],{'title':'Other graph task '+str(i),'expected_output':'Other graph output','unit_id':item['unit_id']}) for i in range(2)]
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    c.execute('INSERT INTO work_dependency VALUES (?,?,?,?)',(others[0]['id'],others[1]['id'],users[0]['id'],links.stamp(NOW)));c.commit()
    before=source_snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and before==source_snapshot(c)


def test_retention_clears_both_dependency_identifiers(action_env):
    env,item,task,prerequisite,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    with transaction(c):actions.cleanup_in_transaction(c,NOW+timedelta(days=181))
    operation=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]
    assert operation['result_code']=='retained_key' and operation['target_id'] is None and operation['dependency_task_id'] is None


def test_expanded_menu_and_missing_permissions_fit_maximum_supported_origin(menu_env,monkeypatch):
    from tests.test_telegram_menu import test_all_consented_menu_has_groups_examples_and_fits_budget
    origin='https://'+'a'*60+'.'+'b'*60+'.'+'c'*60+'.example12'
    assert len(origin)==200
    monkeypatch.setenv('CSS_BASE_URL',origin)
    test_all_consented_menu_has_groups_examples_and_fits_budget(menu_env,monkeypatch)
