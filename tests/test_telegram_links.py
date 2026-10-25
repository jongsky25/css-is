"""Two-channel consent, expiry/replay and durable revocation using synthetic accounts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import re

import pytest
from starlette.testclient import TestClient

import auth
import backups
from documents_storage import transaction, rows
import storage as st
import telegram_bot as bot
import telegram_links as links
from tests.test_work import workspace
from tests.test_telegram_bot import setup, update, submit, NOW, TOKEN, SECRET


@pytest.fixture
def linking(setup, monkeypatch):
    c, users, path, client = setup
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED','1')
    monkeypatch.setenv('CSS_BASE_URL','https://office.example')
    payload = auth.parse_token(auth.make_token(users[0]))
    # Register this synthetic browser session in the same private database.
    st.register_login_session(c, payload);c.commit()
    return c, users, path, client, payload


def start(linking, number=1, sender=101):
    c, _, _, client, _ = linking
    assert submit(client, update(number, sender=sender)).status_code == 200
    assert bot.process_updates(c, NOW) == 1
    ch = rows(c, 'SELECT * FROM telegram_link_challenge WHERE telegram_user_id=? ORDER BY rowid DESC LIMIT 1', (sender,))[0]
    return ch, links.code(ch,'claim'), links.code(ch,'confirm')


def claimed(linking, scopes=('calendar.read','rooms.read')):
    c, _, _, _, payload = linking
    ch, raw, confirmation = start(linking)
    links.claim(c, payload, raw, scopes, NOW)
    return ch, raw, confirmation


def activate(linking, monkeypatch=None):
    c, _, _, client, _ = linking
    ch, raw, confirmation = claimed(linking)
    assert submit(client, update(2,text='/confirm '+confirmation)).status_code == 200
    bot.process_updates(c,NOW)
    return ch, raw, confirmation


def test_link_requires_both_channels_explicit_scopes_and_stores_only_hashes(linking, monkeypatch):
    c, users, _, client, payload = linking
    ch, raw, confirmation = start(linking)
    text = links.render(c, {'kind':'link_code','challenge':ch['id'],'bot':123456,'fingerprint':bot.transport.config()[2]},101,bot.transport.config(),NOW)
    assert raw in text and 'https://office.example/account/telegram' in text and raw not in text.split('https://')[1].split()[0]
    assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0] == 0
    links.claim(c,payload,raw,['calendar.read'],NOW)
    assert c.execute('SELECT count(*) FROM telegram_grant').fetchone()[0] == 0
    messages=[]
    monkeypatch.setattr(bot.transport,'send',lambda token,chat,text: messages.append(text) or ('accepted',9,None))
    assert bot.deliver(c,NOW) == 1
    assert users[0]['username'] in messages[0] and confirmation in messages[0]
    assert submit(client,update(2,text='/confirm '+confirmation)).status_code == 200
    bot.process_updates(c,NOW)
    assert c.execute('SELECT state FROM telegram_connection').fetchone() == ('active',)
    assert c.execute('SELECT action FROM telegram_grant').fetchall() == [('calendar.read',)]
    assert links.authorized(c,users[0]['id'],'calendar.read') is False  # Read capability still off.
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    assert links.authorized(c,users[0]['id'],'calendar.read') is True
    assert links.authorized(c,users[0]['id'],'rooms.read') is False
    assert links.authorized(c,users[0]['id'],'calendar.create') is False
    dump='\n'.join(c.iterdump())
    for secret in (raw, confirmation, TOKEN, SECRET):
        assert secret not in dump
    assert bot.HELP not in dump
    assert c.execute('SELECT session_id FROM telegram_link_challenge WHERE id=?',(ch['id'],)).fetchone() == (None,)


def test_expiry_replay_cross_account_and_wrong_sender_denied(linking):
    c, users, _, client, payload = linking
    ch, raw, confirmation = claimed(linking)
    with pytest.raises(ValueError):
        links.claim(c,payload,raw,[],NOW)
    other_payload=auth.parse_token(auth.make_token(users[1]));st.register_login_session(c,other_payload);c.commit()
    with pytest.raises(ValueError):
        links.claim(c,other_payload,raw,[],NOW)
    submit(client,update(2,sender=102,text='/confirm '+confirmation));bot.process_updates(c,NOW)
    assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0] == 0
    with transaction(c):
        assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW+timedelta(minutes=10)) is None
    submit(client,update(3,text='/confirm '+confirmation));bot.process_updates(c,NOW)
    submit(client,update(4,text='/confirm '+confirmation));bot.process_updates(c,NOW)
    assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0] == 1
    assert c.execute('SELECT count(*) FROM telegram_grant').fetchone()[0] == 2


def test_new_start_invalidates_previous_code_and_forbidden_scopes(linking):
    c, _, _, client, payload = linking
    _, first, _=start(linking)
    _, second, _=start(linking,2)
    with pytest.raises(ValueError):
        links.claim(c,payload,first,[],NOW)
    with pytest.raises(ValueError):
        links.claim(c,payload,second,['calendar.create'],NOW)
    assert c.execute('SELECT count(*) FROM telegram_grant').fetchone()[0] == 0


@pytest.mark.parametrize('change',['session','deactivate','password','role','restore','rotate_secret','pause'])
def test_pending_confirmation_rechecks_current_state(linking,monkeypatch,change):
    c, users, path, client, payload=linking
    ch, raw, confirmation=claimed(linking)
    if change=='session':
        st.revoke_login_session(c,payload['sid'])
    elif change=='deactivate':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='password':
        c.execute("UPDATE admin_user SET pw_hash='new' WHERE id=?",(users[0]['id'],));c.commit()
    elif change=='role':
        c.execute("UPDATE admin_user SET role='encoder' WHERE id=?",(users[0]['id'],));c.commit()
    elif change=='restore':
        backups.clear_restored_sessions(path)
    elif change=='rotate_secret':
        monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET','different_'+'z'*40)
    else:
        monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED','0')
    with transaction(c):
        assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0] == 0


@pytest.mark.parametrize('channel',['browser','private'])
def test_disconnect_blocks_next_read_action_and_send_even_when_paused(linking,monkeypatch,channel):
    c,users,_,client,payload=linking
    activate(linking)
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    assert links.authorized(c,users[0]['id'],'calendar.read')
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED','0')
    monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
    if channel=='browser':
        links.disconnect(c,payload,NOW)
    else:
        submit(client,update(3,text='/disconnect'))  # Revocation commits with intake; no scheduler tick needed.
    assert c.execute('SELECT state FROM telegram_connection').fetchone() == ('revoked',)
    assert not links.authorized(c,users[0]['id'],'calendar.read')
    assert c.execute('SELECT count(*) FROM telegram_grant WHERE revoked_at IS NULL').fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM telegram_delivery WHERE state IN ('queued','sending','retry_wait')").fetchone()[0] == 0
    monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','1')
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Disconnected send'))
    assert bot.deliver(c,NOW)==0


def test_deactivation_and_reactivation_do_not_resurrect_grants(linking):
    c,users,_,_,_=linking
    activate(linking)
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    c.execute('UPDATE admin_user SET active=1 WHERE id=?',(users[0]['id'],));c.commit()
    assert c.execute('SELECT state FROM telegram_connection').fetchone()==('revoked',)
    assert c.execute('SELECT count(*) FROM telegram_grant WHERE revoked_at IS NULL').fetchone()[0]==0


def test_restore_invalidates_new_tables_and_fences_confirmations(linking):
    c,_,path,_,_=linking
    activate(linking)
    backups.clear_restored_sessions(path)
    assert c.execute('SELECT state FROM telegram_connection').fetchone()==('paused',)
    assert c.execute('SELECT count(*) FROM telegram_grant WHERE revoked_at IS NULL').fetchone()[0]==0
    assert c.execute('SELECT session_id FROM telegram_link_challenge').fetchone()==(None,)


def test_replacement_requires_disconnect_and_cancel_pending_is_owner_only(linking):
    c,users,_,_,payload=linking
    ch,raw,_=claimed(linking)
    other=auth.parse_token(auth.make_token(users[1]));st.register_login_session(c,other);c.commit()
    links.disconnect(c,other,NOW)
    assert c.execute('SELECT state FROM telegram_link_challenge WHERE id=?',(ch['id'],)).fetchone()==('claimed',)
    links.disconnect(c,payload,NOW)
    assert c.execute('SELECT state FROM telegram_link_challenge WHERE id=?',(ch['id'],)).fetchone()==('cancelled',)
    # A fresh start after disconnect is deliberately permitted, without resurrecting old codes.
    _,raw2,_=start(linking,2)
    links.claim(c,payload,raw2,[],NOW)


def test_two_confirmations_racing_create_one_connection(linking):
    c,_,path,_,_=linking
    _,_,confirmation=claimed(linking)
    def commit():
        conn=st.connect(path)
        try:
            with transaction(conn):
                return links.confirm(conn,101,links.digest(confirmation),bot.transport.config(),NOW)
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:commit(),range(2)))
    assert sum(result is not None for result in results)==1
    assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0]==1


def test_browser_forms_origin_csrf_bounded_input_and_status_when_off(linking,monkeypatch):
    import app
    c,users,path,_,payload=linking
    _,raw,_=start(linking)
    monkeypatch.setattr(app,'DB',path)
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Unexpected network'))
    client=TestClient(app.app,base_url='https://office.example')
    token=auth.make_token(users[0]);newpayload=auth.parse_token(token);st.register_login_session(c,newpayload);c.commit()
    client.cookies.set(auth.COOKIE_NAME,token)
    page=client.get('/account/telegram')
    assert page.status_code==200 and page.headers['cache-control']=='private, no-store'
    assert page.headers['referrer-policy']=='same-origin'
    csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
    data={'csrf':csrf,'code':raw,'consent':'yes','scopes':'calendar.read'}
    assert client.post('/account/telegram/link',data=data,headers={'Origin':'https://foreign.example'}).status_code==403
    assert client.post('/account/telegram/link',data={**data,'csrf':'bad'}).status_code==400
    assert client.post('/account/telegram/link',content=b'x'*4097,headers={'content-type':'application/x-www-form-urlencoded'}).status_code==400
    result=client.post('/account/telegram/link',data=data,follow_redirects=False)
    assert result.status_code==303 and raw not in result.headers['location']
    assert c.execute('SELECT state FROM telegram_link_challenge').fetchone()==('claimed',)
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED','0')
    monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
    page=client.get('/account/telegram')
    assert page.status_code==200 and 'Disconnect Telegram' in page.text
    assert raw not in page.text and 'type="password"' not in page.text
    assert client.post('/account/telegram/disconnect',data={'csrf':csrf},follow_redirects=False).status_code==303
    assert c.execute('SELECT state FROM telegram_link_challenge').fetchone()==('cancelled',)
    client.close()


def test_active_account_replacement_and_bot_rotation_require_fresh_consent(linking,monkeypatch):
    c,users,_,_,payload=linking
    activate(linking)
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    assert links.authorized(c,users[0]['id'],'calendar.read')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    assert not links.authorized(c,users[0]['id'],'calendar.read')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    _,raw,confirmation=start(linking,3,sender=102)
    with pytest.raises(ValueError):
        links.claim(c,payload,raw,[],NOW)
    links.disconnect(c,payload,NOW)
    # Disconnect cancels the account's pending links, but never another unclaimed sender.
    links.claim(c,payload,raw,[],NOW)
    with transaction(c):
        assert links.confirm(c,102,links.digest(confirmation),bot.transport.config(),NOW) is not None
    assert c.execute("SELECT count(*) FROM telegram_connection WHERE state='active'").fetchone()[0]==1
    assert c.execute("SELECT count(*) FROM telegram_grant WHERE revoked_at IS NULL").fetchone()[0]==0


def test_expired_pending_code_cleanup_and_origin_validation(linking,monkeypatch):
    c,_,_,_,_=linking
    ch,_,_=claimed(linking)
    bot.cleanup(c,NOW+timedelta(minutes=11))
    assert c.execute('SELECT state,session_id FROM telegram_link_challenge WHERE id=?',(ch['id'],)).fetchone()==('cancelled',None)
    bot.cleanup(c,NOW+timedelta(days=2))
    assert c.execute('SELECT count(*) FROM telegram_link_challenge').fetchone()[0]==0
    for origin in ('http://office.example','https://user:secret@office.example','https://office.example/path',
                   'https://office.example?token=private','https://office.example:bad','https://office.example\n'):
        monkeypatch.setenv('CSS_BASE_URL',origin)
        assert links.origin() is None and not links.available()


def test_old_account_changes_cannot_revoke_a_new_owners_connection(linking):
    c,users,_,client,payload=linking
    activate(linking)
    links.disconnect(c,payload,NOW)
    _,raw,confirmation=start(linking,3)
    other=auth.parse_token(auth.make_token(users[1]));st.register_login_session(c,other);c.commit()
    links.claim(c,other,raw,['calendar.read'],NOW)
    submit(client,update(4,text='/confirm '+confirmation));bot.process_updates(c,NOW)
    submit(client,update(5,text='/status'))
    c.execute("UPDATE admin_user SET role='encoder' WHERE id=?",(users[0]['id'],));c.commit()
    assert c.execute('SELECT state FROM telegram_update WHERE update_id=5').fetchone()==('queued',)
    assert c.execute('SELECT state FROM telegram_connection WHERE account_id=?',(users[1]['id'],)).fetchone()==('active',)
    assert c.execute('SELECT count(*) FROM telegram_grant WHERE account_id=? AND revoked_at IS NULL',(users[1]['id'],)).fetchone()[0]==1
