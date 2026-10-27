"""M2.6 unsubmitted travel reimbursement drafts with explicit browser save and stable receipts."""
import hashlib
import json
import os
import time
from uuid import NAMESPACE_URL, uuid5

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import travel_drafts as entries
import storage as st
import tzutil as tz

SCOPE = 'travel:filing:draft'
FLAG = 'CSS_MCP_TRAVEL_DRAFTS_ENABLED'


def install(conn):
    entries.install(conn)
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_travel_draft_operation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      payload_json TEXT, snapshot_json TEXT, snapshot_digest TEXT NOT NULL, domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL, completed_at TEXT, filing_id INTEGER,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_travel_draft_expiry ON mcp_travel_draft_operation(expires_at)
      WHERE payload_json IS NOT NULL;
    ''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1':
        raise actions.ActionError('not_available', 'Saving travel reimbursement drafts through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_travel_draft_operation SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
        (SELECT rowid FROM mcp_travel_draft_operation WHERE payload_json IS NOT NULL AND expires_at<=?
         ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_travel_draft_operation WHERE owner_id=? AND operation_id=?',
                 (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Travel reimbursement draft operation not found or unavailable to you.')
    return found[0]


def _check(conn, user, op, resource):
    _enabled()
    if op['resource'] != resource:
        raise permissions.Denied('Travel reimbursement draft operation not found or unavailable to you.')
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    entries.actor(conn, user)
    if op['completed_at']:
        saved = entries.get(conn, user, op['filing_id'])
        if saved['operation_key'] != op['domain_key']:
            raise permissions.Denied('The original saved travel reimbursement draft is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This travel reimbursement draft preview expired. Prepare and review a new operation.')
    try:
        fields = json.loads(op['payload_json'])
        snapshot = json.loads(op['snapshot_json'])
        if _digest(snapshot) != op['snapshot_digest']:
            raise ValueError
        if _digest(fields) != op['request_digest'] or entries.normalize(fields) != fields:
            raise ValueError
    except (TypeError, ValueError):
        raise actions.ActionError('preview_mismatch', 'The stored travel reimbursement draft preview changed. Prepare and review a new operation.') from None
    # Recheck normal travel policy and checklist before opening the filing.
    if entries.snapshot(conn, user, fields) != snapshot:
        raise actions.ActionError('preview_changed', 'The travel deadline or checklist changed. Prepare and review a new operation.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource',
                                   'request_digest', 'snapshot_digest', 'domain_key', 'created_at', 'expires_at')])


def _result(op, origin, ref=None):
    return {'operation_id': op['operation_id'], 'action': 'prepare_travel_reimbursement_draft',
            'status': 'completed' if op['completed_at'] else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'],
            'filing_id': str(op['filing_id']) if op['filing_id'] else None,
            'web_url': origin + '/travel/f/' + ref if ref else origin + '/travel',
            'confirmation_url': origin + '/account/integrations/mcp/travel-drafts/' + op['operation_id'],
            'instruction': ('Your reimbursement checklist was opened in progress, not submitted or sent for review. Open its source for current state and normal deadline reminders.'
                            if op['completed_at'] else 'Review the exact activity, DPO, role, checklist answers and deadline in Office Connect and confirm saving. No travel reimbursement draft has been saved by this operation yet. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = entries.normalize(fields)
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        _enabled()
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_travel_draft_operation WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different travel reimbursement draft or connection. Recover the original operation first.')
            _check(conn, user, op, resource)
            return _result(op, origin, entries.get(conn, user, op['filing_id'])['ref_code'] if op['completed_at'] else None)
        snapshot = entries.snapshot(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) '
            'FROM mcp_travel_draft_operation WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The travel reimbursement draft preview limit has been reached.')
        now = int(time.time())
        domain_key = str(uuid5(NAMESPACE_URL, _json([resource, user['id'], grant_id, 'travel_draft', operation_id])))
        conn.execute('INSERT INTO mcp_travel_draft_operation VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _json(values), _json(snapshot), _digest(snapshot), domain_key, now, now + actions.PREVIEW_SECONDS))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_travel_draft',
                 target_id=operation_id, summary='MCP travel reimbursement draft preview', commit=False)
        return _result(_op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id:
            raise permissions.Denied('Travel reimbursement draft operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_draft',
                 target_id=operation_id, summary='MCP own reimbursement draft receipt read', commit=False)
        return _result(op, origin, entries.get(conn, user, op['filing_id'])['ref_code'] if op['completed_at'] else None)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user:
            raise permissions.Denied('Sign in again to review this travel reimbursement draft.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this travel reimbursement draft.')
            if not op['completed_at']:
                filing_id = entries.save_in_transaction(conn, user, json.loads(op['payload_json']), operation_key=op['domain_key'], expected_snapshot=json.loads(op['snapshot_json']))
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_travel_draft_operation SET completed_at=?,filing_id=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed, filing_id, user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_travel_draft',
                         target_id=operation_id, summary='MCP travel reimbursement draft saved', commit=False)
                op.update(completed_at=completed, filing_id=filing_id, payload_json=None, snapshot_json=None)
        fields = json.loads(op['payload_json']) if op['payload_json'] else None
        return dict(_result(op, origin, entries.get(conn, user, op['filing_id'])['ref_code'] if op['completed_at'] else None), preview_digest=_preview_digest(op), fields=fields,
                    snapshot=json.loads(op['snapshot_json']) if fields else None,
                    questions=entries.questions(fields) if fields else [])
