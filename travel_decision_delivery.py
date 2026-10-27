"""One committed transport claim for each browser-confirmed travel papers decision."""
import json
import os
import time
from uuid import uuid4

from documents_storage import rows, transaction
import mcp_actions as actions
import mcp_travel_decisions as pilot
import mailer
import storage as st
import travel
import tzutil as tz


def _finish(conn, key, state, *, attempt_id=None, recipient=None, subject=None):
    clause = "operation_key=? AND state='queued'" if attempt_id is None else "operation_key=? AND state='attempting' AND attempt_id=?"
    args = (state, tz.now_iso(), key) if attempt_id is None else (state, tz.now_iso(), key, attempt_id)
    changed = conn.execute('UPDATE mcp_travel_decision_mail SET state=?,finished_at=?,payload_json=NULL WHERE '+clause, args).rowcount
    if changed and recipient:
        status = state if state in ('sent', 'skipped_off', 'not_configured') else 'failed'
        conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
                     (tz.now_iso(), 'travel_review_result', recipient, subject, status,
                      'MCP durable reviewer decision notice: '+state+'; no automatic retry'))
    return changed


def _transport(to, subject, body, html=None):
    # The current-policy checks, committed attempt and email log are owned here.
    return mailer.send(to, subject, body, html=html)


def run(conn, *, send=None, limit=5):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('Use a delivery batch of 1–20.')
    with transaction(conn):
        pilot.prune(conn)
        conn.execute("UPDATE mcp_travel_decision_mail SET state='uncertain',payload_json=NULL,finished_at=? WHERE operation_key IN "
            "(SELECT operation_key FROM mcp_travel_decision_mail WHERE state='attempting' AND attempted_at<=? LIMIT 20)",
            (tz.now_iso(), int(time.time())-600))
        conn.execute("UPDATE mcp_travel_decision_mail SET state='cancelled',payload_json=NULL,finished_at=? WHERE operation_key IN "
            "(SELECT operation_key FROM mcp_travel_decision_mail WHERE state='queued' AND created_at<=? LIMIT 20)",
            (tz.now_iso(), int(time.time())-86400))
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(pilot.FLAG) != '1' or not travel.enabled(conn):
        return 0
    send = send or _transport
    keys = [r[0] for r in conn.execute("SELECT operation_key FROM mcp_travel_decision_mail WHERE state='queued' ORDER BY rowid LIMIT ?", (limit,))]
    attempted = 0
    for key in keys:
        with transaction(conn):
            found = rows(conn, "SELECT * FROM mcp_travel_decision_mail WHERE operation_key=? AND state='queued'", (key,))
            if not found:
                continue
            out = found[0]
            op = rows(conn, 'SELECT * FROM mcp_travel_decision WHERE domain_key=?', (key,))
            owner = st.get_admin_user_by_id(conn, out['owner_id'])
            try:
                if not op or not owner or not op[0]['completed_at']:
                    raise ValueError
                pilot._check(conn, owner, op[0], op[0]['resource'])
                result = json.loads(op[0]['result_json'])
                payload = json.loads(out['payload_json'])
                saved = pilot.live(conn, owner, out['filing_id'])
                if (pilot._digest(payload) != result['mail_digest'] or saved['traveller']['email'] != payload['to']
                        or pilot._source_key(saved['filing']) != out['source_key']):
                    raise ValueError
            except (ValueError, TypeError, KeyError, actions.ActionError):
                _finish(conn, key, 'cancelled')
                continue
            subject, body, html = mailer.travel_review_result_message(payload['traveller_name'], payload['ref'],
                payload['title'], payload['approved'], payload['notes'], payload['link'])
            if not saved['email_enabled']:
                _finish(conn, key, 'skipped_off', recipient=payload['to'], subject=subject)
                continue
            if pilot._digest(saved) != result['live_digest']:
                _finish(conn, key, 'cancelled')
                continue
            if not mailer.email_configured():
                _finish(conn, key, 'not_configured', recipient=payload['to'], subject=subject)
                continue
            attempt = str(uuid4())
            conn.execute("UPDATE mcp_travel_decision_mail SET state='attempting',attempt_id=?,attempted_at=? WHERE operation_key=? AND state='queued'",
                         (attempt, int(time.time()), key))
        attempted += 1
        state = 'uncertain'
        try:
            response = send(payload['to'], subject, body, html=html)
            if isinstance(response, dict) and response.get('sent') is True:
                state = 'sent'
        except Exception:
            pass
        with transaction(conn):
            _finish(conn, key, state, attempt_id=attempt, recipient=payload['to'], subject=subject)
    return attempted
