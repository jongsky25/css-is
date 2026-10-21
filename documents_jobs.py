"""Durable document-job ownership and bounded, receipt-first restart recovery."""
import asyncio
from datetime import timedelta
import threading
import uuid

import documents as d
from documents_storage import rows, transaction
import tzutil as tz

LEASE_SECONDS = 600
PENDING_GRACE = 30
INTERVAL = 30
MAX_ATTEMPTS = 6
_RECOVERY_SLOT = threading.Lock()


def now():
    return tz.now_local().isoformat(timespec='seconds')


def later(seconds):
    return (tz.now_local() + timedelta(seconds=seconds)).isoformat(timespec='seconds')


def active(job):
    return bool(job.get('lease_owner') and (job.get('lease_until') or '') > now())


def claim(conn, operation, *, reconcile=False, recovery=False):
    with transaction(conn):
        d.writable(conn)
        found = rows(conn, 'SELECT * FROM document_job WHERE id=?', (operation,))
        allowed = ('running', 'unknown') if reconcile else ('pending',)
        if not found or found[0]['state'] not in allowed:
            raise d.Conflict('Operation is not pending; reconcile unknown outcomes before retrying.')
        if active(found[0]):
            raise d.Conflict('This operation is still in progress. Wait and check its status again.')
        if recovery and not eligible(found[0]):
            raise d.Conflict('This operation is not due for recovery.')
        token = str(uuid.uuid4())
        conn.execute('''UPDATE document_job SET lease_owner=?,lease_until=?,attempts=attempts+1,
            recovery_blocked=0,recovery_note=?,updated_at=? WHERE id=?''',
            (token, later(LEASE_SECONDS), 'Checking the existing service receipt.' if reconcile else '', now(), operation))
    return token


def owned(conn, operation, token):
    found = rows(conn, 'SELECT * FROM document_job WHERE id=? AND lease_owner=?', (operation, token))
    if not found:
        raise d.Conflict('Another worker now owns this operation. Check its current result.')
    return found[0]


def completed(conn, operation, token):
    owned(conn, operation, token)
    conn.execute('''UPDATE document_job SET state='confirmed',result_json='{"confirmed":true}',
        lease_owner=NULL,lease_until=NULL,next_check_at=NULL,last_checked_at=?,updated_at=?,
        recovery_blocked=0,recovery_note='' WHERE id=? AND lease_owner=?''', (now(), now(), operation, token))


def failed(conn, operation, token, state, *, blocked=False, note=''):
    """Called inside the caller's transaction; stale workers change nothing."""
    found = rows(conn, 'SELECT * FROM document_job WHERE id=? AND lease_owner=?', (operation, token))
    if not found:
        return False
    job = found[0]
    blocked = blocked or job['attempts'] >= MAX_ATTEMPTS or state == 'failed'
    next_check = later(min(60 * 2 ** min(job['attempts'] - 1, 6), 3600)) if state == 'unknown' and not blocked else None
    conn.execute('''UPDATE document_job SET state=?,lease_owner=NULL,lease_until=NULL,
        last_checked_at=?,updated_at=?,next_check_at=?,recovery_blocked=?,recovery_note=?,
        result_json='{"error":"The result needs review before retrying."}' WHERE id=? AND lease_owner=?''',
        (state, now(), now(), next_check, int(blocked), note or 'The service result is unconfirmed. Check before retrying.', operation, token))
    return True


def validation_failed(conn, operation, token, *, recovery=False):
    with transaction(conn):
        found = rows(conn, 'SELECT state FROM document_job WHERE id=? AND lease_owner=?', (operation, token))
        if found:
            state = found[0]['state']
            state = 'unknown' if state == 'running' else ('failed' if recovery and state == 'pending' else state)
            failed(conn, operation, token, state, blocked=True,
                   note='Current account, source or approval needs review before this operation can continue.')


def eligible(job):
    return (not job['recovery_blocked'] and not active(job)
            and (not job['next_check_at'] or job['next_check_at'] <= now())
            and (job['state'] != 'pending' or job['updated_at'] <= later(-PENDING_GRACE))
            and (job['state'] != 'running' or job['lease_until'] or job['updated_at'] <= later(-LEASE_SECONDS)))


def next_candidate(conn):
    stamp = now()
    pending_before = later(-PENDING_GRACE)
    legacy_before = later(-LEASE_SECONDS)
    found = rows(conn, '''SELECT * FROM document_job WHERE recovery_blocked=0
        AND state IN ('pending','running','unknown')
        AND kind IN ('extract','sign','dispatch')
        AND (lease_owner IS NULL OR lease_until<=?)
        AND (next_check_at IS NULL OR next_check_at<=?)
        AND (state<>'pending' OR updated_at<=?)
        AND (state<>'running' OR lease_until IS NOT NULL OR updated_at<=?)
        ORDER BY COALESCE(next_check_at,updated_at),id LIMIT 1''',
        (stamp, stamp, pending_before, legacy_before))
    return found[0] if found else None


def recover_one(get_conn, adapter=None):
    # At most one recovery service call per process, sharing the two-slot pool
    # with interactive requests. Database leases coordinate other processes.
    if not _RECOVERY_SLOT.acquire(blocking=False):
        return None
    try:
        conn = get_conn()
        try:
            if not d.enabled(conn):
                return None
            job = next_candidate(conn)
            if not job:
                return None
            import documents_operations as ops
            if job['kind'] == 'extract':
                # Extraction output is transient; no excerpts survive restart.
                try:
                    token = claim(conn,job['id'],reconcile=job['state'] != 'pending',recovery=True)
                    with transaction(conn):
                        failed(conn,job['id'],token,'failed',blocked=True,
                               note='Reading was interrupted. Extract again or enter the fields manually.')
                except d.Conflict:
                    return None
                return job['id']
            if job['kind'] not in ('sign', 'dispatch'):
                return None
            try:
                ops.execute(conn, job['id'], adapter, reconcile=job['state'] != 'pending', recovery=True)
            except Exception:
                # Lease/receipt state carries safe diagnostics; never log provider text.
                pass
            return job['id']
        finally:
            conn.close()
    finally:
        _RECOVERY_SLOT.release()


async def worker(get_conn):
    import documents_external as external
    while True:
        try:
            if not _RECOVERY_SLOT.locked():
                await external.run(recover_one, get_conn)
        except (external.Busy, external.Unconfirmed):
            pass
        except Exception:
            pass
        await asyncio.sleep(INTERVAL)


def describe(job):
    state = job['state']
    busy = active(job)
    if state == 'confirmed':
        status, label = 'completed', 'Completed'
        message = 'Service result recorded. Check the individual recipient outcomes for a dispatch.'
    elif state in ('cancelled', 'confirmed_no_effect'):
        status, label = 'completed', 'Cancelled' if state == 'cancelled' else 'No effect confirmed'
        message = 'No automatic retry will be made.'
    elif busy:
        status, label, message = 'running', 'Running', 'Wait for processing to finish before checking or changing its outcome.'
    elif state == 'pending' and not job.get('recovery_blocked'):
        status, label, message = 'pending', 'Pending', 'Queued for its first attempt, with current access checked again before it starts.'
    else:
        status, label = 'needs_review', 'Needs review'
        message = job.get('recovery_note') or 'The outcome is not confirmed. Check the service receipt before retrying.'
        if job.get('next_check_at') and not job.get('recovery_blocked'):
            message += ' Another receipt check is scheduled.'
    return {'status': status, 'label': label, 'message': message, 'busy': busy,
            'last_checked_at': job.get('last_checked_at'), 'next_check_at': job.get('next_check_at')}
