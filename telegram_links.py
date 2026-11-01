"""Two-step private account linking; raw codes are derived only at delivery time."""
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import auth
from documents_storage import rows, transaction
import storage as st
import telegram_storage as switches
import telegram_transport as transport

SCOPES = {'calendar.read': 'Read permitted calendar entries', 'rooms.read': 'Read room availability and own requests', 'calendar.create':'Create one meeting after an exact private preview and confirmation', 'rooms.request':'Request a room for my permitted meeting after private confirmation', 'travel.read': 'Read my travel filing checklist and status in private', 'meals.read': 'Read my meal request status in private', 'arrangements.read': 'Read my work-arrangement filing status in private', 'supplies.read': 'Read my supply request approval and collection status in private', 'documents.read': 'Read permitted document metadata and status in private', 'work.read': 'Read my tasks and permitted work status in private', 'tasks.acknowledge': 'Acknowledge my task after private confirmation', 'tasks.submit': 'Submit my task for review after private confirmation'}
SCOPES.update({'calendar.reschedule':'Reschedule my own meeting after private preview and confirmation',
               'calendar.cancel':'Cancel my own meeting after private preview and confirmation'})
SCOPES.update({'rooms.withdraw':'Withdraw my own room request after private preview and confirmation',
               'rooms.move':'Move my own room request date after private preview and confirmation'})
SCOPES['tasks.create']='Propose a task in permitted work after private preview and confirmation'


