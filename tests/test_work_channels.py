"""Private channel preferences, independent claims and actual Apprise transport (mocked I/O)."""
from datetime import datetime,timedelta
import json
import logging
import sqlite3

import pytest
import requests
from starlette.testclient import TestClient

import apprise_transport as transport
import auth
import backups
import documents as docs
import documents_permissions as permissions
import storage as st
import work_channels as channels
import work_digests as email_digests
import work_discussion as discussion
import work_updates as updates
from tests.conftest import session_token
from tests.test_work import workspace,case

BOT='123456:'+('A'*35)
CHAT='123456789'
BASE='https://office.example'
NOW=datetime(2026,10,19,7)


def setup(workspace,monkeypatch,cadence='daily'):
    c,u,unit,_=workspace
    item=case(c,u[0],unit);updates.follow(c,u[1],item['id'])
    channels.save(c,u[1],0,cadence)
    binding=channels.preferences(c,u[1])['binding']
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_ENABLED','1')
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps({binding:{'bot_token':BOT,'chat_id':CHAT}}))
    identifier=discussion.post(c,u[0],item['id'],'Private discussion content')
    calls=[]
    monkeypatch.setattr(transport,'send',lambda value,url:calls.append((value,url)) or True)
    return item,identifier,calls,binding


def test_defaults_owner_revision_disconnect_and_repeat_install(workspace,monkeypatch):
    c,u,_,_=workspace
    before=c.total_changes
    assert channels.preferences(c,u[0])['cadence']=='off'
    assert channels.preferences(c,u[0])['binding'] is None and c.total_changes==before
    channels.save(c,u[0],0,'daily');first=channels.preferences(c,u[0])
    assert len(first['binding'])==32 and channels.preferences(c,u[1])['binding'] is None
    with pytest.raises(docs.Conflict):channels.save(c,u[0],0,'off')
    for revision,cadence in [('x','off'),('1','hourly'),(True,'off')]:
        with pytest.raises(ValueError):channels.save(c,u[0],revision,cadence)
    st.set_setting(c,'work.enabled','0')
    channels.save(c,u[0],1,'daily','disconnect');new=channels.preferences(c,u[0])
    assert new['cadence']=='off' and new['binding']!=first['binding']
    st.init_db(c);assert channels.preferences(c,u[0])['binding']==new['binding']
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    with pytest.raises(permissions.Denied):channels.preferences(c,u[0])
    with pytest.raises(permissions.Denied):channels.save(c,u[0],2,'off')


def test_private_claim_dry_run_dedup_new_notices_and_email_independence(workspace,monkeypatch):
    c,u,_,path=workspace;item,identifier,calls,binding=setup(workspace,monkeypatch)
    before=c.total_changes
    assert channels.deliver(c,BASE,dry_run=True,now=NOW)==1 and c.total_changes==before and not calls
    assert not c.execute('SELECT 1 FROM work_channel_digest').fetchone()
    st.set_email_feature(c,'job_work_updates',False)
    original_send=transport.send
    def inspect(value,url):
        other=st.connect(path)
        assert other.execute('SELECT state FROM work_channel_digest ORDER BY id DESC LIMIT 1').fetchone()[0]=='sending'
        assert channels.deliver(other,BASE,now=NOW)==0
        other.close();assert not c.in_transaction
        return original_send(value,url)
    monkeypatch.setattr(transport,'send',inspect)
    assert channels.deliver(c,BASE,now=NOW)==1
    assert calls==[({'bot_token':BOT,'chat_id':CHAT},BASE+'/work/updates')]
    assert updates.read_revision(c,u[1]['id'],identifier)==0
    assert email_digests.preferences(c,u[1])['digest']=='off'
    assert not c.execute('SELECT 1 FROM work_digest').fetchone()
    assert BOT not in str(list(c.execute('SELECT * FROM work_channel_digest')))
    assert channels.deliver(c,BASE,now=NOW)==0
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=1))==0
    discussion.post(c,u[0],item['id'],'A later update')
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=1))==1 and len(calls)==2
    assert channels.history(c,u[0])==[] and len(channels.history(c,u[1]))==2


@pytest.mark.parametrize('gate',['global','work','account','read','access','preference','destination','disconnect'])
def test_recheck_before_transport_cancels_revoked_claims(workspace,monkeypatch,gate):
    c,u,_,_=workspace;item,identifier,calls,binding=setup(workspace,monkeypatch)
    original=channels.eligible
    def revoke(conn,user):
        ids=original(conn,user)
        if gate=='global':monkeypatch.setenv('CSS_APPRISE_TELEGRAM_ENABLED','0')
        elif gate=='work':conn.execute("UPDATE app_setting SET value='0' WHERE key='work.enabled'")
        elif gate=='account':conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],))
        elif gate=='read':conn.execute('INSERT INTO work_comment_read VALUES (?,?,1)',(identifier,user['id']))
        elif gate=='access':conn.execute('UPDATE document_role_grant SET revoked_at=? WHERE user_id=?',('2026-10-20',user['id']))
        elif gate=='preference':conn.execute("UPDATE work_channel_preference SET cadence='off',revision=revision+1 WHERE user_id=?",(user['id'],))
        elif gate=='destination':monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps({binding:{'bot_token':BOT,'chat_id':'987654321'}}))
        elif gate=='disconnect':conn.execute("UPDATE work_channel_preference SET binding=lower(hex(randomblob(16))),revision=revision+1 WHERE user_id=?",(user['id'],))
        return ids
    monkeypatch.setattr(channels,'eligible',revoke)
    assert channels.deliver(c,BASE,now=NOW)==0 and not calls
    assert c.execute('SELECT state FROM work_channel_digest').fetchone()[0]=='cancelled'
    assert not c.execute('SELECT 1 FROM work_channel_digest_notice').fetchone()


