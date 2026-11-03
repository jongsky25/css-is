"""Private blocker metadata follows source visibility and never resolves workflow."""
import re

import pytest

import backups
import documents as docs
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_task_blockers as reads
import work
import work_reads
import work_tasks
import work_blockers as blockers
import work_decisions as decisions
import work_discussion as discussion
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_task_assign import snapshot


@pytest.fixture
def blocker_env(deadline_env,monkeypatch):
    grant(deadline_env[0],reads.ACTION,monkeypatch)
    return deadline_env


def lookup(blocker_env,number=10,before=None):
    env,item,task=blocker_env
    return command(env,'/task_blockers '+str(item['id'])+' '+str(task['id'])+(' '+str(before) if before else ''),number)


def source_snapshot(c):
    return {**snapshot(c),**{table:list(c.execute('SELECT * FROM '+table)) for table in
            ('work_dependency','work_decision','work_decision_task','work_decision_resolution','work_comment','work_comment_revision')}}


def block(blocker_env,owner=3):
    env,item,task=blocker_env;c,users,*_=env
    current=work_reads.task(c,users[0],item['id'],task['id'])
    return blockers.mutate(c,users[0],item['id'],task['id'],current['revision'],'block',
                           {'reason':'DoNotExposeBlockerReason','followup_owner_id':users[owner]['id'],'followup_date':'2026-10-30'})


def prerequisite(blocker_env,title='Upstream input'):
    env,item,task=blocker_env;c,users,*_=env
    upstream=work_tasks.create(c,users[0],item['id'],{'title':title,'expected_output':'DoNotExposeCriteria','unit_id':item['unit_id'],'due_date':'2026-10-27'})
    current=work_reads.task(c,users[0],item['id'],task['id'])
    blockers.mutate(c,users[0],item['id'],task['id'],current['revision'],'dependency_add',{'reason':'DoNotExposeDependencyNote','prerequisite_id':upstream['id']})
    return upstream


def test_flags_followup_and_prerequisites_are_read_only_and_bodies_stay_private(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    task=block(blocker_env);upstream=prerequisite(blocker_env)
    message=discussion.post(c,users[0],item['id'],'DoNotExposeDiscussion',task_id=task['id'])
    task=work_reads.task(c,users[0],item['id'],task['id'])
    decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'DoNotExposeDecisionBody',
                     'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    before=source_snapshot(c)
    text=lookup(blocker_env)['text']
    assert 'Native blocker check: waiting' in text and 'Recorded blocker: yes' in text and 'changed-decision review: yes' in text
    assert users[3]['username'] in text and '2026-10-30' in text and 'Upstream input' in text and '2026-10-27' in text
    assert '/work/'+str(item['id'])+'#task-'+str(upstream['id']) in text and '/work/'+str(item['id'])+'#task-'+str(task['id']) in text
    assert 'DoNotExpose' not in text and reads.common.units(text)<=4096
    assert before==source_snapshot(c)
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    for row in rows(c,'SELECT payload_json FROM telegram_update'):assert row['payload_json'] is None or 'blocker_query' not in row['payload_json']
    for row in rows(c,'SELECT projection_json FROM telegram_delivery'):assert 'DoNotExpose' not in row['projection_json'] and 'work3@' not in row['projection_json']


def test_unblock_and_prerequisite_acceptance_are_reflected_on_next_read(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    block(blocker_env);upstream=prerequisite(blocker_env)
    assert 'waiting' in lookup(blocker_env)['text']
    task=work_reads.task(c,users[0],item['id'],task['id'])
    blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'unblock',{'reason':'Source resolved'})
    upstream=work_tasks.mutate(c,users[1],item['id'],upstream['id'],upstream['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Upstream owner'})
    upstream=work_tasks.mutate(c,users[3],item['id'],upstream['id'],upstream['revision'],'acknowledge',{'reason':'Upstream work'})
    upstream=work_tasks.mutate(c,users[3],item['id'],upstream['id'],upstream['revision'],'submit',{'reason':'Upstream output','submission':'DoNotExposeSubmission'})
    work_tasks.mutate(c,users[0],item['id'],upstream['id'],upstream['revision'],'accept',{'reason':'Accepted source'})
    before=source_snapshot(c);text=lookup(blocker_env,11)['text']
    assert 'Native blocker check: clear' in text and 'Recorded blocker: no' in text and 'No unfinished prerequisites' in text
    assert 'Upstream input' not in text and 'Other task permissions/state/review rules still apply' in text
    assert source_snapshot(c)==before


def test_cancelled_prerequisite_remains_waiting_and_is_not_treated_as_done(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    upstream=prerequisite(blocker_env)
    work_tasks.mutate(c,users[1],item['id'],upstream['id'],upstream['revision'],'cancel',{'reason':'Cancelled source'})
    text=lookup(blocker_env)['text']
    assert 'Native blocker check: waiting' in text and 'State: cancelled' in text and 'Only Done satisfies a prerequisite' in text


@pytest.mark.parametrize('kind',['inactive','lost_access','lost_membership'])
def test_followup_owner_is_neutral_when_no_longer_permitted(blocker_env,kind):
    env,item,task=blocker_env;c,users,*_=env
    if kind=='lost_access':doc=linked_document(env,item,'2026-10-30')
    task=block(blocker_env)
    if kind=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif kind=='lost_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    else:work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Source transferred'})
    text=lookup(blocker_env)['text']
    assert 'Follow-up owner: unavailable account' in text and users[3]['username'] not in text
    assert '(account '+str(users[3]['id'])+')' not in text and '2026-10-30' in text


