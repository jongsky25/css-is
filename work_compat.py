"""Explicit legacy mapping and one authoritative task store after cutover."""
import json

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work

STATES = {'proposed': 'proposed', 'assigned': 'todo', 'acknowledged': 'in_progress',
          'in_progress': 'in_progress', 'submitted': 'for_review', 'completed': 'done', 'superseded': 'cancelled'}


def mapping(conn, document_id):
    found = rows(conn, 'SELECT * FROM work_legacy_document WHERE document_id=?', (document_id,))
    return found[0] if found else None


def require_open(conn, case_id):
    if work.raw(conn,case_id)['status']=='completed':
        raise ValueError('Reopen the completed work item before changing contributions or shared context.')
    for (did,) in conn.execute('SELECT document_id FROM work_legacy_document WHERE case_id=?', (case_id,)):
        doc = docs.raw(conn, did)
        if doc['status'] in ('closed', 'cancelled') or doc['canonical_id']:
            raise ValueError('Reopen the official document before changing its migrated contributions.')
        if conn.execute("SELECT 1 FROM document_job WHERE document_id=? AND kind IN ('sign','dispatch') AND state IN ('running','unknown')", (did,)).fetchone():
            raise docs.Conflict('Reconcile the running or uncertain document operation first.')


def migrate(conn, user, document_id, revision, outcome, reason):
    """Explicitly map one record to a new case. Caller chooses records, never subject matching."""
    with transaction(conn):
        user = permissions.actor(conn, user)
        doc = docs.get(conn, user, document_id)
        if not permissions.officer(conn, user, doc):
            raise permissions.Denied('The concerned officer must confirm the migration.')
        existing = mapping(conn, document_id)
        if existing:
            work.get(conn, user, existing['case_id'])
            return reconcile(conn, document_id)
        user, doc = docs.check(conn, user, document_id, revision)
        work.writable(conn)
        if doc.get('instruction_state')=='pending':
            raise ValueError('Wait for the Director’s routing instruction before migrating assignments.')
        if conn.execute('SELECT 1 FROM document WHERE canonical_id=?', (document_id,)).fetchone():
            raise ValueError('Reconcile merged source assignments before migration.')
        if doc['status'] in ('closed', 'cancelled'):
            raise ValueError('Only agreed active records can enter this rehearsal.')
        outcome = work._text(outcome, 'Expected outcome', 4000)
        reason = work._text(reason, 'Migration reason', 2000)
        if not doc['unit_id']:
            raise ValueError('Confirm the concerned unit before migration.')
        original = rows(conn, 'SELECT * FROM document_assignment WHERE document_id=? ORDER BY id', (document_id,))
        for a in original:
            if a['status'] not in STATES or a['role'] not in ('lead', 'contributor') or a['mandatory'] not in (0, 1):
                raise ValueError('Resolve unsupported assignment states, roles, or mandatory values first.')
            if a['due_date']:
                from datetime import date
                date.fromisoformat(a['due_date'])
            if a['status'] not in ('completed', 'superseded', 'proposed'):
                owner = work._account(conn, a['user_id'])
                if not permissions.can_view(conn, owner, doc):
                    raise ValueError('Resolve active contributor access before migration.')
        if doc['lead_id']:
            owner = work._account(conn, doc['lead_id'])
            if not permissions.can_view(conn, owner, doc):
                raise ValueError('Resolve confirmed lead access before migration.')
        proposed_leads = {a['user_id'] for a in original if a['role']=='lead' and a['status']=='proposed'}
        now = tz.now_iso()
        cid = conn.execute('''INSERT INTO work_case(title,outcome,unit_id,creator_id,lead_id,created_at,updated_at)
                              VALUES (?,?,?,?,?,?,?)''',
                           (doc['subject'], outcome, doc['unit_id'], user['id'], doc['lead_id'], now, now)).lastrowid
        if not doc['lead_id'] and len(proposed_leads)==1:
            conn.execute('UPDATE work_case SET proposed_lead_id=? WHERE id=?', (next(iter(proposed_leads)),cid))
        conn.execute('INSERT INTO work_document VALUES (?,?,?,?,?)', (cid, document_id, 'reference', user['id'], now))
        for a in original:
            tid = None
            if a['role'] == 'contributor':
                tid = conn.execute('''INSERT INTO work_task(case_id,title,expected_output,unit_id,proposed_owner_id,
                         owner_id,creator_id,status,due_date,submission,created_at,updated_at,mandatory)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (cid, a['action'][:250] or 'Imported contribution', a['action'], doc['unit_id'], a['user_id'],
                          None if a['status']=='proposed' else a['user_id'], user['id'], STATES[a['status']],
                          a['due_date'], a['outcome'], a['created_at'], now, a['mandatory'])).lastrowid
            conn.execute('INSERT INTO work_legacy_assignment VALUES (?,?,?,?)',
                         (a['id'], cid, tid, json.dumps(a, sort_keys=True)))
        conn.execute('INSERT INTO work_legacy_document VALUES (?,?,?,?,?,?)', (document_id, cid, user['id'], reason, revision, now))
        work._event(conn, user, cid, 'assignments_migrated', {'document_id': document_id, 'reason': reason,
                    'source_revision': revision, 'assignment_ids': [a['id'] for a in original]})
        docs.finish(conn, user, doc, 'assignments_migrated', {'case_id': cid, 'reason': reason}, {})
        conn.execute("UPDATE document_notice SET state='cancelled' WHERE document_id=? AND state='pending' AND (kind LIKE 'deadline:%' OR kind LIKE 'milestone:%')", (document_id,))
        return reconcile(conn, document_id)


def reconcile(conn, document_id):
    migration = mapping(conn, document_id)
    if not migration:
        raise ValueError('This document has no shared-work mapping.')
    result = {'document_id': document_id, 'case_id': migration['case_id'], 'source_rows_preserved': True,
              'warnings': [], 'contributors': [], 'lead_assignment_ids': [], 'confirmed_lead_id': work.raw(conn, migration['case_id'])['lead_id']}
    if not result['confirmed_lead_id']:
        result['warnings'].append('Ownership remains unresolved; an officer must confirm the lead.')
    for m in rows(conn, 'SELECT * FROM work_legacy_assignment WHERE case_id=? ORDER BY assignment_id', (migration['case_id'],)):
        source = json.loads(m['source_json'])
        current = rows(conn, 'SELECT * FROM document_assignment WHERE id=?', (m['assignment_id'],))
        result['source_rows_preserved'] &= bool(current and current[0] == source)
        if m['task_id'] is None:
            result['lead_assignment_ids'].append(m['assignment_id'])
            continue
        task = rows(conn, 'SELECT * FROM work_task WHERE id=?', (m['task_id'],))[0]
        doc = docs.raw(conn, document_id)
        if task['due_date'] and doc['due_date'] and task['due_date'] > doc['due_date']:
            result['warnings'].append('Task %s retains an internal target after the official deadline; adjust it explicitly.' % task['id'])
        result['contributors'].append({'assignment_id': m['assignment_id'], 'task_id': task['id'],
            'source_status': source['status'], 'initial_task_status': STATES[source['status']], 'current_status': task['status'],
            'source_owner_id': source['user_id'], 'owner_id': task['owner_id'], 'proposed_owner_id': task['proposed_owner_id'],
            'source_due_date': source['due_date'], 'due_date': task['due_date'], 'mandatory': task['mandatory'],
            'source_mandatory': source['mandatory'], 'initial_evidence_preserved': task['submission']==source['outcome']})
    return result


def change(conn, user, doc, action, fields):
    """Called inside the document transaction, with document + task revision protection."""
    import work_tasks
    migration = mapping(conn, doc['id'])
    if action not in ('contribution', 'milestone'):
        raise ValueError('Manage assignments and ownership in Shared work after migration. Routing and merges require separate reconciliation.')
    aid = int(fields['assignment_id'])
    if aid < 0:
        tid = -aid
    else:
        match = conn.execute('SELECT task_id FROM work_legacy_assignment WHERE assignment_id=? AND case_id=?',
                             (aid, migration['case_id'])).fetchone()
        tid = match[0] if match else None
    if tid is None:
        raise ValueError('This assignment represents ownership, not a contribution task.')
    if not fields.get('task_revision'):
        raise docs.Conflict('Reload the contribution in Shared work to supply its current task revision.')
    target = 'milestone' if action=='milestone' else {'acknowledged':'acknowledge', 'in_progress':'acknowledge',
                                                    'submitted':'submit', 'completed':'accept'}.get(fields.get('status'))
    if not target:
        raise ValueError('Unknown contribution action.')
    task = work_tasks.mutate_in_transaction(conn, user, migration['case_id'], tid, int(fields['task_revision']), target,
                    {**fields, 'reason': fields.get('reason') or fields.get('outcome'), 'submission': fields.get('outcome')})
    return {'task_id': task['id'], 'task_revision': task['revision'], 'task_action': target}


def can_view_assignments(conn, user, document_id):
    migrated = mapping(conn, document_id)
    if not migrated:
        return True
    try:
        work.get(conn, user, migrated['case_id'])
        return True
    except permissions.Denied:
        return False
