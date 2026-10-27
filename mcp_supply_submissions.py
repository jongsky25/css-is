"""M3.3 browser-confirmed own supply submission with immutable domain receipts."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt

import documents_permissions as permissions
from documents_storage import rows
import mcp_actions as actions
import storage as st
import supplies
import supplies_requests as requests
import supplies_storage as domain
import tzutil as tz

SCOPE = 'supplies:request:submit'
FLAG = 'CSS_MCP_SUPPLY_SUBMISSIONS_ENABLED'


class SubmitFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: StrictInt = Field(ge=1, le=2147483647)
    revision: StrictInt = Field(ge=1, le=2147483646)


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_supply_submission (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      request_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_supply_submission_expiry ON mcp_supply_submission(expires_at)
      WHERE payload_json IS NOT NULL;''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1' or not supplies.enabled(conn):
        raise actions.ActionError('not_available', 'Submitting supply requests through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_supply_submission SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_supply_submission WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_supply_submission WHERE owner_id=? AND operation_id=?',
                 (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Supply operation not found or unavailable to you.')
    return found[0]


def context(conn, user, fields):
    user, identity = requests.requester(conn, user)
    request = requests._owned(conn, user, fields['request_id'])
    requests._check_revision(request, fields['revision'])
    if request['approval_status'] not in ('draft', 'returned'):
        raise domain.Conflict('Only a draft or returned request can be submitted.')
    lines = rows(conn, 'SELECT * FROM supply_request_draft_line WHERE request_id=? AND active=1 ORDER BY id', (request['id'],))
    requests._fields({**request, 'lines': lines})
    requests._active_items(conn, lines)
    items = []
    for line in lines:
        item = supplies._item(conn, line['item_id'])
        if any(line[k + '_snapshot'] != item[k] for k in ('code', 'description', 'unit')):
            raise domain.Conflict('Save the current catalog details in the draft before submitting.')
        items.append({'line_id': line['id'], 'item_id': item['id'], 'code': item['code'],
                      'description': item['description'], 'unit': item['unit'], 'item_revision': item['revision'],
                      'requested_quantity': line['requested_quantity']})
    approvers = sorted(u['id'] for u in requests.eligible_approvers(conn, user['id'], identity['unit_id']))
    return {'request_id': request['id'], 'revision': request['revision'], 'status': request['approval_status'],
            'current_revision': request['current_revision'], 'control_number': request['control_number'],
            'purpose': request['purpose'], 'date_needed': request['date_needed'], 'requester': identity,
            'lines': items, 'eligible_approver_ids': approvers, 'number_year': tz.today_local().year,
            'next_actor': {'role': 'supply_request_approver', 'unit_id': str(identity['unit_id']),
                           'eligible_approver_count': len(approvers), 'routing_warning': not bool(approvers)}}


def _check(conn, user, op, resource):
    _enabled(conn)
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if op['resource'] != resource:
        raise permissions.Denied('Supply operation not found or unavailable to you.')
    if op['completed_at']:
        requests._owned(conn, user, op['request_id'])
        saved = json.loads(op['result_json'])['request']
        prior = rows(conn, 'SELECT * FROM supply_operation WHERE operation_key=?', (op['domain_key'],))
        snapshot = conn.execute('SELECT request_id,revision FROM supply_request_revision WHERE operation_key=?', (op['domain_key'],)).fetchone()
        if (not prior or prior[0]['actor_id'] != user['id'] or prior[0]['action'] != 'request_submit'
                or json.loads(prior[0]['result_json']) != saved or not snapshot
                or tuple(snapshot) != (op['request_id'], saved['current_revision'])):
            raise permissions.Denied('The original supply submission receipt is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This supply submission preview expired. Prepare a new operation.')
    try:
        fields = json.loads(op['payload_json'])
        snapshot = json.loads(op['snapshot_json'])
        if (SubmitFields.model_validate(fields).model_dump() != fields or _digest(fields) != op['request_digest']
                or _digest(snapshot) != op['snapshot_digest']):
            raise ValueError
    except (ValueError, TypeError):
        raise actions.ActionError('preview_mismatch', 'The stored supply submission preview changed. Prepare a new operation.') from None
    if context(conn, user, fields) != snapshot:
        raise actions.ActionError('revision_conflict', 'The request, catalog, requester or approval routing changed. Prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource', 'request_digest',
                                   'snapshot_digest', 'domain_key', 'created_at', 'expires_at', 'request_id')])


def _result(op, origin):
    result = json.loads(op['result_json']) if op['completed_at'] else None
    return {'operation_id': op['operation_id'], 'action': 'prepare_supply_request_submission',
            'status': 'completed' if result else 'awaiting_confirmation', 'completed_at': op['completed_at'],
            'expires_at': op['expires_at'], 'request_id': str(op['request_id']),
            'submitted': result['request'] if result else None, 'next_actor': result['next_actor'] if result else None,
            'domain_operation_id': op['domain_key'] if result else None,
            'web_url': origin + '/supplies/requests/' + str(op['request_id']),
            'confirmation_url': origin + '/account/integrations/mcp/supply-submissions/' + op['operation_id'],
            'instruction': ('Supply request submitted for approval. This is the original submitted result, not approval, stock reservation or issuance. Open the source for current status and approval routing.'
                            if result else 'Review every request line, quantity, purpose, requester/unit and approval-routing warning in Office Connect before confirming. This operation has not submitted the request. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = SubmitFields.model_validate(fields).model_dump()
    with domain.transaction(conn):
        prune(conn)
    with domain.transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_supply_submission WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different supply submission or connection. Recover the original operation.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        snapshot = context(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_supply_submission WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The supply submission preview limit has been reached.')
        now = int(time.time())
        key = str(uuid4())
        conn.execute('INSERT INTO mcp_supply_submission VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             key, now, now + actions.PREVIEW_SECONDS, values['request_id']))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_supply_submission',
                 target_id=operation_id, summary='MCP own supply submission preview', commit=False)
        return _result(_op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with domain.transaction(conn):
        prune(conn)
    with domain.transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id:
            raise permissions.Denied('Supply operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_supply_submission',
                 target_id=operation_id, summary='MCP own supply submission receipt read', commit=False)
        return _result(op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with domain.transaction(conn):
        prune(conn)
    with domain.transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user:
            raise permissions.Denied('Sign in again to review this supply submission.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this supply submission.')
            if not op['completed_at']:
                fields = json.loads(op['payload_json'])
                snapshot = json.loads(op['snapshot_json'])
                saved = requests.submit_in_transaction(conn, user, fields['request_id'],
                    expected_revision=fields['revision'], operation_key=op['domain_key'])
                result = {'request': saved, 'next_actor': snapshot['next_actor']}
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_supply_submission SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                    (completed, _json(result), user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_supply_submission',
                         target_id=operation_id, summary='MCP own supply request submitted', commit=False)
                op.update(completed_at=completed, result_json=_json(result), payload_json=None, snapshot_json=None)
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
