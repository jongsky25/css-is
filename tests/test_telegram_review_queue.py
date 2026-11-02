"""Private review metadata, current native eligibility and independently gated guidance."""
import re

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_review_queue as queue
import work
import work_tasks
import work_blockers as blockers
from tests.test_work import workspace,case,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_task_review import review_env
from tests.test_telegram_task_assign import snapshot


@pytest.fixture
def queue_env(review_env,monkeypatch):
    grant(review_env[0],queue.ACTION,monkeypatch)
    return review_env


def seed(env,item,owner=3,title='Synthetic pending review'):
    c,users,*_=env
    task=work_tasks.create(c,users[0],item['id'],{'title':title,'expected_output':'DoNotExposeCriteria','unit_id':item['unit_id'],'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'confirm',{'owner_id':users[owner]['id'],'reason':'Synthetic owner'})
    task=work_tasks.mutate(c,users[owner],item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Synthetic start'})
    return work_tasks.mutate(c,users[owner],item['id'],task['id'],task['revision'],'submit',{'reason':'Synthetic output','submission':'DoNotExposeSubmission'})


def detail(env,item,task,number=11):return command(env,'/review_task '+str(item['id'])+' '+str(task['id']),number)


def ids(text):return [int(value) for value in re.findall(r'Task ([0-9]+) · Work',text)]


def test_queue_metadata_guidance_and_detail_make_no_prepared_or_source_writes(queue_env):
    env,item,task=queue_env;c,users,*_=env
    before=snapshot(c)
    text=command(env,'/review_queue',10)['text']
    assert ids(text)==[task['id']] and item['title'] in text and users[3]['username'] in text and '2026-10-28' in text
    assert '/review_task '+str(item['id'])+' '+str(task['id']) in text
    text=detail(env,item,task)['text']
    assert '/task_accept' in text and '/task_return' in text and '/work/'+str(item['id']) in text
    assert 'DoNotExpose' not in text and '📌' not in text and queue.common.units(text)<=4096
    assert snapshot(c)==before
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    for row in rows(c,'SELECT payload_json FROM telegram_update'):assert row['payload_json'] is None or 'review_query' not in row['payload_json']
    for row in rows(c,'SELECT projection_json FROM telegram_delivery'):assert 'work3@' not in row['projection_json'] and 'DoNotExpose' not in row['projection_json']


@pytest.mark.parametrize('mode',['accept','return'])
def test_review_actions_remain_separately_consented(queue_env,mode):
    env,item,task=queue_env;c,*_=env
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),'tasks.'+mode));c.commit()
    text=detail(env,item,task)['text']
    assert '/task_'+mode not in text
    assert ids(text)==[task['id']]
    assert not rows(c,'SELECT * FROM telegram_operation')


def test_blocked_acceptance_still_lists_permitted_return(queue_env):
    env,item,task=queue_env;c,users,*_=env
    blockers.mutate(c,users[0],item['id'],task['id'],task['revision'],'block',{'reason':'DoNotExposeBlockerReason','followup_owner_id':users[3]['id'],'followup_date':'2026-10-30'})
    text=detail(env,item,task)['text']
    assert '/task_accept' not in text and '/task_return' in text and 'Acceptance is blocked' in text
    assert 'DoNotExposeBlockerReason' not in text
    assert ids(command(env,'/review_queue',12)['text'])==[task['id']]


@pytest.mark.parametrize('kind',['owner','task_unit_officer','lead_revoked'])
def test_visible_ownership_or_task_unit_officer_is_not_case_review_authority(queue_env,kind):
    env,item,task=queue_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    if kind=='owner':c.execute('UPDATE work_task SET owner_id=? WHERE id=?',(users[0]['id'],task['id']));c.commit()
    if kind=='task_unit_officer':
        unit=st.add_org_unit(c,'Contributing unit','division','OTHER/REVIEW')
        c.execute('UPDATE work_task SET unit_id=? WHERE id=?',(unit,task['id']))
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],unit,links.stamp(NOW)));c.commit()
    assert not ids(command(env,'/review_queue',10)['text'])
    assert detail(env,item,task)['text']==queue.DENIED


