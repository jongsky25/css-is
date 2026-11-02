"""Explicit current-access recipients in exact existing comment and reply confirmations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import re

import pytest

import backups
import storage as st
from documents_storage import rows,transaction
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_comment_manage as comments
import telegram_reply_manage as replies
import telegram_mentions as mentions
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


@pytest.fixture(params=[('comment','work'),('comment','task'),('reply','work'),('reply','task')])
def mention_env(deadline_env,request,monkeypatch):
    env,item,task=deadline_env;c,users,*_=env;kind,mode=request.param
    manager=comments if kind=='comment' else replies
    grant(env,manager.MODES[mode],monkeypatch);grant(env,mentions.SCOPE,monkeypatch)
    parent=discussion.post(c,users[3],item['id'],'StoredPrivateParent',task_id=task['id'] if mode=='task' else None) if kind=='reply' else None
    return env,item,task,kind,mode,parent


def prepare(state,number=10,key='mention-operation-key',**changes):
    env,item,task,kind,mode,parent=state;c,users,*_=env
    manager=comments if kind=='comment' else replies
    guide=command(env,'/'+mode+'_'+kind,number)['text']
    ctx=meetings.origin(c,users[0],guide.split('?origin=')[1],NOW,manager.MODES[mode])
    fields={'case_id':item['id'],'body':'Actor-entered mentioned message\n@literal-name','mentions':[users[3]['id']]}
    if mode=='task':fields['task_id']=task['id']
    if kind=='reply':fields['parent_id']=parent
    return ctx,actions.issue(c,ctx,manager.MODES[mode],key,{**fields,**changes},NOW)


def confirmation(state,result,number=20):
    env,item,task,kind,mode,parent=state
    text=command(env,'/'+mode+kind+'_preview '+result['operation_id'],number)['text']
    assert 'Selected colleague mentions:' in text and 'Actor-entered mentioned message' in text
    assert 'StoredPrivate' not in text and mentions.common.units(text)<=4096
    return re.search('/'+mode+kind+r'_confirm [A-Za-z0-9_-]{43}',text)[0]


def test_exact_preview_posts_selected_mentions_once_with_native_deduplicated_notices(mention_env):
    env,item,task,kind,mode,parent=mention_env;c,users,*_=env
    linked_document(env,item,'2026-10-30');work_updates.follow(c,users[3],item['id'])
    before=snapshot(c);_,result=prepare(mention_env);exact=confirmation(mention_env,result)
    text=command(env,'/'+mode+kind+'_preview '+result['operation_id'],19)['text']
    assert users[3]['username']+' (account '+str(users[3]['id'])+')' in text
    assert snapshot(c)==before
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    saved=rows(c,'SELECT * FROM work_comment ORDER BY id DESC LIMIT 1')[0]
    assert saved['task_id']==(task['id'] if mode=='task' else None) and saved['parent_id']==parent
    assert [m['user_id'] for m in work_updates.mentions(c,saved['id'],1)]==[users[3]['id']]
    notices=rows(c,'SELECT * FROM work_notice WHERE comment_id=?',(saved['id'],))
    assert len(notices)==1 and notices[0]['user_id']==users[3]['id'] and notices[0]['reason']=='mention'
    after=snapshot(c)
    for table in before:
        if table not in ('work_comment','work_comment_revision','work_notice','work_comment_read','work_mention'):assert after[table]==before[table]
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    text=command(env,'/'+mode+kind+'_receipt '+result['operation_id'],23)['text']
    assert 'Selected colleague' not in text and users[3]['username'] not in text
    assert snapshot(c)==after and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


@pytest.mark.parametrize('values',[None,'1',True,[True],[0],['01'],[999999],list(range(1,22))])
def test_invalid_or_unavailable_recipient_lists_are_refused(mention_env,values):
    before=snapshot(mention_env[0][0])
    with pytest.raises(ValueError):prepare(mention_env,mentions=values)
    assert snapshot(mention_env[0][0])==before


def test_duplicate_people_are_refused_and_selection_order_normalizes(mention_env):
    env,item,task,kind,mode,parent=mention_env;c,users,*_=env
    with pytest.raises(ValueError,match='only once'):prepare(mention_env,mentions=[users[3]['id'],str(users[3]['id'])])
    _,result=prepare(mention_env,11,mentions=[users[3]['id'],users[0]['id']])
    preview=rows(c,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
    assert json.loads(preview['fields_json'])['mentions']==sorted([users[0]['id'],users[3]['id']])


@pytest.mark.parametrize('kind',['inactive','no_work_access','missing_document_access'])
def test_people_must_already_read_work_and_every_linked_document(mention_env,kind):
    env,item,task,action_kind,mode,parent=mention_env;c,users,*_=env
    chosen=users[3]['id']
    if kind=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(chosen,));c.commit()
    elif kind=='no_work_access':chosen=users[2]['id']
    else:
        doc=linked_document(env,item,'2026-10-30')
        c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],chosen));c.commit()
    before=snapshot(c)
    with pytest.raises(ValueError):prepare(mention_env,mentions=[chosen])
    assert snapshot(c)==before


@pytest.mark.parametrize('change',['name','inactive','document_access','membership','grant','flag','read_grant','expiry','restore','disconnect'])
def test_current_recipient_and_auxiliary_consent_fence_stale_confirmation(mention_env,monkeypatch,change):
    env,item,task,kind,mode,parent=mention_env;c,users,path,_,payload=env
    if change=='document_access':doc=linked_document(env,item,'2026-10-30')
    _,result=prepare(mention_env);exact=confirmation(mention_env,result)
    if change=='name':c.execute('UPDATE admin_user SET username=? WHERE id=?',('renamed-person@example.invalid',users[3]['id']));c.commit()
    elif change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[3]['id'],));c.commit()
    elif change=='document_access':c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',(doc['id'],users[3]['id']));c.commit()
    elif change=='membership':work_tasks.mutate(c,users[1],item['id'],task['id'],task['revision'],'reassign',{'owner_id':users[0]['id'],'reason':'Chosen person no longer reads work'})
    elif change in ('grant','read_grant'):
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),mentions.SCOPE if change=='grant' else 'work.read'));c.commit()
        assert rows(c,'SELECT state,fields_json FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]=={'state':'cancelled','fields_json':None}
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_WORK_MENTIONS_ENABLED','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='restore':backups.clear_restored_sessions(path)
    else:links.disconnect(c,payload,NOW)
    before=snapshot(c)
    response=command(env,exact,21)
    assert 'Recorded outcome:' not in response.get('text','') and snapshot(c)==before
    if change in ('restore','disconnect'):assert 'method' not in response


@pytest.mark.parametrize('missing',['flag','consent'])
def test_base_post_permission_does_not_grant_mentions_but_unmentioned_posts_still_work(mention_env,monkeypatch,missing):
    env,item,task,kind,mode,parent=mention_env;c,*_=env
    if missing=='flag':monkeypatch.setenv('CSS_TELEGRAM_WORK_MENTIONS_ENABLED','0')
    else:c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),mentions.SCOPE));c.commit()
    with pytest.raises(ValueError,match='separate'):prepare(mention_env)
    _,result=prepare(mention_env,11,mentions=[])
    text=command(env,'/'+mode+kind+'_preview '+result['operation_id'],20)['text']
    assert 'Selected colleague mentions:' not in text
    exact=re.search('/'+mode+kind+r'_confirm [A-Za-z0-9_-]{43}',text)[0]
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    assert not rows(c,'SELECT * FROM work_mention')


@pytest.mark.parametrize('failure',['notice','receipt','handoff'])
def test_message_mentions_notices_and_receipt_roll_back_atomically(mention_env,monkeypatch,failure):
    env,item,task,kind,mode,parent=mention_env;c,*_=env
    _,result=prepare(mention_env);exact=confirmation(mention_env,result);before=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    manager=comments if kind=='comment' else replies
    if failure=='notice':monkeypatch.setattr(work_updates,'record',fail)
    elif failure=='receipt':monkeypatch.setattr(actions.ADAPTERS[manager.MODES[mode]],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_mention_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert snapshot(c)==before
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_concurrent_confirmation_creates_one_message_and_recipient_notice(mention_env):
    env,item,task,kind,mode,parent=mention_env;c,users,path,*_=env
    ctx,result=prepare(mention_env);before=c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0]
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1] and c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0]==before+1
    identifier=rows(c,'SELECT comment_id FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]['comment_id']
    assert len(rows(c,'SELECT * FROM work_notice WHERE comment_id=?',(identifier,)))==1


def test_mentioning_yourself_records_metadata_without_self_notice(mention_env):
    env,item,task,kind,mode,parent=mention_env;c,users,*_=env
    _,result=prepare(mention_env,mentions=[users[0]['id']]);exact=confirmation(mention_env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    identifier=rows(c,'SELECT comment_id FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]['comment_id']
    assert [m['user_id'] for m in work_updates.mentions(c,identifier,1)]==[users[0]['id']]
    assert not rows(c,'SELECT * FROM work_notice WHERE comment_id=? AND user_id=?',(identifier,users[0]['id']))


def test_auxiliary_permission_alone_grants_no_post_or_reply(mention_env):
    env,item,task,kind,mode,parent=mention_env;c,*_=env
    manager=comments if kind=='comment' else replies
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),manager.MODES[mode]));c.commit()
    before=snapshot(c)
    text=command(env,'/'+mode+'_'+kind,10).get('text','')
    assert manager.PATH not in text and 'Recorded outcome:' not in text
    assert snapshot(c)==before


def test_mention_link_requires_work_read_and_current_pilot(linking,monkeypatch):
    c,users,path,client,payload=linking;ch,raw,confirmation_code=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_MENTIONS_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[mentions.SCOPE],NOW)
    links.claim(c,payload,raw,['work.read',mentions.SCOPE],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_WORK_MENTIONS_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation_code),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_choices_are_source_scoped_empty_until_loaded_and_never_create_previews(mention_env,monkeypatch):
    env,item,task,kind,mode,parent=mention_env;c,users,*_=env
    values={'case_id':str(item['id']),**({'task_id':str(task['id'])} if mode=='task' else {})}
    if kind=='reply':values['parent_id']=str(parent)
    before=snapshot(c)
    empty=mentions.form_context(c,users[0],mode,{},reply=kind=='reply')
    assert empty['mentions_available'] and not empty['mention_people'] and not empty['mention_loaded']
    loaded=mentions.form_context(c,users[0],mode,values,reply=kind=='reply')
    ids={p['id'] for p in loaded['mention_people']}
    assert users[3]['id'] in ids and users[2]['id'] not in ids
    hidden=mentions.form_context(c,users[0],mode,{**values,'case_id':'999999'},reply=kind=='reply')
    assert not hidden['mention_people'] and hidden['mention_error']
    monkeypatch.setenv('CSS_TELEGRAM_WORK_MENTIONS_ENABLED','0')
    paused=mentions.form_context(c,users[0],mode,values,reply=kind=='reply')
    assert not paused['mentions_available'] and not paused['mention_people']
    assert before==snapshot(c) and not rows(c,'SELECT * FROM telegram_operation')


def test_twenty_currently_eligible_people_are_supported_without_new_access(mention_env):
    env,item,task,kind,mode,parent=mention_env;c,users,*_=env
    people=[]
    for i in range(20):
        uid=st.create_admin_user(c,f'm{i:02}@example.test','unused','unused','viewer',active=True)
        st.mark_onboarded(c,uid)
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(uid,item['unit_id'],links.stamp(NOW)))
        people.append(uid)
    c.commit();before=snapshot(c)
    _,result=prepare(mention_env,mentions=people);exact=confirmation(mention_env,result)
    assert 'Recorded outcome:' in command(env,exact,21)['text']
    identifier=rows(c,'SELECT comment_id FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]['comment_id']
    assert [p['user_id'] for p in work_updates.mentions(c,identifier,1)]==people
    assert len(rows(c,'SELECT * FROM work_notice WHERE comment_id=?',(identifier,)))==20+(kind=='reply')
    for table in ('work_case','work_task','document_access','work_follow','work_channel_preference'):assert snapshot(c)[table]==before[table]
