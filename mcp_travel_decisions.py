"""Browser-confirmed travel reviewer decisions with a durable single-attempt email queue."""
import hashlib
import json
import os
import time
from uuid import uuid4
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import travel
import travel_review as review
import travel_rules as rules
import tzutil as tz

SCOPE = 'travel:review:decide'
FLAG = 'CSS_MCP_TRAVEL_REVIEW_DECISIONS_ENABLED'


class DecisionFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filing_id: StrictInt = Field(ge=1, le=2**63-1)
    decision: Literal['approve', 'return_notes']
    expected_revision: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_travel_decision (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      filing_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_travel_decision_expiry ON mcp_travel_decision(expires_at) WHERE payload_json IS NOT NULL;
    CREATE TABLE IF NOT EXISTS mcp_travel_decision_mail (
      operation_key TEXT PRIMARY KEY REFERENCES mcp_travel_decision(domain_key),
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), filing_id INTEGER NOT NULL,
      traveller_id INTEGER NOT NULL, review_round INTEGER NOT NULL,
      source_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, payload_json TEXT,
      state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','attempting','sent','uncertain','skipped_off','not_configured','cancelled')),
      attempt_id TEXT, attempted_at INTEGER, finished_at TEXT);
    CREATE INDEX IF NOT EXISTS mcp_travel_decision_mail_queue ON mcp_travel_decision_mail(state);''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1' or not travel.enabled(conn):
        raise actions.ActionError('not_available', 'Travel reviewer decisions through ChatGPT are disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_travel_decision SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_travel_decision WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_travel_decision WHERE owner_id=? AND operation_id=?', (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Travel decision operation not found or unavailable to you.')
    return found[0]


def _filing(conn, user, filing_id):
    user = permissions.actor(conn, user)
    filing = travel.get_filing(conn, filing_id)
    if (not filing or filing.get('purged_at') or filing['user_id'] == user['id']
            or not review.can_review(conn, user, filing)):
        raise permissions.Denied('Travel filing not found or unavailable to you as its selected reviewer.')
    return filing


def _account(conn, user_id):
    account = permissions.actor(conn, st.get_admin_user_by_id(conn, user_id))
    rp = rows(conn, 'SELECT * FROM resource_person WHERE id=?', (account.get('rp_id'),))
    unit = rows(conn, 'SELECT * FROM org_unit WHERE id=?', (rp[0]['org_unit_id'],)) if rp else []
    return {'id': account['id'], 'name': st._account_display_name(conn, account['id']) or account['username'],
            'email': account['username'], 'authority_digest': _digest([account['role'], rp, unit])}


def live(conn, user, filing_id):
    filing = _filing(conn, user, filing_id)
    # Bound all child reads, including raw saved checklist metadata not projected
    # into view_items. None of their content is returned to the model.
    for table, cap in (('travel_item', 60), ('travel_flag', 100), ('travel_review_note', 100)):
        if conn.execute('SELECT COUNT(*) FROM (SELECT 1 FROM '+table+' WHERE filing_id=? LIMIT ?)',
                        (filing_id, cap+1)).fetchone()[0] > cap:
            raise actions.ActionError('action_unavailable', 'Use the normal reviewer page for this larger filing.')
    items, flags, notes = travel.view_items(conn, filing), travel.flags_of(conn, filing_id), review.notes_of(conn, filing_id)
    raw = rows(conn, 'SELECT * FROM travel_item WHERE filing_id=? ORDER BY item_code', (filing_id,))
    reviewer, traveller = _account(conn, user['id']), _account(conn, filing['user_id'])
    return {'filing': filing, 'items': items, 'flags': flags, 'notes': notes, 'raw_items': raw,
            'reviewer': reviewer, 'traveller': traveller, 'review_required': review.required(conn),
            'email_enabled': st.email_feature_enabled(conn, 'travel_review_result')}


def context(conn, user, fields):
    saved = live(conn, user, fields['filing_id'])
    if _digest(saved) != fields['expected_revision']:
        raise actions.ActionError('revision_conflict', 'The filing, papers, notes, people or mail policy changed. Read fresh context and prepare a new preview.')
    filing = saved['filing']
    drafts = [n for n in saved['notes'] if n['state'] == 'draft']
    if filing['status'] != 'open' or filing['review_state'] != 'requested' or filing['gen_state'] == 'running':
        raise actions.ActionError('action_unavailable', 'This filing is not currently waiting for a reviewer decision.')
    if any(n['round'] != filing['review_round'] for n in drafts):
        raise actions.ActionError('action_unavailable', 'Resolve older draft notes on the normal reviewer page first.')
    if fields['decision'] == 'approve':
        if drafts or rules.readiness(filing, saved['items'], saved['flags']):
            raise actions.ActionError('action_unavailable', 'Finish the checklist, resolve flags and remove or return draft notes before approving the papers.')
    elif not drafts:
        raise actions.ActionError('action_unavailable', 'Draft at least one note on the normal reviewer page before returning notes.')
    if conn.execute('SELECT 1 FROM mcp_travel_decision_mail WHERE source_key=?', (_source_key(filing),)).fetchone():
        raise actions.ActionError('action_unavailable', 'This review round already has an original MCP decision. Recover that operation.')
    labels = {i['code']: i['label'] for i in saved['items']}
    return {'filing_id': filing['id'], 'reference': filing['ref_code'], 'title': filing['act_title'],
            'start': filing['act_start'], 'end': filing['act_end'], 'review_round': filing['review_round'],
            'decision': fields['decision'], 'reviewer': saved['reviewer'], 'traveller': saved['traveller'],
            'documents': [{'code': i['code'], 'label': i['label'], 'state': i['state'], 'copies': i['copies'],
                           'wet_sign': i['wet_sign']} for i in saved['items']],
            'notes': [{'document': labels.get(n['item_code'], ''), 'kind': n['kind'], 'note': n['note']}
                      for n in drafts], 'email_enabled': saved['email_enabled'], 'content_digest': _digest(saved)}


def _source_key(filing):
    return _digest([filing[k] for k in ('id', 'ref_code', 'opened_at', 'review_round')])


def _check(conn, user, op, resource):
    _enabled(conn)
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if op['resource'] != resource:
        raise permissions.Denied('Travel decision operation not found or unavailable to you.')
    filing = _filing(conn, user, op['filing_id'])
    if op['completed_at']:
        result = json.loads(op['result_json'])
        if (filing['ref_code'], filing['opened_at'], filing['user_id']) != (result['reference'], result['opened_at'], result['traveller_id']):
            raise permissions.Denied('The original travel decision source is unavailable.')
        if not conn.execute('SELECT 1 FROM mcp_travel_decision_mail WHERE operation_key=? AND source_key=? AND traveller_id=?',
                            (op['domain_key'], result['source_key'], result['traveller_id'])).fetchone():
            raise permissions.Denied('The original travel decision receipt is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This travel review preview expired. Prepare a new operation.')
    try:
        fields = json.loads(op['payload_json'])
        snapshot = json.loads(op['snapshot_json'])
        if (DecisionFields.model_validate(fields).model_dump() != fields or _digest(fields) != op['request_digest']
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
    mail = conn.execute('SELECT state FROM mcp_travel_decision_mail WHERE operation_key=?', (op['domain_key'],)).fetchone()
    return {'operation_id': op['operation_id'], 'action': 'prepare_travel_review_decision',
            'status': 'completed' if result else 'awaiting_confirmation', 'completed_at': op['completed_at'],
            'expires_at': op['expires_at'], 'filing_id': str(op['filing_id']),
            'decision': result['decision'] if result else None,
            'recorded_review_state': result['review_state'] if result else None,
            'review_round': result['review_round'] if result else None,
            'returned_note_count': result['note_count'] if result else None,
            'next_actor': {'role': 'traveller', 'user_id': str(result['traveller_id'])} if result else None,
            'notification_status': mail[0] if mail else None,
            'web_url': origin + '/travel/review/' + result['reference'] if result else origin + '/travel/review',
            'confirmation_url': origin + '/account/integrations/mcp/travel-review-decisions/' + op['operation_id'],
            'instruction': ('Original papers-review decision recorded. The traveller fixes returned notes and requests another review, or marks approved papers Ready. Open the source for current state. Notification status is current, not proof of delivery. This does not approve/pay the claim, sign, dispatch or record physical paper handover.'
                            if result else 'Review the exact papers, existing notes, selected reviewer and traveller recipient in Office Connect before confirming. This call has made no decision and sent no email. Keep this key for recovery.')}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = DecisionFields.model_validate(fields).model_dump()
    with transaction(conn): prune(conn)
    with transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_travel_decision WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different reviewer decision or connection. Recover the original operation.')
            _check(conn, user, op, resource)
            return _result(conn, op, origin)
        snapshot = context(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_travel_decision WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The travel review preview limit has been reached.')
        now = int(time.time())
        conn.execute('INSERT INTO mcp_travel_decision VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             str(uuid4()), now, now + actions.PREVIEW_SECONDS, values['filing_id']))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_travel_decision',
                 target_id=operation_id, summary='MCP selected travel reviewer decision preview', commit=False)
        return _result(conn, _op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id: raise permissions.Denied('Travel decision operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_decision',
                 target_id=operation_id, summary='MCP selected travel reviewer decision receipt read', commit=False)
        return _result(conn, op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user: raise permissions.Denied('Sign in again as the selected travel reviewer.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this reviewer decision.')
            if not op['completed_at']:
                fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
                filing = _filing(conn, user, fields['filing_id'])
                approved = fields['decision'] == 'approve'
                if approved:
                    done = review.approve(conn, filing, user['username'], commit=False)
                else:
                    done, _ = review.send_feedback(conn, filing, user['username'], commit=False)
                completed = tz.now_iso()
                result = {'reference': done['ref_code'], 'opened_at': done['opened_at'],
                          'traveller_id': done['user_id'], 'review_round': done['review_round'],
                          'review_state': done['review_state'], 'decision': fields['decision'],
                          'note_count': len(snapshot['notes']), 'source_key': _source_key(done),
                          'live_digest': _digest(live(conn, user, done['id']))}
                mail = {'to': snapshot['traveller']['email'], 'traveller_name': snapshot['traveller']['name'],
                        'ref': done['ref_code'], 'title': snapshot['title'], 'approved': approved,
                        'notes': [[n['document'], n['kind'], n['note']] for n in snapshot['notes']],
                        'link': origin + '/travel/f/' + done['ref_code']}
                result['mail_digest'] = _digest(mail)
                state = 'queued' if snapshot['email_enabled'] else 'skipped_off'
                conn.execute('INSERT INTO mcp_travel_decision_mail(operation_key,owner_id,filing_id,traveller_id,review_round,source_key,created_at,payload_json,state,finished_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (op['domain_key'], user['id'], done['id'], done['user_id'], done['review_round'], result['source_key'],
                     int(time.time()), _json(mail) if state == 'queued' else None, state, None if state == 'queued' else completed))
                if state == 'skipped_off':
                    conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
                        (completed, 'travel_review_result', mail['to'], 'Travel papers review result', 'skipped_off',
                         'MCP reviewer decision: disabled at confirmation; no automatic retry'))
                conn.execute('UPDATE mcp_travel_decision SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                    (completed, _json(result), user['id'], operation_id))
                st.audit(conn, user['username'], 'travel_review_approve' if approved else 'travel_review_feedback', target_type='travel_filing', target_id=done['id'],
                         summary='Recorded selected reviewer papers decision through MCP', commit=False)
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_travel_decision',
                         target_id=operation_id, summary='MCP selected travel reviewer decision recorded', commit=False)
                op.update(completed_at=completed, result_json=_json(result), payload_json=None, snapshot_json=None)
        return dict(_result(conn, op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)


def read_context(conn, token, resource, origin, filing_id):
    if type(filing_id) is not int or not 1 <= filing_id <= 2**63-1:
        raise ValueError('Use a positive filing ID.')
    with transaction(conn):
        _enabled(conn)
        user, _ = actions.token_actor(conn, token, resource, SCOPE)
        saved = live(conn, user, filing_id)
        filing = saved['filing']
        drafts = [n for n in saved['notes'] if n['state'] == 'draft']
        waiting = filing['status']=='open' and filing['review_state']=='requested' and filing['gen_state']!='running'
        waiting = waiting and all(n['round']==filing['review_round'] for n in drafts)
        waiting = waiting and not conn.execute('SELECT 1 FROM mcp_travel_decision_mail WHERE source_key=?', (_source_key(filing),)).fetchone()
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_decision', target_id=filing_id,
                 summary='MCP selected reviewer preparation context', commit=False)
        return {'filing_id': str(filing_id), 'expected_revision': _digest(saved), 'review_round': filing['review_round'],
                'review_state': filing['review_state'], 'status': filing['status'], 'draft_note_count': len(drafts),
                'can_approve_papers': bool(waiting and not drafts and not rules.readiness(filing, saved['items'], saved['flags'])),
                'can_return_notes': bool(waiting and drafts), 'web_url': origin+'/travel/review/'+filing['ref_code']}
