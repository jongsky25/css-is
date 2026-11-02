"""Own unread notice metadata, exact source visibility, no bodies or read-state mutations."""
import re

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_updates as inbox
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_comment_manage import snapshot


@pytest.fixture
def inbox_env(deadline_env,monkeypatch):
    grant(deadline_env[0],inbox.ACTION,monkeypatch)
    return deadline_env


def seed(state,reason='mention',task_level=True,body='StoredPrivateNoticeBody'):
    env,item,task=state;c,users,*_=env;target=task['id'] if task_level else None
    parent=discussion.post(c,users[0],item['id'],'StoredPrivateParent',task_id=target) if reason=='reply' else None
    if reason=='following':work_updates.follow(c,users[0],item['id'],task_id=target)
    identifier=discussion.post(c,users[3],item['id'],body,task_id=target,parent_id=parent,mentions=[users[0]['id']] if reason=='mention' else [])
    notice=rows(c,'SELECT * FROM work_notice WHERE comment_id=? AND user_id=?',(identifier,users[0]['id']))[0]
    return notice


def ids(text):return [int(v) for v in re.findall(r'Update ([0-9]+) ·',text)]


@pytest.mark.parametrize('reason',['mention','reply','following'])
@pytest.mark.parametrize('task_level',[True,False])
def test_own_unread_list_detail_source_links_are_metadata_only_and_mark_nothing_read(inbox_env,reason,task_level):
    env,item,task=inbox_env;c,users,*_=env
    notice=seed(inbox_env,reason,task_level);before=snapshot(c)
    text=command(env,'/my_updates',10)['text']
    assert ids(text)==[notice['id']] and item['title'] in text
    assert '/update_status '+str(notice['id']) in text and '/discussion?focus='+str(notice['comment_id']) in text
    assert ('&task_id='+str(task['id']) in text)==task_level
    text=command(env,'/update_status '+str(notice['id']),11)['text']
    assert 'Status: unread' in text and 'Notice revision 1 · Current revision 1' in text
    assert 'StoredPrivate' not in text and users[3]['username'] not in text
    assert 'marks nothing read' in text and snapshot(c)==before
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    assert not rows(c,"SELECT * FROM telegram_update WHERE payload_json LIKE '%updates_query%'")
    for row in rows(c,'SELECT projection_json FROM telegram_delivery'):assert 'StoredPrivate' not in row['projection_json'] and item['title'] not in row['projection_json']


def test_filters_show_only_own_unread_notice_categories(inbox_env):
    env,*_=inbox_env
    notices={r:seed(inbox_env,r) for r in ('mention','reply','following')}
    for n,(category,reason) in enumerate((('mentions','mention'),('replies','reply'),('following','following')),10):
        assert ids(command(env,'/my_updates '+category,n)['text'])==[notices[reason]['id']]
    assert set(ids(command(env,'/my_updates all',13)['text']))=={n['id'] for n in notices.values()}


def test_source_read_state_and_current_revision_remain_native(inbox_env):
    env,item,task=inbox_env;c,users,*_=env
    notice=seed(inbox_env)
    discussion.edit(c,users[3],item['id'],task['id'],notice['comment_id'],1,'StoredPrivateEditedBody')
    text=command(env,'/update_status '+str(notice['id']),10)['text']
    assert 'Notice revision 1 · Current revision 2' in text and 'Status: unread' in text
    work_updates.mark_read(c,users[0],item['id'],task['id'],[(notice['comment_id'],1)])
    before=snapshot(c)
    assert not ids(command(env,'/my_updates',11)['text'])
    text=command(env,'/update_status '+str(notice['id']),12)['text']
    assert 'already read' in text and 'Current revision 2' in text and snapshot(c)==before


def test_another_recipients_notice_is_never_visible_even_to_case_lead(inbox_env):
    env,item,task=inbox_env;c,users,*_=env
    identifier=discussion.post(c,users[0],item['id'],'StoredPrivateOtherRecipient',mentions=[users[3]['id']])
    foreign=rows(c,'SELECT id FROM work_notice WHERE comment_id=?',(identifier,))[0]['id']
    assert not ids(command(env,'/my_updates',10)['text'])
    assert command(env,'/update_status '+str(foreign),11)['text']==command(env,'/update_status 999999',12)['text']==inbox.DENIED


@pytest.mark.parametrize('change',['work_access','document_access','work_module','documents_module','read_grant','inbox_grant','flag','disconnect','restore','bot','direct'])
def test_current_source_grants_modules_and_context_rechecked(inbox_env,monkeypatch,change):
    env,item,task=inbox_env;c,users,path,_,payload=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    notice=seed(inbox_env)
    assert ids(command(env,'/my_updates',10)['text'])==[notice['id']]
    if change=='work_access':
        c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change in ('work_module','documents_module'):st.set_setting(c,('work' if change=='work_module' else 'documents')+'.enabled','0')
    elif change in ('read_grant','inbox_grant'):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),'work.read' if change=='read_grant' else inbox.ACTION));c.commit()
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_READ_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    else:monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    before=snapshot(c)
    for n,cmd in enumerate(('/my_updates','/update_status '+str(notice['id'])),11):
        response=command(env,cmd,n)
        if change in ('work_access','document_access'):
            assert ids(response['text'])==[] if cmd=='/my_updates' else response['text']==inbox.DENIED
        else:assert 'method' not in response
    assert snapshot(c)==before


