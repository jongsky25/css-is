"""Authenticated private replies use Telegram's existing incoming TLS connection."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from threading import Event

import pytest

import deploy_hf
import storage as st
import telegram_bot as bot
import telegram_links as links
from documents_storage import rows
from tests.test_telegram_bot import setup, submit, update, NOW, TOKEN, HEADERS
from tests.test_telegram_links import linking
from tests.test_work import workspace


@pytest.fixture
def inline(linking, monkeypatch):
    monkeypatch.delenv('CSS_TELEGRAM_REPLY_TRANSPORT')
    def no_provider(*args, **kwargs):
        pytest.fail('Webhook reply opened an outgoing Telegram connection')
    monkeypatch.setattr(bot.transport, 'send', no_provider)
    monkeypatch.setattr(bot.transport, 'member_status', no_provider)
    return linking


def test_start_replies_inline_and_cannot_be_replayed_by_worker_or_duplicate(inline):
    c, _, _, client, _ = inline
    response = submit(client)
    packet = response.json()
    assert response.status_code == 200 and response.headers['content-type'] == 'application/json'
    assert response.headers['cache-control'] == 'no-store'
    assert packet['method'] == 'sendMessage' and packet['chat_id'] == 101
    assert set(packet) == {'method', 'chat_id', 'text', 'link_preview_options'}
    challenge = rows(c, 'SELECT * FROM telegram_link_challenge')[0]
    assert links.code(challenge, 'claim') in packet['text']
    assert TOKEN not in json.dumps(packet)
    delivery = rows(c, 'SELECT * FROM telegram_delivery')[0]
    assert (delivery['state'], delivery['error_code'], delivery['attempts']) == ('uncertain','webhook_response',1)
    assert delivery['provider_message_id'] is None
    assert bot.process_updates(c, NOW) == bot.deliver(c, NOW) == 0
    assert submit(client).json() == {'ok': True}
    assert submit(client, update(text='/help')).json() == {'ok': True}
    assert c.execute('SELECT count(*) FROM telegram_link_challenge').fetchone()[0] == 1
    assert bot.worker_status(c)['webhook_responses'] == 1


def activate_inline(inline):
    c, _, _, client, browser = inline
    submit(client)
    challenge = rows(c, 'SELECT * FROM telegram_link_challenge')[0]
    links.claim(c, browser, links.code(challenge, 'claim'), ['calendar.read','rooms.read'], NOW)
    reply = submit(client, update(2, text='/confirm '+links.code(challenge, 'confirm')))
    assert reply.json()['method'] == 'sendMessage'
    assert rows(c, 'SELECT * FROM telegram_connection')[0]['state'] == 'active'
    return client


@pytest.mark.parametrize('command', ['/help','/status','/calendar','/room_slots','/my_rooms','/room_status REFERENCE'])
def test_link_confirmation_and_private_reads_keep_current_consent(inline, monkeypatch, command):
    c, _, _, _, _ = inline
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_ROOMS_READ_ENABLED','1')
    client = activate_inline(inline)
    reply = submit(client, update(3, text=command)).json()
    assert reply['method'] == 'sendMessage' and reply['chat_id'] == 101 and reply['text']
    assert bot.process_updates(c, NOW) == bot.deliver(c, NOW) == 0
    if command == '/calendar':
        monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
        assert submit(client, update(4,text=command)).json() == {'ok': True}


@pytest.mark.parametrize('flag', ['CSS_TELEGRAM_DELIVERY_ENABLED','CSS_TELEGRAM_INBOUND_ENABLED'])
def test_paused_switch_prevents_inline_handoff(inline, monkeypatch, flag):
    c, _, _, client, _ = inline
    monkeypatch.setenv(flag,'0')
    response = submit(client)
    assert 'method' not in response.json()
    assert not rows(c, "SELECT * FROM telegram_delivery WHERE error_code='webhook_response'")
    assert not rows(c, 'SELECT * FROM telegram_link_challenge')


def test_authentication_is_required_before_private_response(inline):
    c, _, _, client, _ = inline
    assert client.post(bot.PATH, json=update()).status_code == 403
    assert not rows(c,'SELECT * FROM telegram_update')
    assert not rows(c,'SELECT * FROM telegram_link_challenge')


def test_rollback_before_response_allows_exactly_one_later_handoff(inline, monkeypatch):
    c, _, _, client, _ = inline
    original = bot.prepare_webhook_reply
    def interrupted(*args):
        assert original(*args)
        raise sqlite3.OperationalError('synthetic commit failure')
    monkeypatch.setattr(bot,'prepare_webhook_reply',interrupted)
    assert submit(client).status_code == 503
    assert not rows(c,'SELECT * FROM telegram_update')
    assert not rows(c,'SELECT * FROM telegram_link_challenge')
    assert not rows(c,'SELECT * FROM telegram_delivery')
    monkeypatch.setattr(bot,'prepare_webhook_reply',original)
    assert submit(client).json()['method'] == 'sendMessage'
    assert submit(client).json() == {'ok': True}


def test_config_change_during_render_cancels_private_response(inline, monkeypatch):
    c, _, _, client, _ = inline
    original = bot.render_delivery
    def changed(*args, **kwargs):
        message = original(*args, **kwargs)
        monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
        return message
    monkeypatch.setattr(bot,'render_delivery',changed)
    assert submit(client).json() == {'ok': True}
    assert rows(c,'SELECT * FROM telegram_delivery')[0]['state'] == 'cancelled'


def test_concurrent_retry_and_worker_cannot_take_inline_delivery(inline, monkeypatch):
    c, _, path, client, _ = inline
    entered, release = Event(), Event()
    original = bot.render_delivery
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(bot,'render_delivery',blocked)
    def worker():
        db = st.connect(path)
        try:
            return bot.process_updates(db,NOW), bot.deliver(db,NOW)
        finally:
            db.close()
    with ThreadPoolExecutor(3) as executor:
        first = executor.submit(submit,client)
        assert entered.wait(3)
        duplicate = executor.submit(submit,client)
        queued_worker = executor.submit(worker)
        release.set()
        assert first.result(10).json()['method'] == 'sendMessage'
        assert duplicate.result(10).json() == {'ok': True}
        assert queued_worker.result(10) == (0,0)
    assert rows(c,'SELECT * FROM telegram_delivery')[0]['attempts'] == 1


def test_no_backlog_or_group_message_is_returned_as_private_reply(inline):
    c, _, _, client, _ = inline
    submit(client)
    # A new sender must receive only their own challenge, never an older record.
    packet = submit(client,update(2,sender=102)).json()
    assert packet['chat_id'] == 102
    old = rows(c,'SELECT * FROM telegram_link_challenge WHERE telegram_user_id=101')[0]
    assert links.code(old,'claim') not in packet['text']
    group = update(3)
    group['message']['chat']={'id':-100,'type':'supergroup'}
    group['message']['text']='/group_status'
    assert submit(client,group).json() == {'ok': True}


def test_disconnect_still_revokes_immediately_and_never_replays_old_handoffs(inline):
    c, _, _, _, _ = inline
    client = activate_inline(inline)
    before = c.execute("SELECT count(*) FROM telegram_delivery WHERE error_code='webhook_response'").fetchone()[0]
    assert submit(client,update(3,text='/disconnect')).json() == {'ok': True}
    assert rows(c,'SELECT * FROM telegram_connection')[0]['state'] != 'active'
    assert bot.process_updates(c,NOW) == bot.deliver(c,NOW) == 0
    assert c.execute("SELECT count(*) FROM telegram_delivery WHERE error_code='webhook_response'").fetchone()[0] == before


def test_ops_parser_only_reports_bounded_handoff_metadata():
    from tests.test_telegram_deploy_diagnostics import page
    value = deploy_hf.telegram_ops_summary(page(reply_transport='webhook',webhook_responses=2))
    assert value['reply_transport'] == 'webhook' and value['webhook_responses'] == 2
    value = deploy_hf.telegram_ops_summary(page(reply_transport=TOKEN,webhook_responses=True))
    assert 'reply_transport' not in value and 'webhook_responses' not in value


@pytest.mark.parametrize('module_name,kind', [('telegram_calendar','calendar'),('telegram_rooms','rooms')])
def test_private_renderer_never_commits_a_caller_transaction(inline, module_name, kind):
    import importlib
    from documents_storage import transaction
    renderer = importlib.import_module(module_name)
    c, _, _, _, _ = inline
    projection = {'kind':kind, 'bot':123456, 'fingerprint':bot.transport.config()[2], 'query':{'error':'usage'}}
    with pytest.raises(RuntimeError, match='requires a transaction'):
        renderer.render(c, {}, projection, bot.transport.config(), NOW, commit=False)
    with pytest.raises(RuntimeError, match='force caller rollback'):
        with transaction(c):
            c.execute("UPDATE admin_user SET active=0 WHERE id=(SELECT min(id) FROM admin_user)")
            # Missing identity returns no content but retains the caller's transaction.
            delivery={'connection_id':None,'generation':None,'chat_id':101,'topic_id':None,'registration_id':None}
            assert renderer.render(c, delivery, projection, bot.transport.config(), NOW, commit=False) is None
            assert c.in_transaction
            raise RuntimeError('force caller rollback')
    assert c.execute('SELECT min(active) FROM admin_user').fetchone()[0] == 1
