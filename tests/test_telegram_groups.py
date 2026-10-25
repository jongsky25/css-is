"""Exact-destination consent, safe neutral routing and group lifecycle fences."""
import json
from datetime import timedelta

import pytest

import auth
import backups
from documents_storage import rows, transaction
import storage as st
import telegram_bot as bot
import telegram_groups as groups
import telegram_links as links
from tests.test_work import workspace
from tests.test_telegram_bot import setup, NOW, update, submit, TOKEN


def group_update(number=1, sender=101, chat=-100, topic=None, text='/register'):
    value=update(number,sender,text)
    value['message']['chat']={'id':chat,'type':'supergroup'}
    if topic:
        value['message']['message_thread_id']=topic
        value['message']['is_topic_message']=True
    return value


def bind(c,user,sender):
    payload=auth.parse_token(auth.make_token(user));st.register_login_session(c,payload);c.commit()
    with transaction(c):
        links.start(c,sender,bot.transport.config(),NOW)
    ch=rows(c,'SELECT * FROM telegram_link_challenge WHERE telegram_user_id=?',(sender,))[0]
    links.claim(c,payload,links.code(ch,'claim'),[],NOW)
    with transaction(c):
        assert links.confirm(c,sender,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW)
    return payload


@pytest.fixture
def registered(setup,monkeypatch):
    c,users,path,client=setup
    monkeypatch.setenv('CSS_TELEGRAM_GROUPS_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED','1')
    monkeypatch.setenv('CSS_BASE_URL','https://office.example')
    monkeypatch.setattr(bot.transport,'member_status',lambda *args:'administrator')
    payload=bind(c,users[4],101)
    # Remove pending private handshake notices so tests isolate group sends.
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    return c,users,path,client,payload


def register(registered,number=1,chat=-100,topic=None):
    c,_,_,client,payload=registered
    assert submit(client,group_update(number,chat=chat,topic=topic)).status_code==200
    request=rows(c,'SELECT * FROM telegram_group_request WHERE update_id=?',(number,))[0]
    groups.register(c,payload,request['id'],'Internal coordination', 'yes',NOW)
    return rows(c,'SELECT * FROM telegram_group WHERE chat_id=? AND topic_id=?',(chat,topic or 0))[0]


def queue(registered,number=2,chat=-100,topic=None,sender=101):
    c,_,_,client,_=registered
    submit(client,group_update(number,chat=chat,topic=topic,sender=sender,text='/group_status'))
    bot.process_updates(c,NOW)
    return rows(c,'SELECT * FROM telegram_delivery WHERE chat_id=? ORDER BY id DESC LIMIT 1',(chat,))


def test_unregistered_unlinked_and_non_admin_commands_do_not_bind_or_reply(registered):
    c,users,_,client,_=registered
    submit(client,group_update(text='/group_status'));bot.process_updates(c,NOW)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')
    submit(client,group_update(2,sender=999))
    bind(c,users[0],102)
    submit(client,group_update(3,sender=102))
    assert not rows(c,'SELECT * FROM telegram_group_request')
    assert not rows(c,'SELECT * FROM telegram_group')


def test_registration_consent_provider_admin_checks_and_replay(registered,monkeypatch):
    c,_,_,client,payload=registered
    submit(client,group_update())
    request=rows(c,'SELECT * FROM telegram_group_request')[0]
    with pytest.raises(ValueError):
        groups.register(c,payload,request['id'],'Purpose','no',NOW)
    calls=[]
    monkeypatch.setattr(bot.transport,'member_status',lambda token,chat,sender:calls.append(sender) or ('member' if sender==101 else 'administrator'))
    with pytest.raises(ValueError):
        groups.register(c,payload,request['id'],'Purpose','yes',NOW)
    assert not rows(c,'SELECT * FROM telegram_group')
    monkeypatch.setattr(bot.transport,'member_status',lambda token,chat,sender:calls.append(sender) or 'administrator')
    groups.register(c,payload,request['id'],'Purpose','yes',NOW)
    assert calls[-2:]==[101,123456]
    assert rows(c,'SELECT * FROM telegram_group')[0]['owner_account_id']==registered[1][4]['id']
    with pytest.raises(ValueError):
        groups.register(c,payload,request['id'],'Purpose','yes',NOW)
    assert submit(client,group_update()).status_code==200  # Duplicate receipt cannot re-open registration.
    assert len(rows(c,'SELECT * FROM telegram_group_request'))==1


