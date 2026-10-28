"""Supplies email: a durable outbox with at-most-once delivery.

Business operations queue rows from supplies_storage.record() inside their own write transaction, so a
message is owed if and only if the operation committed. Rows hold no message text: the worker composes from
current data at send time and re-checks that the message is still relevant and the recipient still entitled.
A queued row is committed as 'attempting' before any network I/O, so a crash or an ambiguous send is never
retried blindly ('uncertain'); only a definite failure is requeued, up to the admin's retry setting.
Stock-warning notices stay in-app; custodians get the weekly digest instead (see digest_for).
"""
import logging
import time
from uuid import uuid4

import mailer
import storage as st
import supplies as s
import supplies_permissions as permissions
from supplies_storage import rows, transaction
import tzutil as tz

log = logging.getLogger(__name__)

STALE_SECONDS = 3 * 86400       # a message no longer sent after this is cancelled, not delivered late
ATTEMPT_TIMEOUT = 600           # an 'attempting' row older than this is marked uncertain


# ---- queueing (called inside the business transaction) ------------------------------------------------

def _enqueue(conn, kind, recipient_ids, ref_key, operation_key):
    if not conn.in_transaction:
        raise RuntimeError('Supplies email must be queued in the caller write transaction.')
    for recipient_id in sorted(set(recipient_ids)):
        conn.execute('''INSERT INTO supply_mail(kind,recipient_id,ref_key,operation_key,created_at)
          VALUES (?,?,?,?,?) ON CONFLICT(kind,ref_key,recipient_id) DO NOTHING''',
          (kind, recipient_id, ref_key, operation_key, int(time.time())))


def on_record(conn, user, key, action, result, detail):
    """Map a recorded business operation to the messages it owes."""
    if action == 'request_submit':
        import supplies_requests as requests
        approvers = requests.eligible_approvers(conn, user['id'], detail['unit_id'])
        _enqueue(conn, 'supplies_request_pending', [a['id'] for a in approvers],
                 f"request:{result['id']}:{result['current_revision']}", key)
    elif action == 'request_decide':
        request = rows(conn, 'SELECT requester_id FROM supply_request WHERE id=?', (result['id'],))[0]
        _enqueue(conn, 'supplies_request_decided', [request['requester_id']],
                 f"request:{result['id']}:{result['current_revision']}", key)


# ---- composing (at send time, from current data) ------------------------------------------------------

def _name(conn, user):
    rp = st.get_rp(conn, user['rp_id']) if user.get('rp_id') else None
    return (rp['name'] if rp else None) or user['username']


def _request(conn, ref_key):
    _, request_id, revision = ref_key.split(':')
    found = rows(conn, 'SELECT * FROM supply_request WHERE id=?', (int(request_id),))
    return (found[0] if found else None), int(revision)


def _compose_request_pending(conn, row, user, base):
    import supplies_requests as requests
    request, revision = _request(conn, row['ref_key'])
    if not request or request['approval_status'] != 'submitted' or request['current_revision'] != revision:
        return None
    unit_id = requests.submitted_unit(conn, request)
    if request['requester_id'] == user['id'] or not permissions.has_role(conn, user, 'request_approver', unit_id):
        return None
    header = rows(conn, 'SELECT * FROM supply_request_revision WHERE request_id=? AND revision=?', (request['id'], revision))[0]
    return mailer.supply_request_pending_message(
        _name(conn, user), header['requester_snapshot'], request['control_number'], header['unit_snapshot'],
        header['purpose'], f"{base}/supplies/requests/{request['id']}")


def _compose_request_decided(conn, row, user, base):
    request, revision = _request(conn, row['ref_key'])
    if not request or request['requester_id'] != user['id']:
        return None
    found = rows(conn, 'SELECT * FROM supply_request_decision WHERE request_id=? AND submitted_revision=? ORDER BY id DESC LIMIT 1',
                 (request['id'], revision))
    if not found:
        return None
    return mailer.supply_request_decided_message(
        _name(conn, user), request['control_number'], found[0]['decision'], found[0]['reason'],
        f"{base}/supplies/requests/{request['id']}")