def test_ordinary_owner_without_review_or_officer_rights_can_read_permitted_blockers(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different source lead')
    task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Viewer owns task'})
    assert 'accept' not in work_tasks.actions(c,users[0],work.raw(c,item['id']),task)
    assert 'Task blockers' in lookup((env,item,task))['text']


@pytest.mark.parametrize('kind',['hidden_document','unknown','wrong_case','foreign_dependency'])
def test_inaccessible_or_inconsistent_sources_share_neutral_denial(blocker_env,kind):
    env,item,task=blocker_env;c,users,*_=env
    if kind=='hidden_document':
        doc=linked_document(env,item,'2026-10-30')
        c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif kind=='unknown':task={**task,'id':999999}
    else:
        other=case(c,users[2],item['unit_id'],title='DoNotExposeOtherWork')
        other_task=work_tasks.create(c,users[2],other['id'],{'title':'DoNotExposeForeignTask','expected_output':'DoNotExposeOutput','unit_id':item['unit_id']})
        if kind=='wrong_case':task={**task,'id':other_task['id']}
        else:c.execute("INSERT INTO work_dependency VALUES (?,?,?,'2026-10-26')",(task['id'],other_task['id'],users[0]['id']));c.commit()
    before=source_snapshot(c)
    assert lookup((env,item,task))['text']==reads.DENIED
    assert source_snapshot(c)==before


@pytest.mark.parametrize('kind',['read_grant','blocker_grant','pilot','work','documents','disconnect','restore','bot','direct'])
def test_current_grants_modules_context_and_transport_are_enforced(blocker_env,monkeypatch,kind):
    env,item,task=blocker_env;c,users,path,_,payload=env
    assert 'Task blockers' in lookup(blocker_env)['text']
    if kind in ('read_grant','blocker_grant'):
        scope='work.read' if kind=='read_grant' else reads.ACTION
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
    elif kind=='pilot':monkeypatch.setenv('CSS_TELEGRAM_TASKS_BLOCKERS_READ_ENABLED','0')
    elif kind in ('work','documents'):st.set_setting(c,kind+'.enabled','0')
    elif kind=='disconnect':links.disconnect(c,payload,NOW)
    elif kind=='restore':backups.clear_restored_sessions(path)
    elif kind=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    else:monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    before=source_snapshot(c)
    assert 'method' not in lookup(blocker_env,11)
    assert source_snapshot(c)==before


@pytest.mark.parametrize('text',['/task_blockers','/task_blockers 1','/task_blockers 1 0','/task_blockers -1 2',
                                 '/task_blockers 1 2 0','/task_blockers 9223372036854775808 2','/task_blockers true 2','/task_blockers 1 2 3 4'])
def test_input_validation_produces_only_usage_without_retained_query(blocker_env,text):
    env,*_=blocker_env
    assert command(env,text,10)['text']==reads.USAGE
    assert not rows(env[0],"SELECT * FROM telegram_update WHERE payload_json LIKE '%blocker_query%'")


def test_group_topic_and_duplicate_updates_cannot_create_pushes(blocker_env):
    env,item,task=blocker_env;c,*_=env
    text='/task_blockers '+str(item['id'])+' '+str(task['id'])
    packet=update(10,text=text);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    packet=update(11,text=text);packet['message']['message_thread_id']=4
    assert 'method' not in submit(env[3],packet).json()
    packet=update(12,text=text)
    assert 'Task blockers' in submit(env[3],packet).json()['text'] and 'method' not in submit(env[3],packet).json()
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_unicode_prerequisite_pages_have_no_skips_or_duplicates(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    block(blocker_env)
    expected={prerequisite(blocker_env,'📌'*100+' '+str(i))['id'] for i in range(9)}
    seen=[];before=None
    for number in range(10,20):
        text=lookup(blocker_env,number,before)['text'];assert reads.common.units(text)<=4096
        seen += [int(value) for value in re.findall(r'\nTask ([0-9]+) ·',text)]
        match=re.search(r'Next page: /task_blockers [0-9]+ [0-9]+ ([0-9]+)',text)
        if not match:break
        before=int(match[1])
    assert set(seen)==expected and len(seen)==len(expected)


def test_completed_and_cancelled_state_are_read_as_history_not_write_authority(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    task=block(blocker_env)
    work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'cancel',{'reason':'Source cancellation'})
    c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    before=source_snapshot(c);text=lookup(blocker_env)['text']
    assert 'Task state: cancelled' in text and 'Historical state:' in text and 'Recorded blocker: yes' in text
    assert source_snapshot(c)==before


def test_blocker_consent_requires_work_read_and_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking
    ch,raw,confirmation=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_BLOCKERS_READ_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[reads.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',reads.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_BLOCKERS_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_changed_decision_resolution_is_visible_without_projecting_notes(blocker_env):
    env,item,task=blocker_env;c,users,*_=env
    message=discussion.post(c,users[0],item['id'],'DoNotExposeMessage',task_id=task['id'])
    decision=decisions.record(c,users[0],item['id'],message,1,{'kind':'change','body':'DoNotExposeDecision',
                              'affected_tasks':[task['id']],'task_revisions':{str(task['id']):task['revision']}})
    assert 'changed-decision review: yes' in lookup(blocker_env)['text']
    task=work_reads.task(c,users[0],item['id'],task['id'])
    decisions.resolve(c,users[0],item['id'],decision,task['id'],task['revision'],'retain','DoNotExposeResolution')
    before=source_snapshot(c);text=lookup(blocker_env,11)['text']
    assert 'changed-decision review: no' in text and 'Native blocker check: clear' in text and 'DoNotExpose' not in text
    assert source_snapshot(c)==before


def test_own_task_and_review_queue_hints_require_blocker_read_grant(blocker_env,monkeypatch):
    env,item,task=blocker_env;c,users,*_=env
    task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Viewer owns source'})
    command_text='/task_status '+str(item['id'])+' '+str(task['id'])
    assert '/task_blockers' in command(env,command_text,10)['text']
    task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start source'})
    task=work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'submit',{'reason':'Submit source','submission':'DoNotExposeSubmission'})
    grant(env,'tasks.review.read',monkeypatch)
    detail='/review_task '+str(item['id'])+' '+str(task['id'])
    assert '/task_blockers' in command(env,detail,11)['text']
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),reads.ACTION));c.commit()
    assert '/task_blockers' not in command(env,command_text,12)['text']
    assert '/task_blockers' not in command(env,detail,13)['text']
