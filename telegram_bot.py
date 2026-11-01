"""Authenticated Telegram commands and current private reads; no business mutations."""
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import time
from threading import Lock
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
import telegram_calendar as calendar_reads
import telegram_rooms as room_reads
import telegram_work as work_lookup
import telegram_group_reads as shared_reads
import telegram_actions
import telegram_meetings as meetings
import telegram_notices as notices
import telegram_reminders as reminders
import telegram_room_requests

PATH = '/integrations/telegram/webhook'
MAX_BODY = 65536
MAX_TICK = 20
HELP = ('Office Connect Telegram help: /start and /help are available in this private chat. '
        'Account linking, calendar access and actions are not available yet. '
        'Use your usual signed-in Office Connect page for office work.')

_WORKER_LOCK = Lock()
_WORKER = {'state': 'not_started', 'started_at': None, 'finished_at': None,
           'stage': None, 'error': None, 'location': None, 'processed': 0, 'sent': 0}
_WORKER_STARTED = None


def worker_failed(stage, error):
    """Expose a fixed failure category, never exception text, SQL or a traceback."""
    category = ('database_error' if isinstance(error, sqlite3.Error) else
                'configuration_error' if isinstance(error, ValueError) else 'worker_error')
    location = None
    frame = error.__traceback__
    while frame is not None:
        filename = os.path.abspath(frame.tb_frame.f_code.co_filename)
        if os.path.dirname(filename) == os.path.dirname(os.path.abspath(__file__)):
            name = os.path.basename(filename)
            if re.fullmatch(r'[a-z_]+\.py', name):
                location = name + ':' + str(frame.tb_lineno)
        frame = frame.tb_next
    with _WORKER_LOCK:
        _WORKER.update(state='failed', stage=stage, error=category, location=location, finished_at=stamp(now_utc()))
    logging.getLogger(__name__).warning('Telegram worker failed: stage=%s category=%s location=%s', stage, category, location)


def worker_status(conn):
    """Read-only operations summary; no identities, descriptors or credentials."""
    with _WORKER_LOCK:
        status = dict(_WORKER)
        status['stale'] = _WORKER_STARTED is not None and time.monotonic() - _WORKER_STARTED > 180
    status.update(scheduler_disabled=os.environ.get('CSS_NO_SCHEDULER') == '1',
                  switches={name: storage.enabled(name) for name in storage.SWITCHES},
                  bot_configured=transport.config() is not None,
                  webhook_configured=webhook_secret() is not None,
                  reply_transport=reply_transport(),
                  link_origin_configured=links.origin() is not None,
                  provider=transport.last_send_status(), network=transport.last_connection_probe())
    try:
        status['updates'] = dict(conn.execute('SELECT state,count(*) FROM telegram_update GROUP BY state'))
        status['deliveries'] = dict(conn.execute('SELECT state,count(*) FROM telegram_delivery GROUP BY state'))
        status['webhook_responses'] = conn.execute("SELECT count(*) FROM telegram_delivery WHERE error_code='webhook_response'").fetchone()[0]
        status['queue_available'] = True
    except sqlite3.Error:
        status.update(updates={}, deliveries={}, queue_available=False)
    return status


def now_utc():
    return datetime.now(timezone.utc)


