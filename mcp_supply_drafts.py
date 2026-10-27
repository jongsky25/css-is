"""M2.2: new own supply drafts, executed only by signed-in browser confirmation."""
import hashlib
import json
import os
import time
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import supplies
import supplies_requests as requests
import supplies_storage as domain
import tzutil as tz

SCOPE = 'supplies:request:draft'
FLAG = 'CSS_MCP_SUPPLY_DRAFTS_ENABLED'


class DraftLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_id: StrictInt = Field(ge=1, le=2147483647)
    requested_quantity: StrictInt = Field(ge=1, le=2147483647)


class DraftFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: StrictStr = Field(min_length=1, max_length=2000)
    date_needed: StrictStr | None = None
    lines: list[DraftLine] = Field(min_length=1, max_length=20)


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_supply_draft_operation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      completed_at TEXT, result_json TEXT, PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_supply_draft_expiry ON mcp_supply_draft_operation(expires_at)
      WHERE payload_json IS NOT NULL;
    ''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if (os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1'
            or not supplies.enabled(conn)):
        raise actions.ActionError('not_available', 'Creating supply drafts through ChatGPT is disabled.')


def prune(conn):
    """Bounded lazy cleanup: retain key/hash tombstones, discard expired text."""
    conn.execute('''UPDATE mcp_supply_draft_operation SET payload_json=NULL,snapshot_json=NULL
        WHERE rowid IN (SELECT rowid FROM mcp_supply_draft_operation
        WHERE payload_json IS NOT NULL AND expires_at<=? ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _snapshot(conn, user, values):
    _, identity = requests.requester(conn, user)
    items = []
    for line in values['lines']:
        item = supplies.get_item(conn, user, line['item_id'])
        if not item['active']:
            raise actions.ActionError('item_unavailable', 'Choose currently active catalog items.')
        items.append({k: item[k] for k in ('id', 'code', 'description', 'unit', 'revision')})
    return {'requester': identity, 'items': items}


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_supply_draft_operation WHERE owner_id=? AND operation_id=?',
                 (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Draft operation not found or unavailable to you.')
    return found[0]


def _check(conn, user, op, resource):
    _enabled(conn)
    if op['resource'] != resource:
        raise permissions.Denied('Draft operation not found or unavailable to you.')
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if op['completed_at']:
        result = json.loads(op['result_json'])
        requests._owned(conn, user, result['id'])
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This draft preview expired. Prepare and review a new operation.')
    current = _snapshot(conn, user, json.loads(op['payload_json']))
    if _digest(current) != op['snapshot_digest']:
        raise actions.ActionError('revision_conflict', 'The requester or catalog changed. Prepare and review a new draft preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource',
                                   'request_digest', 'snapshot_digest', 'domain_key', 'created_at', 'expires_at')])


def _result(op, origin):
    result = json.loads(op['result_json']) if op['result_json'] else None
    return {'operation_id': op['operation_id'], 'action': 'prepare_supply_request_draft',
            'status': 'completed' if op['completed_at'] else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'],
            'draft': result,
            'web_url': origin + ('/supplies/requests/' + str(result['id']) if result else '/supplies/requests'),
            'confirmation_url': origin + '/account/integrations/mcp/supply-drafts/' + op['operation_id'],
            'instruction': ('The draft was saved. This receipt reports the original save; review current status in Office Connect.'
                            if result else 'Review and confirm the exact draft in Office Connect. No supply request has been created yet. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    # Strict schema first, then the same normalization/limits used by the UI.
    values = requests._fields(DraftFields.model_validate(fields).model_dump())
    digest = _digest(values)
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        existing = conn.execute('SELECT 1 FROM mcp_supply_draft_operation WHERE owner_id=? AND operation_id=?',
                                (user['id'], operation_id)).fetchone()
        if existing:
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different draft or connection. Keep the original key for recovery.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        snapshot = _snapshot(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) '
            'FROM mcp_supply_draft_operation WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The draft preview limit has been reached. Use the ordinary Office Connect screen.')
        now = int(time.time())
        domain_key = str(uuid5(NAMESPACE_URL, _json([resource, user['id'], grant_id, 'supply_draft', operation_id])))
        conn.execute('INSERT INTO mcp_supply_draft_operation VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             domain_key, now, now + actions.PREVIEW_SECONDS))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_supply_draft',
                 target_id=operation_id, summary='MCP own supply draft preview', commit=False)
        return _result(_op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id:
            raise permissions.Denied('Draft operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_supply_draft',
                 target_id=operation_id, summary='MCP own supply draft receipt read', commit=False)
        return _result(op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user:
            raise permissions.Denied('Sign in again to review this draft.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this draft preview.')
            if not op['completed_at']:
                result = requests.save_draft_in_transaction(conn, user, json.loads(op['payload_json']),
                                                            operation_key=op['domain_key'])
                completed = tz.now_iso()
                result = dict(result, saved_status='draft')
                conn.execute('UPDATE mcp_supply_draft_operation SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL '
                    'WHERE owner_id=? AND operation_id=?', (completed, _json(result), user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_supply_draft',
                         target_id=operation_id, summary='MCP own supply draft saved', commit=False)
                op.update(completed_at=completed, result_json=_json(result), payload_json=None, snapshot_json=None)
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
