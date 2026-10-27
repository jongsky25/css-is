"""M3.5 explicit paper-handover recording, never signing, dispatch or payment."""
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

SCOPE = 'travel:filing:submit'
FLAG = 'CSS_MCP_TRAVEL_SUBMISSIONS_ENABLED'


class SubmissionFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filing_id: StrictInt = Field(ge=1, le=2**63-1)
    expected_updated_at: StrictStr = Field(min_length=1, max_length=80)


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_travel_submission (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      filing_id INTEGER NOT NULL REFERENCES travel_filing(id), completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_travel_submission_expiry ON mcp_travel_submission(expires_at)
      WHERE payload_json IS NOT NULL;''')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled(conn):
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1' or not travel.enabled(conn):
        raise actions.ActionError('not_available', 'Recording travel paper submission through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_travel_submission SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_travel_submission WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _op(conn, owner_id, key):
    found = rows(conn, 'SELECT * FROM mcp_travel_submission WHERE owner_id=? AND operation_id=?', (owner_id, actions._key(key)))
    if not found:
        raise permissions.Denied('Paper submission operation not found or unavailable to you.')
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
        raise actions.ActionError('revision_conflict', 'The filing changed. Read its current stamp and prepare a new preview.')
    items, flags = travel.view_items(conn, filing), travel.flags_of(conn, filing['id'])
    if filing['status'] != 'ready' or rules.readiness(filing, items, flags) or review.gate(conn, filing):
        raise actions.ActionError('action_unavailable', 'Use the normal filing to finish its papers, required review and Ready step before recording handover.')
    return {'filing_id': filing['id'], 'reference': filing['ref_code'], 'title': filing['act_title'],
            'start': filing['act_start'], 'end': filing['act_end'], 'updated_at': filing['updated_at'],
            'status': filing['status'], 'review_state': filing['review_state'], 'review_required': review.required(conn),
            'documents': [{'code': i['code'], 'label': i['label'], 'state': i['state'], 'copies': i['copies'], 'wet_sign': i['wet_sign']}
                          for i in items if i['requirement']=='required' and i['state']!='na'],
            'content_digest': _digest([filing, items, flags, review.notes_of(conn, filing['id'])])}


def _check(conn, user, op, resource):
    _enabled(conn)
    actions._grant(conn, op['grant_id'], user['id'], resource, SCOPE)
    if op['resource'] != resource:
        raise permissions.Denied('Paper submission operation not found or unavailable to you.')
    filing = _filing(conn, user, op['filing_id'])
    if op['completed_at']:
        result = json.loads(op['result_json'])
        if (filing['ref_code'], filing['opened_at']) != (result['reference'], result['opened_at']):
            raise permissions.Denied('The original filing source is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired', 'This paper submission preview expired. Prepare a new operation.')
    try:
        fields, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
        if (SubmissionFields.model_validate(fields).model_dump() != fields or _digest(fields) != op['request_digest']
                or _digest(snapshot) != op['snapshot_digest']):
            raise ValueError
    except (ValueError, TypeError):
        raise actions.ActionError('preview_mismatch', 'The stored paper submission preview changed. Prepare a new operation.') from None
    if context(conn, user, fields) != snapshot:
        raise actions.ActionError('revision_conflict', 'The filing, papers, flags or review changed. Prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest',
                                   'domain_key','created_at','expires_at','filing_id')])


def _result(op, origin):
    result = json.loads(op['result_json']) if op['completed_at'] else None
    return {'operation_id': op['operation_id'], 'action': 'prepare_travel_filing_submission',
            'status': 'completed' if result else 'awaiting_confirmation', 'completed_at': op['completed_at'],
            'expires_at': op['expires_at'], 'filing_id': str(op['filing_id']),
            'recorded_status': 'submitted' if result else None, 'submitted_at': result['submitted_at'] if result else None,
            'paper_handover_attested': True if result else None,
            'next_actor': {'role': 'traveller_follow_up_with_receiving_office', 'user_id': str(op['owner_id'])} if result else None,
            'web_url': origin+'/travel/f/'+result['reference'] if result else origin+'/travel',
            'confirmation_url': origin+'/account/integrations/mcp/travel-submissions/'+op['operation_id'],
            'instruction': ('Paper handover recorded from your browser confirmation. Keep your copies and follow up with the receiving office. This original receipt does not confirm receipt, approval or payment; open the source for current state.'
                            if result else 'Only after physically handing in the required papers, review the exact filing/checklist and attest that handover in Office Connect. This call has not submitted a filing or handed over any papers. Keep this key for recovery.')}


def read_context(conn, token, resource, origin, filing_id):
    if type(filing_id) is not int or not 1 <= filing_id <= 2**63-1:
        raise ValueError('Use a positive filing ID.')
    with transaction(conn):
        _enabled(conn)
        user, _ = actions.token_actor(conn, token, resource, SCOPE)
        filing = _filing(conn, user, filing_id)
        ready = not rules.readiness(filing, travel.view_items(conn, filing), travel.flags_of(conn, filing_id))
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_submission', target_id=filing_id,
                 summary='MCP own paper submission context read', commit=False)
        return {'filing_id': str(filing_id), 'reference': filing['ref_code'], 'status': filing['status'],
                'review_state': filing['review_state'], 'review_required': review.required(conn),
                'expected_updated_at': filing['updated_at'], 'checklist_ready': ready,
                'ready_to_record': filing['status']=='ready' and ready and review.gate(conn, filing) is None,
                'web_url': origin+'/travel/f/'+filing['ref_code']}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id)
    values = SubmissionFields.model_validate(fields).model_dump()
    with transaction(conn): prune(conn)
    with transaction(conn):
        _enabled(conn)
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_travel_submission WHERE owner_id=? AND operation_id=?', (user['id'], operation_id)).fetchone():
            op = _op(conn, user['id'], operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict', 'This key belongs to a different paper submission or connection. Recover the original operation.')
            _check(conn, user, op, resource)
            return _result(op, origin)
        snapshot = context(conn, user, values)
        count, pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_travel_submission WHERE owner_id=?', (int(time.time()), user['id'])).fetchone()
        if count >= 10000 or pending >= 50:
            raise actions.ActionError('operation_capacity', 'The paper submission preview limit has been reached.')
        now = int(time.time())
        conn.execute('INSERT INTO mcp_travel_submission VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'], operation_id, grant_id, resource, digest, _digest(snapshot), _json(values), _json(snapshot),
             str(uuid4()), now, now+actions.PREVIEW_SECONDS, values['filing_id']))
        st.audit(conn, user['username'], 'integration_action_prepare', target_type='mcp_travel_submission',
                 target_id=operation_id, summary='MCP own paper submission preview', commit=False)
        return _result(_op(conn, user['id'], operation_id), origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user, grant_id = actions.token_actor(conn, token, resource, SCOPE)
        op = _op(conn, user['id'], operation_id)
        if op['grant_id'] != grant_id: raise permissions.Denied('Paper submission operation not found or unavailable to you.')
        _check(conn, user, op, resource)
        st.audit(conn, user['username'], 'integration_read', target_type='mcp_travel_submission', target_id=operation_id,
                 summary='MCP own paper submission receipt read', commit=False)
        return _result(op, origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user = st.session_actor(conn, payload) if payload else None
        if not user: raise permissions.Denied('Sign in again to record this paper submission.')
        op = _op(conn, user['id'], operation_id)
        _check(conn, user, op, resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op):
                raise actions.ActionError('preview_mismatch', 'The confirmation does not match this paper submission.')
            if not op['completed_at']:
                filing = _filing(conn, user, op['filing_id'])
                done = travel.mark_submitted(conn, filing, commit=False)
                completed = tz.now_iso()
                result = {'reference': done['ref_code'], 'opened_at': done['opened_at'], 'submitted_at': done['submitted_at']}
                conn.execute('UPDATE mcp_travel_submission SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                    (completed, _json(result), user['id'], operation_id))
                st.audit(conn, user['username'], 'travel_submit', target_type='travel_filing', target_id=done['id'],
                         summary='Owner attested physical paper submission through MCP', commit=False)
                st.audit(conn, user['username'], 'integration_action_complete', target_type='mcp_travel_submission',
                         target_id=operation_id, summary='MCP own paper submission recorded', commit=False)
                op.update(completed_at=completed, result_json=_json(result), payload_json=None, snapshot_json=None)
        return dict(_result(op, origin), preview_digest=_preview_digest(op),
                    fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
