"""Private proposals preserve native assignment, source policy and atomicity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re

import pytest

import backups
from documents_storage import rows, transaction
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_task_create as create
import work
import work_tasks
from tests.test_work import workspace, case, document, consolidation_fixture, request_consolidation, formal_review
from tests.test_telegram_bot import setup, submit, update, NOW
from tests.test_telegram_links import linking, claimed, start
from tests.test_telegram_menu import menu_env, command
from tests.test_telegram_brief import grant


@pytest.fixture
def proposal(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'work.read',monkeypatch);grant(env,'tasks.create',monkeypatch)
    unit=c.execute("SELECT id FROM org_unit WHERE path='WORK/D1'").fetchone()[0]
    item=case(c,users[0],unit,title='Synthetic proposal work')
    return env,item


def fields(env,item,**changes):
    values={'case_id':item['id'],'title':'Synthetic new task','expected_output':'A concise expected output',
            'unit_id':'','proposed_owner_id':env[1][3]['id'],'due_date':'2026-10-28'}
    return {**values,**changes}


def prepare(proposal,number=10,key='task-proposal-operation',**changes):
    env,item=proposal;c,users,*_=env
    guide=command(env,'/new_task',number)['text']
    assert create.PATH+'create?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,create.ACTION)
    return ctx,actions.issue(c,ctx,create.ACTION,key,fields(env,item,**changes),NOW)


def confirmation(env,result,number=20):
    text=command(env,'/newtask_preview '+result['operation_id'],number)['text']
    assert 'Synthetic new task' in text and 'Expected output:' in text and 'officer' in text
    assert create.common.units(text)<=4096
    return re.search(r'/newtask_confirm [A-Za-z0-9_-]{43}',text)[0]


def snapshot(c):
    return {table:list(c.execute('SELECT * FROM '+table)) for table in
            ('work_case','work_task','work_event','audit_log','document','document_access',
             'work_review_packet','work_review_source','work_review_invalidation','document_review')}


def test_confirm_creates_one_proposal_and_never_assigns_or_grants_access(proposal):
    env,item=proposal;c,users,*_=env
    _,result=prepare(proposal);exact=confirmation(env,result)
    assert not rows(c,'SELECT * FROM work_task')
    before=list(c.execute('SELECT * FROM document_access'))
    text=command(env,exact,21)['text']
    task=rows(c,'SELECT * FROM work_task')[0]
    assert task['status']=='proposed' and task['owner_id'] is None and task['proposed_owner_id']==users[3]['id']
    assert task['mandatory']==1
    assert task['expected_output']=='A concise expected output' and task['creator_id']==users[0]['id']
    assert list(c.execute('SELECT * FROM document_access'))==before
    assert 'assignment requires officer confirmation' in text and 'Current status: proposed' in text
    assert '/work_status '+str(item['id']) in text and '/task_status' not in text
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/newtask_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    with pytest.raises(ValueError):
        work_tasks.mutate(c,users[0],item['id'],task['id'],task['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Synthetic attempted assignment'})
    assigned=work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'confirm',{'owner_id':users[3]['id'],'reason':'Synthetic officer confirmation'})
    assert assigned['status']=='todo' and assigned['owner_id']==users[3]['id']
    assert 'Current status: todo' in command(env,'/newtask_receipt '+result['operation_id'],24)['text']


@pytest.mark.parametrize('change',['work','completed','hidden_document','deadline','owner_inactive','owner_name',
                                   'unit_name','grant','read_grant','flag','module','disconnect','restore','expiry'])
def test_stale_source_or_authority_never_creates_task(proposal,monkeypatch,change):
    env,item=proposal;c,users,path,_,payload=env
    if change in ('hidden_document','deadline'):
        doc=document(c,users[0],item['unit_id'])
        work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
    _,result=prepare(proposal);exact=confirmation(env,result)
    if change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Changed work title',item['id']));c.commit()
    elif change=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    elif change=='hidden_document':
        c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
        c.execute('DELETE FROM document_access WHERE document_id=?',(doc['id'],));c.commit()
    elif change=='deadline':c.execute("UPDATE document SET due_date='2026-10-27',revision=revision+1 WHERE id=?",(doc['id'],));c.commit()
    elif change=='owner_inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif change=='owner_name':c.execute('UPDATE admin_user SET username=? WHERE id=?',('renamed@example.invalid',users[3]['id']));c.commit()
    elif change=='unit_name':c.execute('UPDATE org_unit SET name=? WHERE id=?',('Renamed unit',item['unit_id']));c.commit()
    elif change in ('grant','read_grant'):
        scope='tasks.create' if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_TASKS_CREATE_ENABLED','0')
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    else:monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','')
    assert saved==snapshot(c) and not rows(c,'SELECT * FROM work_task')


@pytest.mark.parametrize('bad',[{'title':''},{'expected_output':''},{'due_date':'2026-02-30'},{'title':'Bad\x00Title'},
                               {'unit_id':999999},{'proposed_owner_id':999999},{'title':'x'*161},{'owner_id':1}])
def test_invalid_fields_never_create_proposals(proposal,bad):
    env,item=proposal;c,users,*_=env
    guide=command(env,'/new_task')['text'];ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,create.ACTION)
    saved=snapshot(c)
    with pytest.raises(ValueError):actions.issue(c,ctx,create.ACTION,'bad-proposal-operation',fields(env,item,**bad),NOW)
    assert saved==snapshot(c) and not rows(c,'SELECT * FROM telegram_operation')


def test_unknown_and_other_work_ids_have_same_denial(proposal):
    env,item=proposal;c,users,*_=env
    other=case(c,users[3],item['unit_id'],title='Never expose other work')
    guide=command(env,'/new_task')['text'];ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,create.ACTION)
    errors=[]
    for identifier in (other['id'],999999):
        with pytest.raises(ValueError) as error:
            actions.issue(c,ctx,create.ACTION,'hidden-proposal-operation',fields(env,item,case_id=identifier),NOW)
        errors.append(str(error.value))
    assert errors[0]==errors[1] and 'Never expose' not in errors[0]


def test_proposed_owner_gains_no_access_and_assignment_keeps_document_checks(proposal):
    env,item=proposal;c,users,*_=env
    doc=document(c,users[0],item['unit_id'])
    work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
    before=list(c.execute('SELECT * FROM document_access'))
    _,result=prepare(proposal);exact=confirmation(env,result)
    command(env,exact,21)
    task=rows(c,'SELECT * FROM work_task')[0]
    assert task['owner_id'] is None and task['status']=='proposed'
    assert before==list(c.execute('SELECT * FROM document_access'))
    with pytest.raises(ValueError):
        work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'confirm',
                          {'owner_id':users[3]['id'],'reason':'Synthetic officer attempt'})
    assert rows(c,'SELECT status FROM work_task')[0]['status']=='proposed'


def test_initial_deadline_and_oversized_unicode_preview_are_blocked(proposal):
    env,item=proposal;c,users,*_=env
    doc=document(c,users[0],item['unit_id'])
    c.execute("UPDATE document SET due_date='2026-10-27' WHERE id=?",(doc['id'],));c.commit()
    work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
    guide=command(env,'/new_task')['text'];ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,create.ACTION)
    with pytest.raises(ValueError):actions.issue(c,ctx,create.ACTION,'after-official-deadline',fields(env,item),NOW)
    c.execute('UPDATE work_case SET title=? WHERE id=?',('📌'*120,item['id']))
    c.execute('UPDATE org_unit SET name=? WHERE id=?',('📌'*120,item['unit_id']));c.commit()
    with pytest.raises(ValueError):actions.issue(c,ctx,create.ACTION,'unicode-too-large-preview',fields(env,item,title='📌'*160,expected_output='📌'*1000,due_date='2026-10-26'),NOW)
    assert not rows(c,'SELECT * FROM work_task')


@pytest.mark.parametrize('failure',['audit','late_receipt','handoff'])
def test_failed_audit_receipt_or_handoff_rolls_back_task_and_review_events(proposal,monkeypatch,failure):
    env,item=proposal;c,*_=env
    _,result=prepare(proposal);exact=confirmation(env,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='late_receipt':monkeypatch.setattr(actions.ADAPTERS[create.ACTION],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_newtask_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmation_creates_one_task_and_one_source_event(proposal):
    env,item=proposal;c,users,path,*_=env
    ctx,result=prepare(proposal)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1] and len(rows(c,'SELECT * FROM work_task'))==1
    assert len(rows(c,"SELECT * FROM work_event WHERE action='task_proposed'"))==1


def test_private_only_and_ack_submit_commands_cannot_consume_creation_preview(proposal,monkeypatch):
    env,item=proposal;c,*_=env
    _,result=prepare(proposal);exact=confirmation(env,result)
    for number,text in enumerate(('/task_preview '+result['operation_id'],'/task_receipt '+result['operation_id'],'/task_confirm '+result['token']),21):
        assert 'Recorded outcome:' not in command(env,text,number)['text']
    assert not rows(c,'SELECT * FROM work_task')
    packet=update(24,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,25) and not rows(c,'SELECT * FROM work_task')


def test_deleted_task_receipt_cannot_refer_to_reused_numeric_id(proposal):
    env,item=proposal;c,users,*_=env
    _,result=prepare(proposal);exact=confirmation(env,result)
    command(env,exact,21);task=rows(c,'SELECT * FROM work_task')[0]
    c.execute('DELETE FROM work_task WHERE id=?',(task['id'],));c.commit()
    replacement=work_tasks.create(c,users[0],item['id'],{'title':'Replacement task','expected_output':'Different output','unit_id':item['unit_id']})
    assert replacement['id']==task['id']
    text=command(env,'/newtask_receipt '+result['operation_id'],22)['text']
    assert 'was deleted' in text and 'Replacement task' not in text
    assert len(rows(c,'SELECT * FROM work_task'))==1


def test_multiline_output_and_optional_owner_are_normalized_for_exact_preview(proposal):
    env,item=proposal;c,*_=env
    _,result=prepare(proposal,expected_output='First line\r\nSecond line',proposed_owner_id='',due_date='')
    exact=confirmation(env,result)
    command(env,exact,21)
    task=rows(c,'SELECT * FROM work_task')[0]
    assert task['expected_output']=='First line\nSecond line' and task['proposed_owner_id'] is None and task['due_date'] is None


def test_create_consent_requires_separate_read_and_current_host_pilot(linking,monkeypatch):
    c,users,_,_,payload=linking
    ch,raw,confirmation=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_CREATE_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,['tasks.create'],NOW)
    links.claim(c,payload,raw,['work.read','tasks.create'],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_TASKS_CREATE_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_paused_source_module_hides_and_refuses_new_guides(proposal):
    env,item=proposal;c,*_=env
    st.set_setting(c,'work.enabled','0')
    packet=command(env,'/new_task')
    assert 'Task proposal action unavailable' in packet['text']
    assert not rows(c,'SELECT * FROM telegram_meeting_origin WHERE action=?',(create.ACTION,))
    assert '/new_task' not in command(env,'/menu',11)['text']


@pytest.mark.parametrize('when',['before_preview','after_preview'])
def test_active_formal_review_stays_in_source_ui_without_resetting_approvals(proposal,when):
    env,item=proposal;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    if when=='before_preview':
        approved=formal_review(c,users,request_consolidation(c,users,output,reviewed))
        guide=command(env,'/new_task')['text']
        ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,create.ACTION)
        saved=snapshot(c)
        with pytest.raises(ValueError,match='active consolidation review'):
            actions.issue(c,ctx,create.ACTION,'formal-review-proposal',fields(env,reviewed),NOW)
    else:
        _,result=prepare((env,reviewed));exact=confirmation(env,result)
        approved=formal_review(c,users,request_consolidation(c,users,output,reviewed))
        saved=snapshot(c)
        assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)
    current=c.execute('SELECT approved_version,status FROM document WHERE id=?',(approved['id'],)).fetchone()
    assert current==(approved['approved_version'],approved['status'])
