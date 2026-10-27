"""M2.7 private activity drafts: explicit save, stable source and durable recovery."""
import hashlib
import json
import os
import time
from uuid import uuid4

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz
import activity_drafts as drafts

SCOPE = 'activities:draft:save'
FLAG = 'CSS_MCP_ACTIVITY_DRAFTS_ENABLED'


def install(conn):
    drafts.install(conn)
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_activity_draft_operation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      completed_at TEXT, draft_id INTEGER, PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_activity_draft_expiry ON mcp_activity_draft_operation(expires_at)
      WHERE payload_json IS NOT NULL;
    ''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1':
        raise actions.ActionError('not_available', 'Saving private activity drafts through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_activity_draft_operation SET payload_json=NULL,snapshot_json=NULL
        WHERE rowid IN (SELECT rowid FROM mcp_activity_draft_operation
        WHERE payload_json IS NOT NULL AND expires_at<=? ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_activity_draft_operation WHERE owner_id=? AND operation_id=?',
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
        saved = drafts.get(conn, user, op['domain_key'])
        if saved['id'] != op['draft_id']:
            raise permissions.Denied('The original private activity draft is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This preview expired. Prepare and review a new activity draft.')
    try:
        fields = json.loads(op['payload_json'])
        if drafts.normalize(fields) != fields:
            raise ValueError
        snapshot = json.loads(op['snapshot_json'])
    except (TypeError, ValueError):
        raise actions.ActionError('preview_mismatch', 'The stored draft preview is unavailable. Prepare and review a new operation.') from None
    if _digest(fields) != op['request_digest'] or _digest(snapshot) != op['snapshot_digest']:
        raise actions.ActionError('preview_mismatch', 'The stored draft preview changed. Prepare and review a new operation.')
    try:
        current = drafts.context(conn, user, fields)
    except permissions.Denied:
        raise
    except ValueError:
        raise actions.ActionError('draft_unavailable', 'Review the current Create date range and organizing section.') from None
    if _digest(current) != op['snapshot_digest']:
        raise actions.ActionError('revision_conflict', 'The requester or organizing section changed. Prepare and review a new draft preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id', 'operation_id', 'grant_id', 'resource',
                                   'request_digest', 'snapshot_digest', 'domain_key', 'created_at', 'expires_at')])


def _result(op, origin):
    return {'operation_id': op['operation_id'], 'action': 'prepare_activity_draft',
            'status': 'completed' if op['completed_at'] else 'awaiting_confirmation',
            'completed_at': op['completed_at'], 'expires_at': op['expires_at'],
            'draft_id': str(op['draft_id']) if op['draft_id'] else None,
            'saved_status': 'private_draft' if op['completed_at'] else None,
            'notification_status': 'none_created',
            'next_actor': {'role': 'owner_review_in_create'} if op['completed_at'] else None,
            'web_url': (origin + '/activity-drafts/' + op['domain_key']) if op['draft_id'] else None,
            'confirmation_url': origin + '/account/integrations/mcp/activity-drafts/' + op['operation_id'],
            'instruction': ('Your private activity draft was saved. No event, survey, public link or email was created. Open it in Office Connect and load Create for a separate review if needed.'
                            if op['completed_at'] else 'Review the exact draft and confirm saving it in Office Connect. No activity draft or live activity has been saved by this operation yet. Keep this operation key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = drafts.normalize(fields)
    with transaction(conn):
        prune(conn)
    with transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_activity_draft_operation WHERE owner_id=? AND operation_id=?',
                        (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different draft or connection. Recover the original operation before creating another.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        try:
            snapshot = drafts.context(conn, user, values)
        except permissions.Denied:
            raise
        except ValueError:
            raise actions.ActionError('draft_unavailable', 'Review the current Create date range and organizing section.') from None
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) '
            'FROM mcp_activity_draft_operation WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The private draft preview limit has been reached.')
        now = int(time.time())
        domain_key = str(uuid4())
        conn.execute('INSERT INTO mcp_activity_draft_operation VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             domain_key, now, now + actions.PREVIEW_SECONDS))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_activity_draft',
                 target_id=operation_id, summary='MCP private activity draft preview', commit=False)
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
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_activity_draft',
                 target_id=operation_id, summary='MCP own activity draft receipt read', commit=False)
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
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this activity draft.')
            if not op['completed_at']:
                fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
                try:
                    saved = drafts.save_in_transaction(conn, user, fields, expected_context=snapshot, operation_key=op['domain_key'])
                except permissions.Denied:
                    raise
                except ValueError:
                    raise actions.ActionError('draft_unavailable', 'Review the current Create date range, section and private draft limit.') from None
                draft_id = saved['id']
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_activity_draft_operation SET completed_at=?,draft_id=?,payload_json=NULL,snapshot_json=NULL '
                    'WHERE owner_id=? AND operation_id=?', (completed, draft_id, user['id'], operation_id))
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_activity_draft',
                         target_id=operation_id, summary='MCP private activity draft saved', commit=False)
                op.update(completed_at=completed, draft_id=draft_id, payload_json=None, snapshot_json=None)
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)


def read_context(conn,token,resource,origin,*,limit=25,offset=0):
    if type(limit) is not int or not 1<=limit<=25 or type(offset) is not int or not 0<=offset<=500:
        raise ValueError('Use a section page of 1–25 with offset 0–500.')
    with transaction(conn):
        _enabled(conn);user,_=actions.token_actor(conn,token,resource,SCOPE);drafts.actor(conn,user)
        sections=rows(conn,"SELECT id,name FROM org_unit WHERE level='section' ORDER BY path,id LIMIT ? OFFSET ?",(limit+1,offset))
        lo,hi=drafts.scheduling.date_bounds()
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_draft',summary='MCP activity draft section choices',commit=False)
        return {'sections':[dict(s,id=str(s['id'])) for s in sections[:limit]],'offset':offset,'limit':limit,
                'next_offset':offset+limit if len(sections)>limit else None,'date_min':lo,'date_max':hi,
                'event_type':'bureau','modality':'f2f','speakers_supported':False,'web_url':origin+'/activity-drafts/new'}
