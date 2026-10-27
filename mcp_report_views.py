"""M2.4 named report selections with explicit browser save and stable receipts."""
import hashlib
import json
import os
import time
from uuid import NAMESPACE_URL, uuid5

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import report_views as views
import storage as st
import tzutil as tz

SCOPE = 'reports:view:save'
FLAG = 'CSS_MCP_REPORT_VIEWS_ENABLED'


def install(conn):
    views.install(conn)
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_report_view_operation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      payload_json TEXT, domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL, completed_at TEXT, view_id INTEGER,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_report_view_expiry ON mcp_report_view_operation(expires_at)
      WHERE payload_json IS NOT NULL;
    ''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1':
        raise actions.ActionError('not_available', 'Saving report views through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_report_view_operation SET payload_json=NULL WHERE rowid IN
        (SELECT rowid FROM mcp_report_view_operation WHERE payload_json IS NOT NULL AND expires_at<=?
         ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_report_view_operation WHERE owner_id=? AND operation_id=?',
                 (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Report view operation not found or unavailable to you.')
    return found[0]


def _check(conn, user, op, resource):
    _enabled()
    if op['resource'] != resource:
        raise permissions.Denied('Report view operation not found or unavailable to you.')
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    views.actor(conn, user)
    if op['completed_at']:
        saved = views.get(conn, user, op['view_id'])
        if saved['operation_key'] != op['domain_key']:
            raise permissions.Denied('The original saved report view is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This report view preview expired. Prepare and review a new operation.')
    try:
        fields = json.loads(op['payload_json'])
        if _digest(fields) != op['request_digest'] or views.normalize(fields) != fields:
            raise ValueError
    except (TypeError, ValueError):
        raise actions.ActionError('preview_mismatch', 'The stored report view preview changed. Prepare and review a new operation.') from None
    # This creates a selection rather than editing an existing report. The
    # stale conditions are current permission, name uniqueness and capacity.
    views.check_new(conn, user, fields)


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource',
                                   'request_digest', 'domain_key', 'created_at', 'expires_at')])


def _result(op, origin):
    return {'operation_id': op['operation_id'], 'action': 'prepare_saved_report_view',
            'status': 'completed' if op['completed_at'] else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'],
            'view_id': str(op['view_id']) if op['view_id'] else None,
            'web_url': origin + '/reports/saved/' + str(op['view_id']) if op['view_id'] else origin + '/reports/saved',
            'confirmation_url': origin + '/account/integrations/mcp/report-views/' + op['operation_id'],
            'instruction': ('Your personal report selection was saved. Opening it loads current report data through the ordinary signed-in report screen.'
                            if op['completed_at'] else 'Review the name, report type and period in Office Connect and confirm saving. No report view has been saved by this operation yet. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = views.normalize(fields)
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        _enabled()
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_report_view_operation WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different report view or connection. Recover the original operation first.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        views.check_new(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) '
            'FROM mcp_report_view_operation WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The report view preview limit has been reached.')
        now = int(time.time())
        domain_key = str(uuid5(NAMESPACE_URL, _json([resource, user['id'], grant_id, 'report_view', operation_id])))
        conn.execute('INSERT INTO mcp_report_view_operation VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _json(values), domain_key, now, now + actions.PREVIEW_SECONDS))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_report_view',
                 target_id=operation_id, summary='MCP personal report view preview', commit=False)
        return _result(_op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id:
            raise permissions.Denied('Report view operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_report_view',
                 target_id=operation_id, summary='MCP own report view receipt read', commit=False)
        return _result(op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user:
            raise permissions.Denied('Sign in again to review this report view.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this report view.')
            if not op['completed_at']:
                view_id = views.save_in_transaction(conn, user, json.loads(op['payload_json']), operation_key=op['domain_key'])
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_report_view_operation SET completed_at=?,view_id=?,payload_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed, view_id, user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_report_view',
                         target_id=operation_id, summary='MCP personal report view saved', commit=False)
                op.update(completed_at=completed, view_id=view_id, payload_json=None)
        fields = json.loads(op['payload_json']) if op['payload_json'] else None
        return dict(_result(op, origin), preview_digest=_preview_digest(op), fields=fields,
                    report_url=views.report_path(fields) if fields else None)
