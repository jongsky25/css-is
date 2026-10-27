"""M3.6 one own pending room request linked to an existing eligible meeting."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import room_actions
import rooms
import rooms_notify
import storage as st
import tzutil as tz

SCOPE = 'rooms:request'
FLAG = 'CSS_MCP_ROOM_REQUESTS_ENABLED'


class RequestFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entry_id: StrictInt = Field(ge=1, le=2**63-1)
    expected_revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    from_time: StrictStr = Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')
    to_time: StrictStr = Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_room_request (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      entry_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_room_request_expiry ON mcp_room_request(expires_at) WHERE payload_json IS NOT NULL;
    CREATE TABLE IF NOT EXISTS mcp_room_notice (
      notice_id INTEGER PRIMARY KEY REFERENCES room_notice(id) ON DELETE CASCADE, operation_key TEXT NOT NULL REFERENCES mcp_room_request(domain_key),
      state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','attempting','sent','uncertain','skipped_off','not_configured','cancelled')),
      created_at INTEGER NOT NULL, attempt_id TEXT, attempted_at INTEGER, finished_at TEXT);
    CREATE TABLE IF NOT EXISTS mcp_room_identity (room_id INTEGER PRIMARY KEY REFERENCES room_reservation(id) ON DELETE CASCADE,
      operation_key TEXT NOT NULL UNIQUE REFERENCES mcp_room_request(domain_key));''')


def _json(value): return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value): return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1':
        raise actions.ActionError('not_available', 'Room requests through ChatGPT are disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_room_request SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_room_request WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _meeting(conn, user, entry_id, *, for_write=True):
    try:
        return room_actions.meeting(conn, user, entry_id, for_write=for_write)
    except ValueError:
        raise permissions.Denied('Meeting not found or unavailable for this room request.') from None


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_room_request WHERE owner_id=? AND operation_id=?', (owner_id, actions._key(key)))
    if not found: raise permissions.Denied('Room operation not found or unavailable to you.')
    return found[0]


def _recipients(conn, owner_id):
    return sorted(({'id': a['id'], 'name': a['name'], 'email': a['username']} for a in rooms_notify.approver_accounts(conn) if a['id'] != owner_id), key=lambda a:a['id'])


def context(conn, user, fields):
    user, entry = _meeting(conn, user, fields['entry_id'])
    if room_actions.revision(entry) != fields['expected_revision']:
        raise actions.ActionError('revision_conflict', 'The meeting changed. Read its current room context and prepare a new preview.')
    try:
        selected = room_actions.slot_block(conn, fields['from_time'], fields['to_time'])
        room_actions.validate(conn, user, entry['id'], [s['id'] for s in selected], fields['expected_revision'])
    except (ValueError, rooms.RoomError):
        raise actions.ActionError('room_unavailable', 'Review the meeting, current room availability and configured hours before preparing a new request.') from None
    rp = st.get_rp(conn, user['rp_id']) if user.get('rp_id') else None
    return {'entry_id': entry['id'], 'entry_uid': entry['uid'], 'title': entry['title'], 'day': entry['start_date'],
            'calendar_status': entry['status'], 'meeting_start': entry['start_time'], 'meeting_end': entry['end_time'],
            'entry_revision': fields['expected_revision'], 'from_time': fields['from_time'], 'to_time': fields['to_time'],
            'slots': selected, 'requester': {'id': user['id'], 'name': st._account_display_name(conn, user['id']) or user['username'],
                'identity_digest': _digest([user['username'], user.get('rp_id'), rp])},
            'recipients': _recipients(conn, user['id']), 'email_enabled': st.email_feature_enabled(conn, 'room_new_request')}


def room_digest(room):
    return _digest({k:room[k] for k in ('id','ref_code','requester_user_id','title','day','slot_ids','calendar_entry_id','meals_requested','standby','purpose','modality')})


def _check(conn, user, op, resource):
    _enabled()
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if op['resource'] != resource: raise permissions.Denied('Room operation not found or unavailable to you.')
    if op['completed_at']:
        result = json.loads(op['result_json'])
        _, entry = _meeting(conn, user, op['entry_id'], for_write=False)
        room = rooms.get_reservation(conn, result['room_id'])
        if (not conn.execute('SELECT 1 FROM mcp_room_identity WHERE room_id=? AND operation_key=?', (result['room_id'], op['domain_key'])).fetchone()
                or not room or room['requester_user_id'] != user['id'] or room['calendar_entry_id'] != entry['id']
                or room['ref_code'] != result['reference'] or room['created_at'] != result['created_at'] or entry['uid'] != result['entry_uid']):
            raise permissions.Denied('The original room request source is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This room request preview expired. Prepare a new operation.')
    try:
        fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
        if RequestFields.model_validate(fields).model_dump() != fields or _digest(fields) != op['request_digest'] or _digest(snapshot) != op['snapshot_digest']:
            raise ValueError
    except (ValueError, TypeError):
        raise actions.ActionError('preview_mismatch', 'The stored room request preview changed. Prepare a new operation.') from None
    if context(conn, user, fields) != snapshot:
        raise actions.ActionError('revision_conflict', 'The meeting, hours, requester or approver routing changed. Prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','entry_id')])


def _result(conn, op, origin):
    result = json.loads(op['result_json']) if op['completed_at'] else None
    states = {r[0]:r[1] for r in conn.execute('SELECT state,COUNT(*) FROM mcp_room_notice WHERE operation_key=? GROUP BY state', (op['domain_key'],))}
    return {'operation_id': op['operation_id'], 'action': 'prepare_room_request', 'status': 'completed' if result else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'], 'entry_id': str(op['entry_id']),
            'room_request_id': str(result['room_id']) if result else None, 'reference': result['reference'] if result else None,
            'requested_status': 'requested' if result else None, 'booking_held': False if result else None,
            'next_actor': {'role':'administrative_section_room_approver', 'initial_notice_recipient_count':result['eligible_count']} if result else None,
            'notification_status_counts': states, 'web_url': origin+'/rooms/mine',
            'calendar_url': origin+'/calendar/entries/'+str(op['entry_id']),
            'confirmation_url': origin+'/account/integrations/mcp/room-requests/'+op['operation_id'],
            'instruction': ('Room request recorded pending Administrative Section approval; no booking was held by this operation. This is the original request result; inspect the source for current decisions and notification states.'
                            if result else 'Review the linked meeting, exact room hours, requester and notification recipients in Office Connect and confirm. No request or booking has been created yet. Keep this key for recovery.')}


def read_context(conn, token, resource, origin, entry_id):
    if type(entry_id) is not int or not 1 <= entry_id <= 2**63-1: raise ValueError('Use a positive calendar entry ID.')
    with transaction(conn):
        _enabled()
        user, _ = actions.token_actor(conn, token, resource, SCOPE)
        user, entry = _meeting(conn, user, entry_id)
        day = rooms.day_view(conn, entry['start_date'], today=tz.today_local(), max_ahead=rooms.MAX_DAYS_AHEAD)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_room_request', target_id=entry_id,
                 summary='MCP own linked room preparation context', commit=False)
        return {'entry_id': str(entry_id), 'expected_revision': room_actions.revision(entry), 'day': entry['start_date'],
                'calendar_status': entry['status'], 'meeting_start': entry['start_time'], 'meeting_end': entry['end_time'],
                'room_availability': day, 'has_live_request': any(r['status'] in ('requested','approved') for r in rooms.reservations_for_entry(conn, entry_id)),
                'initial_notice_recipient_count': len(_recipients(conn, user['id'])), 'web_url': origin+'/calendar/entries/'+str(entry_id)}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id); values = RequestFields.model_validate(fields).model_dump()
    with transaction(conn): prune(conn)
    with transaction(conn):
        _enabled(); user, grant_id = actions.token_actor(conn, token, resource, SCOPE); digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_room_request WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different room request or connection. Recover the original operation.')
            _check(conn, user, op, resource); return _result(conn, op, origin)
        snapshot = context(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_room_request WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50: raise actions.ActionError('operation_capacity', 'The room preview limit has been reached.')
        now = int(time.time())
        conn.execute('INSERT INTO mcp_room_request VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot), str(uuid4()), now, now+actions.PREVIEW_SECONDS, values['entry_id']))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_room_request', target_id=operation_id,
                 summary='MCP own linked room request preview', commit=False)
        return _result(conn, _op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE); op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id: raise permissions.Denied('Room operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_room_request', target_id=operation_id,
                 summary='MCP own linked room receipt read', commit=False)
        return _result(conn, op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user: raise permissions.Denied('Sign in again to review this room request.')
        op = _op(conn, user['id'], operation_id); _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op): raise actions.ActionError('preview_mismatch', 'The confirmation does not match this room request.')
            if not op['completed_at']:
                fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
                try:
                    room = room_actions.request_in_transaction(conn, user, fields['entry_id'], [s['id'] for s in snapshot['slots']], fields['expected_revision'])
                except (rooms.RoomError, ValueError):
                    raise actions.ActionError('room_unavailable', 'Room availability or the meeting changed. Review a fresh preview.') from None
                result = {'room_id':room['id'], 'reference':room['ref_code'], 'created_at':room['created_at'],
                          'entry_uid':snapshot['entry_uid'], 'eligible_count':len(snapshot['recipients']), 'room_digest':room_digest(room),
                          'recipient_digests':{str(r['id']):_digest(r['email']) for r in snapshot['recipients']}}
                conn.execute('INSERT INTO mcp_room_identity VALUES (?,?)', (room['id'], op['domain_key']))
                now = int(time.time()); completed = tz.now_iso()
                for notice in rows(conn, "SELECT id FROM room_notice WHERE reservation_id=? AND kind='new_request'", (room['id'],)):
                    conn.execute('INSERT INTO mcp_room_notice(notice_id,operation_key,created_at) VALUES (?,?,?)', (notice['id'], op['domain_key'], now))
                conn.execute('UPDATE mcp_room_request SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?', (completed,_json(result),user['id'],operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_room_request', target_id=operation_id,
                         summary='MCP own linked room request recorded', commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(conn, op, origin), preview_digest=_preview_digest(op), fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
