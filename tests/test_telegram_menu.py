"""Private discovery follows current consent/configuration; no record reads or writes."""
import pytest

import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_menu as menu
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed
from tests.test_telegram_work import seed,lookup,work_env
from tests.test_telegram_tasks import task_env


@pytest.fixture
def menu_env(linking,monkeypatch):
    c,_,_,client,_=linking
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    _,_,code=claimed(linking,scopes=['calendar.read'])
    submit(client,update(2,text='/confirm '+code));bot.process_updates(c,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing provider call'))
    return linking


def command(env,text='/menu',number=10):
    result=submit(env[3],update(number,text=text))
    assert result.status_code==200
    return result.json()


def test_menu_alias_has_only_currently_consented_features(menu_env,monkeypatch):
    # Enabling every host flag must never grant business access on its own.
    for flag in bot.storage.SWITCHES:monkeypatch.setenv('CSS_TELEGRAM_'+flag.upper()+'_ENABLED','1')
    for module in ('documents','work','supplies'):st.set_setting(menu_env[0],module+'.enabled','1')
    text=command(menu_env)['text']
    assert 'your private menu' in text and 'Calendar' in text and '/calendar' in text
    for hidden in ('/meeting','/my_tasks','/task_ack','/documents','/my_supplies','/my_travel','/my_meals','/my_arrangements','/room_request'):
        assert hidden not in text
    assert '/status' in text and '/account/telegram' in text
    assert command(menu_env,'/help',11)['text']==text
    assert 'method' not in command(menu_env)


def test_all_consented_menu_has_groups_examples_and_fits_budget(menu_env,monkeypatch):
    c,users,*_=menu_env
    connection=dict(zip([d[0] for d in c.execute('SELECT * FROM telegram_connection').description],c.execute('SELECT * FROM telegram_connection').fetchone()))
    for scope in links.SCOPES:
        if scope=='calendar.read':continue
        c.execute('INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at) VALUES (?,?,?,?,?,?,?)',
            (connection['id'],users[0]['id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()
    for flag in bot.storage.SWITCHES:monkeypatch.setenv('CSS_TELEGRAM_'+flag.upper()+'_ENABLED','1')
    for module in ('documents','work','supplies'):st.set_setting(c,module+'.enabled','1')
    text=command(menu_env)['text']
    for label in ('Calendar','Tasks and work','Documents','Requests','Example: /find_documents budget','Example: /my_tasks overdue'):
        assert label in text
    for command_ in ('/meeting','/my_summary','/task_ack','/task_submit','/my_room_meals','/my_arrangements','/my_supplies','/documents'):
        assert command_ in text
    assert menu.common.units(text)<=4096
    c.execute('UPDATE telegram_grant SET revoked_at=?',(links.stamp(NOW),));c.commit()
    status_text=command(menu_env,'/status',11)['text']
    assert menu.common.units(status_text)<=4096
    assert '/documents' not in status_text and '/task_submit' not in status_text


def test_status_explains_missing_consent_without_advertising_hidden_commands(menu_env,monkeypatch):
    monkeypatch.setenv('CSS_TELEGRAM_DOCUMENTS_READ_ENABLED','1')
    st.set_setting(menu_env[0],'documents.enabled','1')
    text=command(menu_env,'/status')['text']
    assert 'connection: active' in text
    assert 'Calendar lookup' in text and 'Document lookup: missing consent' in text
    assert '/documents' not in text and '/task_submit' not in text
    monkeypatch.setenv('CSS_TELEGRAM_DOCUMENTS_READ_ENABLED','0')
    assert 'Document lookup: host pilot' in command(menu_env,'/status',11)['text']


def test_revoked_or_paused_scope_disappears_from_fresh_menu(menu_env,monkeypatch):
    c,*_=menu_env
    assert '/calendar' in command(menu_env)['text']
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    assert '/calendar' not in command(menu_env,number=11)['text']
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
    assert '/calendar' not in command(menu_env,number=12)['text']


def test_direct_mode_hides_webhook_only_commands(menu_env,monkeypatch):
    c,users,*_=menu_env
    link=c.execute('SELECT id,generation FROM telegram_connection').fetchone()
    for scope in ('work.read','tasks.submit','documents.read'):
        c.execute('INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at) VALUES (?,?,?,?,?,?,?)',
            (link[0],users[0]['id'],scope,link[1],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
        monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','1')
    c.commit()
    st.set_setting(c,'documents.enabled','1');st.set_setting(c,'work.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    command(menu_env)
    bot.process_updates(c,NOW)
    found=bot.rows(c,"SELECT * FROM telegram_delivery WHERE state='queued' ORDER BY id DESC LIMIT 1")[0]
    text=bot.render_delivery(c,found,{'kind':'help','bot':bot.transport.config()[0],'fingerprint':bot.transport.config()[2]},bot.transport.config(),NOW)
    assert '/my_tasks' in text and '/task_submit' not in text and '/documents' not in text


def test_unlinked_and_pending_help_stays_neutral(linking,monkeypatch):
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    text=command(linking)['text']
    assert '/start' in text and '/calendar' not in text and '/my_tasks' not in text
    # The original two-channel flow still supplies its real confirmation via status.
    packet=command(linking,'/start',11)
    import re
    code=re.search(r'(?m)^[a-f0-9]{64}$',packet['text'])[0]
    links.claim(linking[0],linking[4],code,[],NOW)
    assert 'awaiting confirmation' in command(linking,number=12)['text']
    assert '/confirm ' in command(linking,'/status',13)['text']


def test_group_menu_is_ignored(menu_env):
    message=update(10,text='/menu');message['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(menu_env[3],message).json()


def test_task_details_only_offer_consented_and_current_actions(task_env,monkeypatch):
    c,users,*_=task_env
    item,task=seed(task_env)
    packet=command(task_env,f"/task_status {item['id']} {task['id']}")
    assert f"Next: /task_ack {item['id']} {task['id']}" in packet['text']
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='tasks.acknowledge'",(links.stamp(NOW),));c.commit()
    assert '/task_ack' not in command(task_env,f"/task_status {item['id']} {task['id']}",11)['text']
    c.execute("UPDATE work_task SET status='in_progress' WHERE id=?",(task['id'],));c.commit()
    assert '/task_submit' in command(task_env,f"/task_status {item['id']} {task['id']}",12)['text']
    import work_blockers
    monkeypatch.setattr(work_blockers,'waiting',lambda *a:True)
    assert '/task_submit' not in command(task_env,f"/task_status {item['id']} {task['id']}",13)['text']


def test_source_module_pause_hides_work_and_write_commands(task_env):
    assert '/my_tasks' in command(task_env)['text']
    st.set_setting(task_env[0],'work.enabled','0')
    text=command(task_env,number=11)['text']
    assert '/my_tasks' not in text and '/task_ack' not in text and '/task_submit' not in text
    assert 'Work lookup: source module is paused' in command(task_env,'/status',12)['text']


def test_meeting_menu_requires_current_calendar_read_prerequisite(menu_env,monkeypatch):
    c,users,*_=menu_env
    link=c.execute('SELECT id,generation FROM telegram_connection').fetchone()
    c.execute('INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at) VALUES (?,?,?,?,?,?,?)',
        (link[0],users[0]['id'],'calendar.create',link[1],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)));c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','1')
    assert '/meeting' in command(menu_env)['text']
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
    assert '/meeting' not in command(menu_env,number=11)['text']
    assert 'Meeting creation: host pilot or a prerequisite is paused' in command(menu_env,'/status',12)['text']
