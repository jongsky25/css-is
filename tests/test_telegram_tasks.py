"""Explicit private task writes: exact preview, current authority, atomic receipt."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re

import pytest

from documents_storage import rows
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_tasks as tasks
from tests.test_work import workspace, advance, document
from tests.test_telegram_bot import setup, update, submit, NOW
from tests.test_telegram_links import linking, claimed
from tests.test_telegram_work import seed


@pytest.fixture
def task_env(linking, monkeypatch):
    c, _, _, client, _ = linking
    for flag in ('WORK_READ','TASKS_ACKNOWLEDGE','TASKS_SUBMIT'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    _,_,code=claimed(linking,scopes=['work.read','tasks.acknowledge','tasks.submit'])
    submit(client,update(2,text='/confirm '+code));bot.process_updates(c,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram send'))
    return linking


def command(env, text, number=10):
    result=submit(env[3],update(number,text=text))
    assert result.status_code==200
    return result.json()


def token(reply):
    return re.search(r'/task_confirm ([A-Za-z0-9_-]{43})',reply['text'])[1]


def ctx(env):
    return tasks.context(env[0],rows(env[0],'SELECT * FROM telegram_connection')[0])


def submission(env, item, task, key='submission-key-123456'):
    return actions.issue(env[0],ctx(env),'tasks.submit',key,{'case_id':item['id'],'task_id':task['id'],
        'reason':'Synthetic review note','submission':'Synthetic output for review.'},NOW)


def test_ack_preview_then_confirm_once_and_explicit_recovery(task_env):
    c,*_=task_env
    item,task=seed(task_env)
    preview=command(task_env,f"/task_ack {item['id']} {task['id']}")
    raw=token(preview)
    assert preview['link_preview_options']=={'is_disabled':True}
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'
    assert raw not in '\n'.join(c.iterdump())
    reply=command(task_env,'/task_confirm '+raw,11)
    assert 'task_acknowledged' in reply['text'] and 'in_progress' in reply['text']
    revision=c.execute('SELECT revision FROM work_task').fetchone()[0]
    assert 'task_acknowledged' in command(task_env,'/task_confirm '+raw,12)['text']
    assert c.execute('SELECT revision FROM work_task').fetchone()[0]==revision
    assert 'method' not in command(task_env,'/task_confirm '+raw,12)
    operation=c.execute('SELECT operation_id FROM telegram_operation').fetchone()[0]
    assert 'task_acknowledged' in command(task_env,'/task_receipt '+operation,13)['text']
    assert bot.deliver(c,NOW)==0


def test_submit_preview_and_confirmation_reuses_workflow(task_env):
    c,users,*_=task_env
    item,task=seed(task_env)
    task=advance(c,users[0],task,'acknowledge')
    guide=command(task_env,f"/task_submit {item['id']} {task['id']}")
    assert '/account/telegram/task?case_id=' in guide['text']
    issued=submission(task_env,item,task)
    preview=command(task_env,'/task_preview '+issued['operation_id'],11)
    assert 'Synthetic output for review.' in preview['text']
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='in_progress'
    reply=command(task_env,'/task_confirm '+token(preview),12)
    assert 'task_submitted' in reply['text']
    assert c.execute('SELECT status,submission FROM work_task').fetchone()==('for_review','Synthetic output for review.')
    assert all('Synthetic output' not in r[0] for r in c.execute('SELECT projection_json FROM telegram_delivery'))


@pytest.mark.parametrize('change',['revision','owner','read_grant','action_grant','module','switch','account','disconnect','expiry'])
def test_change_after_preview_denies_confirmation(task_env,monkeypatch,change):
    c,users,_,_,payload=task_env
    item,task=seed(task_env)
    preview=command(task_env,f"/task_ack {item['id']} {task['id']}")
    raw=token(preview)
    if change=='revision':c.execute('UPDATE work_task SET revision=revision+1');c.commit()
    elif change=='owner':c.execute('UPDATE work_task SET owner_id=?',(users[3]['id'],));c.commit()
    elif change in ('read_grant','action_grant'):
        action='work.read' if change=='read_grant' else 'tasks.acknowledge'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),action));c.commit()
    elif change=='module':st.set_setting(c,'work.enabled','0')
    elif change=='switch':monkeypatch.setenv('CSS_TELEGRAM_TASKS_ACKNOWLEDGE_ENABLED','0')
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    reply=command(task_env,'/task_confirm '+raw,11)
    assert 'task_acknowledged' not in reply.get('text','')
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'


def test_wrong_sender_group_and_wrong_action_token_denied(task_env):
    c,*_=task_env
    item,task=seed(task_env)
    preview=command(task_env,f"/task_ack {item['id']} {task['id']}")
    raw=token(preview)
    assert 'method' not in submit(task_env[3],update(11,sender=102,text='/task_confirm '+raw)).json()
    message=update(12,text='/task_confirm '+raw);message['message']['chat']={'type':'group','id':-100}
    assert 'method' not in submit(task_env[3],message).json()
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'


def test_atomic_rollback_when_receipt_update_fails(task_env):
    c,*_=task_env
    item,task=seed(task_env)
    raw=token(command(task_env,f"/task_ack {item['id']} {task['id']}"))
    c.execute("CREATE TRIGGER test_receipt_failure BEFORE UPDATE ON telegram_operation WHEN NEW.state='committed' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;");c.commit()
    reply=submit(task_env[3],update(11,text='/task_confirm '+raw))
    assert reply.status_code==503
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'
    assert not c.execute('SELECT 1 FROM telegram_update WHERE update_id=11').fetchone()


def test_late_value_error_rolls_back_mutation_before_neutral_reply(task_env,monkeypatch):
    c,*_=task_env
    item,task=seed(task_env)
    raw=token(command(task_env,f"/task_ack {item['id']} {task['id']}"))
    original=tasks.Adapter.apply
    def fail(self,*args):
        original(self,*args)
        raise ValueError('Synthetic late expiry')
    monkeypatch.setattr(tasks.Adapter,'apply',fail)
    assert 'unavailable' in command(task_env,'/task_confirm '+raw,11)['text']
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'
    assert c.execute('SELECT state FROM telegram_operation').fetchone()[0]=='pending'


def test_separate_write_consent_required_and_direct_mode_cannot_write(task_env,monkeypatch):
    c,*_=task_env
    item,task=seed(task_env)
    c.execute("DELETE FROM telegram_grant WHERE action='tasks.acknowledge'");c.commit()
    assert 'unavailable' in command(task_env,f"/task_ack {item['id']} {task['id']}")['text']
    assert not c.execute('SELECT 1 FROM telegram_operation').fetchone()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(task_env,f"/task_ack {item['id']} {task['id']}",11)
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'


def test_two_confirmers_commit_only_once(task_env):
    c,_,path,*_=task_env
    item,task=seed(task_env)
    raw=token(command(task_env,f"/task_ack {item['id']} {task['id']}"))
    context=ctx(task_env)
    def confirm():
        connection=st.connect(path)
        try:return actions.confirm(connection,context,raw,NOW)
        finally:connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:confirm(),range(2)))
    assert results[0]==results[1]
    assert c.execute('SELECT revision FROM work_task').fetchone()[0]==task['revision']+1


def test_oversized_unicode_preview_is_rejected(task_env):
    c,users,*_=task_env
    item,task=seed(task_env);task=advance(c,users[0],task,'acknowledge')
    with pytest.raises(actions.Unavailable):
        actions.issue(c,ctx(task_env),'tasks.submit','unicode-preview-key-123',{'case_id':item['id'],'task_id':task['id'],
            'reason':'Note','submission':'😀'*1800},NOW)
    assert not c.execute('SELECT 1 FROM telegram_operation').fetchone()


def test_blockers_and_closed_workflow_still_prevent_submission(task_env,monkeypatch):
    c,users,*_=task_env
    item,task=seed(task_env);task=advance(c,users[0],task,'acknowledge')
    issued=submission(task_env,item,task)
    preview=command(task_env,'/task_preview '+issued['operation_id'])
    import work_blockers
    monkeypatch.setattr(work_blockers,'waiting',lambda *a:True)
    assert 'unavailable' in command(task_env,'/task_confirm '+token(preview),11)['text']
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='in_progress'


def test_hidden_document_after_preview_denies_task_change(task_env):
    c,users,*_=task_env
    item,task=seed(task_env)
    raw=token(command(task_env,f"/task_ack {item['id']} {task['id']}"))
    doc=document(c,users[0],item['unit_id'])
    import work
    work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=?',(doc['id'],));c.commit()
    assert 'unavailable' in command(task_env,'/task_confirm '+raw,11)['text']
    assert c.execute('SELECT status FROM work_task').fetchone()[0]=='todo'


def test_work_read_revocation_scrubs_submission_preview(task_env):
    c,users,*_=task_env
    item,task=seed(task_env);task=advance(c,users[0],task,'acknowledge')
    submission(task_env,item,task)
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='work.read'",(links.stamp(NOW),));c.commit()
    assert c.execute('SELECT state,fields_json,summary_json,expected_json FROM telegram_preview').fetchone()==('cancelled',None,None,None)


@pytest.mark.parametrize('action',['tasks.acknowledge','tasks.submit'])
def test_linking_write_consent_requires_work_read_and_enabled_pilot(linking,monkeypatch,action):
    from tests.test_telegram_links import start
    c,_,_,_,payload=linking
    _,code,_=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_'+action.replace('.','_').upper()+'_ENABLED','1')
    with pytest.raises(ValueError,match='work read consent'):
        links.claim(c,payload,code,[action],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_'+action.replace('.','_').upper()+'_ENABLED','0')
    with pytest.raises(ValueError,match='pilot'):
        links.claim(c,payload,code,['work.read',action],NOW)
    assert not c.execute('SELECT 1 FROM telegram_grant').fetchone()
