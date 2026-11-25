"""Remove the trial advisories made with the old poster editor (owner decision, November 25, 2026).

Everything issued before the Google Slides advisories was a trial. This removes, in ONE transaction:
  * every advisory record made with the old editor (advisory_record.kind IS NULL) and all of its
    advisory rows: revisions and their PDF/PNG bytes, review packets and decisions, comments links,
    concern events, issues, delivery links, publication, saved public copies and request receipts;
  * every old poster row (event_advisory), so link-tree pages stop showing old trial posters.

Kept on purpose (append-only audit history, which the app never deletes): the linked Documents
record (archived, with an event saying why), its document_event history and file-version rows, the
Work case and its comments. Unsent email jobs are cancelled. Google Slides advisories are untouched.

Callers take a database backup first (see the admin route). Advisory history tables are append-only
by trigger; the triggers are lifted and restored inside the same transaction, so a failure leaves
the database exactly as it was."""
from documents_storage import rows, transaction, event
import tzutil as tz

# Order matters: children before parents (foreign keys are on).
_LOCKED = ('advisory_concern_event', 'advisory_comment', 'advisory_decision', 'advisory_action_request',
           'advisory_delivery', 'advisory_issue_action', 'advisory_issue', 'advisory_review_packet',
           'advisory_artifact', 'advisory_existing_public', 'advisory_save_request', 'advisory_revision')


def _ids(conn, sql, params=()):
    return [r[0] for r in conn.execute(sql, params)]


def _marks(values):
    return ','.join('?' * len(values)) or 'NULL'


def preview(conn):
    """What a purge would remove, for the confirmation page."""
    records = rows(conn, '''SELECT a.id,a.number,d.subject AS title,d.status,u.username AS started_by,e.title AS activity
        FROM advisory_record a JOIN document d ON d.id=a.document_id LEFT JOIN admin_user u ON u.id=a.initiator_id
        LEFT JOIN event e ON e.id=a.event_id WHERE a.kind IS NULL ORDER BY a.id''')
    posters = rows(conn, '''SELECT p.number,p.headline AS title,e.title AS activity FROM event_advisory p
        LEFT JOIN event e ON e.id=p.event_id
        WHERE NOT EXISTS (SELECT 1 FROM advisory_record a WHERE a.event_id=p.event_id AND a.kind IS NULL)
        ORDER BY p.seq_date,p.seq''')
    issued = conn.execute('''SELECT COUNT(*) FROM advisory_issue i JOIN advisory_record a ON a.id=i.advisory_id
        WHERE a.kind IS NULL''').fetchone()[0]
    return {'records': records, 'posters': posters, 'issued': issued,
            'total': len(records) + len(posters)}


def purge(conn, user, *, reason):
    """Delete the old trial advisories. Returns counts. All or nothing."""
    with transaction(conn):
        aids = _ids(conn, 'SELECT id FROM advisory_record WHERE kind IS NULL')
        docs = _ids(conn, f'SELECT document_id FROM advisory_record WHERE id IN ({_marks(aids)})', aids)
        packets = _ids(conn, f'SELECT id FROM advisory_review_packet WHERE advisory_id IN ({_marks(aids)})', aids)
        issues = _ids(conn, f'SELECT id FROM advisory_issue WHERE advisory_id IN ({_marks(aids)})', aids)
        revisions = _ids(conn, f'SELECT id FROM advisory_revision WHERE advisory_id IN ({_marks(aids)})', aids)
        comments = _ids(conn, f'SELECT comment_id FROM advisory_comment WHERE advisory_id IN ({_marks(aids)})', aids)
        jobs = _ids(conn, f'SELECT job_id FROM advisory_delivery WHERE issue_id IN ({_marks(issues)})', issues)
        posters = conn.execute('SELECT COUNT(*) FROM event_advisory').fetchone()[0]

        # Lift the append-only triggers on the advisory tables for this transaction only.
        saved = rows(conn, f"""SELECT name,sql FROM sqlite_master WHERE type='trigger'
            AND tbl_name IN ({_marks(_LOCKED)}) AND name LIKE '%_no_%'""", _LOCKED)
        for trig in saved:
            conn.execute(f'DROP TRIGGER "{trig["name"]}"')

        conn.execute(f"""UPDATE document_job SET state='cancelled',recovery_blocked=1,updated_at=?
            WHERE id IN ({_marks(jobs)}) AND state='pending'""", [tz.now_iso(), *jobs])
        conn.execute(f'DELETE FROM advisory_concern_event WHERE comment_id IN ({_marks(comments)})', comments)
        conn.execute(f'DELETE FROM advisory_comment WHERE advisory_id IN ({_marks(aids)})', aids)
        conn.execute(f'DELETE FROM advisory_decision WHERE packet_id IN ({_marks(packets)})', packets)
        conn.execute(f'DELETE FROM advisory_action_request WHERE advisory_id IN ({_marks(aids)})', aids)
        conn.execute(f'DELETE FROM advisory_delivery WHERE issue_id IN ({_marks(issues)})', issues)
        conn.execute(f'DELETE FROM advisory_issue_action WHERE issue_id IN ({_marks(issues)})', issues)
        conn.execute(f'DELETE FROM advisory_publication WHERE advisory_id IN ({_marks(aids)})', aids)
        conn.execute(f'UPDATE advisory_issue SET supersedes_id=NULL WHERE id IN ({_marks(issues)})', issues)
        conn.execute(f'DELETE FROM advisory_issue WHERE id IN ({_marks(issues)})', issues)
        conn.execute(f'UPDATE advisory_record SET active_packet=NULL,current_revision=NULL WHERE id IN ({_marks(aids)})', aids)
        conn.execute(f'DELETE FROM advisory_review_packet WHERE id IN ({_marks(packets)})', packets)
        conn.execute(f'DELETE FROM advisory_artifact WHERE revision_id IN ({_marks(revisions)})', revisions)
        conn.execute(f'DELETE FROM advisory_existing_public WHERE advisory_id IN ({_marks(aids)})', aids)
        conn.execute(f'DELETE FROM advisory_save_request WHERE advisory_id IN ({_marks(aids)})', aids)
        conn.execute(f'DELETE FROM advisory_revision WHERE id IN ({_marks(revisions)})', revisions)
        conn.execute(f'DELETE FROM advisory_record WHERE id IN ({_marks(aids)})', aids)
        conn.execute('DELETE FROM event_advisory')

        for trig in saved:
            conn.execute(trig['sql'])

        now = tz.now_iso()
        for doc_id in docs:
            conn.execute('UPDATE document SET archived_at=COALESCE(archived_at,?),archived_by=COALESCE(archived_by,?) WHERE id=?',
                         (now, user['id'], doc_id))
            event(conn, doc_id, user, 'advisory_trial_removed', {'reason': reason})
        return {'records': len(aids), 'issues': len(issues), 'posters': posters, 'documents': len(docs),
                'cancelled_jobs': len(jobs)}