@pytest.mark.parametrize('outcome',['false','exception','crash'])
def test_uncertain_or_crash_attempts_are_never_replayed(workspace,monkeypatch,outcome):
    c,u,_,_=workspace;item,identifier,calls,binding=setup(workspace,monkeypatch)
    class Crash(BaseException):pass
    def send(value,url):
        calls.append(url)
        if outcome=='exception':raise ValueError(BOT)
        if outcome=='crash':raise Crash()
        return False
    monkeypatch.setattr(transport,'send',send)
    if outcome=='crash':
        with pytest.raises(Crash):channels.deliver(c,BASE,now=NOW)
    else:assert channels.deliver(c,BASE,now=NOW)==0
    state=c.execute('SELECT state FROM work_channel_digest').fetchone()[0]
    assert state==('sending' if outcome=='crash' else 'unknown')
    assert channels.deliver(c,BASE,now=NOW)==0
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=8))==0 and len(calls)==1
    assert updates.read_revision(c,u[1]['id'],identifier)==0


def test_claim_rolls_back_without_transport_on_queue_failure(workspace,monkeypatch):
    c,u,_,_=workspace;_,_,calls,_=setup(workspace,monkeypatch)
    c.execute("CREATE TRIGGER fail_channel BEFORE INSERT ON work_channel_digest_notice BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;");c.commit()
    with pytest.raises(sqlite3.IntegrityError):channels.deliver(c,BASE,now=NOW)
    assert not calls and not c.execute('SELECT 1 FROM work_channel_digest').fetchone()


def test_weekly_morning_bounds_and_notice_batch_limit(workspace,monkeypatch):
    c,u,_,_=workspace;item,_,calls,_=setup(workspace,monkeypatch,'weekly')
    assert channels.deliver(c,BASE,now=NOW.replace(hour=6))==0
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=1))==0
    assert channels.deliver(c,'http://office.example',now=NOW)==0
    assert channels.deliver(c,BASE,now=NOW)==1
    discussion.post(c,u[0],item['id'],'Second');discussion.post(c,u[0],item['id'],'Third')
    monkeypatch.setattr(channels,'MAX_NOTICES',1)
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=7))==1
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=14))==1 and len(calls)==3


def test_disconnect_and_deliberate_restore_revoke_host_binding(workspace,monkeypatch):
    c,u,_,path=workspace;_,_,calls,binding=setup(workspace,monkeypatch)
    backups.clear_restored_sessions(path,revoke_integrations=False)
    assert channels.preferences(c,u[1])['binding']==binding
    backups.clear_restored_sessions(path,revoke_integrations=True)
    pref=channels.preferences(c,u[1])
    assert pref['cadence']=='off' and pref['binding']!=binding and not channels.status(c,u[1],BASE)['ready']
    assert channels.deliver(c,BASE,now=NOW)==0 and not calls


def test_deleted_account_reuse_cannot_inherit_channel(workspace,monkeypatch):
    c,u,_,_=workspace
    uid=st.create_admin_user(c,'channel-owner@example.test','unused','unused','viewer',active=True)
    owner=st.get_admin_user_by_id(c,uid);channels.save(c,owner,0,'daily');old=channels.preferences(c,owner)
    c.execute('DELETE FROM admin_user WHERE id=?',(uid,));c.commit()
    new_id=st.create_admin_user(c,'replacement@example.test','unused','unused','viewer',active=True)
    assert new_id==uid
    owner=st.get_admin_user_by_id(c,new_id)
    assert channels.preferences(c,owner)['binding'] is None
    channels.save(c,owner,0,'daily');assert channels.preferences(c,owner)['binding']!=old['binding']


def test_bounded_ticks_drain_other_configured_users(workspace,monkeypatch):
    c,u,unit,_=workspace;item,_,calls,binding=setup(workspace,monkeypatch)
    mapping={binding:{'bot_token':BOT,'chat_id':CHAT}}
    for index in range(5):
        uid=st.create_admin_user(c,f'channel-{index}@example.test','unused','unused','viewer',active=True)
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-16')",(uid,unit));c.commit()
        user=st.get_admin_user_by_id(c,uid);updates.follow(c,user,item['id']);channels.save(c,user,0,'daily')
        mapping[channels.preferences(c,user)['binding']]={'bot_token':BOT,'chat_id':str(123456790+index)}
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps(mapping))
    discussion.post(c,u[0],item['id'],'Shared unread update')
    assert channels.deliver(c,BASE,now=NOW)==5
    assert channels.deliver(c,BASE,now=NOW)==1
    assert channels.deliver(c,BASE,now=NOW)==0 and len(calls)==6


