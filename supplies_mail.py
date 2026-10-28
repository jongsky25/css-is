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
    elif action == 'replenishment_submit':
        approvers = rows(conn, '''SELECT DISTINCT u.id FROM admin_user u JOIN supply_role_grant g ON g.user_id=u.id
          WHERE u.active=1 AND u.id<>? AND g.role='replenishment_approver' AND g.revoked_at IS NULL''', (user['id'],))
        _enqueue(conn, 'supplies_replenishment_pending', [a['id'] for a in approvers],
                 f"replenishment:{result['id']}:{result['current_revision']}", key)
    elif action == 'replenishment_decide':
        found = rows(conn, 'SELECT prepared_by,current_revision FROM supply_replenishment WHERE id=?', (result['id'],))[0]
        _enqueue(conn, 'supplies_replenishment_decided', [found['prepared_by']],
                 f"replenishment:{result['id']}:{found['current_revision']}", key)
    elif action == 'issue_post':
        recipient = rows(conn, 'SELECT recipient_id FROM supply_issue WHERE id=?', (result['id'],))[0]['recipient_id']
        if recipient != user['id']:
            _enqueue(conn, 'supplies_issue_recorded', [recipient], f"issue:{result['id']}", key)


def on_reservation_increase(conn, request_ids, key):
    """Supplies became reserved for these approved requests. The approval email already says so, so a request
    decided in this same operation gets no second message."""
    for request_id in sorted(set(request_ids)):
        requester = rows(conn, 'SELECT requester_id FROM supply_request WHERE id=?', (request_id,))[0]['requester_id']
        if conn.execute("SELECT 1 FROM supply_mail WHERE kind='supplies_request_decided' AND operation_key=? AND ref_key LIKE ?",
                        (key, f'request:{request_id}:%')).fetchone():
            continue
        _enqueue(conn, 'supplies_stock_ready', [requester], f'request:{request_id}:{key}', key)


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


def _replenishment(conn, ref_key):
    _, replenishment_id, revision = ref_key.split(':')
    found = rows(conn, 'SELECT * FROM supply_replenishment WHERE id=?', (int(replenishment_id),))
    return (found[0] if found else None), int(revision)


def _compose_replenishment_pending(conn, row, user, base):
    request, revision = _replenishment(conn, row['ref_key'])
    if (not request or request['status'] != 'submitted' or request['current_revision'] != revision
            or request['prepared_by'] == user['id'] or not permissions.has_role(conn, user, 'replenishment_approver')):
        return None
    preparer = st.get_admin_user_by_id(conn, request['prepared_by'])
    header = rows(conn, 'SELECT purpose FROM supply_replenishment_revision WHERE replenishment_id=? AND revision=?',
                  (request['id'], revision))[0]
    return mailer.supply_replenishment_pending_message(
        _name(conn, user), _name(conn, preparer) if preparer else None, request['control_number'], header['purpose'],
        f"{base}/supplies/replenishments/{request['id']}")


def _compose_replenishment_decided(conn, row, user, base):
    request, revision = _replenishment(conn, row['ref_key'])
    if not request or request['prepared_by'] != user['id']:
        return None
    found = rows(conn, '''SELECT d.decision,d.reason FROM supply_replenishment_decision d
      JOIN supply_replenishment_revision v ON v.id=d.revision_id WHERE d.replenishment_id=? AND v.revision=?''',
      (request['id'], revision))
    if not found:
        return None
    return mailer.supply_replenishment_decided_message(
        _name(conn, user), request['control_number'], found[0]['decision'], found[0]['reason'],
        f"{base}/supplies/replenishments/{request['id']}")