def test_exact_topic_and_fixed_group_projection_only(registered,monkeypatch):
    c,_,_,_,_=registered
    group=register(registered,topic=7)
    assert queue(registered,topic=8)==[]
    assert queue(registered,3,topic=None)==[]
    deliveries=queue(registered,4,topic=7)
    assert len(deliveries)==1 and deliveries[0]['registration_id']==group['id']
    calls=[]
    monkeypatch.setattr(bot.transport,'send',lambda *args:calls.append(args) or ('accepted',17,None))
    assert bot.deliver(c,NOW)==1
    assert calls==[(TOKEN,-100,groups.STATUS,7)]
    assert 'Internal coordination' not in calls[0][2]
    # Arbitrary private projections and business fields cannot travel through a registered group.
    queue(registered,5,topic=7)
    c.execute("UPDATE telegram_delivery SET projection_json=? WHERE chat_id<0 AND state='queued'",(json.dumps({'kind':'help','note':'restricted','participants':['private person']}),));c.commit()
    assert bot.deliver(c,NOW+timedelta(seconds=2))==0
    assert len(calls)==1


@pytest.mark.parametrize('event', ['removed','owner_demoted','migration','topic_closed','topic_reopened'])
def test_lifecycle_pauses_and_cancels_before_acknowledgement(registered,event):
    c,_,_,client,_=registered
    register(registered,topic=7);queue(registered,topic=7)
    if event in ('removed','owner_demoted'):
        value={'update_id':3, 'my_chat_member' if event=='removed' else 'chat_member': {
            'chat':{'id':-100,'type':'supergroup'},'from':{'id':999},
            'new_chat_member':{'user':{'id':123456 if event=='removed' else 101},'status':'kicked' if event=='removed' else 'member'}}}
    else:
        value=group_update(3,topic=7,text='')
        if event=='migration':
            value['message']['migrate_to_chat_id']=-200
        else:
            value['message']['forum_topic_closed' if event=='topic_closed' else 'forum_topic_reopened']={}
    assert submit(client,value).status_code==200
    assert rows(c,'SELECT * FROM telegram_group')[0]['state']=='paused'
    assert rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')[0]['state']=='cancelled'
    assert not groups.route(c,-200,7,bot.transport.config())
    assert submit(client,value).status_code==200


def test_new_members_gain_no_office_access_and_departed_actor_is_denied(registered,monkeypatch):
    c,users,_,client,_=registered
    register(registered)
    value={'update_id':2,'chat_member':{'chat':{'id':-100,'type':'supergroup'},'from':{'id':999},
        'new_chat_member':{'user':{'id':102},'status':'member'}}}
    submit(client,value)
    assert rows(c,'SELECT * FROM telegram_group')[0]['state']=='active'
    assert not rows(c,'SELECT * FROM telegram_connection WHERE telegram_user_id=102')
    assert queue(registered,3,sender=102)==[]
    bind(c,users[0],102)
    queue(registered,4,sender=102)
    monkeypatch.setattr(bot.transport,'member_status',lambda token,chat,sender:'left' if sender==102 else 'administrator')
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Departed requester send'))
    assert bot.deliver(c,NOW)==0
    assert rows(c,'SELECT * FROM telegram_group')[0]['state']=='active'


@pytest.mark.parametrize('change',['disconnect','deactivate','restore','bot_rotation','switch','provider_failure'])
def test_queued_delivery_rechecks_registration_and_owner(registered,monkeypatch,change):
    c,users,path,_,payload=registered
    register(registered);queue(registered)
    if change=='disconnect':
        links.disconnect(c,payload,NOW)
    elif change=='deactivate':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[4]['id'],));c.commit()
    elif change=='restore':
        backups.clear_restored_sessions(path)
    elif change=='bot_rotation':
        monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    elif change=='switch':
        monkeypatch.setenv('CSS_TELEGRAM_GROUPS_ENABLED','0')
    else:
        monkeypatch.setattr(bot.transport,'member_status',lambda *args:None)
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Ineligible group send'))
    assert bot.deliver(c,NOW)==0
    assert rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')[0]['state']=='cancelled'


def test_group_changed_during_provider_checks_fences_the_send(registered,monkeypatch):
    c,_,path,_,_=registered
    register(registered);queue(registered)
    def verify(*args):
        other=st.connect(path)
        with transaction(other):
            groups.pause(other,-100,reason='concurrent_change')
        other.close()
        return 'administrator'
    monkeypatch.setattr(bot.transport,'member_status',verify)
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Stale registration send'))
    assert bot.deliver(c,NOW)==0
    assert rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')[0]['state']=='cancelled'


def test_pause_reverification_stale_form_and_owner_change(registered):
    c,users,_,_,payload=registered
    group=register(registered)
    groups.manage(c,payload,group['id'],group['generation'],'pause')
    with pytest.raises(ValueError):
        groups.manage(c,payload,group['id'],group['generation'],'revoke')
    replacement=register(registered,3)
    assert replacement['generation']!=group['generation'] and replacement['state']=='active'
    other=bind(c,users[0],102)
    with pytest.raises(ValueError):
        groups.manage(c,other,group['id'],replacement['generation'],'revoke')