def reply_transport():
    return 'direct' if os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT') == 'direct' else 'webhook'


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
        if text in ('/meeting','/room_request'):
            clean['command']=text
        parts = text.split()
        if len(parts)==2 and parts[0] in ('/meeting_confirm','/room_confirm') and re.fullmatch('[A-Za-z0-9_-]{43}',parts[1]):
            clean['command']=parts[0];clean['meeting_argument']=links.digest(parts[1])
        if len(parts)==2 and parts[0] in ('/meeting_receipt','/room_receipt') and re.fullmatch('[a-f0-9]{32}',parts[1]):
            clean['command']=parts[0];clean['meeting_argument']=parts[1]
        if first in ('/calendar', '/calendar_next'):
            clean['command'] = first
            try:
                clean['calendar_query'] = calendar_reads.parse(text, now_utc())
            except ValueError:
                clean['calendar_query'] = {'error': 'usage'}
        if first in ('/room_slots','/my_rooms','/room_status'):
            clean['command'] = first
            try:
                clean['room_query'] = room_reads.parse(text, now_utc())
            except ValueError:
                clean['room_query'] = {'error': 'usage'}
        if first in work_lookup.COMMANDS:
            clean['command'] = first
            try:
                clean['work_query'] = work_lookup.parse(text)
            except ValueError:
                clean['work_query'] = {'error': 'usage'}
        if first == '/confirm' and len(parts) == 2 and re.fullmatch(r'[a-f0-9]{64}', parts[1]):
            clean['command'] = first
            clean['argument_hash'] = links.digest(parts[1])
    if (message['chat'].get('type') in ('group','supergroup') and clean['chat_id'] < 0
            and message['from'].get('is_bot') is False
            and (clean['topic_id'] is None or (message['chat']['type']=='supergroup' and message.get('is_topic_message') is True))
            and text in ('/register','/group_status','/meeting','/room_request')):
        clean['command'] = text
    if (message['chat'].get('type') in ('group','supergroup') and clean['chat_id']<0
            and message['from'].get('is_bot') is False
            and (clean['topic_id'] is None or (message['chat']['type']=='supergroup' and message.get('is_topic_message') is True))
            and text.split() and text.split()[0] in ('/group_calendar','/group_rooms')):
        clean['command']=text.split()[0]
        try:
            clean['shared_query']=shared_reads.parse(text,now_utc())
        except ValueError:
            clean['shared_query']={'error':'usage','mode':'rooms'} if clean['command']=='/group_rooms' else {'error':'usage'}
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


