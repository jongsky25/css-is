"""Explicit blockers and acyclic, same-work-item dependencies; no deadline propagation."""
from datetime import date
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work

ACTIONS = {'block', 'unblock', 'dependency_add', 'dependency_remove'}


def dependencies(conn, task_id):
    return rows(conn, '''SELECT t.id,t.title,t.status,t.due_date FROM work_dependency d
        JOIN work_task t ON t.id=d.prerequisite_id WHERE d.task_id=? ORDER BY t.id''', (task_id,))


def waiting(conn, task):
    import work_decisions
    return bool(work_decisions.pending(conn,task['id'])) or bool(task.get('blocker_reason')) or any(t['status'] != 'done' for t in dependencies(conn, task['id']))


def authority(conn, user, case, task):
    coordinator = case['lead_id'] == user['id'] or work.officer(conn, user, case) or work.officer(conn, user, task)
    active = task['status'] not in ('done','cancelled')
    participant = user['id'] in (task['owner_id'], task.get('blocker_owner_id'))
    return active and (coordinator or participant), active and coordinator


def mutate(conn, user, case_id, task_id, revision, action, fields):
    import work_tasks
    import work_compat
    with transaction(conn):
        user = permissions.actor(conn, user)
        case = work.get(conn, user, case_id)
        work.writable(conn)
        work_compat.require_open(conn, case_id)
        found = rows(conn, 'SELECT * FROM work_task WHERE id=? AND case_id=?', (task_id,case_id))
        if not found:
            raise permissions.Denied('Contribution unavailable.')
        task = found[0]
        work._check_revision(task, revision)
        can_block, can_depend = authority(conn,user,case,task)
        if action not in ACTIONS or not (can_depend if action.startswith('dependency_') else can_block):
            raise permissions.Denied('This blocker action is not available to you.')
        note = work._text(fields.get('reason'), 'Reason', 2000)
        detail = {}
        if action == 'block':
            owner = work_tasks._owner(conn,case_id,fields.get('followup_owner_id'))
            work.get(conn, {'id':owner}, case_id)  # Follow-up responsibility cannot create membership.
            if not can_depend and owner not in (user['id'], task.get('blocker_owner_id')):
                raise permissions.Denied('Ask the lead or an officer to assign another follow-up owner.')
            due = date.fromisoformat(fields.get('followup_date') or '').isoformat()
            conn.execute('UPDATE work_task SET blocker_reason=?,blocker_owner_id=?,blocker_due_date=? WHERE id=?',
                         (note,owner,due,task_id))
            detail = {'blocker_reason':note,'followup_owner_id':owner,'followup_date':due}
        elif action == 'unblock':
            if not task['blocker_reason']:
                raise ValueError('This contribution has no recorded blocker.')
            detail = {'previous_blocker':task['blocker_reason'], 'followup_owner_id':task['blocker_owner_id'],
                      'followup_date':task['blocker_due_date']}
            conn.execute("UPDATE work_task SET blocker_reason='',blocker_owner_id=NULL,blocker_due_date=NULL WHERE id=?",(task_id,))
        else:
            prerequisite_id = int(fields.get('prerequisite_id') or 0)
            found = rows(conn,'SELECT * FROM work_task WHERE id=? AND case_id=?',(prerequisite_id,case_id))
            if not found or prerequisite_id == task_id:
                raise ValueError('Choose another contribution in this work item.')
            prerequisite = found[0]
            exists = conn.execute('SELECT 1 FROM work_dependency WHERE task_id=? AND prerequisite_id=?',(task_id,prerequisite_id)).fetchone()
            if action == 'dependency_add':
                if exists:
                    raise ValueError('This dependency already exists.')
                if prerequisite['status']=='cancelled':
                    raise ValueError('Choose a contribution that has not been cancelled.')
                cycle = conn.execute('''WITH RECURSIVE upstream(id) AS (
                    SELECT ? UNION SELECT d.prerequisite_id FROM work_dependency d JOIN upstream u ON d.task_id=u.id)
                    SELECT 1 FROM upstream WHERE id=?''',(prerequisite_id,task_id)).fetchone()
                if cycle:
                    raise ValueError('This dependency would create a cycle.')
                conn.execute('INSERT INTO work_dependency VALUES (?,?,?,?)',(task_id,prerequisite_id,user['id'],tz.now_iso()))
            else:
                if not exists:
                    raise ValueError('This dependency is no longer present.')
                conn.execute('DELETE FROM work_dependency WHERE task_id=? AND prerequisite_id=?',(task_id,prerequisite_id))
            detail = {'prerequisite_id':prerequisite_id,'prerequisite_title':prerequisite['title']}
        conn.execute('UPDATE work_task SET revision=revision+1,updated_at=? WHERE id=?',(tz.now_iso(),task_id))
        updated = rows(conn,'SELECT * FROM work_task WHERE id=?',(task_id,))[0]
        work._event(conn,user,case_id,'task_'+action,{'task_id':task_id,'title':task['title'],
                    'reason':note,'status':task['status'],'revision':updated['revision'],**detail})
        return updated
