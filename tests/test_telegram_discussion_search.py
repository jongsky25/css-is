"""Private current-thread excerpts require independent consent and never mutate source."""
import re
import sqlite3

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_search as search
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
def search_env(deadline_env,monkeypatch):
    grant(deadline_env[0],search.ACTION,monkeypatch)
    return deadline_env


def ask(state,term='needle',task_id=None,number=10,before=None,case_id=None):
    env,item,task=state
    return command(env,'/discussion_search '+str(item['id'] if case_id is None else case_id)+' '+('work' if task_id is None else str(task_id))
                   +(' before:'+str(before) if before is not None else '')+' '+term,number)


def ids(text):return [int(i) for i in re.findall(r'(?:Comment|Reply) ([0-9]+) · Revision',text)]


@pytest.mark.parametrize('task_level',[True,False])
def test_exact_thread_current_comment_and_reply_excerpts_are_read_only(search_env,task_level):
    env,item,task=search_env;c,users,*_=env;target=task['id'] if task_level else None
    work_updates.follow(c,users[0],item['id'],target)
    parent=discussion.post(c,users[3],item['id'],'Current NEEDLE parent text',task_id=target,mentions=[users[0]['id']])
    reply=discussion.post(c,users[3],item['id'],'Current needle reply text',task_id=target,parent_id=parent)
    other=discussion.post(c,users[3],item['id'],'OtherThreadNeedle',task_id=None if task_level else task['id'])
    before=snapshot(c);text=ask(search_env,task_id=target)['text']
    assert ids(text)==[reply,parent] and other not in ids(text)
    assert 'Reply '+str(reply)+' · Revision 1' in text and 'Current NEEDLE parent text' in text and 'Current needle reply text' in text
    assert 'OtherThreadNeedle' not in text and users[3]['username'] not in text
    assert ('&task_id='+str(task['id']) in text)==task_level
    assert '/discussion?focus='+str(reply) in text and '#message-'+str(reply) in text
    assert 'Search marks nothing read' in text and before==snapshot(c)
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    for table,column in (('telegram_update','payload_json'),('telegram_delivery','projection_json')):
        for row in rows(c,'SELECT '+column+' FROM '+table):
            value=(row[column] or '').casefold()
            assert all(marker not in value for marker in ('needle','discussion_search_query','parent text','reply text'))


def test_only_latest_revision_matches_and_results_refresh_after_native_edit(search_env):
    env,item,task=search_env;c,users,*_=env
    cid=discussion.post(c,users[3],item['id'],'OldOnlyNeedle private old revision')
    assert ids(ask(search_env,'OldOnlyNeedle')['text'])==[cid]
    discussion.edit(c,users[3],item['id'],None,cid,1,'NewOnlyNeedle current replacement')
    before=snapshot(c);old=ask(search_env,'OldOnlyNeedle',number=11)['text'];new=ask(search_env,'NewOnlyNeedle',number=12)['text']
    assert not ids(old) and 'private old revision' not in old
    assert ids(new)==[cid] and 'Revision 2' in new and 'current replacement' in new and before==snapshot(c)


@pytest.mark.parametrize('term,body',[('STRASSE','Eine Straße in the current text'),('%_','Literal %_ tokens'),("' OR 1=1 --","Literal ' OR 1=1 -- string"),('ΣΣ','Greek σς text')])
def test_literal_unicode_casefold_and_sql_metacharacters(search_env,term,body):
    env,item,task=search_env;c,users,*_=env
    cid=discussion.post(c,users[3],item['id'],body)
    discussion.post(c,users[3],item['id'],'Unrelated private content must not match')
    text=ask(search_env,term)['text'];assert ids(text)==[cid] and body in text


def test_excerpt_window_is_bounded_near_late_unicode_expansion_match(search_env):
    env,item,task=search_env;c,users,*_=env
    body='DoNotCopyPrivatePrefix'+('x'*1200)+' Straße needle '+('y'*1200)+'DoNotCopyPrivateSuffix'
    cid=discussion.post(c,users[3],item['id'],body)
    text=ask(search_env,'STRASSE')['text'];assert ids(text)==[cid] and 'Straße needle' in text
    assert 'DoNotCopyPrivatePrefix' not in text and 'DoNotCopyPrivateSuffix' not in text
    excerpt=re.search(r'Excerpt: (.*)',text)[1];assert len(excerpt)<=search.EXCERPT_LIMIT+2 and excerpt.startswith('…') and excerpt.endswith('…')
    assert len(search.excerpt('x'*200+'Straße'+'y'*500,'STRASSE'))<=search.EXCERPT_LIMIT+2
    assert search.excerpt('no match here','absent')==''


