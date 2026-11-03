"""Thread reply links are suggestions; native private confirmation remains authoritative."""
import re
from urllib.parse import urlparse,parse_qs

import pytest

from documents_storage import rows
import telegram_actions as actions
import telegram_links as links
import telegram_meetings as meetings
import telegram_discussion_read as reader
import telegram_reply_manage as replies
import work_discussion as discussion
from tests.test_work import workspace,case
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_discussion_read import read_env,thread_env,ask,reply_ids
from tests.test_telegram_comment_manage import snapshot


def controls(text):return re.findall(r'(?:^|\n)Reply form: ([^\s]+)',text)


@pytest.fixture
def shortcut_env(thread_env,monkeypatch):
    env=thread_env[0][0];target=thread_env[2]
    grant(env,'tasks.reply' if target is not None else 'work.reply',monkeypatch)
    return thread_env


def fields(url,body='Actor-entered shortcut reply'):
    parsed=parse_qs(urlparse(url).query)
    assert all(len(v)==1 for v in parsed.values())
    return {**{k:v[0] for k,v in parsed.items()},'body':body}


def prepare(state,url,number=15,key='shortcut-preview-operation'):
    source,cid,target=state;env,item,task=source;c,users,*_=env;mode='task' if target is not None else 'work'
    guide=command(env,'/'+mode+'_reply',number)['text']
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,replies.MODES[mode])
    return ctx,actions.issue(c,ctx,replies.MODES[mode],key,fields(url),NOW)


def test_root_direct_reply_and_message_part_links_prefill_only_exact_source_ids(shortcut_env):
    source,cid,target=shortcut_env;env,item,task=source;c,users,*_=env
    child=discussion.post(c,users[3],item['id'],'ChildParentText',task_id=target,parent_id=cid)
    before=snapshot(c);text=ask(shortcut_env)['text'];urls=controls(text)
    assert len(urls)==2 and ('first send /task_reply' if target is not None else 'first send /work_reply') in text
    for url,parent in zip(urls,(cid,child)):
        assert urlparse(url).path==replies.PATH+('task' if target is not None else 'work')
        assert fields(url)=={'case_id':str(item['id']),'parent_id':str(parent),'body':'Actor-entered shortcut reply',**({'task_id':str(target)} if target is not None else {})}
        assert all(v not in url for v in ('StoredSelectedText','ChildParentText','origin=','body=','mentions=','token='))
    for number,parent in enumerate((cid,child),11):
        text=ask(shortcut_env,'/discussion_message',comment_id=parent,number=number)['text']
        assert controls(text)==[urls[0 if parent==cid else 1]]
    assert before==snapshot(c)
    for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_reader_and_opposite_reply_permission_do_not_offer_shortcuts(thread_env,monkeypatch):
    source,cid,target=thread_env;env,*_=source
    grant(env,'work.reply' if target is not None else 'tasks.reply',monkeypatch)
    for number,kind in enumerate(reader.COMMANDS,10):
        text=ask(thread_env,kind,number=number)['text']
        assert 'StoredSelectedText' in text and not controls(text) and 'To use Reply links' not in text


@pytest.mark.parametrize('guard',['grant','pilot'])
def test_current_matching_reply_consent_and_pilot_control_availability(shortcut_env,monkeypatch,guard):
    source,cid,target=shortcut_env;env,item,task=source;c,*_=env;scope='tasks.reply' if target is not None else 'work.reply'
    assert controls(ask(shortcut_env)['text'])
    if guard=='grant':c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
    else:monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','0')
    before=snapshot(c)
    for n,kind in enumerate(reader.COMMANDS,11):
        text=ask(shortcut_env,kind,number=n)['text'];assert 'StoredSelectedText' in text and not controls(text)
    assert before==snapshot(c)


def test_existing_writer_previews_current_parent_and_refuses_newer_parent_after_preview(shortcut_env):
    source,cid,target=shortcut_env;env,item,task=source;c,users,*_=env
    url=controls(ask(shortcut_env)['text'])[0]
    discussion.edit(c,users[3],item['id'],target,cid,1,'ParentUpdatedBeforePreparation')
    before=snapshot(c);ctx,result=prepare(shortcut_env,url)
    mode='task' if target is not None else 'work'
    text=command(env,'/'+mode+'reply_preview '+result['operation_id'],16)['text']
    assert 'Reply to comment '+str(cid)+' · Revision 2' in text and 'Actor-entered shortcut reply' in text
    assert 'StoredSelectedText' not in text and 'ParentUpdatedBeforePreparation' not in text and before==snapshot(c)
    exact=re.search('/'+mode+r'reply_confirm [A-Za-z0-9_-]{43}',text)[0]
    discussion.edit(c,users[3],item['id'],target,cid,2,'ParentChangedAfterPreview');before=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,17)['text'] and before==snapshot(c)


def test_shortcut_does_not_preserve_lost_source_authority(shortcut_env):
    source,cid,target=shortcut_env;env,item,task=source;c,users,*_=env
    doc=linked_document(env,item,'2026-10-30');url=controls(ask(shortcut_env)['text'])[0]
    c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[0]['id']));c.commit()
    before=snapshot(c)
    with pytest.raises(ValueError):prepare(shortcut_env,url)
    assert before==snapshot(c) and not rows(c,'SELECT * FROM telegram_operation')
    assert ask(shortcut_env,number=16)['text']==reader.DENIED


def test_maximum_origin_long_unicode_parent_and_reply_pages_still_continue(shortcut_env,monkeypatch):
    source,cid,target=shortcut_env;env,item,task=source;c,users,*_=env
    origin='https://'+'a'*60+'.'+'b'*60+'.'+'c'*60+'.example12';assert len(origin)==200
    monkeypatch.setenv('CSS_BASE_URL',origin)
    c.execute('UPDATE work_case SET title=? WHERE id=?',('🌿'*300,item['id']));c.execute('UPDATE work_task SET title=? WHERE id=?',('🌼'*300,task['id']));c.commit()
    selected=discussion.post(c,users[3],item['id'],'🌻'*4000,task_id=target,parent_id=cid)
    expected=[discussion.post(c,users[3],item['id'],'🌺'*1000,task_id=target,parent_id=selected) for _ in range(8)]
    text=ask(shortcut_env,comment_id=selected)['text'];seen=[]
    for number in range(11,23):
        assert reader.common.units(text)<=4096
        found=reply_ids(text);assert found and len(controls(text))==len(found)+1;seen.extend(found)
        next_=re.search(r'Older direct replies: (.*)',text)
        if not next_:break
        text=command(env,next_[1],number)['text']
    assert seen==list(reversed(expected))
    text=ask(shortcut_env,'/discussion_message',comment_id=selected,number=24,extra='part:1:2')['text']
    assert reader.common.units(text)<=4096 and 'Previous part:' in text and 'Next part:' in text and len(controls(text))==1


def test_stale_or_unavailable_message_parts_offer_no_reply_link(shortcut_env):
    source,cid,target=shortcut_env;env,item,task=source;c,users,*_=env
    discussion.edit(c,users[3],item['id'],target,cid,1,'NewCurrentText')
    stale=ask(shortcut_env,'/discussion_message',extra='part:1:2')['text']
    assert 'This message changed' in stale and not controls(stale) and 'To use Reply links' not in stale
    unavailable=ask(shortcut_env,'/discussion_message',number=11,extra='part:2:5')['text']
    assert 'That part is unavailable' in unavailable and not controls(unavailable)
