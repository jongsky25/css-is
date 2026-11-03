"""Synthetic private brief: independent consent, source rules and staged preferences."""
from datetime import timedelta

import pytest

import backups
import storage as st
import telegram_bot as bot
import telegram_brief as brief
import telegram_brief_preferences as prefs
import telegram_links as links
from tests.test_work import workspace, document
from tests.test_telegram_bot import setup, submit, update, NOW
from tests.test_telegram_links import linking, claimed
from tests.test_telegram_menu import menu_env, command
from tests.test_telegram_work import work_env, seed
from tests.test_telegram_personal import personal_env, seed as personal_seed
from tests.test_telegram_supplies import supply_env, seed as supply_seed


def grant(env, scope, monkeypatch):
    c, users, *_ = env
    link=c.execute('SELECT id,generation FROM telegram_connection').fetchone()
    c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
        VALUES(?,?,?,?,?,?,?)''',(link[0],users[0]['id'],scope,link[1],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','1')


def choices():
    return dict(calendar=True, work=True, requests=True, reminder_requested=False, local_time='08:00')


def test_calendar_only_brief_uses_current_mine_scope_and_manila_window(menu_env):
    c,users,*_=menu_env
    today=NOW.astimezone(brief.common.ZONE).date()
    st.cal_create(c,'Own synthetic meeting',today.isoformat(),people=[users[0]['id']],audience='bureau',by='another')
    st.cal_create(c,'Other bureau meeting',today.isoformat(),people=[users[3]['id']],audience='bureau',by='another')
    st.cal_create(c,'Outside brief window',(today+timedelta(days=7)).isoformat(),people=[users[0]['id']],audience='bureau',by='another')
    text=command(menu_env,'/brief')['text']
    assert 'Own synthetic meeting' in text and 'Other bureau meeting' not in text and 'Outside brief window' not in text
    assert 'Asia/Manila' in text and '/calendar '+today.isoformat() in text
    assert '/my_tasks' not in text and '/my_travel' not in text
    assert 'Scheduled daily brief delivery is not active' in text
    assert '/brief' in command(menu_env,'/menu',11)['text']
    assert brief.common.units(text)<=4096


def test_task_summary_rechecks_hidden_document_and_never_submits(work_env,monkeypatch):
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing call'))
    c,users,*_=work_env
    item,task=seed(work_env)
    c.execute("UPDATE work_task SET due_date='2026-01-01',submission='NeverExposeOutput' WHERE id=?",(task['id'],));c.commit()
    assert 'Overdue tasks: 1' in command(work_env,'/brief')['text']
    import work
    doc=document(c,users[0],item['unit_id'])
    work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=?',(doc['id'],));c.commit()
    text=command(work_env,'/brief',11)['text']
    assert 'Overdue tasks: 0' in text and 'NeverExposeOutput' not in text
    assert c.execute('SELECT status FROM work_task WHERE id=?',(task['id'],)).fetchone()[0]=='todo'
    assert not c.execute('SELECT count(*) FROM telegram_operation').fetchone()[0]


def test_personal_brief_is_owner_only_even_for_admin_and_does_not_expose_notes(personal_env):
    env,adapter=personal_env
    own=personal_seed(personal_env);other=personal_seed(personal_env,3)
    text=command(env,'/brief')['text']
    assert adapter.COMMANDS[1]+' '+str(own) in text
    assert adapter.COMMANDS[1]+' '+str(other) not in text
    assert 'DoNotExpose' not in text
    for other_adapter in (brief.personal.TRAVEL,brief.personal.MEALS,brief.personal.ARRANGEMENTS):
        if other_adapter is not adapter:assert other_adapter.COMMANDS[0] not in text


def test_supply_brief_uses_requester_needs_action_policy(supply_env):
    env,_=supply_env
    rid=supply_seed(supply_env)
    other=supply_seed(supply_env,3)
    text=command(env,'/brief')['text']
    assert '/my_supplies needs_action' in text
    assert 'DoNotExpose' not in text and '/supply_status '+str(other) not in text
    expected=brief.supplies.dashboard.queue(env[0],env[1][0],'requests',state='needs_action',limit=2)
    assert 'My supplies needing action: '+str(expected['total']) in text
    for r in expected['requests']:assert '/supply_status '+str(r['id']) in text


@pytest.mark.parametrize('change',['grant','flag','inactive','disconnect','fingerprint','direct','group','topic'])
def test_private_identity_transport_and_current_scope_fences(menu_env,monkeypatch,change):
    c,users,_,_,payload=menu_env
    if change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=?",(links.stamp(NOW),));c.commit()
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
    elif change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='fingerprint':c.execute("UPDATE telegram_connection SET bot_fingerprint='other'");c.commit()
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    packet=update(10,text='/brief')
    if change=='group':packet['message']['chat']={'id':-100,'type':'group'}
    if change=='topic':packet['message']['message_thread_id']=7
    result=submit(menu_env[3],packet).json()
    if change in ('grant','flag'):
        assert 'No selected sections' in result['text'] and '/calendar ' not in result['text']
    else:assert 'method' not in result


def test_bad_arguments_deduplication_and_no_cached_business_text(menu_env,monkeypatch):
    monkeypatch.setattr(brief.office_calendar,'items_between',lambda *a,**kw:pytest.fail('Invalid command queried source'))
    assert command(menu_env,'/brief extra')['text']==brief.USAGE
    assert 'method' not in command(menu_env,'/brief extra')
    assert all('daily brief' not in (r[0] or '') for r in menu_env[0].execute('SELECT payload_json FROM telegram_update'))


def test_all_sections_fit_utf16_budget(menu_env,monkeypatch):
    c,users,*_=menu_env
    for scope in ('work.read','rooms.read','travel.read','meals.read','arrangements.read'):
        grant(menu_env,scope,monkeypatch)
    st.set_setting(c,'work.enabled','1')
    for _ in range(3):
        st.cal_create(c,'Synthetic calendar title',NOW.astimezone(brief.common.ZONE).date().isoformat(),people=[users[0]['id']],audience='bureau',by='another')
    c.execute('UPDATE calendar_entry SET title=?',('📅'*400,));c.commit()
    text=command(menu_env,'/brief')['text']
    assert 'My work summary' in text and 'Recent room-linked meals' in text
    assert brief.common.units(text)<=4096
    assert '3 entries in range' in text


def test_saved_choices_filter_manual_brief_without_granting_or_scheduling(menu_env):
    c,users,_,_,payload=menu_env
    values=choices();values.update(calendar=False,reminder_requested=True,local_time='07:30')
    prefs.save(c,payload,0,values,NOW)
    text=command(menu_env,'/brief')['text']
    assert 'No selected sections' in text and '/calendar ' not in text and '/my_tasks' not in text
    assert prefs.get(c,users[0]['id'])['reminder_requested']==1
    assert prefs.get(c,users[1]['id'])['revision']==0
    assert not c.execute("SELECT count(*) FROM telegram_delivery WHERE state='queued'").fetchone()[0]
    assert not c.execute('SELECT count(*) FROM telegram_operation').fetchone()[0]
    assert prefs.get(c,users[0]['id'])['local_time']=='07:30'
    import telegram_reminders
    # Existing workers cannot consume this staged choice, even on later days.
    assert telegram_reminders.enqueue(c,NOW+timedelta(days=1))==0


def test_idempotent_install_preserves_staged_choices_without_changing_existing_reminders(menu_env):
    c,users,_,_,payload=menu_env
    import telegram_reminders
    before=telegram_reminders.get(c,users[0]['id'])
    values=choices();values['reminder_requested']=True
    prefs.save(c,payload,0,values,NOW)
    prefs.install(c);prefs.install(c)
    assert prefs.get(c,users[0]['id'])['reminder_requested']==1
    assert telegram_reminders.get(c,users[0]['id'])==before


@pytest.mark.parametrize('bad',[{'local_time':'25:00'},{'local_time':'8:00'},{'calendar':1},
                              {'calendar':False,'work':False,'requests':False},{'unknown':True}])
def test_invalid_choices_never_persist(menu_env,bad):
    c,users,_,_,payload=menu_env;values=choices();values.update(bad)
    with pytest.raises(ValueError):prefs.save(c,payload,0,values,NOW)
    assert prefs.get(c,users[0]['id'])['revision']==0


def test_stale_session_audit_rollback_and_restore_keep_choices_without_enabling(menu_env,monkeypatch):
    c,users,path,_,payload=menu_env
    prefs.save(c,payload,0,choices(),NOW)
    with pytest.raises(prefs.Conflict):prefs.save(c,payload,0,choices(),NOW)
    monkeypatch.setattr(st,'audit',lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic audit failure')))
    with pytest.raises(ValueError):prefs.save(c,payload,1,choices(),NOW)
    assert prefs.get(c,users[0]['id'])['revision']==1
    backups.clear_restored_sessions(path)
    assert prefs.get(c,users[0]['id'])['revision']==1
    with pytest.raises(ValueError):prefs.save(c,payload,1,choices(),NOW)
    assert 'method' not in command(menu_env,'/brief')
