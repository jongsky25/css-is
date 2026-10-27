"""M3.1 own-task acknowledgement, browser review and canonical API receipts."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

import documents_permissions as permissions
from documents_storage import rows, transaction
import integration_operations as operations
import mcp_actions as actions
import storage as st
import work
import work_compat
import work_reads
import work_tasks

SCOPE = 'work:task:acknowledge'
FLAG = 'CSS_MCP_TASK_ACKNOWLEDGEMENTS_ENABLED'


class AckFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    work_item_id: StrictInt = Field(ge=1, le=2**63-1)
    task_id: StrictInt = Field(ge=1, le=2**63-1)
    revision: StrictInt = Field(ge=1, le=2**63-2)
    reason: StrictStr = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def exact_reason(cls, value):
        value = value.strip()
        value.encode('utf-8')
        if not value or any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 for c in value):
            raise ValueError('Provide a progress note without control characters.')
        return value


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_task_acknowledgement (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      case_id INTEGER NOT NULL, task_id INTEGER NOT NULL, completed_at TEXT, result_revision INTEGER,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_task_ack_expiry ON mcp_task_acknowledgement(expires_at)
      WHERE payload_json IS NOT NULL;''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1':
        raise actions.ActionError('not_available', 'Acknowledging tasks through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_task_acknowledgement SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_task_acknowledgement WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_task_acknowledgement WHERE owner_id=? AND operation_id=?',
                 (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Task operation not found or unavailable to you.')
    return found[0]


def context(conn, user, fields):
    user = permissions.actor(conn, user)
    case = work.get(conn, user, fields['work_item_id'])
    task = work_reads.task(conn, user, case['id'], fields['task_id'])
    try:
        work.writable(conn)
        work_compat.require_open(conn, case['id'])
    except ValueError:
        raise actions.ActionError('action_unavailable', 'Review the current task, work item and enabled work module before acknowledging.') from None
    if task['revision'] != fields['revision']:
        raise actions.ActionError('revision_conflict', 'The task changed. Read its current revision and review a new preview.')
    # This first M3 pilot is restricted to the assigned owner even where an
    # officer could acknowledge someone else's task in the ordinary UI/API.
    if task['owner_id'] != user['id'] or 'acknowledge' not in work_tasks.actions(conn, user, case, task):
        raise permissions.Denied('This assigned task cannot be acknowledged by you now.')
    return {'case_id': case['id'], 'case_title': case['title'], 'case_revision': case['revision'],
            'task_id': task['id'], 'task_title': task['title'], 'task_revision': task['revision'],
            'status': task['status'], 'owner_id': task['owner_id'], 'due_date': task['due_date']}


def _check(conn, user, op, resource):
    _enabled()
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if resource != op['resource']:
        raise permissions.Denied('Task operation not found or unavailable to you.')
    if op['completed_at']:
        receipt = operations.find(conn, user, op['domain_key'])
        if (receipt['case_id'], receipt['task_id'], receipt['result_revision'], receipt['action']) != (
                op['case_id'], op['task_id'], op['result_revision'], 'acknowledge'):
            raise permissions.Denied('The original task receipt is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This acknowledgement preview expired. Prepare a new operation.')
    try:
        fields = json.loads(op['payload_json'])
        snapshot = json.loads(op['snapshot_json'])
        if (_digest(fields) != op['request_digest'] or _digest(snapshot) != op['snapshot_digest']
                or AckFields.model_validate(fields).model_dump() != fields):
            raise ValueError
    except (ValueError, TypeError):
        raise actions.ActionError('preview_mismatch', 'The stored acknowledgement preview changed. Prepare a new operation.') from None
    if context(conn, user, fields) != snapshot:
        raise actions.ActionError('revision_conflict', 'The work item or task changed. Prepare a new acknowledgement preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource', 'request_digest',
                                   'snapshot_digest', 'domain_key', 'created_at', 'expires_at', 'case_id', 'task_id')])


def _result(op, origin):
    done = bool(op['completed_at'])
    return {'operation_id': op['operation_id'], 'action': 'prepare_task_acknowledgement',
            'status': 'completed' if done else 'awaiting_confirmation', 'completed_at': op['completed_at'],
            'expires_at': op['expires_at'], 'work_item_id': str(op['case_id']), 'task_id': str(op['task_id']),
            'result_status': 'in_progress' if done else None, 'result_revision': op['result_revision'],
            'next_actor': {'role': 'assigned_task_owner', 'user_id': str(op['owner_id'])} if done else None,
            'api_operation_id': op['domain_key'] if done else None,
            'api_receipt_url': origin + '/api/v1/operations/' + op['domain_key'] if done else None,
            'web_url': origin + '/work/' + str(op['case_id']) + '#task-' + str(op['task_id']),
            'confirmation_url': origin + '/account/integrations/mcp/task-acknowledgements/' + op['operation_id'],
            'instruction': ('Acknowledgement committed: the task moved to In progress and its assigned owner acts next. This is the original result; open the source for current state.'
                            if done else 'Review the assigned task, revision, progress note and effects in Office Connect and confirm acknowledgement. No task has changed yet. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = AckFields.model_validate(fields).model_dump()
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        _enabled()
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_task_acknowledgement WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different acknowledgement or connection. Recover the original operation.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        snapshot = context(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_task_acknowledgement WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The task acknowledgement preview limit has been reached.')
        now = int(time.time())
        key = str(uuid4())  # API v1 requires UUID v4; persist once, then reuse.
        conn.execute('INSERT INTO mcp_task_acknowledgement VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             key, now, now + actions.PREVIEW_SECONDS, values['work_item_id'], values['task_id']))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_task_acknowledgement',
                 target_id=operation_id, summary='MCP own task acknowledgement preview', commit=False)
        return _result(_op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id:
            raise permissions.Denied('Task operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_task_acknowledgement',
                 target_id=operation_id, summary='MCP own task acknowledgement receipt read', commit=False)
        return _result(op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user:
            raise permissions.Denied('Sign in again to review this acknowledgement.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this acknowledgement.')
            if not op['completed_at']:
                fields = json.loads(op['payload_json'])
                try:
                    receipt = operations.acknowledge_in_transaction(conn, payload, fields['work_item_id'], fields['task_id'],
                        op['domain_key'], fields['revision'], fields['reason'])
                except operations.OperationError as exc:
                    raise actions.ActionError(exc.code, exc.message) from None
                conn.execute('UPDATE mcp_task_acknowledgement SET completed_at=?,result_revision=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                    (receipt['completed_at'], receipt['result_revision'], user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_task_acknowledgement',
                         target_id=operation_id, summary='MCP own task acknowledged', commit=False)
                op.update(completed_at=receipt['completed_at'], result_revision=receipt['result_revision'], payload_json=None, snapshot_json=None)
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
