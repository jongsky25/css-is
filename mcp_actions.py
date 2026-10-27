"""M2 pilot: actor/grant-bound previews and atomic, recoverable receipts.

MCP can prepare or inspect an operation. Only a current browser session can
confirm it. Never accept a model-supplied confirmation boolean or token.
"""
import hashlib
import json
import os
import re
import time

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_auth
import storage as st
import tzutil as tz
import work
import work_discussion
import work_updates

SCOPE = 'notifications:mark_read'
FLAG = 'CSS_MCP_NOTIFICATION_WRITES_ENABLED'
PREVIEW_SECONDS = 600


class ActionError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_action_operation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, action TEXT NOT NULL,
      request_digest TEXT NOT NULL, notice_id INTEGER NOT NULL,
      comment_id INTEGER NOT NULL, case_id INTEGER NOT NULL, task_id INTEGER,
      notice_revision INTEGER NOT NULL, comment_revision INTEGER NOT NULL,
      read_revision INTEGER NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      completed_at TEXT, PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_action_operation_expiry ON mcp_action_operation(expires_at);
    ''')


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', value):
        raise ActionError('invalid_operation_id', 'Use a random operation key of 16–80 letters, digits, hyphens or underscores. Keep it for retries.')
    return value


def _enabled(conn):
    if (os.environ.get('CSS_MCP_ENABLED') != '1'
            or os.environ.get(FLAG) != '1'
            or os.environ.get('CSS_MCP_NOTIFICATIONS_ENABLED') != '1'
            or not work.enabled(conn)):
        raise ActionError('not_available', 'Marking work notices read through ChatGPT is disabled.')


def _grant(conn, grant_id, owner_id, resource):
    row = conn.execute('SELECT scopes_json FROM mcp_oauth_grant WHERE id=? AND owner_id=? '
                       'AND resource=? AND revoked_at IS NULL AND refresh_expires>?',
                       (grant_id, owner_id, resource, int(time.time()))).fetchone()
    user = mcp_auth._active(conn, owner_id)
    if not row or SCOPE not in json.loads(row[0]) or not user:
        raise ActionError('authorization_required', 'Reconnect Office Connect and explicitly allow marking your own work notices read.')
    return user


def token_actor(conn, token, resource):
    # Called under the same writer lock as prepare/recovery.
    user = mcp_auth.current_grant(conn, token, resource, SCOPE)
    if not user:
        raise ActionError('authorization_required', 'Reconnect Office Connect and explicitly allow marking your own work notices read.')
    grant_id = conn.execute('SELECT id FROM mcp_oauth_grant WHERE access_hash=?',
                            (mcp_auth._digest(token),)).fetchone()[0]
    return user, grant_id


def _notice(conn, user, notice_id):
    # Metadata only: do not load the message body or author into MCP context.
    found = rows(conn, '''SELECT n.id,n.comment_id,n.revision,n.created_at,n.reason,
        c.case_id,c.task_id,(SELECT MAX(revision) FROM work_comment_revision WHERE comment_id=c.id) AS comment_revision
        FROM work_notice n JOIN work_comment c ON c.id=n.comment_id
        WHERE n.id=? AND n.user_id=?''', (notice_id, user['id']))
    if not found:
        raise permissions.Denied('Record not found or unavailable to you.')
    notice = found[0]
    _, case, _ = work_discussion.scope(conn, user, notice['case_id'], notice['task_id'])
    notice['case_title'] = case['title']
    notice['read_revision'] = work_updates.read_revision(conn, user['id'], notice['comment_id'])
    return notice


def _operation(conn, owner_id, operation_id):
    found = rows(conn, 'SELECT * FROM mcp_action_operation WHERE owner_id=? AND operation_id=?',
                 (owner_id, _key(operation_id)))
    if not found:
        raise permissions.Denied('Operation not found or unavailable to you.')
    return found[0]


def _check(conn, user, op, resource):
    _enabled(conn)
    if op['resource'] != resource:
        raise permissions.Denied('Operation not found or unavailable to you.')
    _grant(conn, op['grant_id'], user['id'], resource)
    notice = _notice(conn, user, op['notice_id'])
    if not op['completed_at']:
        if op['expires_at'] <= int(time.time()):
            raise ActionError('preview_expired', 'This preview expired. Prepare a new operation and review it again.')
        if any(notice[k] != op[k] for k in ('comment_id', 'case_id', 'task_id', 'comment_revision', 'read_revision')) or notice['revision'] != op['notice_revision']:
            raise ActionError('revision_conflict', 'The notice or its read state changed. Prepare a new operation and review it again.')
    return notice


def _result(op, origin):
    return {'operation_id': op['operation_id'], 'action': op['action'],
            'notification_id': str(op['notice_id']), 'observed_revision': op['comment_revision'],
            'status': 'completed' if op['completed_at'] else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'],
            'web_url': origin + '/work/updates',
            'confirmation_url': origin + '/account/integrations/mcp/actions/' + op['operation_id'],
            'instruction': ('The notice was marked read. Check this receipt again with the same operation key.'
                            if op['completed_at'] else 'Open the confirmation link and review the notice. Nothing has been marked read yet. Reuse this operation key to check the result.')}


def _preview_digest(op):
    fields = ('owner_id', 'operation_id', 'grant_id', 'resource', 'action', 'request_digest',
              'notice_id', 'comment_id', 'case_id', 'task_id', 'notice_revision',
              'comment_revision', 'read_revision', 'created_at', 'expires_at')
    return hashlib.sha256(json.dumps([op[k] for k in fields], separators=(',', ':')).encode()).hexdigest()


def prepare(conn, token, resource, origin, notification_id, operation_id):
    _key(operation_id)
    if type(notification_id) is not int or not 1 <= notification_id <= 2**63-1:
        raise ActionError('invalid_notification', 'Use a positive notification ID from list_my_notifications.')
    digest = hashlib.sha256(json.dumps(['mark_my_notification_read', notification_id], separators=(',', ':')).encode()).hexdigest()
    with transaction(conn):
        _enabled(conn)
        user, grant_id = token_actor(conn, token, resource)
        existing = conn.execute('SELECT 1 FROM mcp_action_operation WHERE owner_id=? AND operation_id=?',
                                (user['id'], operation_id)).fetchone()
        if existing:
            op = _operation(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise ActionError('idempotency_conflict', 'This operation key belongs to another request or connection. Do not reuse it for a different action.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        n = _notice(conn, user, notification_id)
        if n['read_revision'] >= n['revision']:
            raise ActionError('already_read', 'This notice is already read. No action was prepared.')
        # Do not permit unbounded pending previews. Completed keys are retained
        # for recovery and are never silently recycled by cleanup.
        if conn.execute('SELECT COUNT(*) FROM mcp_action_operation WHERE owner_id=? AND completed_at IS NULL AND expires_at>?',
                        (user['id'], int(time.time()))).fetchone()[0] >= 50:
            raise ActionError('too_many_previews', 'Too many pending previews. Complete one or wait for it to expire.')
        if conn.execute('SELECT COUNT(*) FROM mcp_action_operation WHERE owner_id=?', (user['id'],)).fetchone()[0] >= 10000:
            raise ActionError('operation_capacity', 'The action receipt limit has been reached. Use the ordinary Office Connect screen and contact the operator.')
        now = int(time.time())
        conn.execute('''INSERT INTO mcp_action_operation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)''',
                     (user['id'], operation_id, grant_id, resource, 'mark_my_notification_read', digest,
                      notification_id, n['comment_id'], n['case_id'], n['task_id'], n['revision'],
                      n['comment_revision'], n['read_revision'], now, now + PREVIEW_SECONDS))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_operation',
                 target_id=operation_id, summary='MCP own work notice read preview', commit=False)
        return _result(_operation(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn):
        user, grant_id = token_actor(conn, token, resource)
        op = _operation(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id:
            raise permissions.Denied('Operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_operation',
                 target_id=operation_id, summary='MCP own notice action receipt read', commit=False)
        return _result(op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user:
            raise permissions.Denied('Sign in again to review this action.')
        op = _operation(conn, user['id'], operation_id)
        n = _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise ActionError('preview_mismatch', 'The confirmation does not match the prepared action.')
            if not op['completed_at']:
                # Shared service writes only the exact revision reviewed on the
                # page. The writer lock prevents a racing edit/confirmation.
                work_updates.mark_read_in_transaction(conn, user, op['case_id'], op['task_id'],
                                                       [[op['comment_id'], op['comment_revision']]])
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_action_operation SET completed_at=? WHERE owner_id=? AND operation_id=?',
                             (completed, user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_operation',
                         target_id=operation_id, summary='MCP own work notice marked read', commit=False)
                op['completed_at'] = completed
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    category=n['reason'], created_at=n['created_at'], case_title=n['case_title'])
