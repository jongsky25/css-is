"""Browser-confirmed travel review requests with a durable single-attempt email queue."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import travel
import travel_review as review
import travel_rules as rules
import tzutil as tz

SCOPE = 'travel:review:request'
FLAG = 'CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED'


class ReviewFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filing_id: StrictInt = Field(ge=1, le=2**63-1)
    reviewer_id: StrictInt = Field(ge=1, le=2**63-1)
    expected_updated_at: StrictStr = Field(min_length=1, max_length=80)


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_travel_review (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      filing_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_travel_review_expiry ON mcp_travel_review(expires_at) WHERE payload_json IS NOT NULL;
    CREATE TABLE IF NOT EXISTS mcp_travel_review_mail (
      operation_key TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      filing_id INTEGER NOT NULL REFERENCES travel_filing(id), reviewer_id INTEGER NOT NULL,
      review_round INTEGER NOT NULL, created_at INTEGER NOT NULL, payload_json TEXT,
      state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','attempting','sent','uncertain','skipped_off','not_configured','cancelled')),
      attempt_id TEXT, attempted_at INTEGER, finished_at TEXT,
      UNIQUE(filing_id,review_round));
    CREATE INDEX IF NOT EXISTS mcp_travel_review_mail_queue ON mcp_travel_review_mail(state);''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1' or not travel.enabled(conn):
        raise actions.ActionError('not_available', 'Requesting travel review through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_travel_review SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_travel_review WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_travel_review WHERE owner_id=? AND operation_id=?', (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Travel review operation not found or unavailable to you.')
    return found[0]


def _filing(conn, user, filing_id):
    user = permissions.actor(conn, user)
    filing = travel.get_filing(conn, filing_id)
    if not travel.is_owner(user, filing) or filing.get('purged_at'):
        raise permissions.Denied('Travel filing not found or unavailable to you.')
    return filing


def context(conn, user, fields):
    filing = _filing(conn, user, fields['filing_id'])
    if filing['updated_at'] != fields['expected_updated_at']:
        raise actions.ActionError('revision_conflict', 'The filing changed. Read its current update stamp and prepare a new preview.')
    try:
        review._need_state(filing, '', 'changes', why='This filing cannot be requested for review now.')
    except travel.TravelError:
        raise actions.ActionError('action_unavailable', 'Review the current filing status before requesting review.') from None
    items = travel.view_items(conn, filing)
    flags = travel.flags_of(conn, filing['id'])
    if rules.readiness(filing, items, flags):
        raise actions.ActionError('action_unavailable', 'Finish the filing checklist and resolve its flags before requesting review.')
    candidates = {r['id']: r for r in review.reviewers(conn, exclude_user_id=user['id'])}
    selected = candidates.get(fields['reviewer_id'])
    if not selected:
        raise permissions.Denied('Choose a current Administrative Section reviewer other than yourself.')
    notes = review.notes_of(conn, filing['id'])
    return {'filing_id': filing['id'], 'ref_code': filing['ref_code'], 'title': filing['act_title'],
            'start': filing['act_start'], 'end': filing['act_end'], 'updated_at': filing['updated_at'],
            'review_state': filing['review_state'], 'review_round': filing['review_round'],
            'reviewer': {'id': selected['id'], 'name': selected['name'], 'email': selected['username']},
            'traveller_name': st._account_display_name(conn, user['id']) or user['username'],
            'documents': [{'code': i['code'], 'label': i['label'], 'state': i['state']} for i in items],
            'sent_notes_to_resolve': sum(n['state'] == 'sent' for n in notes),
            'content_digest': _digest([filing, items, flags, notes]),
            'email_enabled': st.email_feature_enabled(conn, 'travel_review_request'),
            'review_required': review.required(conn)}


def _check(conn, user, op, resource):
    _enabled(conn)
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if op['resource'] != resource:
        raise permissions.Denied('Travel review operation not found or unavailable to you.')
    filing = _filing(conn, user, op['filing_id'])
    if op['completed_at']:
        result = json.loads(op['result_json'])
        if filing['ref_code'] != result['ref_code'] or filing['opened_at'] != result['opened_at']:
            raise permissions.Denied('The original travel review source is unavailable.')
        if not conn.execute('SELECT 1 FROM mcp_travel_review_mail WHERE operation_key=? AND filing_id=? AND review_round=?',
                            (op['domain_key'], filing['id'], result['review_round'])).fetchone():
            raise permissions.Denied('The original travel review receipt is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This travel review preview expired. Prepare a new operation.')
    try:
        fields = json.loads(op['payload_json'])
        snapshot = json.loads(op['snapshot_json'])
        if (ReviewFields.model_validate(fields).model_dump() != fields or _digest(fields) != op['request_digest']
                or _digest(snapshot) != op['snapshot_digest']):
            raise ValueError
    except (ValueError, TypeError):
        raise actions.ActionError('preview_mismatch', 'The stored travel review preview changed. Prepare a new operation.') from None
    if context(conn, user, fields) != snapshot:
        raise actions.ActionError('revision_conflict', 'The filing, papers, notes, reviewer or mail setting changed. Prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest',
                                   'domain_key','created_at','expires_at','filing_id')])


def _result(conn, op, origin):
    result = json.loads(op['result_json']) if op['completed_at'] else None
    mail = conn.execute('SELECT state FROM mcp_travel_review_mail WHERE operation_key=?', (op['domain_key'],)).fetchone()
    return {'operation_id': op['operation_id'], 'action': 'prepare_travel_review_request',
            'status': 'completed' if result else 'awaiting_confirmation', 'completed_at': op['completed_at'],
            'expires_at': op['expires_at'], 'filing_id': str(op['filing_id']),
            'review_state': 'requested' if result else None, 'review_round': result['review_round'] if result else None,
            'next_actor': {'role': 'selected_travel_reviewer', 'user_id': str(result['reviewer_id'])} if result else None,
            'notification_status': mail[0] if mail else None,
            'web_url': origin + '/travel/f/' + result['ref_code'] if result else origin + '/travel',
            'confirmation_url': origin + '/account/integrations/mcp/travel-review-requests/' + op['operation_id'],
            'instruction': ('Travel papers requested for review; the selected reviewer acts next. This original receipt does not confirm approval or email delivery. Notification status is current; source state may have changed.'
                            if result else 'Review the filing, document checklist and selected reviewer/email in Office Connect before confirming. No review request or email has been created yet. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = ReviewFields.model_validate(fields).model_dump()
    with transaction(conn): prune(conn)
    with transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_travel_review WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different review request or connection. Recover the original operation.')
            _check(conn, user, op, resource)
            return _result(conn, op, origin)
        snapshot = context(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_travel_review WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The travel review preview limit has been reached.')
        now = int(time.time())
        conn.execute('INSERT INTO mcp_travel_review VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             str(uuid4()), now, now + actions.PREVIEW_SECONDS, values['filing_id']))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_travel_review',
                 target_id=operation_id, summary='MCP own travel review preview', commit=False)
        return _result(conn, _op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id: raise permissions.Denied('Travel review operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_review',
                 target_id=operation_id, summary='MCP own travel review receipt read', commit=False)
        return _result(conn, op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user: raise permissions.Denied('Sign in again to review this travel request.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this review request.')
            if not op['completed_at']:
                fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
                filing = _filing(conn, user, fields['filing_id'])
                done = review.request_review(conn, filing, fields['reviewer_id'], user['username'], commit=False)
                completed = tz.now_iso()
                result = {k: done[k] for k in ('ref_code','opened_at','reviewer_id','review_round')}
                mail = {'to': snapshot['reviewer']['email'], 'reviewer_name': snapshot['reviewer']['name'],
                        'traveller_name': snapshot['traveller_name'], 'ref': done['ref_code'], 'title': snapshot['title'],
                        'link': origin + '/travel/review/' + done['ref_code'], 'again': snapshot['review_state'] == 'changes'}
                result['mail_digest'] = _digest(mail)
                conn.execute('INSERT INTO mcp_travel_review_mail(operation_key,owner_id,filing_id,reviewer_id,review_round,created_at,payload_json) VALUES (?,?,?,?,?,?,?)',
                    (op['domain_key'], user['id'], done['id'], done['reviewer_id'], done['review_round'], int(time.time()), _json(mail)))
                conn.execute('UPDATE mcp_travel_review SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                    (completed, _json(result), user['id'], operation_id))
                st.audit(conn, user['username'], 'travel_review_request', target_type='travel_filing', target_id=done['id'],
                         summary='Requested travel papers review through MCP', commit=False)
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_travel_review',
                         target_id=operation_id, summary='MCP own travel review requested', commit=False)
                op.update(completed_at=completed, result_json=_json(result), payload_json=None, snapshot_json=None)
        return dict(_result(conn, op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)


def read_context(conn, token, resource, origin, filing_id, before=0, limit=10):
    if type(filing_id) is not int or not 1 <= filing_id <= 2**63-1 or type(before) is not int or not 0 <= before <= 2**63-1 or type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError('Use a positive filing ID, a nonnegative reviewer cursor and limit 1–25.')
    with transaction(conn):
        _enabled(conn)
        user, _ = actions.token_actor(conn, token, resource, SCOPE)
        filing = _filing(conn, user, filing_id)
        selected = sorted((r for r in review.reviewers(conn, exclude_user_id=user['id']) if not before or r['id'] < before),
                          key=lambda r: r['id'], reverse=True)[:limit+1]
        ready = not rules.readiness(filing, travel.view_items(conn, filing), travel.flags_of(conn, filing_id))
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_review', target_id=filing_id,
                 summary='MCP own travel review preparation context', commit=False)
        return {'filing_id': str(filing_id), 'reference': filing['ref_code'], 'status': filing['status'],
                'review_status': filing['review_state'], 'expected_updated_at': filing['updated_at'],
                'checklist_ready': ready, 'ready_to_request': ready and filing['status']=='open' and filing['review_state'] in ('','changes'),
                'reviewers': [{'id': str(r['id']), 'name': r['name'] if r['name'] and '@' not in r['name'] else 'Reviewer account '+str(r['id'])} for r in selected[:limit]],
                'next_before': selected[limit-1]['id'] if len(selected)>limit else None,
                'web_url': origin+'/travel/f/'+filing['ref_code']}