def test_case_officer_without_lead_status_has_current_queue_access(queue_env):
    env,item,task=queue_env;c,users,*_=env
    work.confirm_lead(c,users[1],item['id'],item['revision'],users[2]['id'],'Different lead')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    assert ids(command(env,'/review_queue',10)['text'])==[task['id']]
    c.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',(links.stamp(NOW),users[0]['id']));c.commit()
    assert detail(env,item,task)['text']==queue.DENIED


@pytest.mark.parametrize('kind',['hidden','owner_access','owner_inactive','missing_owner','completed','accepted','cancelled'])
def test_source_state_and_owner_eligibility_are_current_on_every_read(queue_env,kind):
    env,item,task=queue_env;c,users,*_=env
    if kind in ('hidden','owner_access'):doc=linked_document(env,item,'2026-10-30')
    assert ids(command(env,'/review_queue',10)['text'])==[task['id']]
    if kind in ('hidden','owner_access'):
        uid=users[0]['id'] if kind=='hidden' else users[3]['id']
        c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],uid));c.commit()
    elif kind=='owner_inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif kind=='missing_owner':c.execute('UPDATE work_task SET owner_id=NULL WHERE id=?',(task['id'],));c.commit()
    elif kind=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    else:work_tasks.mutate(c,users[0] if kind=='accepted' else users[1],item['id'],task['id'],task['revision'],'accept' if kind=='accepted' else 'cancel',{'reason':'Changed source state'})
    before=snapshot(c)
    assert not ids(command(env,'/review_queue',11)['text'])
    assert detail(env,item,task,12)['text']==command(env,'/review_task 999999 999999',13)['text']==queue.DENIED
    assert snapshot(c)==before


@pytest.mark.parametrize('kind',['read_grant','queue_grant','pilot','work','documents','disconnect','restore','bot','direct'])
def test_read_consent_host_context_and_transport_are_rechecked(queue_env,monkeypatch,kind):
    env,item,task=queue_env;c,users,path,_,payload=env
    assert 'Tasks I can review' in command(env,'/review_queue',10)['text']
    if kind in ('read_grant','queue_grant'):
        scope='work.read' if kind=='read_grant' else queue.ACTION
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
    elif kind=='pilot':monkeypatch.setenv('CSS_TELEGRAM_TASKS_REVIEW_READ_ENABLED','0')
    elif kind in ('work','documents'):st.set_setting(c,kind+'.enabled','0')
    elif kind=='disconnect':links.disconnect(c,payload,NOW)
    elif kind=='restore':backups.clear_restored_sessions(path)
    elif kind=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    else:monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    before=snapshot(c)
    assert 'method' not in command(env,'/review_queue',11)
    assert 'method' not in detail(env,item,task,12)
    assert snapshot(c)==before


def test_group_topic_and_duplicate_updates_cannot_create_pushes(queue_env):
    env,item,task=queue_env;c,*_=env
    packet=update(10,text='/review_queue');packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    packet=update(11,text='/review_queue');packet['message']['message_thread_id']=4
    assert 'method' not in submit(env[3],packet).json()
    packet=update(12,text='/review_queue');response=submit(env[3],packet).json()
    assert 'Tasks I can review' in response['text'] and 'method' not in submit(env[3],packet).json()
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('text',['/review_queue 0','/review_queue -1','/review_queue 9223372036854775808',
                                 '/review_queue 1 2','/review_task','/review_task 1','/review_task 1 2 3','/review_task true 2'])
def test_usage_input_is_bounded_and_no_query_is_retained(queue_env,text):
    env,*_=queue_env;c=env[0]
    assert command(env,text,10)['text']==queue.USAGE
    assert not rows(c,"SELECT * FROM telegram_update WHERE payload_json LIKE '%review_query%'")