@pytest.mark.parametrize('text',['/discussion_search','/discussion_search 1 work','/discussion_search 0 work needle','/discussion_search 01 work needle',
    '/discussion_search 1 0 needle','/discussion_search 1 -1 needle','/discussion_search 1 all needle','/discussion_search 1 work x',
    '/discussion_search 1 work '+'x'*81,'/discussion_search 1 work bad\tquery','/discussion_search 1 work bad\u202equery',
    '/discussion_search 1 work before:0 needle','/discussion_search 1 work before:01 needle','/discussion_search 1 work before:2',
    '/discussion_search 9223372036854775808 work needle','/discussion_search 1 9223372036854775808 needle'])
def test_strict_source_phrase_and_cursor_usage(search_env,text):
    env,*_=search_env;before=snapshot(env[0])
    assert command(env,text,10)['text']==search.USAGE and before==snapshot(env[0])


def test_metadata_inbox_follow_and_write_scopes_do_not_grant_discussion_text_search(deadline_env,monkeypatch):
    env,item,task=deadline_env;c,users,*_=env
    for scope in ('work.updates.read','work.follows.read','work.follow','work.comment'):grant(env,scope,monkeypatch)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_SEARCH_ENABLED','1')
    discussion.post(c,users[3],item['id'],'needle PrivateDiscussionBody')
    before=snapshot(c);assert 'method' not in ask(deadline_env) and before==snapshot(c)
    assert 'PrivateDiscussionBody' not in command(env,'/find needle',11)['text']


@pytest.mark.parametrize('target',['hidden','missing','cross_work_task'])
def test_native_scope_denial_precedes_any_body_query_and_has_neutral_response(search_env,target):
    env,item,task=search_env;c,users,*_=env
    other=case(c,users[3] if target=='hidden' else users[0],item['unit_id'])
    discussion.post(c,users[3] if target=='hidden' else users[0],other['id'],'needle HiddenText')
    query_case=999999 if target=='missing' else other['id'];query_task=task['id'] if target=='cross_work_task' else None
    def deny_body(op,table,column,*_):
        return sqlite3.SQLITE_DENY if op==sqlite3.SQLITE_READ and table=='work_comment_revision' and column=='body' else sqlite3.SQLITE_OK
    c.set_authorizer(deny_body)
    try:text=ask(search_env,case_id=query_case,task_id=query_task)['text']
    finally:c.set_authorizer(None)
    assert text==search.DENIED


@pytest.mark.parametrize('change',['work_access','document_access','work_module','documents_module','work.read',search.ACTION,'pilot','disconnect','restore','account','bot','direct','delivery'])
def test_current_source_and_private_consent_guards(search_env,change,monkeypatch):
    env,item,task=search_env;c,users,path,_,payload=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    cid=discussion.post(c,users[3],item['id'],'needle CurrentPrivateExcerpt')
    assert ids(ask(search_env)['text'])==[cid]
    if change=='work_access':c.execute('UPDATE work_case SET creator_id=?,lead_id=? WHERE id=?',(users[1]['id'],users[1]['id'],item['id']));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    elif change in ('work_module','documents_module'):st.set_setting(c,('work' if change=='work_module' else 'documents')+'.enabled','0')
    elif change in ('work.read',search.ACTION):c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),change));c.commit()
    elif change=='pilot':monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_SEARCH_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','987654321:OtherSyntheticToken_abcdefghijklmnopqrstuvwxyz')
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    else:monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
    before=snapshot(c);reply=ask(search_env,number=11)
    if change in ('work_access','document_access'):assert reply['text']==search.DENIED
    else:assert 'method' not in reply
    assert before==snapshot(c)


@pytest.mark.parametrize('task_level',[True,False])
def test_seek_pages_preserve_exact_scope_and_literal_query(search_env,task_level):
    env,item,task=search_env;c,users,*_=env;target=task['id'] if task_level else None;expected=[]
    for i in range(8):expected.append(discussion.post(c,users[3],item['id'],'Paging phrase '+str(i),task_id=target))
    text=ask(search_env,'Paging phrase',task_id=target)['text'];seen=[]
    for number in range(11,20):
        seen.extend(ids(text));assert search.common.units(text)<=4096
        next_=re.search(r'Next page: (.*)',text)
        if not next_:break
        assert (' '+str(target)+' before:' if target else ' work before:') in next_[1] and next_[1].endswith('Paging phrase')
        text=command(env,next_[1],number)['text']
    assert seen==list(reversed(expected))


