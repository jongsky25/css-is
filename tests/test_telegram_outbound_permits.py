"""The primary database grants at most one actual send, including across service restarts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

import storage
import telegram_bot as bot
import telegram_outbound_protocol as protocol
from tests.test_telegram_bot import setup, submit, TOKEN, NOW
from tests.test_work import workspace

NONCE = 'c'*32


def pending(setup, monkeypatch):
    conn, _, path, web = setup
    monkeypatch.setenv('CSS_TELEGRAM_OUTBOUND_URL', 'https://office-connect-telegram.onrender.com')
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED', '1')
    monkeypatch.setenv('CSS_BASE_URL', 'https://office.example')
    assert submit(web).status_code == 200
    bot.process_updates(conn, NOW)
    conn.execute("UPDATE telegram_delivery SET state='sending',claim_token=?,lease_until=?,attempts=1", (NONCE, bot.stamp(NOW+timedelta(minutes=2))))
    conn.commit()
    body, proof = protocol.packet(TOKEN, 'sendMessage',
        {'chat_id': 101, 'text': 'private link', 'link_preview_options': {'is_disabled': True}}, nonce=NONCE)
    value = protocol.verify(body, proof, protocol.public_key(TOKEN))
    return conn, path, web, body, proof, value


def test_only_one_database_permit_survives_fresh_connections_and_local_cache_reset(setup, monkeypatch):
    conn, path, _, _, _, value = pending(setup, monkeypatch)
    def consume(_):
        c = storage.connect(path)
        try:
            return bot.consume_outbound_permit(c, value, bot.transport.config(), NOW)
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(consume, range(8))) == 1
    assert not consume(None)
    assert tuple(conn.execute('SELECT state,error_code FROM telegram_delivery').fetchone()) == ('sending', 'outbound_started')


@pytest.mark.parametrize('change', ['expired_lease', 'link_disabled', 'different_chat', 'unknown_nonce'])
def test_permit_rechecks_lease_scope_current_switch_and_destination(setup, monkeypatch, change):
    conn, _, web, body, proof, value = pending(setup, monkeypatch)
    if change == 'expired_lease':
        conn.execute('UPDATE telegram_delivery SET lease_until=?', (bot.stamp(NOW-timedelta(seconds=1)),))
        conn.commit()
    elif change == 'link_disabled':
        monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED', '0')
    else:
        params = dict(value['params'], chat_id=102) if change == 'different_chat' else value['params']
        body, proof = protocol.packet(TOKEN, 'sendMessage', params,
                                      nonce='d'*32 if change == 'unknown_nonce' else NONCE)
    response = web.post(protocol.PERMIT_PATH, content=body, headers={'x-office-proof': proof})
    assert response.status_code == 409 and response.json() == {'ok': False}
    assert conn.execute('SELECT error_code FROM telegram_delivery').fetchone()[0] is None


def test_real_app_accepts_proof_without_browser_origin_and_rejects_unsigned_requests(setup, client, app_mod, monkeypatch):
    conn, path, _, body, proof, _ = pending(setup, monkeypatch)
    monkeypatch.setattr(app_mod, 'DB', path)
    client.headers.pop('origin', None)
    assert client.post(protocol.PERMIT_PATH, content=body).status_code == 403
    assert conn.execute('SELECT error_code FROM telegram_delivery').fetchone()[0] is None
    response = client.post(protocol.PERMIT_PATH, content=body, headers={'x-office-proof': proof})
    assert response.status_code == 200 and response.json() == {'ok': True}
    assert client.post(protocol.PERMIT_PATH, content=body, headers={'x-office-proof': proof}).status_code == 409
    assert TOKEN not in response.text
