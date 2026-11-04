"""Private current comment views preserve scope, revision consistency and read state."""
import re
import sqlite3

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_read as reader
import work_discussion as discussion
import work_updates
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_comment_manage import snapshot


@pytest.fixture
def read_env(deadline_env,monkeypatch):
    grant(deadline_env[0],reader.ACTION,monkeypatch)
    return deadline_env


@pytest.fixture(params=[True,False])
def thread_env(read_env,request):
    env,item,task=read_env;c,users,*_=env;target=task['id'] if request.param else None
    work_updates.follow(c,users[0],item['id'],target)
    cid=discussion.post(c,users[3],item['id'],'StoredSelectedText needle',task_id=target)
    return read_env,cid,target


def ask(state,kind='/discussion_thread',number=10,comment_id=None,extra='',case_id=None,task_id='selected'):
    source,cid,target=state;env,item,task=source
    q={'case_id':item['id'] if case_id is None else case_id,'task_id':target if task_id=='selected' else task_id}
    text=reader.command(q,cid if comment_id is None else comment_id,kind)+((' '+extra) if extra else '')
    return command(env,text,number)


def reply_ids(text):return [int(v) for v in re.findall(r'(?:^|\n)Reply ([0-9]+) · Revision',text)]


def test_selected_direct_replies_and_nested_parent_navigation_are_exact_and_read_only(thread_env):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    a=discussion.post(c,users[3],item['id'],'DirectOneText',task_id=target,parent_id=cid)
    b=discussion.post(c,users[3],item['id'],'DirectTwoText',task_id=target,parent_id=cid)
    child=discussion.post(c,users[3],item['id'],'NestedChildText',task_id=target,parent_id=a)
    discussion.post(c,users[3],item['id'],'UnrelatedTopLevelText',task_id=target)
    before=snapshot(c);text=ask(thread_env)['text']
    assert 'StoredSelectedText' in text and reply_ids(text)==[b,a]
    assert 'NestedChildText' not in text and 'UnrelatedTopLevelText' not in text
    assert 'Read message: /discussion_message ' in text and 'Replies: /discussion_thread ' in text
    assert users[3]['username'] not in text and 'marks nothing read' in text
    nested=ask(thread_env,number=11,comment_id=a)['text']
    assert 'DirectOneText' in nested and reply_ids(nested)==[child] and 'DirectTwoText' not in nested and 'StoredSelectedText' not in nested
    assert 'Parent: '+reader.command({'case_id':item['id'],'task_id':target},cid) in nested
    assert ('&task_id='+str(task['id']) in text)==(target is not None)
    assert before==snapshot(c)
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    for table,column in (('telegram_update','payload_json'),('telegram_delivery','projection_json')):
        for row in rows(c,'SELECT '+column+' FROM '+table):
            assert all(marker not in (row[column] or '') for marker in ('StoredSelectedText','DirectOneText','discussion_read_query'))


def test_all_current_message_parts_are_complete_bounded_and_control_safe(thread_env):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    body=('Line one\n'+('🌿'*1000)+'\x00'+('x'*1800)+'\u202e'+('y'*1400))[:3999]+'Z'
    discussion.edit(c,users[3],item['id'],target,cid,1,body)
    before=snapshot(c);text=ask(thread_env,'/discussion_message')['text'];parts=[]
    for number in range(11,20):
        assert reader.common.units(text)<=4096 and '\x00' not in text and '\u202e' not in text
        assert 'Revision 2' in text
        content=text.split('Text (current part):\n',1)[1].split('\nEnd of message part.',1)[0]
        assert len(content)<=reader.PART_SIZE;parts.append(content)
        next_=re.search(r'Next part: (.*)',text)
        if not next_:break
        assert 'part:2:' in next_[1];text=command(env,next_[1],number)['text']
    expected=body.replace('\x00',' ').replace('\u202e',' ')
    assert ''.join(parts)==expected and len(parts)==5 and before==snapshot(c)
    assert 'Previous part:' in text and 'Part 5/5' in text


def test_changed_revision_refuses_old_parts_before_any_body_query(thread_env):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    assert 'StoredSelectedText' in ask(thread_env,'/discussion_message')['text']
    discussion.edit(c,users[3],item['id'],target,cid,1,'CurrentReplacement '+('x'*1900))
    before=snapshot(c)
    def deny_body(op,table,column,*_):
        return sqlite3.SQLITE_DENY if op==sqlite3.SQLITE_READ and table=='work_comment_revision' and column=='body' else sqlite3.SQLITE_OK
    c.set_authorizer(deny_body)
    try:text=ask(thread_env,'/discussion_message',number=11,extra='part:1:2')['text']
    finally:c.set_authorizer(None)
    assert 'This message changed' in text and 'CurrentReplacement' not in text and 'StoredSelectedText' not in text
    text=ask(thread_env,'/discussion_message',number=12)['text']
    assert 'CurrentReplacement' in text and 'Revision 2' in text and before==snapshot(c)