KINDS = {
    'supplies_request_pending': _compose_request_pending,
    'supplies_request_decided': _compose_request_decided,
}


# ---- delivery -----------------------------------------------------------------------------------------

def _finish(conn, row, state, user, subject, detail):
    conn.execute('UPDATE supply_mail SET state=?,finished_at=?,attempt_id=NULL WHERE id=?', (state, int(time.time()), row['id']))
    if subject and user:
        status = {'sent': 'sent', 'skipped_off': 'skipped_off', 'not_configured': 'not_configured'}.get(state, 'failed')
        conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
                     (tz.now_iso(), row['kind'], user['username'], subject, status, detail))


def _retry_limit(conn):
    import email_params
    return email_params.param(conn, 'send_retry_attempts')


def run(conn, base=None, *, limit=20, send=None):
    """Send what is owed. Returns the number of send attempts made."""
    now = int(time.time())
    with transaction(conn):
        conn.execute("UPDATE supply_mail SET state='uncertain',finished_at=?,attempt_id=NULL WHERE state='attempting' AND attempted_at<=?",
                     (now, now - ATTEMPT_TIMEOUT))
        conn.execute("UPDATE supply_mail SET state='cancelled',finished_at=? WHERE state='queued' AND created_at<=?",
                     (now, now - STALE_SECONDS))
    if base is None:
        import send_reminders
        base = send_reminders._base_url()
    # Without a public link or with Supplies off, messages wait (and expire) rather than go out unusable.
    if not base or not s.enabled(conn):
        return 0
    send = send or mailer.send
    ids = [r[0] for r in conn.execute("SELECT id FROM supply_mail WHERE state='queued' ORDER BY id LIMIT ?", (limit,))]
    attempted = 0
    for mail_id in ids:
        with transaction(conn):
            found = rows(conn, "SELECT * FROM supply_mail WHERE id=? AND state='queued'", (mail_id,))
            if not found:
                continue
            row = found[0]
            user = st.get_admin_user_by_id(conn, row['recipient_id'])
            content = None
            if user and user['active'] and '@' in (user.get('username') or ''):
                try:
                    content = KINDS[row['kind']](conn, row, user, base)
                except Exception:       # noqa: BLE001 - a bad row must not block the queue
                    log.exception('Supplies email %s could not be composed.', mail_id)
            if content is None:
                _finish(conn, row, 'cancelled', None, None, None)
                continue
            subject, body, html = content
            if not st.email_feature_enabled(conn, row['kind']):
                _finish(conn, row, 'skipped_off', user, subject, 'Turned off in /admin/email.')
                continue
            if not mailer.email_configured():
                _finish(conn, row, 'not_configured', user, subject, 'Email is not configured on this server.')
                continue
            conn.execute("UPDATE supply_mail SET state='attempting',attempt_id=?,attempted_at=?,attempts=attempts+1 WHERE id=?",
                         (str(uuid4()), int(time.time()), mail_id))
        # No transaction is open during the network call; a concurrent worker sees 'attempting' only.
        attempted += 1
        outcome, detail = 'uncertain', 'Delivery could not be confirmed; not resent.'
        try:
            response = send(user['username'], subject, body, html=html)
            if isinstance(response, dict) and response.get('sent') is True:
                outcome, detail = 'sent', None
            elif isinstance(response, dict):
                outcome, detail = 'retry', response.get('detail')
        except Exception:               # noqa: BLE001 - ambiguous: the message may have gone out
            pass
        with transaction(conn):
            attempts = conn.execute('SELECT attempts FROM supply_mail WHERE id=?', (mail_id,)).fetchone()[0]
            if outcome == 'retry' and attempts < _retry_limit(conn):
                conn.execute("UPDATE supply_mail SET state='queued',attempt_id=NULL,attempted_at=NULL WHERE id=?", (mail_id,))
            else:
                _finish(conn, row, 'failed' if outcome == 'retry' else outcome, user, subject, detail)
    return attempted
