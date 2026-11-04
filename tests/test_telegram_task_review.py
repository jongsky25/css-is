"""Private task reviews retain native authority, blockers and atomic history."""
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
import telegram_task_review as review
import work
import work_tasks
import work_blockers as blockers
from tests.test_work import workspace, consolidation_fixture, request_consolidation, formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env, linked_document, snapshot


@pytest.fixture
def review_env(deadline_env,monkeypatch):
    env,item,task=deadline_env;c,users,*_=env
    for action in review.MODES.values():grant(env,action,monkeypatch)
    task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start synthetic work'})
    task=work_tasks.mutate(c,users[3],item['id'],task['id'],task['revision'],'submit',
                           {'reason':'Submit synthetic work','submission':'DoNotExposeSubmission '+'📌'*7900})
    return env,item,task


def prepare(review_env,mode='accept',number=10,key='task-review-operation-key',**changes):
    env,item,task=review_env;c,users,*_=env
    guide=command(env,'/task_'+mode,number)['text']
    assert review.PATH+mode+'?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,review.MODES[mode])
    fields={'case_id':item['id'],'task_id':task['id'],'reason':'Synthetic review reason',**changes}
    return ctx,actions.issue(c,ctx,review.MODES[mode],key,fields,NOW)


def confirmation(env,result,mode='accept',number=20):
    text=command(env,'/task'+mode+'_preview '+result['operation_id'],number)['text']
    assert 'Task review preview' in text and 'for review' in text and 'Reason:' in text
    assert 'DoNotExposeSubmission' not in text and '📌' not in text
    assert review.common.units(text)<=4096
    return re.search('/task'+mode+r'_confirm [A-Za-z0-9_-]{43}',text)[0]


@pytest.mark.parametrize('mode',review.MODES)
def test_native_review_preserves_contents_owner_dates_and_does_not_complete_work(review_env,mode):
    env,item,task=review_env;c,users,*_=env
    _,result=prepare(review_env,mode,reason='Synthetic review reason\r\nSecond line')
    exact=confirmation(env,result,mode)
    assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    changed=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
    assert changed['status']==('done' if mode=='accept' else 'in_progress')
    assert changed['revision']==task['revision']+1
    for key in ('title','expected_output','owner_id','proposed_owner_id','due_date','submission','mandatory'):
        assert changed[key]==task[key]
    assert work.raw(c,item['id'])==item
    assert rows(c,"SELECT * FROM work_event WHERE action=?",('task_'+mode,))[-1]['actor_id']==users[0]['id']
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/task'+mode+'_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('mode',review.MODES)
def test_owner_without_coordinator_cannot_review_own_submission(review_env,mode):
    env,item,task=review_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    c.execute('UPDATE work_task SET owner_id=? WHERE id=?',(users[0]['id'],task['id']));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError,match='authority'):prepare(review_env,mode)
    assert saved==snapshot(c)


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('revoke',[False,True])
def test_source_officer_authority_is_current_not_a_telegram_grant(review_env,mode,revoke):
    env,item,task=review_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    if revoke:
        c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    saved=snapshot(c);text=command(env,exact,21)['text']
    if revoke:assert 'Recorded outcome:' not in text and saved==snapshot(c)
    else:assert 'Recorded outcome:' in text


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('change',['task','revert','submission','work','owner','completed','done','cancelled','document',
                                   'hidden_document','authority','grant','read_grant','flag','module','expiry','disconnect','restore'])