def test_thread_refreshes_only_current_root_and_reply_revisions(thread_env):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    reply=discussion.post(c,users[3],item['id'],'OldReplyText',task_id=target,parent_id=cid)
    discussion.edit(c,users[3],item['id'],target,cid,1,'CurrentRootText')
    discussion.edit(c,users[3],item['id'],target,reply,1,'CurrentReplyText')
    text=ask(thread_env)['text']
    assert 'CurrentRootText' in text and 'CurrentReplyText' in text
    assert 'OldReplyText' not in text and 'StoredSelectedText' not in text and 'Revision 2' in text


@pytest.mark.parametrize('target',['hidden','missing_work','missing_comment','wrong_thread','cross_work_task'])
def test_source_and_selected_message_denials_precede_body_sql(read_env,target):
    env,item,task=read_env;c,users,*_=env
    root=discussion.post(c,users[3],item['id'],'SelectedTaskText',task_id=task['id'])
    other=case(c,users[3] if target=='hidden' else users[0],item['unit_id'])
    other_root=discussion.post(c,users[3] if target=='hidden' else users[0],other['id'],'OtherSourceText')
    chosen_case=other['id'] if target in ('hidden','cross_work_task') else (999999 if target=='missing_work' else item['id'])
    chosen_task=task['id'] if target in ('cross_work_task','missing_comment') else None
    chosen_comment=other_root if target=='hidden' else (999999 if target=='missing_comment' else root)
    def deny_body(op,table,column,*_):
        return sqlite3.SQLITE_DENY if op==sqlite3.SQLITE_READ and table=='work_comment_revision' and column=='body' else sqlite3.SQLITE_OK
    c.set_authorizer(deny_body)
    try:
        for n,kind in enumerate(('/discussion_thread','/discussion_message'),10):
            assert ask((read_env,root,task['id']),kind,number=n,comment_id=chosen_comment,case_id=chosen_case,task_id=chosen_task)['text']==reader.DENIED
    finally:c.set_authorizer(None)


@pytest.mark.parametrize('text',['/discussion_thread','/discussion_thread 1 work','/discussion_thread 0 work 1','/discussion_thread 1 0 1',
    '/discussion_thread 1 all 1','/discussion_thread 1 work 0','/discussion_thread 1 work 01','/discussion_thread 1 work 1 before:0',
    '/discussion_thread 1 work 1 part:1:1','/discussion_thread 1 work 1 extra extra','/discussion_message 1 work 1 before:2',
    '/discussion_message 1 work 1 part:0:1','/discussion_message 1 work 1 part:1:0','/discussion_message 1 work 1 part:1:6',
    '/discussion_browse','/discussion_browse 1','/discussion_browse 1 work before:0','/discussion_browse 1 work before:01',
    '/discussion_browse 1 work 2','/discussion_browse 1 all','/discussion_browse 1 work before:2 extra',
    '/discussion_message 1 work 1 part:01:1','/discussion_message 9223372036854775808 work 1','/discussion_message 1 work 1 part:9223372036854775808:1'])
def test_strict_source_cursor_and_revision_part_grammar(read_env,text):
    env,*_=read_env;before=snapshot(env[0])
    assert command(env,text,10)['text']==reader.USAGE and before==snapshot(env[0])


def test_unavailable_part_is_not_a_historical_revision_request(thread_env):
    source,cid,target=thread_env
    text=ask(thread_env,'/discussion_message',extra='part:1:5')['text']
    assert 'That part is unavailable' in text and 'StoredSelectedText' not in text


def test_existing_search_and_metadata_grants_do_not_grant_thread_or_full_message_reading(deadline_env,monkeypatch):
    env,item,task=deadline_env;c,users,*_=env
    for scope in ('work.discussion.search','work.updates.read','work.follows.read','work.follow','work.comment'):grant(env,scope,monkeypatch)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED','1')
    cid=discussion.post(c,users[3],item['id'],'needle SelectedPrivateText')
    before=snapshot(c)
    for n,kind in enumerate(reader.COMMANDS,10):assert 'method' not in ask((deadline_env,cid,None),kind,number=n)
    text=command(env,'/discussion_search '+str(item['id'])+' work needle',14)['text']
    assert 'SelectedPrivateText' in text and 'View thread:' not in text and before==snapshot(c)


