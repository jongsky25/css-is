"""Own saved follows are current metadata, never a preference/read-state mutation."""
import re
import sqlite3

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_followed_discussions as reads
import work
import work_tasks
import work_updates
import work_discussion as discussion
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_comment_manage import snapshot


@pytest.fixture
def follows_env(deadline_env,monkeypatch):
    grant(deadline_env[0],reads.ACTION,monkeypatch)
    env,item,task=deadline_env;c,users,*_=env
    for target in (None,task['id']):work_updates.follow(c,users[0],item['id'],target)
    work_updates.follow(c,users[3],item['id'])
    return deadline_env


def keys(text):
    return [(int(a),int(b) if b else 0) for a,b in re.findall(re.escape(links.origin())+r'/work/([0-9]+)/discussion(?:\?task_id=([0-9]+))?',text)]


def test_own_saved_work_and_task_follows_are_metadata_only_and_make_no_changes(follows_env):
    env,item,task=follows_env;c,users,*_=env
    discussion.post(c,users[3],item['id'],'StoredPrivateComment',task_id=task['id'],mentions=[users[0]['id']])
    before=snapshot(c)
    text=command(env,'/my_follows',10)['text']
    assert keys(text)==[(item['id'],task['id']),(item['id'],0)]
    assert 'Task-specific follow · Work-wide also on' in text and 'all task discussions' in text
    assert 'StoredPrivate' not in text and users[3]['username'] not in text
    assert '/discussion_follow' not in text and '/account/telegram/discussion-follow/' not in text
    assert 'Lookup changes nothing' in text and before==snapshot(c)
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    assert not rows(c,"SELECT * FROM telegram_update WHERE payload_json LIKE '%follows_query%'")
    for r in rows(c,'SELECT projection_json FROM telegram_delivery'):
        assert item['title'] not in r['projection_json'] and 'StoredPrivate' not in r['projection_json']


def test_work_and_tasks_filters_show_saved_rows_without_expanding_inherited_coverage(follows_env):
    env,item,task=follows_env;c,users,*_=env
    work_tasks.create(c,users[0],item['id'],{'title':'Inherited but not explicitly followed','expected_output':'StoredPrivateOutput','unit_id':item['unit_id']})
    assert keys(command(env,'/my_follows work',10)['text'])==[(item['id'],0)]
    assert keys(command(env,'/my_follows tasks',11)['text'])==[(item['id'],task['id'])]
    work_updates.follow(c,users[0],item['id'],enabled=False)
    text=command(env,'/my_follows tasks',12)['text']
    assert keys(text)==[(item['id'],task['id'])] and 'Work-wide also off' in text


def test_other_account_follows_are_never_listed_and_own_hidden_follows_grant_no_access(follows_env):
    env,item,task=follows_env;c,users,*_=env
    other=case(c,users[3],item['unit_id'])
    work_updates.follow(c,users[3],other['id'])
    c.execute('INSERT INTO work_follow VALUES (?,?,NULL,?)',(other['id'],users[0]['id'],links.stamp(NOW)));c.commit()
    before=snapshot(c);text=command(env,'/my_follows',10)['text']
    assert keys(text)==[(item['id'],task['id']),(item['id'],0)] and other['title'] not in text and before==snapshot(c)
    with pytest.raises(ValueError):reads.detail(c,users[0],other['id'],None)
    work_updates.follow(c,users[0],item['id'],task['id'],enabled=False)
    with pytest.raises(ValueError):reads.detail(c,users[0],item['id'],task['id'])


@pytest.mark.parametrize('change',['work_access','document_access','work_module','documents_module','read_grant','list_grant','pilot','disconnect','restore','bot','direct','delivery'])
def test_current_source_and_private_account_scope_guards(follows_env,change,monkeypatch):
    env,item,task=follows_env;c,users,path,_,payload=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    assert keys(command(env,'/my_follows',10)['text'])
    if change=='work_access':c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change in ('work_module','documents_module'):st.set_setting(c,('work' if change=='work_module' else 'documents')+'.enabled','0')
    elif change in ('read_grant','list_grant'):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),'work.read' if change=='read_grant' else reads.ACTION));c.commit()
    elif change=='pilot':monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOWS_READ_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    else:monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
    before=snapshot(c);reply=command(env,'/my_follows',11)
    if change in ('work_access','document_access'):assert not keys(reply['text']) and item['title'] not in reply['text']
    else:assert 'method' not in reply
    assert before==snapshot(c)