def test_actual_apprise_plugin_fixed_endpoint_timeout_privacy_and_no_secret_logs(monkeypatch,caplog):
    import apprise.plugins.telegram as plugin
    calls=[]
    def post(url,**kwargs):
        calls.append((url,kwargs))
        logging.getLogger('urllib3.connectionpool').debug('https://api.telegram.org:443 POST %s',url)
        response=requests.Response();response.status_code=200;response._content=b'{"ok":true,"result":{"message_id":1}}';return response
    monkeypatch.setattr(plugin.requests,'post',post)
    caplog.set_level(logging.DEBUG)
    assert transport.send({'bot_token':BOT,'chat_id':CHAT},BASE+'/work/updates')
    assert len(calls)==1
    url,kwargs=calls[0]
    assert url==f'https://api.telegram.org/bot{BOT}/sendMessage'
    assert kwargs['timeout']==(3.0,7.0) and kwargs['verify'] is True and kwargs['allow_redirects'] is False
    payload=json.loads(kwargs['data']);assert payload['chat_id']==int(CHAT)
    assert '/work/updates' in payload['text'] and payload['disable_web_page_preview'] is True
    assert BOT not in caplog.text and CHAT not in caplog.text
    calls.clear()
    def fail(url,**kwargs):
        calls.append(url);raise requests.Timeout(BOT)
    monkeypatch.setattr(plugin.requests,'post',fail)
    assert not transport.send({'bot_token':BOT,'chat_id':CHAT},BASE+'/work/updates')
    assert len(calls)==1 and BOT not in caplog.text


@pytest.mark.parametrize('raw',['not json','[]','{}',json.dumps({'x':{'bot_token':BOT,'chat_id':CHAT}})])
def test_unconfigured_or_malformed_host_secrets_never_activate(raw,monkeypatch):
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',raw)
    assert transport.target('a'*32) is None


def test_preferences_http_csrf_owner_no_credentials_and_scheduler(workspace,monkeypatch,app_mod):
    app=app_mod
    c,u,_,path=workspace;_,_,calls,_=setup(workspace,monkeypatch)
    monkeypatch.setattr(app,'DB',path);monkeypatch.setenv('CSS_BASE_URL',BASE)
    monkeypatch.setattr(app,'_now_local',lambda:NOW)
    client=TestClient(app.app,base_url=BASE,headers={'origin':BASE})
    try:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        response=client.get('/work/notification-preferences')
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        import re
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',response.text)[1]
        url='/work/notification-preferences/telegram'
        assert client.post(url,headers={'origin':BASE},data={'channel_revision':'0','cadence':'daily'}).status_code==403
        result=client.post(url,headers={'origin':BASE},data={'csrf':csrf,'channel_revision':'0','cadence':'daily','user_id':u[1]['id']})
        assert result.status_code==200 and 'Telegram digest frequency' in result.text and BOT not in result.text
        assert channels.preferences(c,u[0])['cadence']=='daily' and channels.preferences(c,u[1])['revision']==1
        assert client.post(url,headers={'origin':BASE},data={'csrf':csrf,'channel_revision':'0','cadence':'off'}).status_code==409
        assert app._work_channels_tick()==1 and len(calls)==1
        assert app._work_channels_tick()==0

    finally:
        client.close()


@pytest.mark.parametrize('value',[
    {'bot_token':'bad','chat_id':CHAT},
    {'bot_token':BOT,'chat_id':'-100123456789'},
    {'bot_token':BOT,'chat_id':'@public-channel'},
    {'bot_token':BOT,'chat_id':123456789},
    {'bot_token':BOT,'chat_id':CHAT,'notify_url':'https://private.example'},
])
def test_host_config_accepts_only_fixed_provider_private_chats(value,monkeypatch):
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps({'a'*32:value}))
    assert transport.target('a'*32) is None


@pytest.mark.parametrize('base',['http://office.example','https://user:password@office.example',
    'https://office.example?token=secret','https://office.example#secret','https://office.example/\nextra'])
def test_message_links_reject_non_https_credentials_queries_and_controls(base):
    assert transport.link(base) is None


def test_restore_during_transport_cannot_overwrite_uncertain_history(workspace,monkeypatch):
    c,u,_,path=workspace;_,_,calls,binding=setup(workspace,monkeypatch)
    def send(value,url):
        calls.append(url)
        backups.clear_restored_sessions(path,revoke_integrations=True)
        return True
    monkeypatch.setattr(transport,'send',send)
    assert channels.deliver(c,BASE,now=NOW)==1
    assert c.execute('SELECT state FROM work_channel_digest').fetchone()[0]=='unknown'
    assert channels.preferences(c,u[1])['binding']!=binding
    assert channels.deliver(c,BASE,now=NOW+timedelta(days=1))==0 and len(calls)==1