@pytest.mark.parametrize('guard',['grant','pilot'])
def test_search_thread_links_require_current_separate_read_grant_and_pilot(thread_env,monkeypatch,guard):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env;grant(env,'work.discussion.search',monkeypatch)
    search='/discussion_search '+str(item['id'])+' '+(str(target) if target is not None else 'work')+' needle'
    text=command(env,search,10)['text'];assert 'View thread: '+reader.command({'case_id':item['id'],'task_id':target},cid) in text
    if guard=='grant':c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),reader.ACTION));c.commit()
    else:monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED','0')
    assert 'View thread:' not in command(env,search,11)['text'] and 'method' not in ask(thread_env,number=12)


@pytest.mark.parametrize('change',['work_access','document_access','work_module','documents_module','work.read',reader.ACTION,'pilot','disconnect','restore','account','bot','direct','delivery'])
def test_current_source_context_and_consent_guards_on_thread_and_message(read_env,change,monkeypatch):
    env,item,task=read_env;c,users,path,_,payload=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    cid=discussion.post(c,users[3],item['id'],'CurrentPrivateText');state=(read_env,cid,None)
    assert 'CurrentPrivateText' in ask(state)['text']
    if change=='work_access':c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change in ('work_module','documents_module'):st.set_setting(c,('work' if change=='work_module' else 'documents')+'.enabled','0')
    elif change in ('work.read',reader.ACTION):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),change));c.commit()
    elif change=='pilot':monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    else:monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
    before=snapshot(c)
    for n,kind in enumerate(reader.COMMANDS,11):
        reply=ask(state,kind,number=n)
        if change in ('work_access','document_access'):assert reply['text']==reader.DENIED
        else:assert 'method' not in reply
    assert before==snapshot(c)


def test_reply_seek_and_unicode_max_origin_budgets_keep_all_direct_replies(thread_env,monkeypatch):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    origin='https://'+'a'*60+'.'+'b'*60+'.'+'c'*60+'.example12';assert len(origin)==200
    monkeypatch.setenv('CSS_BASE_URL',origin)
    c.execute('UPDATE work_case SET title=? WHERE id=?',('🌿'*300,item['id']));c.execute('UPDATE work_task SET title=? WHERE id=?',('🌼'*300,task['id']));c.commit()
    discussion.edit(c,users[3],item['id'],target,cid,1,'🌻'*1000)
    expected=[discussion.post(c,users[3],item['id'],'🌺'*1000,task_id=target,parent_id=cid) for _ in range(8)]
    text=ask(thread_env)['text'];seen=[]
    for number in range(11,25):
        assert reader.common.units(text)<=4096;found=reply_ids(text);assert found;seen.extend(found)
        next_=re.search(r'Older direct replies: (.*)',text)
        if not next_:break
        text=command(env,next_[1],number)['text']
    assert seen==list(reversed(expected))
    assert reader.common.units(ask(thread_env,'/discussion_message',number=25)['text'])<=4096
    grant(env,'work.discussion.search',monkeypatch)
    text=command(env,'/discussion_search '+str(item['id'])+' '+(str(target) if target is not None else 'work')+' 🌺🌺',26)['text'];seen=[]
    for number in range(27,40):
        assert reader.common.units(text)<=4096 and 'View thread:' in text;seen.extend(int(v) for v in re.findall(r'Reply ([0-9]+) · Revision',text))
        next_=re.search(r'Next page: (.*)',text)
        if not next_:break
        text=command(env,next_[1],number)['text']
    assert seen==list(reversed(expected))


def test_actual_render_connection_reads_no_authors_submissions_or_notice_follow_state(thread_env):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    def authorize(op,table,column,*_):
        if op==sqlite3.SQLITE_READ and (table in ('work_notice','work_comment_read','work_mention','work_follow') or
            (table=='work_comment' and column=='author_id') or (table=='work_task' and column in ('submission','expected_output'))):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    c.set_authorizer(authorize)
    try:
        for kind in reader.COMMANDS:
            clean=bot.normalize(update(10,text=reader.command({'case_id':item['id'],'task_id':target},cid,kind)))
            with transaction(c):text=reader.render(c,clean,bot.transport.config(),NOW)
            assert 'StoredSelectedText' in text
    finally:c.set_authorizer(None)
    with pytest.raises(RuntimeError,match='intake transaction'):reader.render(c,clean,bot.transport.config(),NOW)


def test_legacy_cross_work_reply_and_parent_references_do_not_expand_scope(read_env):
    env,item,task=read_env;c,users,*_=env
    root=discussion.post(c,users[3],item['id'],'RootVisibleText')
    other=case(c,users[0],item['unit_id'])
    cross=c.execute('INSERT INTO work_comment(case_id,task_id,parent_id,author_id,created_at) VALUES (?,NULL,?,?,?)',
                    (other['id'],root,users[0]['id'],links.stamp(NOW))).lastrowid
    c.execute('INSERT INTO work_comment_revision VALUES (?,1,?,?)',(cross,'CrossSourceLegacyText',links.stamp(NOW)));c.commit()
    text=ask((read_env,root,None))['text'];assert 'CrossSourceLegacyText' not in text and not reply_ids(text)
    text=ask((read_env,cross,None),case_id=other['id'],number=11)['text']
    assert 'CrossSourceLegacyText' in text and 'Parent:' not in text and 'RootVisibleText' not in text