def test_current_source_and_authority_fences_old_review(review_env,monkeypatch,mode,change):
    env,item,task=review_env;c,users,path,_,payload=env
    if change in ('document','hidden_document'):doc=linked_document(env,item,'2026-10-30')
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    if change in ('task','revert'):
        current=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'milestone',{'due_date':'2026-10-27','reason':'Source changed'})
        if change=='revert':work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'milestone',{'due_date':task['due_date'],'reason':'Source reverted'})
    elif change=='submission':
        current=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'return',{'reason':'Revise output'})
        work_tasks.mutate(c,users[3],item['id'],task['id'],current['revision'],'submit',{'reason':'Revised','submission':'Different evidence'})
    elif change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Different work',item['id']));c.commit()
    elif change=='owner':c.execute('UPDATE work_task SET owner_id=?,revision=revision+1 WHERE id=?',(users[2]['id'],task['id']));c.commit()
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change in ('done','cancelled'):c.execute('UPDATE work_task SET status=?,revision=revision+1 WHERE id=?',(change,task['id']));c.commit()
    elif change=='document':c.execute("UPDATE document SET due_date='2026-10-28',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='hidden_document':
        c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
        c.execute('DELETE FROM document_access WHERE document_id=?',(doc['id'],));c.commit()
    elif change=='authority':work.confirm_lead(c,users[1],item['id'],work.raw(c,item['id'])['revision'],users[2]['id'],'Lead changed')
    elif change in ('grant','read_grant'):
        scope=review.MODES[mode] if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and saved==snapshot(c)


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('when',['before','after'])
@pytest.mark.parametrize('kind',['blocker','prerequisite','decision'])
def test_acceptance_checks_all_native_blockers_but_return_is_permitted(review_env,mode,when,kind):
    env,item,task=review_env;c,users,*_=env
    if when=='after':_,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    if kind=='blocker':
        blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',
                        {'reason':'Waiting for evidence','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
    elif kind=='prerequisite':
        upstream=work_tasks.create(c,users[0],item['id'],{'title':'Pending prerequisite','expected_output':'Upstream evidence','unit_id':item['unit_id']})
        blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'dependency_add',{'reason':'Upstream needed','prerequisite_id':upstream['id']})
    else:
        import work_discussion as discussion
        import work_decisions as decisions
        message=discussion.post(c,users[0],item['id'],'Changed source decision',task_id=task['id'])
        decisions.record(c,users[0],item['id'],message,1,
                         {'kind':'change','body':'Review changed evidence','affected_tasks':[task['id']],
                          'task_revisions':{str(task['id']):task['revision']}})
    saved=snapshot(c)
    if when=='before':
        if mode=='accept':
            with pytest.raises(ValueError):prepare(review_env,mode)
            assert saved==snapshot(c);return
        _,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    response=command(env,exact,21)['text']
    # A blocker added after preview also changes task/work revision; both actions require a fresh preview.
    if mode=='accept' or when=='after':assert 'Recorded outcome:' not in response and saved==snapshot(c)
    else:assert 'Recorded outcome:' in response


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('bad',[{'reason':''},{'reason':'x'*501},{'reason':'unsafe\x00reason'},{'owner_id':1},{'submission':'replace'},{'task_id':999999}])
def test_invalid_fields_never_review_a_task(review_env,mode,bad):
    saved=snapshot(review_env[0][0])
    with pytest.raises(ValueError):prepare(review_env,mode,**bad)
    assert saved==snapshot(review_env[0][0])


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('failure',['audit','receipt','handoff'])
def test_review_and_native_effects_roll_back_together(review_env,monkeypatch,mode,failure):
    env,item,task=review_env;c,*_=env
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[review.MODES[mode]],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_review_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


@pytest.mark.parametrize('mode',review.MODES)
def test_concurrent_reviews_record_one_transition(review_env,mode):
    env,item,task=review_env;c,users,path,*_=env
    ctx,result=prepare(review_env,mode)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]['revision']==task['revision']+1


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('when',['pending','committed'])
def test_deleted_review_target_cannot_touch_or_show_reused_id(review_env,mode,when):
    env,item,task=review_env;c,users,*_=env
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    if when=='committed':command(env,exact,21)
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    other=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different evidence','unit_id':item['unit_id']})
    assert other['id']==task['id']
    if when=='committed':
        text=command(env,'/task'+mode+'_receipt '+result['operation_id'],22)['text']
        assert 'was deleted' in text and 'Replacement task' not in text
    else:
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
        assert 'Recorded outcome:' not in command(env,exact,22)['text']
    assert rows(c,'SELECT * FROM work_task WHERE id=?',(other['id'],))[0]==other


