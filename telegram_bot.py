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
import telegram_links as links
import telegram_groups as groups

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
    event = groups.lifecycle(value)
    if event:
        clean.update(event)
        return clean
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
        if first in ('/start', '/help', '/status', '/disconnect'):
            clean['command'] = first
        parts = text.split()
        if first == '/confirm' and len(parts) == 2 and re.fullmatch(r'[a-f0-9]{64}', parts[1]):
            clean['command'] = first
            clean['argument_hash'] = links.digest(parts[1])
    if (message['chat'].get('type') in ('group','supergroup') and clean['chat_id'] < 0
            and message['from'].get('is_bot') is False
            and (clean['topic_id'] is None or (message['chat']['type']=='supergroup' and message.get('is_topic_message') is True))
            and text in ('/register','/group_status')):
        clean['command'] = text
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
        if clean.get('group_event'):
            groups.handle_event(conn, clean, bot)
        cid, generation, permitted = identity(conn, clean['sender_id'])
        group_route = None
        if clean['command'] == '/register':
            groups.observe(conn, clean, bot, now)
        elif clean['command'] == '/group_status' and cid is not None and permitted:
            group_route = groups.route(conn, clean['chat_id'], clean['topic_id'], bot)
        command = clean['command']
        special = command == '/disconnect' or (storage.enabled('link') and command in ('/start','/confirm'))
        supported = command is not None and (permitted or special)
        if command in ('/register','/group_status'):
            supported = group_route is not None
        projection = {'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]}
        if supported and (special or command == '/status'):
            projection = {'kind': 'command', 'command': command, 'bot': bot[0], 'fingerprint': bot[2]}
            if command == '/confirm':
                projection['argument_hash'] = clean['argument_hash']
        if group_route:
            projection = {'kind': 'group_status', 'bot': bot[0], 'fingerprint': bot[2]}
        immediate_disconnect = supported and command == '/disconnect'
        if immediate_disconnect:
            linked = rows(conn, 'SELECT a.username FROM telegram_connection c JOIN admin_user a ON a.id=c.account_id WHERE c.telegram_user_id=? AND c.revoked_at IS NULL', (clean['sender_id'],))
            links.disconnect_in_transaction(conn, now=now, sender=clean['sender_id'])
            if linked:
                import storage as app_storage
                app_storage.audit(conn, linked[0]['username'], 'telegram_disconnect', summary='Disconnected private Telegram access from the bot.', commit=False)
        if group_route:
            projection['registration_id'] = group_route['id']
            projection['registration_generation'] = group_route['generation']
        payload = json.dumps(projection) if supported and not immediate_disconnect else None
        state = 'processed' if immediate_disconnect else ('queued' if supported else 'ignored')
        conn.execute('''INSERT INTO telegram_update
            (bot_identity,update_id,sender_id,chat_id,topic_id,connection_id,generation,
             payload_json,payload_hash,received_at,state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (bot[0], clean['update_id'], clean['sender_id'], clean['chat_id'], clean['topic_id'], cid,
             generation, payload, hashlib.sha256(raw).hexdigest(), stamp(now), state))
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
            normal = projection == {'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]}
            command = projection.get('command') if isinstance(projection, dict) else None
            command_shape = {'kind','command','bot','fingerprint'} | ({'argument_hash'} if command == '/confirm' else set())
            special = (isinstance(projection, dict) and set(projection) == command_shape
                       and projection.get('kind') == 'command' and projection.get('bot') == bot[0]
                       and projection.get('fingerprint') == bot[2]
                       and command in ('/start','/status','/confirm','/disconnect')
                       and update['chat_id'] == update['sender_id'] and update['chat_id'] > 0
                       and update['received_at'] > stamp(now-timedelta(minutes=10)))
            if special and command == '/disconnect':
                linked = rows(conn, 'SELECT a.username FROM telegram_connection c JOIN admin_user a ON a.id=c.account_id WHERE c.telegram_user_id=? AND c.revoked_at IS NULL', (update['sender_id'],))
                links.disconnect_in_transaction(conn, now=now, sender=update['sender_id'])
                if linked:
                    import storage as st
                    st.audit(conn, linked[0]['username'], 'telegram_disconnect', summary='Disconnected private Telegram access from the bot.', commit=False)
                projection, valid = None, False
            elif special and command == '/start' and storage.enabled('link'):
                projection = links.start(conn, update['sender_id'], bot, datetime.fromisoformat(update['received_at']))
                cid, generation, _permitted = identity(conn, update['sender_id'])
                valid = True
            elif special and command == '/confirm' and storage.enabled('link'):
                result = links.confirm(conn, update['sender_id'], projection.get('argument_hash'), bot, now)
                valid = result is not None
                if valid:
                    cid, generation = result
                    projection = {'kind': 'status', 'bot': bot[0], 'fingerprint': bot[2]}
            elif special and command == '/status':
                projection = {'kind': 'status', 'bot': bot[0], 'fingerprint': bot[2]}
            else:
                valid = valid and normal
            group_route = None
            if isinstance(projection, dict) and projection.get('kind') == 'group_status':
                group_route = groups.route(conn, update['chat_id'], update['topic_id'], bot)
                expected = {'kind': 'group_status', 'bot': bot[0], 'fingerprint': bot[2],
                            'registration_id': group_route['id'], 'registration_generation': group_route['generation']} if group_route else None
                valid = (permitted and cid is not None and cid == update['connection_id'] and generation == update['generation']
                         and update['received_at'] > stamp(now-timedelta(hours=24)) and group_route is not None and projection == expected)
                if valid:
                    projection = {'kind': 'group_status', 'bot': bot[0], 'fingerprint': bot[2]}
            if valid:
                conn.execute('''INSERT INTO telegram_delivery
                    (dedupe_key,event_key,connection_id,generation,chat_id,projection_json,expires_at,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING''',
                    ('help:' + str(update['id']), str(bot[0]), cid, generation, update['chat_id'],
                     json.dumps(projection), stamp(datetime.fromisoformat(update['received_at']) + timedelta(hours=24)), stamp(now), stamp(now)))
                if group_route:
                    conn.execute('''UPDATE telegram_delivery SET registration_id=?,registration_generation=?,topic_id=? WHERE dedupe_key=?''',
                        (group_route['id'], group_route['generation'], update['topic_id'], 'help:' + str(update['id'])))
            conn.execute('''UPDATE telegram_update SET state=?,payload_json=NULL,claim_token=NULL,lease_until=NULL,
                attempts=attempts+1,error_code=? WHERE id=?''',
                ('processed' if valid else 'cancelled', None if valid else 'ineligible', update['id']))
    return MAX_TICK


def eligible(conn, delivery, bot, now=None):
    try:
        projection = json.loads(delivery['projection_json'])
    except ValueError:
        return False
    if delivery['chat_id'] < 0:
        return groups.authorize_delivery(conn, delivery, bot) is not None
    cid, generation, permitted = identity(conn, delivery['chat_id'])
    linking = projection.get('kind') in ('link_code','link_confirm') if isinstance(projection, dict) else False
    if linking:
        permitted = links.render(conn, projection, delivery['chat_id'], bot, now or now_utc()) is not None
        cid, generation = delivery['connection_id'], delivery['generation']
    rejected = conn.execute('''SELECT 1 FROM telegram_delivery WHERE chat_id=?
        AND state='failed' AND error_code='provider_rejected' AND updated_at>=? LIMIT 1''',
        (delivery['chat_id'], delivery['created_at'])).fetchone()
    return (not rejected and delivery['chat_id'] > 0 and delivery['topic_id'] is None and delivery['registration_id'] is None
            and permitted and cid == delivery['connection_id'] and generation == delivery['generation']
            and (linking or projection in ({'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]},
                                          {'kind': 'status', 'bot': bot[0], 'fingerprint': bot[2]})))


def deliver(conn, now=None):
    if not storage.enabled('delivery'):
        return 0
    bot = transport.config()
    if not bot:
        return 0
    fixed_now = now
    clock = now_utc if fixed_now is None else lambda: fixed_now
    count = 0
    group_checks = 0
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
                WHERE (d.chat_id>0 OR ?<2) AND (d.state='queued' OR (d.state='retry_wait' AND d.retry_at<=?)
                    OR (d.state='claimed' AND d.lease_until<=?))
                AND NOT EXISTS (SELECT 1 FROM telegram_delivery busy WHERE busy.chat_id=d.chat_id
                    AND ((busy.state IN ('sending','claimed') AND busy.lease_until>?)
                    OR (busy.state='accepted' AND busy.updated_at>?)))
                ORDER BY d.id LIMIT 1''', (group_checks, stamp(now), stamp(now), stamp(now), stamp(now-timedelta(seconds=1))))
            if not found:
                break
            delivery = found[0]
            if delivery['expires_at'] <= stamp(now) or not eligible(conn, delivery, bot, now):
                conn.execute("UPDATE telegram_delivery SET state='cancelled',error_code='ineligible',updated_at=? WHERE id=?",
                             (stamp(now), delivery['id']))
                continue
            # Commit the sending marker before network I/O. Conditional finalizers fence restores.
            conn.execute('''UPDATE telegram_delivery SET state=?,claim_token=?,lease_until=?,
                attempts=attempts+1,updated_at=? WHERE id=?''',
                ('claimed' if delivery['chat_id'] < 0 else 'sending', token, stamp(now+timedelta(minutes=2)), stamp(now), delivery['id']))
        # Provider checks occur outside the writer lock; group reads remain unimplemented.
        group_verified = True
        if delivery['chat_id'] < 0:
            group_checks += 1
            group_verified = groups.verify_delivery(conn, delivery, bot)
            with transaction(conn):
                if (group_verified and storage.enabled('delivery') and transport.config() == bot
                        and eligible(conn, delivery, bot, clock()) and delivery['expires_at'] > stamp(clock())):
                    group_verified = conn.execute("UPDATE telegram_delivery SET state='sending' WHERE id=? AND state='claimed' AND claim_token=?",
                                                  (delivery['id'], token)).rowcount == 1
                else:
                    group_verified = False
                    conn.execute("UPDATE telegram_delivery SET state='cancelled',claim_token=NULL,lease_until=NULL,error_code='group_ineligible' WHERE id=? AND state='claimed' AND claim_token=?",
                                 (delivery['id'], token))
        # Recheck immediately before sending; an in-flight send cannot be recalled.
        current_bot = transport.config()
        if (not group_verified or not storage.enabled('delivery') or current_bot != bot or not eligible(conn, delivery, bot, clock())
                or delivery['expires_at'] <= stamp(clock())
                or not conn.execute("SELECT 1 FROM telegram_delivery WHERE id=? AND claim_token=? AND state='sending'",
                                    (delivery['id'], token)).fetchone()):
            outcome, message_id, retry = 'cancelled', None, None
        else:
            projection = json.loads(delivery['projection_json'])
            if projection['kind'] == 'group_status':
                message = groups.STATUS
            elif projection['kind'] == 'help':
                message = (HELP if not storage.enabled('link') else
                    'Office Connect private commands: /start to link, /status to check your connection, '
                    '/disconnect to revoke it. Never send your Office Connect password here.')
            else:
                message = links.render(conn, projection, delivery['chat_id'], bot, clock())
            if message:
                if delivery['chat_id'] < 0:
                    outcome, message_id, retry = transport.send(bot[1], delivery['chat_id'], message, delivery['topic_id'])
                else:
                    outcome, message_id, retry = transport.send(bot[1], delivery['chat_id'], message)
                count += 1
            else:
                outcome, message_id, retry = 'cancelled', None, None
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
        conn.execute('''UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL WHERE id IN
            (SELECT id FROM telegram_link_challenge WHERE expires_at<=? AND state IN ('issued','claimed') LIMIT 20)''',
            (stamp(now),))
        conn.execute('''DELETE FROM telegram_group_request WHERE id IN
            (SELECT id FROM telegram_group_request WHERE expires_at<? LIMIT 20)''',
            (stamp(now-timedelta(days=1)),))
        conn.execute('''DELETE FROM telegram_link_challenge WHERE id IN
            (SELECT id FROM telegram_link_challenge WHERE expires_at<? LIMIT 20)''',
            (stamp(now-timedelta(days=1)),))
        conn.execute('''DELETE FROM telegram_delivery WHERE id IN (SELECT id FROM telegram_delivery
            WHERE state IN ('accepted','failed','uncertain','cancelled') AND updated_at<? LIMIT 20)''',
            (stamp(now-timedelta(days=180)),))


def tick(conn, now=None):
    processed = process_updates(conn, now or now_utc())
    sent = deliver(conn, now)
    cleanup(conn, now or now_utc())
    return processed, sent
