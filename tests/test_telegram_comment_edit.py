"""Author-only text edits preserve native immutable history, mention eligibility and atomicity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re

import pytest

import backups
from documents_storage import rows,transaction
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_comment_edit as manage
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.test_work import workspace,case,consolidation_fixture,request_consolidation,formal_review
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed,start
from tests.test_telegram_menu import menu_env,command
from tests.test_telegram_brief import grant
from tests.test_telegram_task_deadline import deadline_env,linked_document
from tests.test_telegram_task_blockers import source_snapshot


def snapshot(c):
    return {**source_snapshot(c),**{t:list(c.execute('SELECT * FROM '+t)) for t in
        ('work_notice','work_comment_read','work_mention','work_follow','work_digest','work_channel_preference')}}


@pytest.fixture
def edit_env(deadline_env,monkeypatch):
    for scope in manage.MODES.values():grant(deadline_env[0],scope,monkeypatch)
    env,item,task=deadline_env;c,users,*_=env
    item=work.confirm_lead(c,users[1],item['id'],item['revision'],users[3]['id'],'Ordinary author is not source lead')
    return env,item,task


@pytest.fixture(params=['work','task'])
def action_env(edit_env,request):
    env,item,task=edit_env;c,users,*_=env;mode=request.param
    identifier=discussion.post(c,users[0],item['id'],'StoredPrivateOriginalText',task_id=task['id'] if mode=='task' else None)
    return env,item,task,identifier,mode


def prepare(action_env,number=10,key='comment-operation-key',**changes):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    guide=command(env,'/'+mode+'_comment_edit',number)['text']
    assert manage.PATH+mode+'?origin=' in guide
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,manage.MODES[mode])
    fields={'case_id':item['id'],'comment_id':identifier,'revision':1,'body':'Actor-entered '+mode+' comment\n@plain-name is literal text.'}
    if mode=='task':fields['task_id']=task['id']
    return ctx,actions.issue(c,ctx,manage.MODES[mode],key,{**fields,**changes},NOW)


def confirmation(env,result,mode,number=20):
    text=command(env,'/'+mode+'edit_preview '+result['operation_id'],number)['text']
    assert 'Discussion edit preview' in text and 'Actor-entered '+mode+' comment' in text
    assert 'StoredPrivate' not in text and manage.common.units(text)<=4096
    return re.search('/'+mode+r'edit_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_exact_confirmation_adds_one_revision_and_native_author_read_without_follower_notices(action_env):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    linked_document(env,item,'2026-10-30')
    work_updates.follow(c,users[3],item['id'])
    assert task['owner_id']!=users[0]['id'] and item['lead_id']!=users[0]['id'] and not work.officer(c,users[0],item)
    before=snapshot(c);_,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert before==snapshot(c)
    assert 'Recorded outcome: comment edited.' in command(env,exact,21)['text']
    saved=rows(c,'SELECT * FROM work_comment ORDER BY id DESC LIMIT 1')[0]
    assert saved['case_id']==item['id'] and saved['task_id']==(task['id'] if mode=='task' else None)
    assert saved['author_id']==users[0]['id'] and saved['parent_id'] is None
    current=discussion.message(c,item['id'],saved['task_id'],saved['id'])
    assert current['revision']==2 and current['body']=='Actor-entered '+mode+' comment\n@plain-name is literal text.'
    assert not rows(c,'SELECT * FROM work_mention')
    notice=rows(c,'SELECT * FROM work_notice WHERE comment_id=?',(saved['id'],))
    assert not notice  # Native text edits do not create new follower notices.
    assert work_updates.read_revision(c,users[0]['id'],saved['id'])==2
    after=snapshot(c)
    for table in before:
        if table not in ('work_comment_revision','work_comment_read'):assert after[table]==before[table]
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    text=command(env,'/'+mode+'edit_receipt '+result['operation_id'],23)['text']
    assert '/discussion?focus='+str(saved['id']) in text and 'Actor-entered' not in text
    assert after==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('bad',[{'body':''},{'body':'x'*1001},{'body':'unsafe\x00text'},{'body':'bad\ttext'},{'body':True},{'submission':'replace'},{'parent_id':1},{'mentions':[1]},{'case_id':999999}])
def test_strict_plain_comment_fields_do_not_change_source(action_env,bad):
    before=snapshot(action_env[0][0])
    with pytest.raises(ValueError):prepare(action_env,**bad)
    assert snapshot(action_env[0][0])==before


@pytest.mark.parametrize('change',['work','grant','read_grant','flag','module','documents_module','expiry','disconnect','restore','account','document_access','document_revision'])
def test_current_source_and_context_fence_stale_confirmation(action_env,monkeypatch,change):
    env,item,task,identifier,mode=action_env;c,users,path,_,payload=env
    if change.startswith('document_'):doc=linked_document(env,item,'2026-10-30')
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    if change=='work':c.execute('UPDATE work_case SET title=?,revision=revision+1 WHERE id=?',('Changed work',item['id']));c.commit()
    elif change in ('grant','read_grant'):
        scope=manage.MODES[mode] if change=='grant' else 'work.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_'+manage.MODES[mode].replace('.','_').upper()+'_ENABLED','0')
    elif change in ('module','documents_module'):st.set_setting(c,('work' if change=='module' else 'documents')+'.enabled','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE user_id=? AND document_id=?',(users[0]['id'],doc['id']));c.commit()
    else:c.execute('UPDATE document SET revision=revision+1 WHERE id=?',(doc['id'],));c.commit()
    before=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21).get('text','') and snapshot(c)==before


@pytest.mark.parametrize('failure',['notice','receipt','handoff'])
def test_comment_history_notices_receipt_and_handoff_are_atomic(action_env,monkeypatch,failure):
    env,item,task,identifier,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode);before=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='notice':monkeypatch.setattr(work_updates,'record',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[manage.MODES[mode]],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_comment_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert snapshot(c)==before
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'
    assert rows(c,'SELECT comment_id,comment_revision FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]=={'comment_id':identifier,'comment_revision':None}


def test_concurrent_confirmation_edits_once(action_env):
    env,item,task,identifier,mode=action_env;c,users,path,*_=env
    ctx,result=prepare(action_env);before=c.execute('SELECT COUNT(*) FROM work_comment_revision').fetchone()[0]
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1] and c.execute('SELECT COUNT(*) FROM work_comment_revision').fetchone()[0]==before+1


@pytest.mark.parametrize('state',['done','cancelled','completed'])
def test_native_informal_discussion_remains_available_on_terminal_work_or_task(action_env,state):
    env,item,task,identifier,mode=action_env;c,*_=env
    if state=='completed':c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],))
    else:c.execute('UPDATE work_task SET status=? WHERE id=?',(state,task['id']))
    c.commit();before=snapshot(c)
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    for table in ('work_task','work_case','document','document_review','work_review_packet','work_review_invalidation'):
        assert snapshot(c)[table]==before[table]


@pytest.mark.parametrize('when',['before','after'])
def test_informal_comments_do_not_change_formal_review(action_env,when):
    env,item,task,identifier,mode=action_env;c,users,path,*_=env
    source,output,reviewed,accepted=consolidation_fixture((c,users,item['unit_id'],path))
    new_identifier=discussion.post(c,users[0],reviewed['id'],'StoredPrivateFormalOriginal',task_id=accepted['id'] if mode=='task' else None)
    state=(env,reviewed,accepted,new_identifier,mode)
    if when=='before':formal_review(c,users,request_consolidation(c,users,output,reviewed))
    _,result=prepare(state);exact=confirmation(env,result,mode)
    if when=='after':
        formal_review(c,users,request_consolidation(c,users,output,reviewed))
        # Changed source requires a fresh exact preview even though discussion remains allowed.
        before=snapshot(c);assert 'Recorded outcome:' not in command(env,exact,21)['text'];assert before==snapshot(c)
        _,result=prepare(state,22,key='fresh-formal-comment-key');exact=confirmation(env,result,mode,23)
    before=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,24)['text']
    for table in ('work_task','work_case','work_event','document','document_review','work_review_packet','work_review_invalidation'):
        assert snapshot(c)[table]==before[table]


def test_unrelated_discussion_does_not_invalidate_new_comment_or_leak_old_text(action_env):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    discussion.post(c,users[3],item['id'],'StoredPrivateOtherDiscussion',task_id=task['id'] if mode=='task' else None)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    text=command(env,'/'+mode+'edit_receipt '+result['operation_id'],22)['text']
    assert 'StoredPrivate' not in text


def test_receipt_reports_later_author_edit_revision_without_reposting_text(action_env):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    operation=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]
    discussion.edit(c,users[0],item['id'],task['id'] if mode=='task' else None,operation['comment_id'],2,'StoredPrivateEditedComment')
    before=snapshot(c)
    text=command(env,'/'+mode+'edit_receipt '+result['operation_id'],22)['text']
    assert 'Recorded edit revision: 2' in text and 'Current comment revision: 3' in text and 'StoredPrivate' not in text and before==snapshot(c)


def test_groups_direct_and_other_protocols_cannot_post(action_env,monkeypatch):
    env,item,task,identifier,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode);before=snapshot(c)
    other='task' if mode=='work' else 'work'
    for number,text in enumerate(('/'+other+'edit_confirm '+result['token'],'/taskdepadd_confirm '+result['token'],'/workreply_confirm '+result['token']),21):
        assert 'Recorded outcome:' not in command(env,text,number).get('text','')
    packet=update(25,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,26)
    assert before==snapshot(c)


@pytest.mark.parametrize('mode',['work','task'])
def test_link_requires_independent_comment_scope_work_read_and_current_pilot(linking,monkeypatch,mode):
    c,users,path,client,payload=linking;ch,raw,confirmation_code=start(linking)
    flag='CSS_TELEGRAM_'+manage.MODES[mode].replace('.','_').upper()+'_ENABLED'
    monkeypatch.setenv(flag,'1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[manage.MODES[mode]],NOW)
    links.claim(c,payload,raw,['work.read',manage.MODES[mode]],NOW)
    monkeypatch.setenv(flag,'0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_native_caller_owned_post_rejects_no_transaction(edit_env):
    env,item,task=edit_env;c,users,*_=env
    assert not c.in_transaction
    with pytest.raises(RuntimeError,match='caller transaction'):discussion.edit_in_transaction(c,users[0],item['id'],None,999999,1,'No transaction')


def test_comment_retention_clears_source_identifiers(action_env):
    env,item,task,identifier,mode=action_env;c,*_=env
    _,result=prepare(action_env);exact=confirmation(env,result,mode)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    with transaction(c):actions.cleanup_in_transaction(c,NOW+timedelta(days=181))
    operation=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]
    assert operation['result_code']=='retained_key' and operation['comment_id'] is None and operation['comment_revision'] is None and operation['target_id'] is None


@pytest.mark.parametrize('when',['prepare','confirm','receipt'])
def test_comment_consent_never_grants_source_membership(action_env,when):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    if when!='prepare':
        _,result=prepare(action_env);exact=confirmation(env,result,mode)
        if when=='receipt':assert 'Recorded outcome:' in command(env,exact,21)['text']
    c.execute('UPDATE work_case SET creator_id=? WHERE id=?',(users[1]['id'],item['id']));c.commit()
    before=snapshot(c)
    if when=='prepare':
        with pytest.raises(ValueError):prepare(action_env)
    else:
        text=command(env,exact if when=='confirm' else '/'+mode+'edit_receipt '+result['operation_id'],22)['text']
        assert 'Recorded outcome:' not in text and 'Actor-entered' not in text
    assert snapshot(c)==before


def test_comment_line_endings_are_normalized_in_exact_preview_and_saved_text(action_env):
    env,item,task,identifier,mode=action_env;c,*_=env
    _,result=prepare(action_env,body='First line\r\nSecond line\rThird line')
    text=command(env,'/'+mode+'edit_preview '+result['operation_id'],20)['text']
    assert 'First line\nSecond line\nThird line' in text
    exact=re.search('/'+mode+r'edit_confirm [A-Za-z0-9_-]{43}',text)[0]
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert rows(c,'SELECT body FROM work_comment_revision ORDER BY comment_id DESC,revision DESC LIMIT 1')[0]['body']=='First line\nSecond line\nThird line'


@pytest.mark.parametrize('role',['reader','lead','officer','technical_admin'])
def test_other_authors_cannot_be_edited_even_with_management_roles(action_env,role):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    other=discussion.post(c,users[3],item['id'],'StoredPrivateOtherAuthor',task_id=task['id'] if mode=='task' else None)
    if role=='lead':work.confirm_lead(c,users[1],item['id'],item['revision'],users[0]['id'],'Current lead remains unable to edit another author')
    elif role=='officer':c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(users[0]['id'],item['unit_id'],links.stamp(NOW)));c.commit()
    elif role=='technical_admin':
        c.execute("UPDATE admin_user SET role='admin' WHERE id=?",(users[0]['id'],));c.commit()
        # The account change revokes this connection; domain authority must still refuse independently.
        with pytest.raises(ValueError,match='original author'):manage.Adapter(mode).prepare(c,users[0],{'case_id':item['id'],'comment_id':other,'revision':1,'body':'No admin override',**({'task_id':task['id']} if mode=='task' else {})})
        return
    before=snapshot(c)
    with pytest.raises(ValueError,match='original author'):prepare(action_env,comment_id=other)
    assert snapshot(c)==before


@pytest.mark.parametrize('kind',['other_work','work_vs_task','other_task','missing','boolean'])
def test_comment_must_belong_to_exact_selected_discussion(action_env,kind):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    selected=999999
    if kind=='other_work':
        other=case(c,users[0],item['unit_id']);selected=discussion.post(c,users[0],other['id'],'StoredPrivateOtherWork')
    elif kind=='work_vs_task':selected=discussion.post(c,users[0],item['id'],'StoredPrivateOtherThread',task_id=None if mode=='task' else task['id'])
    elif kind=='other_task':
        other=work_tasks.create(c,users[0],item['id'],{'title':'Other task','expected_output':'Other output','unit_id':item['unit_id']})
        selected=discussion.post(c,users[0],item['id'],'StoredPrivateOtherTask',task_id=other['id'])
    elif kind=='boolean':selected=True
    before=snapshot(c)
    with pytest.raises(ValueError):prepare(action_env,comment_id=selected)
    assert snapshot(c)==before


@pytest.mark.parametrize('when',['prepare','preview','confirm'])
def test_newer_edit_prevents_stale_revision_overwrite(action_env,when):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    if when!='prepare':
        _,result=prepare(action_env)
        exact=confirmation(env,result,mode) if when=='confirm' else None
    discussion.edit(c,users[0],item['id'],task['id'] if mode=='task' else None,identifier,1,'StoredPrivateNewerEdit')
    before=snapshot(c)
    if when=='prepare':
        with pytest.raises(ValueError,match='edited elsewhere'):prepare(action_env)
    else:
        text=command(env,exact if exact else '/'+mode+'edit_preview '+result['operation_id'],21)['text']
        assert 'Recorded outcome:' not in text and 'edit_confirm' not in text and 'StoredPrivate' not in text
    assert snapshot(c)==before
    _,fresh=prepare(action_env,22,key='fresh-comment-edit-key',revision=2)
    text=command(env,'/'+mode+'edit_preview '+fresh['operation_id'],23)['text']
    assert 'Revision 2 → 3' in text and 'StoredPrivate' not in text
    exact=re.search('/'+mode+r'edit_confirm [A-Za-z0-9_-]{43}',text)[0]
    assert 'Recorded outcome:' in command(env,exact,24)['text']


@pytest.mark.parametrize('bad',[{'revision':0},{'revision':True},{'revision':''},{'revision':2},{'body':'StoredPrivateOriginalText'}])
def test_revision_and_actual_text_change_are_required(action_env,bad):
    before=snapshot(action_env[0][0])
    with pytest.raises(ValueError):prepare(action_env,**bad)
    assert snapshot(action_env[0][0])==before


def test_editing_own_reply_preserves_parent_and_old_revision_without_text_projection(action_env):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    parent=discussion.post(c,users[3],item['id'],'StoredPrivateParent',task_id=task['id'] if mode=='task' else None)
    reply=discussion.post(c,users[0],item['id'],'StoredPrivateReplyOriginal',task_id=task['id'] if mode=='task' else None,parent_id=parent)
    _,result=prepare(action_env,comment_id=reply)
    preview=rows(c,'SELECT fields_json,summary_json,expected_json FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
    assert all('StoredPrivate' not in str(v) for v in preview.values())
    assert 'Recorded outcome:' in command(env,confirmation(env,result,mode),21)['text']
    current=discussion.message(c,item['id'],task['id'] if mode=='task' else None,reply)
    assert current['parent_id']==parent and current['revision']==2
    assert rows(c,'SELECT body FROM work_comment_revision WHERE comment_id=? AND revision=1',(reply,))[0]['body']=='StoredPrivateReplyOriginal'


@pytest.mark.parametrize('phase',['eligible','inactive_before','inactive_after','lost_access_after'])
def test_existing_structured_mentions_are_retained_and_currently_validated(action_env,phase):
    env,item,task,identifier,mode=action_env;c,users,*_=env
    mentioned=discussion.post(c,users[0],item['id'],'StoredPrivateMentionedOriginal',task_id=task['id'] if mode=='task' else None,mentions=[users[3]['id']])
    state=(env,item,task,mentioned,mode)
    if phase=='inactive_before':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit();before=snapshot(c)
        with pytest.raises(ValueError,match='no longer has access'):prepare(state)
        assert snapshot(c)==before
        return
    _,result=prepare(state);exact=confirmation(env,result,mode)
    if phase=='inactive_after':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
        before=snapshot(c);assert 'Recorded outcome:' not in command(env,exact,21)['text'];assert snapshot(c)==before
    elif phase=='lost_access_after':
        work.confirm_lead(c,users[1],item['id'],item['revision'],users[0]['id'],'Changed lead')
        work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Mentioned person no longer participates'})
        before=snapshot(c);assert 'Recorded outcome:' not in command(env,exact,21)['text'];assert snapshot(c)==before
    else:
        text=command(env,'/'+mode+'edit_preview '+result['operation_id'],19)['text'];assert 'Existing structured mentions retained: 1' in text
        assert 'StoredPrivate' not in text and users[3]['username'] not in text
        notice_before=rows(c,'SELECT * FROM work_notice')
        assert 'Recorded outcome:' in command(env,exact,21)['text']
        assert [m['user_id'] for m in work_updates.mentions(c,mentioned,1)]==[users[3]['id']]
        assert [m['user_id'] for m in work_updates.mentions(c,mentioned,2)]==[users[3]['id']]
        assert rows(c,'SELECT * FROM work_notice')==notice_before
