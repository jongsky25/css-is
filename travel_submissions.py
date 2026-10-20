"""Durable receipts for opening travel filings; no external effects in this transaction.

A pending marker commits before work starts. The filing, checklist, audit and
completed receipt then commit together under SQLite's writer lock. A restarted
process can resume a pending operation: it either sees the committed receipt or
starts after the previous writer rolled back. Callbacks must not commit.
"""
from __future__ import annotations

import hashlib
import json
import uuid

import tzutil as tz


class MissingOperation(ValueError):
    pass


class ChangedSubmission(ValueError):
    pass


class RejectedSubmission(ValueError):
    pass


def _key(value):
    try:
        key = str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise MissingOperation('This submission could not be found.') from None
    if key != value:
        raise MissingOperation('This submission could not be found.')
    return key


def issue(conn, user_id):
    key, now = str(uuid.uuid4()), tz.now_iso()
    with conn:
        conn.execute('INSERT INTO travel_submission VALUES (?,?,\'ready\',NULL,NULL,?,?)',
                     (key, user_id, now, now))
    return key


def lookup(conn, user_id, operation_id):
    row = conn.execute('SELECT state,request_hash,result_ref FROM travel_submission '
                       'WHERE operation_id=? AND user_id=?', (_key(operation_id), user_id)).fetchone()
    if row is None:
        raise MissingOperation('This submission could not be found.')
    return dict(zip(('state', 'request_hash', 'ref'), row))


def close_unfinished(conn, user_id, operation_id, *, on_close=None):
    """Retire a lost form only after the active writer has finished or rolled back."""
    if conn.in_transaction:
        raise RuntimeError('Travel submissions require a dedicated connection')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        state = lookup(conn, user_id, operation_id)
        if state['state'] in ('ready', 'pending'):
            conn.execute("UPDATE travel_submission SET state='rejected',updated_at=? WHERE operation_id=?",
                         (tz.now_iso(), operation_id))
            if on_close is not None:
                on_close()


def execute(conn, user_id, operation_id, fields, action, *, rejected_exceptions=()):
    """Return the original reference, or execute the local action once.

    Only server-issued keys belonging to this actor are accepted. Validation
    rejections consume the key; a corrected form receives a new key. Unexpected
    failures leave a pending marker and roll back every business write.
    """
    key = _key(operation_id)
    fingerprint = hashlib.sha256(json.dumps(
        {k: v for k, v in fields.items() if k != 'operation_id'},
        sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()

    def checked():
        state = lookup(conn, user_id, key)
        if state['request_hash'] is not None and state['request_hash'] != fingerprint:
            raise ChangedSubmission('This form has already been used with different answers. '
                                    'Check its status before opening another filing.')
        if state['state'] == 'rejected':
            raise RejectedSubmission('This attempt did not open a filing. Review the form and submit again.')
        return state

    if conn.in_transaction:
        raise RuntimeError('Travel submissions require a dedicated connection')
    # Persist intent separately so a process crash leaves something to look up.
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        state = checked()
        if state['state'] == 'completed':
            return state['ref']
        conn.execute("UPDATE travel_submission SET state='pending',request_hash=?,updated_at=? "
                     'WHERE operation_id=?', (fingerprint, tz.now_iso(), key))

    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            state = checked()  # Another request may have completed while we waited.
            if state['state'] == 'completed':
                return state['ref']
            ref = action()
            if not conn.in_transaction:
                raise RuntimeError('Travel submission action must not commit')
            conn.execute("UPDATE travel_submission SET state='completed',result_ref=?,updated_at=? "
                         'WHERE operation_id=?', (ref, tz.now_iso(), key))
        return ref
    except rejected_exceptions:
        with conn:
            conn.execute("UPDATE travel_submission SET state='rejected',updated_at=? "
                         "WHERE operation_id=? AND state='pending' AND request_hash=?",
                         (tz.now_iso(), key, fingerprint))
        raise
