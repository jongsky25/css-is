"""Atomic task actions and actor-owned recovery receipts for API v1."""
import hashlib
import json

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import storage as st
import tzutil as tz
import work_reads
import work_tasks

RESULT_STATUS = {'acknowledge': 'in_progress', 'submit': 'for_review'}


class OperationError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def session_actor(conn, payload):
    # Recheck after acquiring the snapshot/writer lock, including revocation that
    # happened after the parent HTTP middleware authenticated the cookie.
    user = st.session_actor(conn, payload) if payload else None
    if not user:
        raise OperationError(401, 'authentication_required', 'A current signed-in session is required.')
    return permissions.actor(conn, user)


def find(conn, user, operation_id):
    found = rows(conn, 'SELECT * FROM work_api_operation WHERE actor_id=? AND operation_id=?',
                 (user['id'], operation_id))
    if not found:
        raise permissions.Denied('Operation not found or unavailable to you.')
    receipt = found[0]
    # A receipt never keeps access alive after reassignment, grant revocation,
    # restricted/canonical document changes or lost case readership.
    work_reads.task(conn, user, receipt['case_id'], receipt['task_id'])
    return receipt


def acknowledge(conn, payload, case_id, task_id, operation_id, revision, reason):
    return _change(conn, payload, case_id, task_id, operation_id, revision, 'acknowledge', {'reason': reason})


def submit(conn, payload, case_id, task_id, operation_id, revision, reason, submission):
    return _change(conn, payload, case_id, task_id, operation_id, revision, 'submit',
                   {'reason': reason, 'submission': submission})


def acknowledge_in_transaction(conn, payload, case_id, task_id, operation_id, revision, reason):
    """Shared API receipt contract for an already verified browser confirmation.

    The caller owns the writer transaction; current session/target authority is
    checked here again and the caller must commit the receipt with its own state.
    """
    return _change_in_transaction(conn, payload, case_id, task_id, operation_id, revision,
                                  'acknowledge', {'reason': reason})


def submit_in_transaction(conn, payload, case_id, task_id, operation_id, revision, reason, submission):
    """Use the canonical submission receipt in the caller's writer transaction."""
    return _change_in_transaction(conn, payload, case_id, task_id, operation_id, revision,
                                  'submit', {'reason': reason, 'submission': submission})


def _change(conn, payload, case_id, task_id, operation_id, revision, action, fields):
    with transaction(conn):
        return _change_in_transaction(conn, payload, case_id, task_id, operation_id, revision, action, fields)


def _change_in_transaction(conn, payload, case_id, task_id, operation_id, revision, action, fields):
    if not conn.in_transaction:
        raise RuntimeError('A caller-owned task-operation transaction is required.')
    # Keep the 7.97 acknowledgement fingerprint byte-for-byte compatible.
    content = [action, str(case_id), str(task_id), revision, fields['reason']]
    if action == 'submit':
        content.append(fields['submission'])
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    user = session_actor(conn, payload)
    # Check current target visibility before revealing a key collision.
    current_task = work_reads.task(conn, user, case_id, task_id)
    found = rows(conn, 'SELECT * FROM work_api_operation WHERE actor_id=? AND operation_id=?',
                 (user['id'], operation_id))
    if found:
        receipt = find(conn, user, operation_id)
        if receipt['request_digest'] != digest:
            raise OperationError(409, 'idempotency_conflict',
                                 'This operation key was already used for a different request.')
        return receipt
    try:
        # Shared UI service owns feature switches, open-case checks, task
        # revision, owner/officer authority, audit and review invalidation.
        updated = work_tasks.mutate_in_transaction(conn, user, case_id, task_id,
                                                   revision, action, fields)
    except docs.Conflict:
        if current_task['revision'] != revision:
            raise OperationError(409, 'revision_conflict',
                                 'The task changed. Read its current revision before making a new request.') from None
        raise OperationError(409, 'action_unavailable',
                             'A related workflow operation needs attention. Review the task in the system.') from None
    except permissions.Denied:
        raise
    except ValueError:
        raise OperationError(409, 'action_unavailable',
                             'The task action is unavailable in the current workflow. Review it in the system.') from None
    conn.execute('''INSERT INTO work_api_operation
        (actor_id,operation_id,request_digest,case_id,task_id,result_revision,completed_at,action)
        VALUES(?,?,?,?,?,?,?,?)''',
        (user['id'], operation_id, digest, case_id, task_id, updated['revision'], tz.now_iso(), action))
    return find(conn, user, operation_id)