@pytest.mark.parametrize('text',['/my_updates invalid','/my_updates mentions 0','/my_updates -1','/my_updates 1 2','/my_updates all 9223372036854775808','/my_updates all 1 extra','/update_status','/update_status 1 2','/update_status true','/update_status 0'])
def test_strict_usage_has_no_retained_query(inbox_env,text):
    env,*_=inbox_env
    assert command(env,text,10)['text']==inbox.USAGE
    assert not rows(env[0],"SELECT * FROM telegram_update WHERE payload_json LIKE '%updates_query%'")


def test_paging_unicode_and_source_visibility_without_hidden_counts(inbox_env,monkeypatch):
    env,item,task=inbox_env;c,users,*_=env
    c.execute('UPDATE work_case SET title=? WHERE id=?',('📌'*110,item['id']))
    c.execute('UPDATE work_task SET title=? WHERE id=?',('🔒'*110,task['id']));c.commit()
    expected={seed(inbox_env)['id'] for _ in range(9)}
    seen=[];query='/my_updates mentions'
    for n in range(10,20):
        text=command(env,query,n)['text'];seen+=ids(text)
        assert inbox.common.units(text)<=4096 and 'StoredPrivate' not in text
        next_=re.search(r'/my_updates mentions ([0-9]+)',text)
        if not next_:break
        query=next_[0]
    assert set(seen)==expected and len(seen)==len(expected)


def test_bounded_scan_continuation_is_honest_and_seek_safe(inbox_env,monkeypatch):
    env,*_=inbox_env
    for _ in range(5):seed(inbox_env)
    monkeypatch.setattr(inbox,'SCAN_LIMIT',2);monkeypatch.setattr(inbox,'BATCH_SIZE',1)
    text=command(env,'/my_updates',10)['text'];assert len(ids(text))==2 and 'Continue: /my_updates all ' in text
    cursor=re.search(r'Continue: (/my_updates all [0-9]+)',text)[1]
    assert not set(ids(text)) & set(ids(command(env,cursor,11)['text']))


def test_groups_topics_duplicate_and_direct_never_queue_pushes(inbox_env,monkeypatch):
    env,*_=inbox_env;c=env[0];seed(inbox_env)
    packet=update(10,text='/my_updates');packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    packet=update(11,text='/my_updates');packet['message']['message_thread_id']=4
    assert 'method' not in submit(env[3],packet).json()
    packet=update(12,text='/my_updates');assert 'My unread' in submit(env[3],packet).json()['text']
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct');assert 'method' not in command(env,'/my_updates',13)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_transaction_required_and_no_message_body_column_is_read(inbox_env):
    import sqlite3
    env,item,task=inbox_env;c,users,*_=env;notice=seed(inbox_env)
    clean=bot.normalize(update(10,text='/my_updates'))
    with pytest.raises(RuntimeError):inbox.render(c,clean,bot.transport.config(),NOW)
    def authorize(action,arg1,arg2,*args):
        if action==sqlite3.SQLITE_READ and arg1=='work_comment_revision' and arg2=='body':return sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_READ and arg1=='work_task' and arg2 in ('submission','expected_output'):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    c.set_authorizer(authorize)
    try:
        with transaction(c):assert ids(inbox.render(c,clean,bot.transport.config(),NOW))==[notice['id']]
        clean=bot.normalize(update(12,text='/update_status '+str(notice['id'])))
        with transaction(c):assert 'Comment '+str(notice['comment_id']) in inbox.render(c,clean,bot.transport.config(),NOW)
    finally:c.set_authorizer(None)


def test_link_requires_work_read_and_current_inbox_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking;ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_READ_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[inbox.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',inbox.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


@pytest.mark.parametrize('state',['done','cancelled','completed'])
def test_notice_reads_preserve_native_terminal_discussion_visibility(inbox_env,state):
    env,item,task=inbox_env;c,*_=env;notice=seed(inbox_env)
    if state=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],))
    else:c.execute('UPDATE work_task SET status=? WHERE id=?',(state,task['id']))
    c.commit();before=snapshot(c)
    assert ids(command(env,'/my_updates',10)['text'])==[notice['id']]
    assert 'Update '+str(notice['id']) in command(env,'/update_status '+str(notice['id']),11)['text']
    assert snapshot(c)==before


def test_current_origin_limit_prevents_replies(inbox_env,monkeypatch):
    env,*_=inbox_env;seed(inbox_env)
    monkeypatch.setenv('CSS_BASE_URL','https://'+'a'*200+'.invalid')
    assert 'method' not in command(env,'/my_updates',10)


def test_only_read_consent_exposes_no_post_reply_edit_or_mention_controls(inbox_env):
    env,*_=inbox_env;c=env[0]
    text=command(env,'/menu',10)['text']
    assert '/my_updates' in text
    for command_ in ('/work_comment','/task_comment','/work_reply','/task_reply','/work_comment_edit','/task_comment_edit'):
        assert command_ not in text
    assert not rows(c,'SELECT * FROM telegram_operation')