@pytest.mark.parametrize('mode',review.MODES)
def test_review_scopes_are_independent_and_require_read_and_current_pilot(linking,monkeypatch,mode):
    c,users,path,client,payload=linking
    ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[review.MODES[mode]],NOW)
    links.claim(c,payload,raw,['work.read',review.MODES[mode]],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


@pytest.mark.parametrize('mode',review.MODES)
@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_formal_review_amendments_stay_in_office_connect(review_env,mode,when):
    env,item,task=review_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",
              (users[0]['id'],reviewed['unit_id'],links.stamp(NOW)));c.commit()
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'Review target','expected_output':'Evidence',
                                                    'unit_id':reviewed['unit_id'],'proposed_owner_id':users[0]['id']})
    target=work_tasks.mutate(c,users[1],reviewed['id'],target['id'],target['revision'],'confirm',{'owner_id':users[0]['id'],'reason':'Source assignment'})
    target=work_tasks.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'acknowledge',{'reason':'Start source work'})
    target=work_tasks.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'submit',{'reason':'Source submission','submission':'Review input'})
    if when=='before_preview':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):prepare((env,reviewed,target),mode)
    else:
        _,result=prepare((env,reviewed,target),mode);exact=confirmation(env,result,mode)
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)


@pytest.mark.parametrize('mode',review.MODES)
def test_groups_direct_mode_and_other_action_commands_cannot_consume_review(review_env,monkeypatch,mode):
    env,item,task=review_env;c,*_=env
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode);saved=snapshot(c)
    other='return' if mode=='accept' else 'accept'
    for number,text in enumerate(('/task_confirm '+result['token'],'/deadline_confirm '+result['token'],
                                  '/task'+other+'_confirm '+result['token'],'/task'+other+'_preview '+result['operation_id']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    packet=update(26,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,27)
    assert saved==snapshot(c)


@pytest.mark.parametrize('mode',review.MODES)
def test_review_never_changes_linked_official_document_and_recovery_is_current(review_env,mode):
    env,item,task=review_env;c,users,*_=env
    doc=linked_document(env,item,'2026-10-30')
    doc_before=rows(c,'SELECT * FROM document WHERE id=?',(doc['id'],))[0]
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    current=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
    if mode=='accept':work_tasks.mutate(c,users[0],item['id'],task['id'],current['revision'],'reopen',{'reason':'Source rework'})
    else:work_tasks.mutate(c,users[3],item['id'],task['id'],current['revision'],'submit',{'reason':'Revised source','submission':'New evidence'})
    saved=snapshot(c)
    text=command(env,'/task'+mode+'_receipt '+result['operation_id'],22)['text']
    assert 'Recorded outcome:' in text and ('in progress' if mode=='accept' else 'for review') in text
    assert snapshot(c)==saved and rows(c,'SELECT * FROM document WHERE id=?',(doc['id'],))[0]==doc_before


@pytest.mark.parametrize('mode',review.MODES)
def test_other_review_scope_grants_neither_action_nor_menu_hint(review_env,monkeypatch,mode):
    env,item,task=review_env;c,*_=env
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),review.MODES[mode]));c.commit()
    text=command(env,'/menu',10)['text']
    other='return' if mode=='accept' else 'accept'
    assert '/task_'+mode not in text and '/task_'+other in text
    assert review.PATH+mode not in command(env,'/task_'+mode,11)['text']
    _,result=prepare(review_env,other,12)
    assert 'Recorded outcome:' in command(env,confirmation(env,result,other),21)['text']


@pytest.mark.parametrize('first',review.MODES)
def test_opposite_pending_review_cannot_reverse_confirmed_outcome(review_env,first):
    env,item,task=review_env;c,*_=env
    other='return' if first=='accept' else 'accept'
    _,chosen=prepare(review_env,first)
    _,stale=prepare(review_env,other,11,'opposite-review-operation-key')
    exact=confirmation(env,chosen,first)
    obsolete=confirmation(env,stale,other,19)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,obsolete,22)['text'] and snapshot(c)==saved


@pytest.mark.parametrize('mode',review.MODES)
def test_native_owner_account_rules_are_rechecked_inside_write(review_env,mode):
    env,item,task=review_env;c,users,*_=env
    _,result=prepare(review_env,mode);exact=confirmation(env,result,mode)
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text'] and snapshot(c)==saved