@pytest.mark.parametrize('text',['/my_follows invalid','/my_follows 0:0','/my_follows 1:-1','/my_follows 01:0','/my_follows 1:01','/my_follows 1:','/my_follows all 1:0 extra','/my_follows work tasks','/my_follows all 9223372036854775808:0','/my_follows all 1:9223372036854775808','/my_follows all ١:0'])
def test_strict_usage_does_not_retain_query_or_create_action(follows_env,text):
    env,*_=follows_env
    assert command(env,text,10)['text']==reads.USAGE
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(env[0],'SELECT * FROM '+table)


def test_sqlite_maximum_cursor_is_supported_and_inbound_pause_blocks(follows_env,monkeypatch):
    env,*_=follows_env
    assert keys(command(env,'/my_follows 9223372036854775807:9223372036854775807',10)['text'])
    monkeypatch.setenv('CSS_TELEGRAM_INBOUND_ENABLED','0')
    assert submit(env[3],update(11,text='/my_follows')).status_code==503


def test_private_groups_topics_other_senders_callbacks_and_duplicate_updates(follows_env):
    env,*_=follows_env;c=env[0];before=snapshot(c)
    for n,kind in enumerate(('group','topic','sender','callback'),10):
        packet=update(n,text='/my_follows')
        if kind=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif kind=='topic':packet['message']['message_thread_id']=7
        elif kind=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        else:packet={'update_id':n,'callback_query':{'id':'synthetic','from':{'id':101},'data':'/my_follows'}}
        assert 'method' not in submit(env[3],packet).json()
    packet=update(20,text='/my_follows');assert keys(submit(env[3],packet).json()['text'])
    assert 'method' not in submit(env[3],packet).json() and before==snapshot(c)


@pytest.mark.parametrize('category',['all','tasks'])
def test_composite_seek_pages_preserve_category_and_every_saved_row(follows_env,category):
    env,item,task=follows_env;c,users,*_=env
    expected={(item['id'],task['id'])}
    if category=='all':expected.add((item['id'],0))
    for i in range(9):
        task=work_tasks.create(c,users[0],item['id'],{'title':'Page task '+str(i),'expected_output':'StoredPrivateOutput','unit_id':item['unit_id']})
        work_updates.follow(c,users[0],item['id'],task['id']);expected.add((item['id'],task['id']))
    other=case(c,users[0],item['unit_id']);work_updates.follow(c,users[0],other['id'])
    if category=='all':expected.add((other['id'],0))
    query='/my_follows '+category;seen=[]
    for number in range(10,20):
        text=command(env,query,number)['text'];seen.extend(keys(text));assert reads.common.units(text)<=4096
        next_=re.search(r'Next page: (/my_follows '+category+r' [0-9]+:[0-9]+)',text)
        if not next_:break
        query=next_[1]
    assert set(seen)==expected and seen==sorted(expected,reverse=True)


def test_unicode_long_origin_and_control_links_keep_budget_and_continuation(follows_env,monkeypatch):
    env,item,task=follows_env;c,users,*_=env;grant(env,'work.follow',monkeypatch)
    origin='https://'+'a'*60+'.'+'b'*60+'.'+'c'*60+'.example12';assert len(origin)==200
    monkeypatch.setenv('CSS_BASE_URL',origin)
    expected={(item['id'],task['id']),(item['id'],0)}
    for i in range(7):
        selected=work_tasks.create(c,users[0],item['id'],{'title':'Unicode task '+str(i),'expected_output':'StoredPrivateOutput','unit_id':item['unit_id']})
        work_updates.follow(c,users[0],item['id'],selected['id']);expected.add((item['id'],selected['id']))
    c.execute('UPDATE work_case SET title=? WHERE id=?',('🌿'*300,item['id']));c.execute('UPDATE work_task SET title=? WHERE case_id=?',('🌼'*300,item['id']));c.commit()
    query='/my_follows all';seen=[]
    for number in range(10,20):
        text=command(env,query,number)['text'];assert reads.common.units(text)<=4096
        found=keys(text);assert found and '/account/telegram/discussion-follow/change?case_id=' in text
        seen.extend(found);next_=re.search(r'Next page: (/my_follows all [0-9]+:[0-9]+)',text)
        if not next_:break
        query=next_[1]
    assert seen==sorted(expected,reverse=True)


def test_visibility_sql_filters_precede_bounded_native_scan(follows_env,monkeypatch):
    env,item,task=follows_env;c,users,*_=env
    for i in range(3):
        hidden=case(c,users[3],item['unit_id'])
        c.execute('INSERT INTO work_follow VALUES (?,?,NULL,?)',(hidden['id'],users[0]['id'],links.stamp(NOW)))
        c.commit()
    c.commit();monkeypatch.setattr(reads,'SCAN_LIMIT',2)
    text=command(env,'/my_follows',10)['text']
    assert keys(text)==[(item['id'],task['id']),(item['id'],0)]