def _compose_issue_recorded(conn, row, user, base):
    issue_id = int(row['ref_key'].split(':')[1])
    found = rows(conn, '''SELECT i.*,q.control_number FROM supply_issue i JOIN supply_request q ON q.id=i.request_id
      WHERE i.id=?''', (issue_id,))
    if not found or found[0]['recipient_id'] != user['id']:
        return None
    issue = found[0]
    if conn.execute('SELECT 1 FROM supply_issue_acknowledgment WHERE issue_id=? LIMIT 1', (issue_id,)).fetchone():
        return None             # already acknowledged or disputed (for example on paper): nothing left to ask
    lines = [f"{l['issued_quantity']} {l['unit_snapshot']} {l['description_snapshot']}" for l in
             rows(conn, 'SELECT * FROM supply_issue_line WHERE issue_id=? ORDER BY id', (issue_id,))]
    return mailer.supply_issue_recorded_message(
        _name(conn, user), issue['release_number'], issue['control_number'], lines, f"{base}/supplies/issues/{issue_id}")


def _compose_stock_ready(conn, row, user, base):
    request_id = int(row['ref_key'].split(':')[1])
    request = rows(conn, 'SELECT * FROM supply_request WHERE id=?', (request_id,))
    if not request or request[0]['requester_id'] != user['id'] or request[0]['approval_status'] != 'approved':
        return None
    lines = rows(conn, '''SELECT l.description_snapshot,l.unit_snapshot,r.reserved_quantity,
        d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity AS outstanding
      FROM supply_reservation r JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
      JOIN supply_request_revision_line l ON l.id=r.revision_line_id WHERE r.request_id=? ORDER BY r.id''', (request_id,))
    ready = [f"{l['reserved_quantity']} of {l['outstanding']} {l['unit_snapshot']} {l['description_snapshot']}"
             for l in lines if l['reserved_quantity'] > 0 and l['outstanding'] > 0]
    if not ready:
        return None
    return mailer.supply_stock_ready_message(_name(conn, user), request[0]['control_number'], ready,
                                             f"{base}/supplies/requests/{request_id}")


KINDS = {
    'supplies_request_pending': _compose_request_pending,
    'supplies_request_decided': _compose_request_decided,
    'supplies_replenishment_pending': _compose_replenishment_pending,
    'supplies_replenishment_decided': _compose_replenishment_decided,
    'supplies_issue_recorded': _compose_issue_recorded,
    'supplies_stock_ready': _compose_stock_ready,
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


# ---- weekly custodian digest --------------------------------------------------------------------------

DIGEST_WARNING_CAP = 15


def digest_for(conn):
    """What the Monday digest says, or None when there is nothing to chase. The same for every custodian."""
    import json
    warnings = []
    for row in rows(conn, '''SELECT a.snapshot_json FROM supply_alert_episode e
      JOIN supply_item_alert a ON a.item_id=e.item_id WHERE e.resolved_at IS NULL'''):
        snap = json.loads(row['snapshot_json'])
        if snap.get('severity'):
            warnings.append(snap)
    warnings.sort(key=lambda w: (-w['severity'], w['code']))
    lines = [f"{w['code']} {w['description']}: {w['availability_label'].lower()}"
             f" ({w['available']} {w['unit']} available, {w['on_hand']} on hand)" for w in warnings[:DIGEST_WARNING_CAP]]
    if len(warnings) > DIGEST_WARNING_CAP:
        lines.append(f"…and {len(warnings) - DIGEST_WARNING_CAP} more item(s)")
    queue = rows(conn, '''SELECT SUM(d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity) AS outstanding,
        SUM(r.reserved_quantity) AS reserved
      FROM supply_request q JOIN supply_reservation r ON r.request_id=q.id
      JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
      WHERE q.approval_status='approved' GROUP BY q.id HAVING outstanding>0''')
    to_issue = sum(1 for q in queue if q['reserved'] > 0)
    waiting = len(queue) - to_issue
    if not (lines or queue):
        return None
    return {'warnings': lines, 'warning_count': len(warnings), 'to_issue': to_issue, 'awaiting_stock': waiting}


def custodians(conn):
    return rows(conn, '''SELECT DISTINCT u.* FROM admin_user u JOIN supply_role_grant g ON g.user_id=u.id
      WHERE u.active=1 AND g.role='custodian' AND g.revoked_at IS NULL ORDER BY u.id''')
