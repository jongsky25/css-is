"""M2.3 task comment drafts: explicit save, private source and durable recovery."""
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
import tzutil as tz
import work
import work_comment_drafts as drafts

SCOPE = 'work:comment:draft'
FLAG = 'CSS_MCP_COMMENT_DRAFTS_ENABLED'


class DraftFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    work_item_id: StrictInt = Field(ge=1, le=2**63-1)
    task_id: StrictInt = Field(ge=1, le=2**63-1)
    body: StrictStr = Field(min_length=1, max_length=4000)


def install(conn):
    drafts.install(conn)
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_comment_draft_operation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      completed_at TEXT, draft_id INTEGER, PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_comment_draft_expiry ON mcp_comment_draft_operation(expires_at)
      WHERE payload_json IS NOT NULL;
    ''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if (os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1' or not work.enabled(conn)):
        raise actions.ActionError('not_available', 'Saving task comment drafts through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_comment_draft_operation SET payload_json=NULL,snapshot_json=NULL
        WHERE rowid IN (SELECT rowid FROM mcp_comment_draft_operation
        WHERE payload_json IS NOT NULL AND expires_at<=? ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_comment_draft_operation WHERE owner_id=? AND operation_id=?',
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
        drafts.get(conn, user, op['draft_id'])
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This preview expired. Prepare and review a new comment draft.')
    try:
        fields = json.loads(op['payload_json'])
        snapshot = json.loads(op['snapshot_json'])
    except (TypeError, ValueError):
        raise actions.ActionError('preview_mismatch', 'The stored draft preview is unavailable. Prepare and review a new operation.') from None
    if _digest(fields) != op['request_digest'] or _digest(snapshot) != op['snapshot_digest']:
        raise actions.ActionError('preview_mismatch', 'The stored draft preview changed. Prepare and review a new operation.')
    current = drafts.context(conn, user, fields['work_item_id'], fields['task_id'])
    if _digest(current) != op['snapshot_digest']:
        raise actions.ActionError('revision_conflict', 'The work item or task changed. Prepare and review a new draft preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource',
                                   'request_digest', 'snapshot_digest', 'domain_key', 'created_at', 'expires_at')])


def _result(op, origin):
    return {'operation_id': op['operation_id'], 'action': 'prepare_task_comment_draft',
            'status': 'completed' if op['completed_at'] else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'],
            'draft_id': str(op['draft_id']) if op['draft_id'] else None,
            'web_url': (origin + '/account/integrations/mcp/comment-drafts/saved/' + str(op['draft_id'])) if op['draft_id'] else None,
            'confirmation_url': origin + '/account/integrations/mcp/comment-drafts/' + op['operation_id'],
            'instruction': ('Your private draft was saved without posting a message. Review it in Office Connect.'
                            if op['completed_at'] else 'Review the exact draft and confirm saving it in Office Connect. This operation has not saved a draft or posted a message. Keep this operation key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = DraftFields.model_validate(fields).model_dump()
    values['body'] = drafts.normalize_body(values['body'])
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_comment_draft_operation WHERE owner_id=? AND operation_id=?',
                        (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different draft or connection. Recover the original operation before creating another.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        snapshot = drafts.context(conn, user, values['work_item_id'], values['task_id'])
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) '
            'FROM mcp_comment_draft_operation WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The private draft preview limit has been reached.')
        now = int(time.time())
        domain_key = str(uuid5(NAMESPACE_URL, _json([resource, user['id'], grant_id, 'task_comment_draft', operation_id])))
        conn.execute('INSERT INTO mcp_comment_draft_operation VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             domain_key, now, now + actions.PREVIEW_SECONDS))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_comment_draft',
                 target_id=operation_id, summary='MCP private task comment draft preview', commit=False)
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
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_comment_draft',
                 target_id=operation_id, summary='MCP own comment draft receipt read', commit=False)
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
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this comment draft.')
            if not op['completed_at']:
                fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
                draft_id = drafts.save_in_transaction(conn, user, fields['work_item_id'], fields['task_id'], fields['body'],
                    expected_context=snapshot, operation_key=op['domain_key'])
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_comment_draft_operation SET completed_at=?,draft_id=?,payload_json=NULL,snapshot_json=NULL '
                    'WHERE owner_id=? AND operation_id=?', (completed, draft_id, user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_comment_draft',
                         target_id=operation_id, summary='MCP private task comment draft saved', commit=False)
                op.update(completed_at=completed, draft_id=draft_id, payload_json=None, snapshot_json=None)
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
