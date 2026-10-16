"""Independent contribution revisions; formal document decisions stay in Documents."""
from datetime import date

import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work

LABELS = {'proposed': 'Proposed', 'todo': 'To do', 'in_progress': 'In progress',
          'for_review': 'For review', 'done': 'Done', 'cancelled': 'Cancelled'}


def list_for_case(conn, user, case_id):
    work.get(conn, user, case_id)
    return rows(conn, 'SELECT * FROM work_task WHERE case_id=? ORDER BY id', (case_id,))


def _due(conn, case_id, value):
    due = date.fromisoformat(value).isoformat() if value else None
    if due:
        for (document_id,) in conn.execute('SELECT document_id FROM work_document WHERE case_id=?', (case_id,)):
            doc = work.resolved_document(conn, document_id)
            if doc and doc['due_date'] and due > doc['due_date']:
                raise ValueError('A contribution target cannot follow a linked official deadline.')
    return due


def _owner(conn, case_id, owner_id):
    owner = work._account(conn, owner_id)
    for (document_id,) in conn.execute('SELECT document_id FROM work_document WHERE case_id=?', (case_id,)):
        if not permissions.can_view(conn, owner, work.resolved_document(conn, document_id)):
            raise ValueError('Grant the owner access to every linked document before assigning them.')
    return owner['id']


def _event(conn, user, case_id, task, action, reason):
    # Snapshot preserves submissions and earlier ownership through returns/reassignment.
    work._event(conn, user, case_id, 'task_' + action, {'task_id': task['id'], 'title': task['title'],
                 'owner_id': task['owner_id'], 'status': task['status'], 'revision': task['revision'],
                 'submission': task['submission'], 'reason': reason, 'unit_id': task['unit_id'],
                 'due_date': task['due_date'], 'proposed_owner_id': task['proposed_owner_id'],
                 'expected_output': task['expected_output']})


def create(conn, user, case_id, fields):
    with transaction(conn):
        user = permissions.actor(conn, user)
        case = work.get(conn, user, case_id)
        work.writable(conn)
        title = work._text(fields.get('title'), 'Contribution title', 250)
        output = work._text(fields.get('expected_output'), 'Expected output', 4000)
        unit_id = int(fields.get('unit_id') or case['unit_id'])
        if not conn.execute('SELECT 1 FROM org_unit WHERE id=?', (unit_id,)).fetchone():
            raise ValueError('Choose the contributing unit.')
        proposed = work._account(conn, fields['proposed_owner_id'])['id'] if fields.get('proposed_owner_id') else None
        due = _due(conn, case_id, fields.get('due_date'))
        now = tz.now_iso()
        task_id = conn.execute('''INSERT INTO work_task(case_id,title,expected_output,unit_id,
            proposed_owner_id,creator_id,status,due_date,created_at,updated_at)
            VALUES (?,?,?,?,?,?,'proposed',?,?,?)''',
            (case_id, title, output, unit_id, proposed, user['id'], due, now, now)).lastrowid
        task = rows(conn, 'SELECT * FROM work_task WHERE id=?', (task_id,))[0]
        _event(conn, user, case_id, task, 'proposed', 'Contribution proposed for officer confirmation.')
        return task


def actions(conn, user, case, task):
    """The same authority/state predicate serves forms and mutations."""
    scoped = work.officer(conn, user, task)
    coordinator = work.officer(conn, user, case) or case['lead_id'] == user['id']
    own = task['owner_id'] == user['id']
    state = task['status']
    result = []
    if state == 'proposed' and scoped:
        result.append('confirm')
    if state in ('todo', 'in_progress', 'for_review') and scoped:
        result.append('reassign')
    if state == 'todo' and (own or scoped):
        result.append('acknowledge')
    if state == 'in_progress' and (own or scoped):
        result.append('submit')
    if state == 'for_review' and coordinator:
        result.extend(('return', 'accept'))
    if state == 'done' and coordinator:
        result.append('reopen')
    if state not in ('done', 'cancelled') and scoped:
        result.append('cancel')
    return result


def mutate(conn, user, case_id, task_id, revision, action, fields):
    with transaction(conn):
        user = permissions.actor(conn, user)
        case = work.get(conn, user, case_id)
        work.writable(conn)
        found = rows(conn, 'SELECT * FROM work_task WHERE id=? AND case_id=?', (task_id, case_id))
        if not found:
            raise permissions.Denied('Contribution not found or unavailable to you.')
        task = found[0]
        work._check_revision(task, revision)
        if action not in actions(conn, user, case, task):
            raise permissions.Denied('This contribution action is not available to you in its current state.')
        note = work._text(fields.get('reason'), 'Reason or progress note', 2000)
        owner, due, submission = task['owner_id'], task['due_date'], task['submission']
        if action in ('confirm', 'reassign'):
            owner = _owner(conn, case_id, fields.get('owner_id'))
            due = _due(conn, case_id, fields.get('due_date', due))
            if action == 'reassign' and owner == task['owner_id']:
                raise ValueError('Choose a different owner for reassignment.')
            state = 'todo'
        else:
            state = {'acknowledge': 'in_progress', 'submit': 'for_review', 'return': 'in_progress',
                     'accept': 'done', 'reopen': 'in_progress', 'cancel': 'cancelled'}[action]
            if action != 'cancel':
                _owner(conn, case_id, owner)
            if action == 'submit':
                submission = work._text(fields.get('submission'), 'Output or evidence', 8000)
        conn.execute('''UPDATE work_task SET owner_id=?,status=?,due_date=?,submission=?,
                        revision=revision+1,updated_at=? WHERE id=?''',
                     (owner, state, due, submission, tz.now_iso(), task_id))
        updated = rows(conn, 'SELECT * FROM work_task WHERE id=?', (task_id,))[0]
        _event(conn, user, case_id, updated, action, note)
        return updated
