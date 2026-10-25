"""Authenticated private help only. No linking, group reads or business mutations."""
import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import auth
from documents_storage import transaction, rows
import telegram_storage as storage
import telegram_transport as transport

PATH = '/integrations/telegram/webhook'
MAX_BODY = 65536
MAX_TICK = 20
HELP = ('Office Connect Telegram help: /start and /help are available in this private chat. '
        'Account linking, calendar access and actions are not available yet. '
        'Use your usual signed-in Office Connect page for office work.')


def now_utc():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.isoformat(timespec='seconds')


def webhook_secret():
    value = os.environ.get('CSS_TELEGRAM_WEBHOOK_SECRET', '')
    return value if re.fullmatch(r'[A-Za-z0-9_-]{32,256}', value) else None


def integer(value, *, positive=False):
    if type(value) is not int or not -(2**63) <= value < 2**63 or (positive and value <= 0):
        raise ValueError('Invalid identifier')
    return value


def normalize(value):
    if not isinstance(value, dict):
        raise ValueError('Object required')
    update_id = integer(value.get('update_id'))
    if update_id < 0:
        raise ValueError('Invalid update')
    clean = {'update_id': update_id, 'sender_id': None, 'chat_id': None, 'topic_id': None, 'command': None}
    if 'callback_query' in value:
        query = value['callback_query']
        if not isinstance(query, dict) or not isinstance(query.get('from'), dict):
            raise ValueError('Invalid callback')
        clean['sender_id'] = integer(query['from'].get('id'), positive=True)
        data = query.get('data', '')
        if not isinstance(data, str) or len(data.encode('utf-8')) > 64:
            raise ValueError('Invalid callback data')
        return clean
    if 'message' not in value:
        return clean
    message = value['message']
    if not isinstance(message, dict) or not isinstance(message.get('from'), dict) or not isinstance(message.get('chat'), dict):
        raise ValueError('Invalid message')
    integer(message.get('message_id'), positive=True)
    clean['sender_id'] = integer(message['from'].get('id'), positive=True)
    clean['chat_id'] = integer(message['chat'].get('id'))
    if clean['chat_id'] == 0:
        raise ValueError('Invalid chat')
    if 'message_thread_id' in message:
        clean['topic_id'] = integer(message['message_thread_id'], positive=True)
    text = message.get('text', '')
    if not isinstance(text, str) or len(text) > 4096:
        raise ValueError('Invalid text')
    # No arbitrary text, names, usernames or link arguments are retained.
    if (message['chat'].get('type') == 'private' and clean['chat_id'] == clean['sender_id']
            and message['from'].get('is_bot') is False and clean['topic_id'] is None):
        first = text.split(maxsplit=1)[0] if text.strip() else ''
        if first in ('/start', '/help'):
            clean['command'] = first
    return clean


def identity(conn, sender):
    found = rows(conn, 'SELECT * FROM telegram_connection WHERE telegram_user_id=? ORDER BY id DESC LIMIT 1', (sender,))
    if not found:
        return None, None, True  # Unlinked neutral help only.
    link = found[0]
    user = rows(conn, 'SELECT active,must_change,role FROM admin_user WHERE id=?', (link['account_id'],))
    permitted = (link['state'] == 'active' and user and user[0]['active']
                 and not user[0]['must_change'] and auth.valid_role(user[0]['role']))
    return link['id'], link['generation'], bool(permitted)