def test_registration_proof_cannot_race_with_revocation_or_expiry(registered,monkeypatch):
    c,_,_,client,payload=registered
    submit(client,group_update())
    request=rows(c,'SELECT * FROM telegram_group_request')[0]
    def verify(*args):
        with transaction(c):
            groups.pause(c,-100,reason='changed')
        return 'administrator'
    monkeypatch.setattr(bot.transport,'member_status',verify)
    with pytest.raises(ValueError):
        groups.register(c,payload,request['id'],'Purpose','yes',NOW)
    assert not rows(c,'SELECT * FROM telegram_group')
    submit(client,group_update(2))
    request=rows(c,'SELECT * FROM telegram_group_request WHERE update_id=2')[0]
    with pytest.raises(ValueError):
        groups.register(c,payload,request['id'],'Purpose','yes',NOW+timedelta(minutes=10))


def test_unauthorized_browser_actor_cannot_use_an_admins_observed_request(registered,monkeypatch):
    c,users,_,client,_=registered
    submit(client,group_update())
    request=rows(c,'SELECT * FROM telegram_group_request')[0]
    staff=bind(c,users[0],102)
    monkeypatch.setattr(bot.transport,'member_status',lambda *args:pytest.fail('Unauthorized provider lookup'))
    with pytest.raises(ValueError):
        groups.register(c,staff,request['id'],'Purpose','yes',NOW)
    assert not rows(c,'SELECT * FROM telegram_group')


def test_group_network_budget_and_persisted_bot_binding(registered,monkeypatch):
    c,_,_,_,_=registered
    register(registered,1,chat=-100);register(registered,2,chat=-200);register(registered,3,chat=-300)
    queue(registered,4,chat=-100);queue(registered,5,chat=-200);queue(registered,6,chat=-300)
    calls=[]
    monkeypatch.setattr(bot.transport,'send',lambda *args:calls.append(args) or ('accepted',9,None))
    assert bot.deliver(c,NOW)==2
    assert len(calls)==2
    assert bot.deliver(c,NOW)==1
    assert len(calls)==3
    group=rows(c,'SELECT * FROM telegram_group WHERE chat_id=-100')[0]
    c.execute('UPDATE telegram_connection SET bot_fingerprint=NULL WHERE id=?',(group['owner_connection_id'],));c.commit()
    assert groups.route(c,-100,None,bot.transport.config()) is None


def test_concurrent_group_workers_serialize_provider_checks(registered,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    c,_,path,_,_=registered
    register(registered);queue(registered)
    queue(registered,3)
    entered,release=Event(),Event()
    def check(*args):
        entered.set()
        assert release.wait(5)
        return 'administrator'
    monkeypatch.setattr(bot.transport,'member_status',check)
    calls=[]
    monkeypatch.setattr(bot.transport,'send',lambda *args:calls.append(args) or ('accepted',11,None))
    def drain():
        conn=st.connect(path)
        try:
            return bot.deliver(conn,NOW)
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first=executor.submit(drain)
        assert entered.wait(5)
        second=executor.submit(drain)
        try:
            assert second.result(timeout=5)==0
        finally:
            release.set()
        assert first.result(timeout=5)==1
    assert len(calls)==1
    assert rows(c,"SELECT * FROM telegram_delivery WHERE chat_id<0 AND state='queued'")


def test_upgrade_requires_fresh_provenance_and_restart_preserves_registration(registered):
    c,users,path,_,_=registered
    owner=rows(c,'SELECT * FROM telegram_connection WHERE account_id=?',(users[4]['id'],))[0]
    c.execute('DROP TRIGGER telegram_connection_groups')
    c.execute('DROP TABLE telegram_group_request');c.execute('DROP TABLE telegram_group')
    c.execute('ALTER TABLE telegram_connection DROP COLUMN bot_identity')
    c.execute('ALTER TABLE telegram_connection DROP COLUMN bot_fingerprint');c.commit()
    st.init_db(c)
    migrated=rows(c,'SELECT * FROM telegram_connection WHERE id=?',(owner['id'],))[0]
    assert migrated['generation']==owner['generation'] and migrated['state']=='active'
    assert migrated['bot_identity'] is None and migrated['bot_fingerprint'] is None
    assert bot.identity(c,101)[2] is True  # Existing private pilot remains separate.
    with pytest.raises(ValueError):
        groups.linked(c,users[4]['id'],admin=True)
    # Restore explicit synthetic provenance to exercise ordinary process restart persistence.
    c.execute('UPDATE telegram_connection SET bot_identity=?,bot_fingerprint=? WHERE id=?',
              (bot.transport.config()[0],bot.transport.config()[2],owner['id']));c.commit()
    group=register(registered)
    restarted=st.connect(path)
    try:
        st.init_db(restarted)
        current=groups.route(restarted,-100,None,bot.transport.config())
        assert current['generation']==group['generation'] and current['state']=='active'
    finally:
        restarted.close()
