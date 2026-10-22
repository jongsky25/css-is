"""Atomic task acknowledgement and actor-owned recovery receipts for API v1."""
import hashlib
import json

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import storage as st
import tzutil as tz
import work_reads
import work_tasks


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
    digest = hashlib.sha256(json.dumps(
        ['acknowledge', str(case_id), str(task_id), revision, reason],
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    with transaction(conn):
        user = session_actor(conn, payload)
        # Check current target visibility before revealing a key collision.
        work_reads.task(conn, user, case_id, task_id)
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
                                                       revision, 'acknowledge', {'reason': reason})
        except docs.Conflict:
            raise OperationError(409, 'revision_conflict',
                                 'The task changed. Read its current revision before making a new request.') from None
        except permissions.Denied:
            raise
        except ValueError:
            raise OperationError(409, 'action_unavailable',
                                 'The task cannot be acknowledged in the current workflow. Review it in the system.') from None
        conn.execute('''INSERT INTO work_api_operation
            (actor_id,operation_id,request_digest,case_id,task_id,result_revision,completed_at)
            VALUES(?,?,?,?,?,?,?)''',
            (user['id'], operation_id, digest, case_id, task_id, updated['revision'], tz.now_iso()))
        return find(conn, user, operation_id)