def receive(conn, clean, raw, bot, now):
    with transaction(conn):
        if conn.execute('SELECT 1 FROM telegram_update WHERE bot_identity=? AND update_id=?',
                        (bot[0], clean['update_id'])).fetchone():
            return 200
        since = stamp(now - timedelta(minutes=1))
        total = conn.execute('SELECT count(*) FROM (SELECT 1 FROM telegram_update WHERE received_at>? LIMIT 120)', (since,)).fetchone()[0]
        personal = conn.execute('SELECT count(*) FROM (SELECT 1 FROM telegram_update WHERE sender_id=? AND received_at>? LIMIT 20)',
                                (clean['sender_id'], since)).fetchone()[0]
        if total >= 120 or personal >= 20:
            return 429
        cid, generation, permitted = identity(conn, clean['sender_id'])
        supported = clean['command'] is not None and permitted
        payload = json.dumps({'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]}) if supported else None
        conn.execute('''INSERT INTO telegram_update
            (bot_identity,update_id,sender_id,chat_id,topic_id,connection_id,generation,
             payload_json,payload_hash,received_at,state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (bot[0], clean['update_id'], clean['sender_id'], clean['chat_id'], clean['topic_id'], cid,
             generation, payload, hashlib.sha256(raw).hexdigest(), stamp(now), 'queued' if supported else 'ignored'))
    return 200


def make_router(get_conn):
    router = APIRouter()

    @router.post(PATH)
    async def webhook(request: Request):
        if not storage.enabled('inbound'):
            return JSONResponse({'error': 'paused'}, status_code=503)
        secret, bot = webhook_secret(), transport.config()
        if not secret or not bot:
            return JSONResponse({'error': 'unavailable'}, status_code=503)
        supplied = request.headers.getlist('x-telegram-bot-api-secret-token')
        if len(supplied) != 1 or not hmac.compare_digest(supplied[0].encode(), secret.encode()):
            return JSONResponse({'error': 'forbidden'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return JSONResponse({'error': 'invalid_input'}, status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return JSONResponse({'error': 'too_large'}, status_code=413)
        try:
            clean = normalize(json.loads(body))
        except (ValueError, UnicodeError, RecursionError):
            return JSONResponse({'error': 'invalid_input'}, status_code=400)
        conn = None
        try:
            conn = get_conn()
            status = receive(conn, clean, body, bot, now_utc())
        except sqlite3.Error:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503)
        finally:
            if conn is not None:
                conn.close()
        return JSONResponse({'ok': status == 200}, status_code=status,
                            headers={'Retry-After': '60'} if status == 429 else None)

    return router


def process_updates(conn, now):
    if not storage.enabled('inbound'):
        return 0
    bot = transport.config()
    if not bot:
        return 0
    for _ in range(MAX_TICK):
        with transaction(conn):
            found = rows(conn, '''SELECT * FROM telegram_update WHERE state='queued'
                OR (state='processing' AND lease_until<=?) ORDER BY id LIMIT 1''', (stamp(now),))
            if not found:
                return _
            update = found[0]
            cid, generation, permitted = identity(conn, update['sender_id'])
            valid = (permitted and cid == update['connection_id'] and generation == update['generation']
                     and update['bot_identity'] == bot[0] and update['received_at'] > stamp(now - timedelta(hours=24)))
            try:
                projection = json.loads(update['payload_json'] or '{}')
            except ValueError:
                projection = {}
            valid = valid and projection == {'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]}
            if valid:
                conn.execute('''INSERT INTO telegram_delivery
                    (dedupe_key,event_key,connection_id,generation,chat_id,projection_json,expires_at,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING''',
                    ('help:' + str(update['id']), str(bot[0]), cid, generation, update['chat_id'],
                     json.dumps(projection), stamp(datetime.fromisoformat(update['received_at']) + timedelta(hours=24)), stamp(now), stamp(now)))
            conn.execute('''UPDATE telegram_update SET state=?,payload_json=NULL,claim_token=NULL,lease_until=NULL,
                attempts=attempts+1,error_code=? WHERE id=?''',
                ('processed' if valid else 'cancelled', None if valid else 'ineligible', update['id']))
    return MAX_TICK


def eligible(conn, delivery, bot):
    try:
        projection = json.loads(delivery['projection_json'])
    except ValueError:
        return False
    cid, generation, permitted = identity(conn, delivery['chat_id'])
    rejected = conn.execute('''SELECT 1 FROM telegram_delivery WHERE chat_id=?
        AND state='failed' AND error_code='provider_rejected' AND updated_at>=? LIMIT 1''',
        (delivery['chat_id'], delivery['created_at'])).fetchone()
    return (not rejected and delivery['chat_id'] > 0 and delivery['topic_id'] is None and delivery['registration_id'] is None
            and permitted and cid == delivery['connection_id'] and generation == delivery['generation']
            and projection == {'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]})


def deliver(conn, now=None):
    if not storage.enabled('delivery'):
        return 0
    bot = transport.config()
    if not bot:
        return 0
    fixed_now = now
    clock = now_utc if fixed_now is None else lambda: fixed_now
    count = 0
    now = clock()
    with transaction(conn):
        # A crashed sender is uncertain, never automatically retried.
        conn.execute('''UPDATE telegram_delivery SET state='uncertain',claim_token=NULL,lease_until=NULL,
                error_code='interrupted',updated_at=? WHERE id IN
                (SELECT id FROM telegram_delivery WHERE state='sending' AND lease_until<=? LIMIT 20)''', (stamp(now), stamp(now)))
    for _ in range(MAX_TICK):
        now = clock()
        token = uuid4().hex
        with transaction(conn):
            found = rows(conn, '''SELECT d.* FROM telegram_delivery d
                WHERE (d.state='queued' OR (d.state='retry_wait' AND d.retry_at<=?)
                    OR (d.state='claimed' AND d.lease_until<=?))
                AND NOT EXISTS (SELECT 1 FROM telegram_delivery busy WHERE busy.chat_id=d.chat_id
                    AND ((busy.state='sending' AND busy.lease_until>?)
                    OR (busy.state='accepted' AND busy.updated_at>?)))
                ORDER BY d.id LIMIT 1''', (stamp(now), stamp(now), stamp(now), stamp(now-timedelta(seconds=1))))
            if not found:
                break
            delivery = found[0]
            if delivery['expires_at'] <= stamp(now) or not eligible(conn, delivery, bot):
                conn.execute("UPDATE telegram_delivery SET state='cancelled',error_code='ineligible',updated_at=? WHERE id=?",
                             (stamp(now), delivery['id']))
                continue
            # Commit the sending marker before network I/O. Conditional finalizers fence restores.
            conn.execute('''UPDATE telegram_delivery SET state='sending',claim_token=?,lease_until=?,
                attempts=attempts+1,updated_at=? WHERE id=?''',
                (token, stamp(now+timedelta(minutes=2)), stamp(now), delivery['id']))
        # Recheck immediately before sending; an in-flight send cannot be recalled.
        current_bot = transport.config()
        if (not storage.enabled('delivery') or current_bot != bot or not eligible(conn, delivery, bot)
                or delivery['expires_at'] <= stamp(clock())
                or not conn.execute("SELECT 1 FROM telegram_delivery WHERE id=? AND claim_token=? AND state='sending'",
                                    (delivery['id'], token)).fetchone()):
            outcome, message_id, retry = 'cancelled', None, None
        else:
            outcome, message_id, retry = transport.send(bot[1], delivery['chat_id'], HELP)
            count += 1
        error_code = 'provider_rejected' if outcome == 'failed' else outcome
        if outcome == 'retry_wait' and delivery['attempts'] + 1 >= 5:
            outcome, retry, error_code = 'failed', None, 'retry_exhausted'
        now = clock()
        with transaction(conn):
            conn.execute('''UPDATE telegram_delivery SET state=?,provider_message_id=?,retry_at=?,
                claim_token=NULL,lease_until=NULL,error_code=?,updated_at=?
                WHERE id=? AND state='sending' AND claim_token=?''',
                (outcome, message_id, stamp(now+timedelta(seconds=retry)) if retry else None,
                 None if outcome == 'accepted' else error_code, stamp(now), delivery['id'], token))
    return count


def cleanup(conn, now):
    with transaction(conn):
        conn.execute('''UPDATE telegram_update SET sender_id=NULL,chat_id=NULL,topic_id=NULL,payload_json=NULL,
            state=CASE WHEN state IN ('queued','processing') THEN 'cancelled' ELSE state END,
            claim_token=NULL,lease_until=NULL WHERE id IN
            (SELECT id FROM telegram_update WHERE received_at<? AND
             (sender_id IS NOT NULL OR chat_id IS NOT NULL OR payload_json IS NOT NULL) LIMIT 20)''',
            (stamp(now-timedelta(days=7)),))
        conn.execute('''DELETE FROM telegram_delivery WHERE id IN (SELECT id FROM telegram_delivery
            WHERE state IN ('accepted','failed','uncertain','cancelled') AND updated_at<? LIMIT 20)''',
            (stamp(now-timedelta(days=180)),))


def tick(conn, now=None):
    processed = process_updates(conn, now or now_utc())
    sent = deliver(conn, now)
    cleanup(conn, now or now_utc())
    return processed, sent