def test_unicode_max_origin_reply_budget_keeps_continuation(search_env,monkeypatch):
    env,item,task=search_env;c,users,*_=env
    origin='https://'+'a'*60+'.'+'b'*60+'.'+'c'*60+'.example12';assert len(origin)==200
    monkeypatch.setenv('CSS_BASE_URL',origin)
    c.execute('UPDATE work_case SET title=? WHERE id=?',('🌿'*300,item['id']));c.execute('UPDATE work_task SET title=? WHERE id=?',('🌼'*300,task['id']));c.commit()
    expected=[discussion.post(c,users[3],item['id'],('🌻'*180)+' needle '+('🌻'*180),task_id=task['id']) for _ in range(7)]
    text=ask(search_env,task_id=task['id'])['text'];seen=[]
    for number in range(11,20):
        assert search.common.units(text)<=4096;seen.extend(ids(text));next_=re.search(r'Next page: (.*)',text)
        if not next_:break
        text=command(env,next_[1],number)['text']
    assert seen==list(reversed(expected))


def test_actual_renderer_fetches_only_bounded_excerpts_without_author_or_task_submission_fields(search_env):
    env,item,task=search_env;c,users,*_=env
    cid=discussion.post(c,users[3],item['id'],'needle CurrentExcerpt',task_id=task['id'])
    clean=bot.normalize(update(10,text='/discussion_search '+str(item['id'])+' '+str(task['id'])+' needle'))
    def authorize(op,table,column,*_):
        if op==sqlite3.SQLITE_READ and (table in ('work_notice','work_comment_read','work_mention','work_follow') or
            (table=='work_comment' and column=='author_id') or (table=='work_task' and column in ('submission','expected_output'))):return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    c.set_authorizer(authorize)
    try:
        with transaction(c):text=search.render(c,clean,bot.transport.config(),NOW)
    finally:c.set_authorizer(None)
    assert ids(text)==[cid]
    with transaction(c):matches=search.page(c,users[0],clean['discussion_search_query'])[2]
    assert set(matches[0])=={'id','is_reply','revision','excerpt'} and len(matches[0]['excerpt'])<=search.EXCERPT_LIMIT+2
    with pytest.raises(RuntimeError,match='intake transaction'):search.render(c,clean,bot.transport.config(),NOW)


def test_groups_topics_foreign_senders_callbacks_and_duplicate_webhooks_never_disclose_or_repeat(search_env):
    env,item,task=search_env;c,users,*_=env
    discussion.post(c,users[3],item['id'],'needle PrivateBody');before=snapshot(c)
    for number,kind in enumerate(('group','topic','sender','callback'),10):
        packet=update(number,text='/discussion_search '+str(item['id'])+' work needle')
        if kind=='group':packet['message']['chat']={'id':-100,'type':'group'}
        elif kind=='topic':packet['message']['message_thread_id']=7
        elif kind=='sender':packet['message']['from']['id']=102;packet['message']['chat']['id']=102
        else:packet={'update_id':number,'callback_query':{'id':'synthetic','from':{'id':101},'data':'/discussion_search'}}
        assert 'method' not in submit(env[3],packet).json()
    packet=update(20,text='/discussion_search '+str(item['id'])+' work needle')
    assert 'PrivateBody' in submit(env[3],packet).json()['text'] and 'method' not in submit(env[3],packet).json()
    assert before==snapshot(c)


def test_independent_link_consent_current_pilot_and_no_inferred_other_scopes(linking,monkeypatch):
    c,users,path,client,payload=linking;_,raw,code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_SEARCH_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[search.ACTION],NOW)
    links.claim(c,payload,raw,['work.read',search.ACTION],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_SEARCH_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_terminal_native_discussions_remain_searchable_and_large_cursor_is_valid(search_env):
    env,item,task=search_env;c,users,*_=env
    cid=discussion.post(c,users[3],item['id'],'needle TerminalReadable',task_id=task['id'])
    c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.execute("UPDATE work_task SET status='done' WHERE id=?",(task['id'],));c.commit()
    assert ids(ask(search_env,task_id=task['id'],before=9223372036854775807)['text'])==[cid]