def test_foreign_group_topic_callback_and_duplicate_update_paths_do_not_disclose(thread_env):
    source,cid,target=thread_env;env,item,task=source;c=env[0];before=snapshot(c)
    text=reader.command({'case_id':item['id'],'task_id':target},cid)
    for number,kind in enumerate(('group','topic','sender','callback'),10):
        packet=update(number,text=text)
        if kind=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif kind=='topic':packet['message']['message_thread_id']=7
        elif kind=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        else:packet={'update_id':number,'callback_query':{'id':'synthetic','from':{'id':101},'data':'/discussion_thread'}}
        assert 'method' not in submit(env[3],packet).json()
    packet=update(20,text=text);assert 'StoredSelectedText' in submit(env[3],packet).json()['text']
    assert 'method' not in submit(env[3],packet).json() and before==snapshot(c)


def test_independent_link_scope_and_current_read_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking;_,raw,code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[reader.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',reader.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_terminal_source_and_maximum_seek_remain_readable(thread_env):
    source,cid,target=thread_env;env,item,task=source;c,*_=env
    c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.execute("UPDATE work_task SET status='done' WHERE id=?",(task['id'],));c.commit()
    assert 'StoredSelectedText' in ask(thread_env,extra='before:9223372036854775807')['text']
    assert 'StoredSelectedText' in ask(thread_env,'/discussion_message',number=11)['text']


def test_browse_seek_pages_current_roots_only_and_navigation_are_read_only(thread_env,monkeypatch):
    source,cid,target=thread_env;env,item,task=source;c,users,*_=env
    origin='https://'+'a'*60+'.'+'b'*60+'.'+'c'*60+'.example12'
    monkeypatch.setenv('CSS_BASE_URL',origin)
    grant(env,'tasks.reply' if target is not None else 'work.reply',monkeypatch)
    c.execute('UPDATE work_case SET title=? WHERE id=?',('🌿'*300,item['id']));c.commit()
    expected=[cid]+[discussion.post(c,users[3],item['id'],'🌺'*1000,task_id=target) for _ in range(8)]
    discussion.edit(c,users[3],item['id'],target,cid,1,'CurrentBrowseRoot')
    discussion.post(c,users[3],item['id'],'ExcludedReply',task_id=target,parent_id=cid)
    discussion.post(c,users[3],item['id'],'ExcludedScope',task_id=None if target else task['id'])
    before=snapshot(c);text=ask(thread_env,'/discussion_browse')['text'];seen=[]
    for n in range(11,30):
        assert reader.common.units(text)<=4096
        assert 'ExcludedReply' not in text and 'ExcludedScope' not in text and 'StoredSelectedText' not in text
        ids=[int(v) for v in re.findall(r'(?:^|\n)Comment ([0-9]+) · Revision',text)]
        assert ids and 'View thread:' in text and 'Read message:' in text and 'Reply form:' in text
        seen.extend(ids)
        next_=re.search(r'Older comments: (.*)',text)
        if not next_:break
        text=command(env,next_[1],n)['text']
    assert seen==list(reversed(expected)) and 'CurrentBrowseRoot' in text and 'Revision 2' in text
    empty=command(env,reader.browse_command({'case_id':item['id'],'task_id':target})+' before:'+str(cid),30)['text']
    assert 'No current top-level comments' in empty and before==snapshot(c)
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    for table,column in (('telegram_update','payload_json'),('telegram_delivery','projection_json')):
        for row in rows(c,'SELECT '+column+' FROM '+table):
            assert 'CurrentBrowseRoot' not in (row[column] or '') and 'discussion_read_query' not in (row[column] or '')


@pytest.mark.parametrize('target',['hidden','missing_work','cross_work_task'])
def test_browse_checks_source_before_reading_any_body(read_env,target):
    env,item,task=read_env;c,users,*_=env
    other=case(c,users[3],item['unit_id'])
    query={'case_id':999999 if target=='missing_work' else other['id'],'task_id':task['id'] if target=='cross_work_task' else None}
    def deny_body(op,table,column,*_):
        return sqlite3.SQLITE_DENY if op==sqlite3.SQLITE_READ and table=='work_comment_revision' and column=='body' else sqlite3.SQLITE_OK
    c.set_authorizer(deny_body)
    try:assert command(env,reader.browse_command(query),10)['text']==reader.DENIED
    finally:c.set_authorizer(None)