def receive(conn, clean, raw, bot, now, webhook_reply=None):
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
        if clean['command'] in ('/meeting','/room_request','/meeting_confirm','/meeting_receipt','/room_confirm','/room_receipt'):
            projection=None;state='ignored'
            try:
                connection=rows(conn,'SELECT * FROM telegram_connection WHERE id=?',(cid,))[0]
                if clean['command'] in ('/meeting','/room_request'):
                    action='calendar.create' if clean['command']=='/meeting' else 'rooms.request'
                    meetings.observe(conn,clean,connection,bot,now,action);state='processed'
                else:
                    projection=meetings.intake_action(conn,clean,connection,bot,now);state='queued'
            except (ValueError,IndexError):
                pass
            conn.execute('''INSERT INTO telegram_update
                (bot_identity,update_id,sender_id,chat_id,topic_id,connection_id,generation,payload_json,payload_hash,received_at,state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(bot[0],clean['update_id'],clean['sender_id'],clean['chat_id'],clean['topic_id'],cid,generation,
                    json.dumps(projection) if projection else None,hashlib.sha256(raw).hexdigest(),stamp(now),state))
            return 200
        group_route = None
        if clean['command'] == '/register':
            groups.observe(conn, clean, bot, now)
        elif clean['command'] in ('/group_status','/group_calendar','/group_rooms') and cid is not None and permitted:
            group_route = groups.route(conn, clean['chat_id'], clean['topic_id'], bot)
        command = clean['command']
        special = command == '/disconnect' or (storage.enabled('link') and command in ('/start','/confirm'))
        if command == '/status' and links.pending_confirmation(conn, clean['sender_id'], bot, now):
            special = True
        supported = command is not None and (permitted or special)
        if command in ('/register','/group_status','/group_calendar','/group_rooms'):
            supported = group_route is not None
        projection = {'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]}
        if supported and (special or command == '/status'):
            projection = {'kind': 'command', 'command': command, 'bot': bot[0], 'fingerprint': bot[2]}
            if command == '/confirm':
                projection['argument_hash'] = clean['argument_hash']
        if command in ('/calendar','/calendar_next'):
            context = {'connection_id': cid, 'generation': generation, 'chat_id': clean['chat_id'],
                       'topic_id': clean['topic_id'], 'registration_id': None}
            supported = cid is not None and permitted and calendar_reads.actor(conn, context, bot) is not None
            projection = {'kind': 'calendar', 'bot': bot[0], 'fingerprint': bot[2], 'query': clean['calendar_query']}
        if command in ('/room_slots','/my_rooms','/room_status'):
            context = {'connection_id': cid, 'generation': generation, 'chat_id': clean['chat_id'],
                       'topic_id': clean['topic_id'], 'registration_id': None}
            supported = cid is not None and permitted and room_reads.actor(conn, context, bot) is not None
            projection = {'kind': 'rooms', 'bot': bot[0], 'fingerprint': bot[2], 'query': clean['room_query']}
        if command in work_lookup.COMMANDS:
            context = {'connection_id': cid, 'generation': generation, 'chat_id': clean['chat_id'],
                       'topic_id': clean['topic_id'], 'registration_id': None}
            supported = cid is not None and permitted and work_lookup.actor(conn, context, bot) is not None
            projection = {'kind': 'work', 'bot': bot[0], 'fingerprint': bot[2], 'query': clean['work_query']}
        if group_route:
            projection = {'kind': 'group_status', 'bot': bot[0], 'fingerprint': bot[2]}
        immediate_disconnect = supported and command == '/disconnect'
        if immediate_disconnect:
            linked = rows(conn, 'SELECT a.username FROM telegram_connection c JOIN admin_user a ON a.id=c.account_id WHERE c.telegram_user_id=? AND c.revoked_at IS NULL', (clean['sender_id'],))
            links.disconnect_in_transaction(conn, now=now, sender=clean['sender_id'])
            if linked:
                import storage as app_storage
                app_storage.audit(conn, linked[0]['username'], 'telegram_disconnect', summary='Disconnected private Telegram access from the bot.', commit=False)
        if group_route and command in ('/group_calendar','/group_rooms'):
            projection={'kind':'group_read','bot':bot[0],'fingerprint':bot[2],'query':clean['shared_query']}
            context={'chat_id':clean['chat_id'],'topic_id':clean['topic_id'],'connection_id':cid,'generation':generation,
                     'registration_id':group_route['id'],'registration_generation':group_route['generation'],
                     'projection_json':json.dumps(projection)}
            supported=groups.authorize_delivery(conn,context,bot) is not None
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
        if webhook_reply is not None:
            packet = prepare_webhook_reply(conn, clean, bot, now)
            if packet:
                webhook_reply.append(packet)
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
        reply = []
        try:
            conn = get_conn()
            inline = reply_transport() == 'webhook'
            status = receive(conn, clean, body, bot, now_utc(), reply if inline else None)
        except sqlite3.Error:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503)
        finally:
            if conn is not None:
                conn.close()
        if reply and status == 200:
            return JSONResponse(reply[0], headers={'Cache-Control': 'no-store'})
        return JSONResponse({'ok': status == 200}, status_code=status,
                            headers={'Retry-After': '60'} if status == 429 else None)

    return router


def prepare_webhook_reply(conn, clean, bot, now):
    """One private command, atomically consumed before its webhook response.

    Telegram does not return a result for webhook-embedded requests. Persist an
    uncertain handoff, never an accepted delivery and never an automatic resend.
    Only this authenticated update can supply the destination; no backlog drains.
    """
    if (not storage.enabled('inbound') or not storage.enabled('delivery')
            or transport.config() != bot or clean['chat_id'] != clean['sender_id']
            or not clean['chat_id'] or clean['chat_id'] < 0 or clean['topic_id'] is not None
            or clean['command'] not in ('/start', '/help', '/status', '/confirm',
                '/calendar', '/calendar_next', '/room_slots', '/my_rooms', '/room_status',
                *work_lookup.COMMANDS)):
        return None
    found = rows(conn, 'SELECT * FROM telegram_update WHERE bot_identity=? AND update_id=?',
                 (bot[0], clean['update_id']))
    if not found or found[0]['state'] != 'queued':
        return None
    update = found[0]
    _process_update_in_transaction(conn, update, bot, now)
    found = rows(conn, "SELECT * FROM telegram_delivery WHERE dedupe_key=? AND state='queued' AND attempts=0",
                 ('help:' + str(update['id']),))
    if not found:
        return None
    delivery = found[0]
    projection = json.loads(delivery['projection_json'])
    message = render_delivery(conn, delivery, projection, bot, now, commit=False) if eligible(conn, delivery, bot, now) else None
    if (not message or delivery['chat_id'] != clean['chat_id'] or delivery['expires_at'] <= stamp(now)
            or not storage.enabled('inbound') or not storage.enabled('delivery') or transport.config() != bot
            or not eligible(conn, delivery, bot, now)):
        conn.execute("UPDATE telegram_delivery SET state='cancelled',error_code='ineligible',updated_at=? WHERE id=?",
                     (stamp(now), delivery['id']))
        return None
    consumed = conn.execute("""UPDATE telegram_delivery SET state='uncertain',attempts=attempts+1,
        error_code='webhook_response',updated_at=? WHERE id=? AND state='queued' AND attempts=0""",
        (stamp(now), delivery['id'])).rowcount
    if consumed != 1:
        return None
    return {'method': 'sendMessage', 'chat_id': delivery['chat_id'], 'text': message,
            'link_preview_options': {'is_disabled': True}}


def process_updates(conn, now):
    if not storage.enabled('inbound'):
        return 0
    bot = transport.config()
    if not bot:
        return 0
    group_actions=0;started=time.monotonic()
    for _ in range(MAX_TICK):
        handled=meetings.process_one(conn,now+timedelta(seconds=time.monotonic()-started),allow_group=group_actions<2)
        if handled=='defer':return _
        if handled:
            group_actions+=handled=='group'
            continue
        with transaction(conn):
            found = rows(conn, '''SELECT * FROM telegram_update WHERE state='queued'
                OR (state='processing' AND lease_until<=?) ORDER BY id LIMIT 1''', (stamp(now),))
            if not found:
                return _
            update = found[0]
            _process_update_in_transaction(conn, update, bot, now)
    return MAX_TICK


def _process_update_in_transaction(conn, update, bot, now):
    """Apply one queued projection under the caller's writer transaction."""
    cid, generation, permitted = identity(conn, update['sender_id'])
    valid = (permitted and cid == update['connection_id'] and generation == update['generation']
             and update['bot_identity'] == bot[0] and update['received_at'] > stamp(now - timedelta(hours=24)))
    try:
        projection = json.loads(update['payload_json'] or '{}')
    except ValueError:
        projection = {}
    if isinstance(projection,dict) and projection.get('kind')=='meeting_action':
        return  # The action worker owns this update.
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
        pending = links.pending_confirmation(conn, update['sender_id'], bot, now)
        projection = pending or {'kind': 'status', 'bot': bot[0], 'fingerprint': bot[2]}
        if pending:
            valid = True
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
    if isinstance(projection,dict) and projection.get('kind')=='group_read':
        projection=dict(projection)
        reg_id=projection.pop('registration_id',None);reg_gen=projection.pop('registration_generation',None)
        context={**update,'registration_id':reg_id,'registration_generation':reg_gen,
                 'projection_json':json.dumps(projection)}
        authorized=groups.authorize_delivery(conn,context,bot)
        group_route=authorized[0] if authorized else None
        valid=(group_route is not None and cid==update['connection_id'] and generation==update['generation']
               and update['received_at']>stamp(now-timedelta(hours=24)))
    if calendar_reads.descriptor(projection, bot):
        context = {'connection_id': cid, 'generation': generation, 'chat_id': update['chat_id'],
                   'topic_id': update['topic_id'], 'registration_id': None}
        valid = (cid is not None and cid == update['connection_id'] and generation == update['generation']
                 and update['received_at'] > stamp(now-timedelta(hours=24))
                 and calendar_reads.actor(conn, context, bot) is not None)
    if room_reads.descriptor(projection, bot):
        context = {'connection_id': cid, 'generation': generation, 'chat_id': update['chat_id'],
                   'topic_id': update['topic_id'], 'registration_id': None}
        valid = (cid is not None and cid == update['connection_id'] and generation == update['generation']
                 and update['received_at'] > stamp(now-timedelta(hours=24))
                 and room_reads.actor(conn, context, bot) is not None)
    if work_lookup.descriptor(projection, bot):
        context = {'connection_id': cid, 'generation': generation, 'chat_id': update['chat_id'],
                   'topic_id': update['topic_id'], 'registration_id': None}
        valid = (cid is not None and cid == update['connection_id'] and generation == update['generation']
                 and update['received_at'] > stamp(now-timedelta(hours=24))
                 and work_lookup.actor(conn, context, bot) is not None)
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


def eligible(conn, delivery, bot, now=None):
    try:
        projection = json.loads(delivery['projection_json'])
    except ValueError:
        return False
    if isinstance(projection,dict) and projection.get('kind')==reminders.KIND:
        return reminders.allowed(conn,delivery,projection,bot,now or now_utc()) is not None
    if isinstance(projection,dict) and projection.get('kind')==notices.KIND:
        return notices.allowed(conn,delivery,projection,bot,now or now_utc()) is not None
    if delivery['chat_id'] < 0:
        return groups.authorize_delivery(conn, delivery, bot) is not None
    cid, generation, permitted = identity(conn, delivery['chat_id'])
    calendar_lookup = calendar_reads.descriptor(projection, bot) and calendar_reads.actor(conn, delivery, bot) is not None
    room_lookup = room_reads.descriptor(projection, bot) and room_reads.actor(conn, delivery, bot) is not None
    work_read = work_lookup.descriptor(projection, bot) and work_lookup.actor(conn, delivery, bot) is not None
    meeting_lookup = meetings.delivery_context(conn,delivery,projection,now or now_utc()) is not None
    linking = projection.get('kind') in ('link_code','link_confirm') if isinstance(projection, dict) else False
    if linking:
        permitted = links.render(conn, projection, delivery['chat_id'], bot, now or now_utc()) is not None
        cid, generation = delivery['connection_id'], delivery['generation']
    rejected = conn.execute('''SELECT 1 FROM telegram_delivery WHERE chat_id=?
        AND state='failed' AND error_code='provider_rejected' AND updated_at>=? LIMIT 1''',
        (delivery['chat_id'], delivery['created_at'])).fetchone()
    return (not rejected and delivery['chat_id'] > 0 and delivery['topic_id'] is None and delivery['registration_id'] is None
            and permitted and cid == delivery['connection_id'] and generation == delivery['generation']
            and (work_read or meeting_lookup or room_lookup or calendar_lookup or linking or projection in ({'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]},
                                          {'kind': 'status', 'bot': bot[0], 'fingerprint': bot[2]})))


def render_delivery(conn, delivery, projection, bot, now, *, commit=True):
    """Render current authorized content without calling a provider."""
    if projection['kind']==reminders.KIND:
        message=reminders.render(conn,delivery,projection,bot,now)
    elif projection['kind']==notices.KIND:
        message=notices.render(conn,delivery,projection,bot,now)
    elif projection['kind'] in meetings.KINDS:
        try:
            message = meetings.render(conn,delivery,projection,now)
        except ValueError:
            message = None
    elif projection['kind'] == 'calendar':
        message = (calendar_reads.render(conn, delivery, projection, bot, now) if commit else
                   calendar_reads.render(conn, delivery, projection, bot, now, commit=False))
    elif projection['kind'] == 'work':
        message = work_lookup.render(conn, delivery, projection, bot, now, commit=commit)
    elif projection['kind'] == 'rooms':
        message = (room_reads.render(conn, delivery, projection, bot, now) if commit else
                   room_reads.render(conn, delivery, projection, bot, now, commit=False))
    elif projection['kind'] == 'group_read':
        message = shared_reads.render(conn, delivery, projection, bot, now)
    elif projection['kind'] == 'group_status':
        message = groups.STATUS
    elif projection['kind'] == 'help':
        message = (HELP if not storage.enabled('link') else
            'Office Connect private commands: /start to link, /status to check your connection, '
            '/disconnect to revoke it. Never send your Office Connect password here.'
            + (' Private calendar lookup: /calendar (Asia/Manila).' if storage.enabled('calendar_read') else '')
            + (' Private work lookup: /my_tasks, /task_status WORK_ID TASK_ID, /my_work, /work_status WORK_ID (separate work read consent).' if storage.enabled('work_read') else '')
            + (' Private room lookup: /room_slots, /my_rooms, /room_status REFERENCE.' if storage.enabled('rooms_read') else '')
            + (' Guided meeting pilot: /meeting (separate read/create consent required).' if storage.enabled('calendar_create') else '')
            + (' Linked room request pilot: /room_request (separate room request/read and calendar read consent).' if storage.enabled('rooms_request') else ''))
    else:
        message = links.render(conn, projection, delivery['chat_id'], bot, now)
    return message


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
                AND (d.not_before IS NULL OR d.not_before<=?)
                AND NOT EXISTS (SELECT 1 FROM telegram_delivery busy WHERE busy.chat_id=d.chat_id
                    AND ((busy.state IN ('sending','claimed') AND busy.lease_until>?)
                    OR (busy.state='accepted' AND busy.updated_at>?)))
                ORDER BY d.id LIMIT 1''', (group_checks, stamp(now), stamp(now), stamp(now), stamp(now), stamp(now-timedelta(seconds=1))))
            if not found:
                break
            delivery = found[0]
            if delivery['expires_at']>stamp(now) and (notices.defer(conn,delivery,bot,now) or reminders.defer(conn,delivery,bot,now)):continue
            if delivery['expires_at'] <= stamp(now) or not eligible(conn, delivery, bot, now):
                conn.execute("UPDATE telegram_delivery SET state='cancelled',error_code='ineligible',updated_at=? WHERE id=?",
                             (stamp(now), delivery['id']))
                continue
            # Commit the sending marker before network I/O. Conditional finalizers fence restores.
            conn.execute('''UPDATE telegram_delivery SET state=?,claim_token=?,lease_until=?,
                attempts=attempts+1,updated_at=? WHERE id=?''',
                ('claimed' if delivery['chat_id'] < 0 else 'sending', token, stamp(now+timedelta(minutes=2)), stamp(now), delivery['id']))
        # Provider checks occur outside the writer lock.
        group_verified = True
        if delivery['chat_id'] < 0:
            group_checks += 1
            projection=json.loads(delivery['projection_json'])
            group_verified = (notices.verify_delivery(conn,delivery,bot,clock()) if projection.get('kind')==notices.KIND
                              else groups.verify_delivery(conn, delivery, bot))
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
            message = render_delivery(conn, delivery, projection, bot, clock())
            # Rendering can race with disconnect/config changes; fence again at the I/O boundary.
            if message and (not storage.enabled('delivery') or transport.config()!=bot
                    or not eligible(conn, delivery, bot, clock())
                    or not conn.execute("SELECT 1 FROM telegram_delivery WHERE id=? AND state='sending' AND claim_token=?",
                                        (delivery['id'], token)).fetchone()):
                message = None
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
            finalized=conn.execute('''UPDATE telegram_delivery SET state=?,provider_message_id=?,retry_at=?,
                claim_token=NULL,lease_until=NULL,error_code=?,updated_at=?
                WHERE id=? AND state='sending' AND claim_token=?''',
                (outcome, message_id, stamp(now+timedelta(seconds=retry)) if retry else None,
                 None if outcome == 'accepted' else error_code, stamp(now), delivery['id'], token)).rowcount
            if finalized and error_code=='provider_rejected':notices.record_rejection(conn,delivery,now)
    return count