def stamp(now):
    return now.isoformat(timespec='seconds')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def code(challenge, phase):
    key = os.environ.get('CSS_TELEGRAM_WEBHOOK_SECRET', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', key):
        raise ValueError('Telegram linking is unavailable.')
    return hmac.new(key.encode(), ('telegram-link:' + phase + ':' + challenge['id']).encode(), hashlib.sha256).hexdigest()


def origin():
    value = os.environ.get('CSS_BASE_URL', '')
    try:
        parsed = urlsplit(value)
        parsed.port
        if (parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
                and parsed.path in ('','/') and not parsed.query and not parsed.fragment
                and not any(ord(c) <= 32 or c in '<>"\\' for c in value)):
            return value.rstrip('/')
    except ValueError:
        pass
    return None


def available():
    return (switches.enabled('link') and origin() and transport.config() is not None
            and re.fullmatch(r'[A-Za-z0-9_-]{32,256}', os.environ.get('CSS_TELEGRAM_WEBHOOK_SECRET','')) is not None)


def current(conn, payload):
    user = st.session_actor(conn, payload) if payload else None
    if not user or not auth.valid_role(user['role']):
        raise ValueError('A current signed-in account is required.')
    return user


def challenge_live(challenge, bot, now):
    try:
        return (available() and challenge['expires_at'] > stamp(now)
                and challenge['bot_identity'] == bot[0] and challenge['bot_fingerprint'] == bot[2]
                and hmac.compare_digest(challenge['token_hash'], digest(code(challenge, 'claim'))))
    except ValueError:
        return False


def start(conn, sender, bot, now):
    """Called within the update's transaction. No grant or connection is created."""
    if not available():
        return {'kind': 'help', 'bot': bot[0], 'fingerprint': bot[2]}
    # Both sides must explicitly disconnect before replacing an existing binding.
    if conn.execute('SELECT 1 FROM telegram_connection WHERE telegram_user_id=? AND revoked_at IS NULL', (sender,)).fetchone():
        return {'kind': 'status', 'bot': bot[0], 'fingerprint': bot[2]}
    conn.execute("UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL WHERE telegram_user_id=? AND state IN ('issued','claimed')", (sender,))
    challenge = {'id': secrets.token_hex(32)}
    token_hash, confirm_hash = digest(code(challenge, 'claim')), digest(code(challenge, 'confirm'))
    conn.execute('''INSERT INTO telegram_link_challenge
        (id,token_hash,confirm_hash,telegram_user_id,private_chat_id,bot_identity,bot_fingerprint,
         state,created_at,expires_at) VALUES (?,?,?,?,?,?,?,'issued',?,?)''',
        (challenge['id'], token_hash, confirm_hash, sender, sender, bot[0], bot[2], stamp(now), stamp(now+timedelta(minutes=10))))
    return {'kind': 'link_code', 'challenge': challenge['id'], 'bot': bot[0], 'fingerprint': bot[2]}


def claim(conn, payload, raw_code, scopes, now):
    if not re.fullmatch(r'[a-f0-9]{64}', raw_code) or not set(scopes) <= SCOPES.keys():
        raise ValueError('That code or permission choice is invalid. Start again in your private bot chat.')
    if 'calendar.create' in scopes and ('calendar.read' not in scopes or not switches.enabled('calendar_create')):
        raise ValueError('Meeting creation requires its pilot and separate calendar read consent.')
    for action in ('calendar.reschedule','calendar.cancel'):
        if action in scopes and ('calendar.read' not in scopes or not switches.enabled(action.replace('.','_'))):
            raise ValueError('Meeting management requires its separate pilot and calendar read consent.')
    for action in ('rooms.withdraw','rooms.move'):
        if action in scopes and ('rooms.read' not in scopes or not switches.enabled(action.replace('.','_'))):
            raise ValueError('Room management requires its separate pilot and room read consent.')
    if 'rooms.request' in scopes and (not {'calendar.read','rooms.read'}<=set(scopes) or not switches.enabled('rooms_request')):
        raise ValueError('Room requests require their pilot and separate calendar and room read consent.')
    for action in ('tasks.acknowledge','tasks.submit','tasks.create'):
        if action in scopes and ('work.read' not in scopes or not switches.enabled(action.replace('.','_'))):
            raise ValueError('Task actions require their pilot and separate work read consent.')
    with transaction(conn):
        user = current(conn, payload)
        found = rows(conn, 'SELECT * FROM telegram_link_challenge WHERE token_hash=?', (digest(raw_code),))
        bot = transport.config()
        if not found or not bot or not challenge_live(found[0], bot, now) or found[0]['state'] != 'issued':
            raise ValueError('That code expired or was already used. Start again in your private bot chat.')
        ch = found[0]
        if conn.execute('SELECT 1 FROM telegram_connection WHERE revoked_at IS NULL AND (account_id=? OR telegram_user_id=?)',
                        (user['id'], ch['telegram_user_id'])).fetchone():
            raise ValueError('Disconnect the existing Telegram connection before linking another.')
        conn.execute("UPDATE telegram_link_challenge SET state='claimed',account_id=?,session_id=?,scopes_json=?,claimed_at=? WHERE id=?",
                     (user['id'], payload['sid'], json.dumps(sorted(set(scopes))), stamp(now), ch['id']))
        projection = {'kind': 'link_confirm', 'challenge': ch['id'], 'bot': bot[0], 'fingerprint': bot[2]}
        if os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT') == 'direct':
            conn.execute('''INSERT INTO telegram_delivery
                (dedupe_key,event_key,chat_id,projection_json,expires_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)''', ('link-confirm:'+ch['id'], str(bot[0]), ch['private_chat_id'],
                    json.dumps(projection), ch['expires_at'], stamp(now), stamp(now)))
        st.audit(conn, user['username'], 'telegram_link_claim', summary='Requested a private Telegram account link.', commit=False)


def confirm(conn, sender, argument_hash, bot, now):
    """Called under update writer lock; both Telegram sender and browser session remain current."""
    found = rows(conn, 'SELECT * FROM telegram_link_challenge WHERE confirm_hash=?', (argument_hash,))
    if not found:
        return None
    ch = found[0]
    if (ch['state'] != 'claimed' or ch['telegram_user_id'] != sender or not challenge_live(ch, bot, now)):
        return None
    try:
        user = current(conn, {'uid': ch['account_id'], 'sid': ch['session_id']})
    except ValueError:
        return None
    if conn.execute('SELECT 1 FROM telegram_connection WHERE revoked_at IS NULL AND (account_id=? OR telegram_user_id=?)',
                    (user['id'], sender)).fetchone():
        return None
    if 'calendar.create' in json.loads(ch['scopes_json']) and not switches.enabled('calendar_create'):
        return None
    if 'rooms.request' in json.loads(ch['scopes_json']) and not switches.enabled('rooms_request'):
        return None
    if any(scope in json.loads(ch['scopes_json']) and not switches.enabled(scope.replace('.','_')) for scope in ('calendar.reschedule','calendar.cancel','rooms.withdraw','rooms.move','tasks.create')):
        return None
    cid, generation = conn.execute('''INSERT INTO telegram_connection
        (account_id,telegram_user_id,private_chat_id,bot_identity,bot_fingerprint,state,created_at,updated_at)
        VALUES (?,?,?,?,?,'active',?,?) RETURNING id,generation''', (user['id'], sender, sender, bot[0], bot[2], stamp(now), stamp(now))).fetchone()
    for scope in json.loads(ch['scopes_json']):
        conn.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''', (cid, user['id'], scope, generation, bot[0], bot[2], stamp(now)))
    conn.execute("UPDATE telegram_link_challenge SET state='confirmed',session_id=NULL,consumed_at=? WHERE id=?", (stamp(now), ch['id']))
    # Invalidate competing challenges for either side, not just the claimed code.
    conn.execute("UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL WHERE id<>? AND state IN ('issued','claimed') AND (account_id=? OR telegram_user_id=?)",
                 (ch['id'], user['id'], sender))
    st.audit(conn, user['username'], 'telegram_link_confirm', summary='Confirmed a private Telegram account link.', commit=False)
    return cid, generation


def disconnect_in_transaction(conn, *, now, account_id=None, sender=None):
    if (account_id is None) == (sender is None):
        raise ValueError('Choose one identity')
    clause, value = ('account_id', account_id) if account_id is not None else ('telegram_user_id', sender)
    links = rows(conn, 'SELECT * FROM telegram_connection WHERE '+clause+'=? AND revoked_at IS NULL', (value,))
    senders = {link['telegram_user_id'] for link in links}
    if sender is not None:
        senders.add(sender)
    # A pending browser claim also belongs to the account before a connection exists.
    senders.update(row[0] for row in conn.execute('SELECT telegram_user_id FROM telegram_link_challenge WHERE '+clause+"=? AND state IN ('issued','claimed')", (value,)))
    conn.execute("UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL WHERE "+clause+"=? AND state IN ('issued','claimed')", (value,))
    for link in links:
        conn.execute("UPDATE telegram_connection SET state='revoked',generation=lower(hex(randomblob(16))),revoked_at=?,updated_at=? WHERE id=?",
                     (stamp(now), stamp(now), link['id']))
        conn.execute('UPDATE telegram_grant SET revoked_at=COALESCE(revoked_at,?) WHERE connection_id=?', (stamp(now), link['id']))
        conn.execute("UPDATE telegram_operation SET state='cancelled',result_code='disconnected',updated_at=? WHERE connection_id=? AND state='pending'", (stamp(now), link['id']))
    for target in senders:
        conn.execute("UPDATE telegram_update SET state='cancelled',payload_json=NULL,claim_token=NULL,lease_until=NULL,error_code='disconnected' WHERE sender_id=? AND state IN ('queued','processing')", (target,))
        conn.execute("""UPDATE telegram_delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END,
            claim_token=NULL,lease_until=NULL,projection_json='{}',error_code='disconnected',updated_at=?
            WHERE chat_id=? AND state IN ('queued','claimed','retry_wait','sending')""", (stamp(now), target))
        conn.execute("UPDATE telegram_link_challenge SET state='cancelled',session_id=NULL WHERE telegram_user_id=? AND state IN ('issued','claimed')", (target,))


def disconnect(conn, payload, now):
    with transaction(conn):
        user = current(conn, payload)
        disconnect_in_transaction(conn, now=now, account_id=user['id'])
        st.audit(conn, user['username'], 'telegram_disconnect', summary='Disconnected private Telegram access.', commit=False)


def status(conn, payload, now=None):
    user = current(conn, payload)
    found = rows(conn, 'SELECT * FROM telegram_connection WHERE account_id=? ORDER BY id DESC LIMIT 1', (user['id'],))
    link = found[0] if found else None
    grants = rows(conn, 'SELECT action FROM telegram_grant WHERE connection_id=? AND generation=? AND revoked_at IS NULL',
                  (link['id'], link['generation'])) if link and link['state'] == 'active' else []
    pending = conn.execute("SELECT 1 FROM telegram_link_challenge WHERE account_id=? AND state='claimed' AND expires_at>?", (user['id'], stamp(now or datetime.now(timezone.utc)))).fetchone()
    return user, link, [g['action'] for g in grants], bool(pending)


def authorized(conn, account_id, action):
    """Future domain reads/writes must additionally enforce this current delegated grant."""
    if action not in SCOPES or not switches.enabled('link') or not switches.enabled(action.replace('.', '_')):
        return False
    bot = transport.config()
    if not bot:
        return False
    return bool(conn.execute('''SELECT 1 FROM telegram_connection c JOIN admin_user u ON u.id=c.account_id
        JOIN telegram_grant g ON g.connection_id=c.id AND g.account_id=c.account_id AND g.generation=c.generation
        WHERE c.account_id=? AND c.state='active' AND u.active=1 AND u.must_change=0 AND u.role IN ('viewer','encoder','section_manager','admin') AND g.action=? AND g.revoked_at IS NULL AND g.bot_identity=? AND g.bot_fingerprint=?''', (account_id, action, bot[0], bot[2])).fetchone())


def render(conn, projection, sender, bot, now):
    """Return a private message or None. Credentials are never persisted in delivery JSON."""
    if projection.get('kind') == 'status':
        found = rows(conn, 'SELECT state FROM telegram_connection WHERE telegram_user_id=? ORDER BY id DESC LIMIT 1', (sender,))
        return 'Office Connect Telegram connection: '+(found[0]['state'] if found else 'not linked')+'. Manage or disconnect it on your signed-in account page.'
    if set(projection) != {'kind','challenge','bot','fingerprint'} or projection['bot'] != bot[0] or projection['fingerprint'] != bot[2]:
        return None
    found = rows(conn, 'SELECT * FROM telegram_link_challenge WHERE id=?', (projection['challenge'],))
    if not found:
        return None
    ch = found[0]
    if ch['telegram_user_id'] != sender or not challenge_live(ch, bot, now):
        return None
    if projection['kind'] == 'link_code' and ch['state'] == 'issued':
        return 'To link your own account, sign in at '+origin()+'/account/telegram and paste this code within 10 minutes:\n'+code(ch,'claim')+'\nDo not forward this code. Never send your Office Connect password to Telegram.'
    if projection['kind'] == 'link_confirm' and ch['state'] == 'claimed':
        try:
            user = current(conn, {'uid': ch['account_id'], 'sid': ch['session_id']})
        except ValueError:
            return None
        labels = ', '.join(SCOPES[s] for s in json.loads(ch['scopes_json'])) or 'No business access'
        return 'Confirm linking to Office Connect account '+user['username']+' with '+labels+'. Only if this is your account, send:\n/confirm '+code(ch,'confirm')+'\nOtherwise send /disconnect. This code expires with the original 10-minute request.'
    return None


def pending_confirmation(conn, sender, bot, now):
    """Only the original Telegram sender can retrieve a current browser claim."""
    found = rows(conn, '''SELECT id FROM telegram_link_challenge
        WHERE telegram_user_id=? AND private_chat_id=? AND state='claimed' AND expires_at>?
        ORDER BY created_at DESC,id DESC LIMIT 1''', (sender, sender, stamp(now)))
    if not found:
        return None
    projection = {'kind': 'link_confirm', 'challenge': found[0]['id'], 'bot': bot[0], 'fingerprint': bot[2]}
    return projection if render(conn, projection, sender, bot, now) else None