def test_paging_covers_all_eligible_rows_and_unicode_budget(queue_env):
    env,item,task=queue_env;c,users,*_=env
    expected={task['id']}
    for i in range(8):expected.add(seed(env,item,title='📌'*110+' '+str(i))['id'])
    seen=[];command_text='/review_queue'
    for number in range(10,20):
        text=command(env,command_text,number)['text'];assert queue.common.units(text)<=4096
        seen+=ids(text)
        match=re.search(r'(?:Next page:|Continue:) (/review_queue [0-9]+)',text)
        if not match:break
        command_text=match[1]
    assert set(seen)==expected and len(seen)==len(expected)


def test_bounded_scan_can_continue_past_ineligible_owners_without_false_global_empty(queue_env,monkeypatch):
    env,item,task=queue_env;c,users,*_=env
    for i in range(5):seed(env,item,owner=2,title='DoNotExposeIneligible '+str(i))
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[2]['id'],));c.commit()
    monkeypatch.setattr(queue,'SCAN_LIMIT',3);monkeypatch.setattr(queue,'BATCH_SIZE',2)
    first=command(env,'/review_queue',10)['text']
    assert not ids(first) and 'More permitted source candidates remain' in first and 'DoNotExposeIneligible' not in first
    next_command=re.search(r'Continue: (/review_queue [0-9]+)',first)[1]
    assert ids(command(env,next_command,11)['text'])==[task['id']]


def test_visibility_and_coordinator_filtering_precede_scan_limit(queue_env,monkeypatch):
    env,item,task=queue_env;c,users,*_=env
    other=case(c,users[0],item['unit_id'],title='DoNotExposeOtherCase')
    for i in range(5):seed(env,other,title='DoNotExposeNonCoordinator '+str(i))
    monkeypatch.setattr(queue,'SCAN_LIMIT',2);monkeypatch.setattr(queue,'BATCH_SIZE',1)
    text=command(env,'/review_queue',10)['text']
    assert ids(text)==[task['id']] and 'DoNotExpose' not in text and 'Continue:' not in text


def test_active_formal_review_stays_in_source_ui_and_never_leaks_queue_row(queue_env):
    env,item,task=queue_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],reviewed['unit_id'],links.stamp(NOW)));c.commit()
    target=work_tasks.create(c,users[0],reviewed['id'],{'title':'DoNotExposeFormalReview','expected_output':'Evidence','unit_id':reviewed['unit_id']})
    target=work_tasks.mutate(c,users[1],reviewed['id'],target['id'],target['revision'],'confirm',{'owner_id':users[0]['id'],'reason':'Source assignment'})
    target=work_tasks.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'acknowledge',{'reason':'Source start'})
    target=work_tasks.mutate(c,users[0],reviewed['id'],target['id'],target['revision'],'submit',{'reason':'Source output','submission':'DoNotExposeEvidence'})
    assert target['id'] in ids(command(env,'/review_queue',10)['text'])
    formal_review(c,users,request_consolidation(c,users,output,reviewed))
    before=snapshot(c)
    assert 'DoNotExposeFormalReview' not in command(env,'/review_queue',20)['text']
    assert detail(env,reviewed,target,21)['text']==queue.DENIED and snapshot(c)==before


def test_review_queue_requires_work_read_and_its_own_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking
    ch,raw,confirmation=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_REVIEW_READ_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[queue.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',queue.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_REVIEW_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


@pytest.mark.parametrize('mode',['accept','return'])
def test_write_pilot_pause_hides_only_its_guidance_not_permitted_queue_metadata(queue_env,monkeypatch,mode):
    env,item,task=queue_env
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_'+mode.upper()+'_ENABLED','0')
    text=detail(env,item,task)['text']
    assert ids(text)==[task['id']] and '/task_'+mode not in text
    assert ids(command(env,'/review_queue',12)['text'])==[task['id']]