def cleanup(conn, now):
    with transaction(conn):
        import telegram_changes
        telegram_changes.cleanup_in_transaction(conn,now)
        notices.cleanup_in_transaction(conn,now)
        reminders.cleanup_in_transaction(conn,now)
        telegram_actions.cleanup_in_transaction(conn,now)
        conn.execute('DELETE FROM telegram_meeting_origin WHERE id IN (SELECT id FROM telegram_meeting_origin WHERE expires_at<? LIMIT 20)',(stamp(now-timedelta(days=1)),))
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
    global _WORKER_STARTED
    processed = sent = 0
    with _WORKER_LOCK:
        _WORKER_STARTED = time.monotonic()
        _WORKER.update(state='running', started_at=stamp(now_utc()), finished_at=None,
                       stage='updates', error=None, location=None, processed=0, sent=0)
    def prepare_changes():
        import telegram_changes
        return telegram_changes.prepare_routes(conn, now or now_utc())

    stages = (
        ('updates', lambda: process_updates(conn, now or now_utc())),
        ('change_routes', prepare_changes),
        ('change_notices', lambda: notices.enqueue(conn, now or now_utc())),
        ('reminders', lambda: reminders.enqueue(conn, now or now_utc())),
        ('delivery', lambda: deliver(conn, now)),
        ('cleanup', lambda: cleanup(conn, now or now_utc())),
    )
    for stage, action in stages:
        with _WORKER_LOCK:
            _WORKER['stage'] = stage
        try:
            result = action()
        except Exception as error:
            worker_failed(stage, error)
            raise  # Preserve transaction/retry semantics; the scheduler isolates jobs.
        if stage in ('updates', 'delivery'):
            if stage == 'updates':
                processed = result
            else:
                sent = result
            with _WORKER_LOCK:
                _WORKER['processed' if stage == 'updates' else 'sent'] = result
    with _WORKER_LOCK:
        _WORKER.update(state='finished', stage=None, finished_at=stamp(now_utc()),
                       processed=processed, sent=sent)
    if processed or sent:
        logging.getLogger(__name__).info('Telegram worker completed: processed=%s attempted=%s', processed, sent)
    return processed, sent