def test_bounded_scan_continues_without_claiming_globally_empty(follows_env,monkeypatch):
    env,item,task=follows_env;c,users,*_=env
    selected=work_tasks.create(c,users[0],item['id'],{'title':'Third saved follow','expected_output':'StoredPrivateOutput','unit_id':item['unit_id']})
    work_updates.follow(c,users[0],item['id'],selected['id'])
    assert reads.SCAN_LIMIT==200;monkeypatch.setattr(reads,'SCAN_LIMIT',2)
    calls=[]
    def denied(*args):calls.append(args[2:]);raise ValueError('Synthetic current-source revocation')
    monkeypatch.setattr(reads,'detail',denied)
    text=command(env,'/my_follows tasks',10)['text']
    # Task-only has exactly two candidates; work-wide remains only in all.
    assert len(calls)==2 and 'More source candidates remain' not in text
    calls.clear();text=command(env,'/my_follows all',11)['text']
    assert len(calls)==2 and 'More source candidates remain. Continue: /my_follows all ' in text


def test_live_renderer_connection_never_reads_discussion_or_submission_columns(follows_env):
    env,item,task=follows_env;c,users,*_=env;clean=bot.normalize(update(10,text='/my_follows'))
    def authorize(op,table,column,*_):
        if op==sqlite3.SQLITE_READ and (table in ('work_comment','work_comment_revision','work_notice','work_comment_read','work_mention') or (table=='work_task' and column in ('submission','expected_output'))):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    c.set_authorizer(authorize)
    try:
        with transaction(c):text=reads.render(c,clean,bot.transport.config(),NOW)
    finally:c.set_authorizer(None)
    assert keys(text)==[(item['id'],task['id']),(item['id'],0)]
    with pytest.raises(RuntimeError,match='intake transaction'):reads.render(c,clean,bot.transport.config(),NOW)


@pytest.mark.parametrize('guard',['write_scope','write_pilot'])
def test_control_links_require_current_separate_write_scope_and_pilot(follows_env,monkeypatch,guard):
    env,item,task=follows_env;c,users,*_=env;grant(env,'work.follow',monkeypatch)
    before=snapshot(c);text=command(env,'/my_follows',10)['text']
    assert '/account/telegram/discussion-follow/change?case_id='+str(item['id'])+'&task_id='+str(task['id']) in text
    assert 'first send /discussion_follow' in text and before==snapshot(c)
    if guard=='write_scope':c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),'work.follow'));c.commit()
    else:monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOW_ENABLED','0')
    text=command(env,'/my_follows',11)['text'];assert keys(text) and '/discussion_follow' not in text and 'Follow controls:' not in text


def test_link_requires_independent_read_scope_and_work_read_and_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking;_,raw,code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOWS_READ_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[reads.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',reads.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOWS_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_terminal_discussions_remain_readable_without_write_or_inbox_consent(follows_env):
    env,item,task=follows_env;c,users,*_=env
    c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.execute("UPDATE work_task SET status='done' WHERE id=?",(task['id'],));c.commit()
    before=snapshot(c);text=command(env,'/my_follows',10)['text']
    assert keys(text)==[(item['id'],task['id']),(item['id'],0)] and before==snapshot(c)
    for scope in ('work.follow','work.updates.read','work.updates.acknowledge'):assert not links.authorized(c,users[0]['id'],scope)


def test_each_list_refreshes_native_follow_rows_and_current_titles(follows_env):
    env,item,task=follows_env;c,users,*_=env
    assert keys(command(env,'/my_follows',10)['text'])==[(item['id'],task['id']),(item['id'],0)]
    c.execute('UPDATE work_case SET title=? WHERE id=?',('Current work title',item['id']))
    c.execute('UPDATE work_task SET title=? WHERE id=?',('Current task title',task['id']));c.commit()
    text=command(env,'/my_follows',11)['text'];assert 'Current work title' in text and 'Current task title' in text
    work_updates.follow(c,users[0],item['id'],task['id'],enabled=False)
    assert keys(command(env,'/my_follows',12)['text'])==[(item['id'],0)]


def test_legacy_cross_work_task_reference_is_not_projected(follows_env):
    env,item,task=follows_env;c,users,*_=env;other=case(c,users[0],item['unit_id'])
    c.execute('INSERT INTO work_follow VALUES (?,?,?,?)',(other['id'],users[0]['id'],task['id'],links.stamp(NOW)));c.commit()
    before=snapshot(c);text=command(env,'/my_follows',10)['text']
    assert keys(text)==[(item['id'],task['id']),(item['id'],0)] and before==snapshot(c)
