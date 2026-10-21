"""Personal responsibilities, distinct from permission to administer a record."""
from datetime import date

import documents as docs
import documents_permissions as permissions
from documents_storage import rows
import storage as st
import tzutil as tz
import work
import work_compat
import work_blockers
import work_decisions


def _reviewer(conn, user, case):
    # A confirmed, active lead with access owns the review. Officers are fallback
    # decision makers only when no lead can currently perform it.
    if case['lead_id']:
        try:
            work.get(conn, {'id': case['lead_id']}, case['id'])
            return case['lead_id'] == user['id']
        except permissions.Denied:
            pass
    return work.officer(conn, user, case)


def _entry(conn, user, row, waiting, today):
    task = None
    waiting_on = []
    if row['kind'] in ('task', 'lead'):
        try:
            case = work.get(conn, user, row['case_id'])
            work_compat.require_open(conn, case['id'])
        except (permissions.Denied, ValueError):
            return None
        if row['kind']=='task':
            task = rows(conn,'SELECT * FROM work_task WHERE id=?',(row['id'],))[0]
            waiting_on = [t for t in work_blockers.dependencies(conn,task['id']) if t['status']!='done']
        pending = work_decisions.pending(conn,task['id']) if task else []
        if pending and not waiting and (task['owner_id']==user['id'] or _reviewer(conn,user,case)):
            action = 'Review changed work direction'
        elif task and task['blocker_reason'] and task['blocker_owner_id']==user['id'] and not waiting:
            action = 'Follow up on blocker'
        elif row['kind'] == 'lead':
            if waiting or not work.officer(conn, user, case):
                return None
            action = 'Confirm accountable lead'
        elif row['state'] == 'proposed':
            if waiting or not work.officer(conn, user, {'unit_id': row['unit_id']}):
                return None
            action = 'Confirm contribution owner'
        elif row['state'] == 'for_review':
            reviewer = _reviewer(conn, user, case)
            if waiting:
                if row['owner_id'] != user['id'] or reviewer:
                    return None
                action = 'Waiting for contribution review'
            elif reviewer:
                action = 'Review submitted contribution'
            else:
                return None
        elif not waiting and row['owner_id'] == user['id']:
            action = 'Acknowledge and start' if row['state'] == 'todo' else 'Prepare and submit output'
        else:
            return None
        if task and (task['blocker_reason'] or waiting_on) and action not in ('Follow up on blocker','Review changed work direction'):
            action = 'Review blocker or prerequisites'
        title, context = row['title'], case['title']
        url = f"/work/{case['id']}" + (f"#task-{row['id']}" if row['kind']=='task' else '')
        can_act = work.enabled(conn)
    else:
        doc = docs.raw(conn, row['document_id'])
        if not permissions.can_view(conn, user, doc):
            return None
        if conn.execute("SELECT 1 FROM document_job WHERE document_id=? AND kind IN ('sign','dispatch') AND state IN ('running','unknown')", (doc['id'],)).fetchone():
            return None
        lead = st.get_admin_user_by_id(conn, doc['lead_id']) if doc['lead_id'] else None
        lead_available = lead and lead['active'] and permissions.can_view(conn, lead, doc)
        reviewer = user['id']==doc['lead_id'] if lead_available else permissions.officer(conn, user, doc)
        if row['state']=='proposed':
            if waiting or not permissions.officer(conn, user, doc):
                return None
            action = 'Confirm document assignment'
        elif row['state']=='submitted':
            if waiting and row['owner_id']==user['id'] and not reviewer:
                action = 'Waiting for contribution review'
            elif not waiting and reviewer:
                action = 'Review document contribution'
            else:
                return None
        elif not waiting and row['owner_id']==user['id']:
            action = 'Acknowledge document assignment' if row['state']=='assigned' else 'Prepare and submit document input'
        else:
            return None
        title, context = row['title'], doc['number'] + ' · ' + doc['subject']
        url, can_act = f"/documents/{doc['id']}", docs.enabled(conn)
    due = row['due_date']
    due_label = 'No internal target'
    if due:
        try:
            target = date.fromisoformat(due)
            due_label = 'Overdue' if target < today else ('Due today' if target==today else 'Upcoming')
        except ValueError:
            due_label = 'Target needs correction'
    return {'key': 'work:' + row['kind'] + ':' + str(row['id']), 'title': title,
            'context': context, 'url': url, 'action': action, 'due_date': due,
            'due_label': due_label, 'waiting': waiting, 'can_act': can_act,
            'blocker_reason':task['blocker_reason'] if task else '',
            'followup_date':task['blocker_due_date'] if task else None,
            'prerequisites':[t['title'] for t in waiting_on]}


def page(conn, user, before=None, waiting=False, limit=25, today=None):
    user = permissions.actor(conn, user)
    today = today or tz.today_local()
    cursor = int(before) if before is not None else 9223372036854775807
    if not 1 <= cursor <= 9223372036854775807 or not 1 <= limit <= 25:
        raise ValueError('Invalid work page.')
    boundary = '\uffff'
    if before is not None:
        table = {0:'work_task',1:'document_assignment',2:'work_case'}[cursor % 3]
        found = conn.execute('SELECT created_at FROM '+table+' WHERE id=?',(cursor//3,)).fetchone()
        if not found:
            raise ValueError('This work page is no longer available. Start from My work.')
        boundary = found[0]
    # Candidate selection excludes broad officer ownership. Python rechecks current
    # scope and complete source visibility for decision candidates before rendering.
    candidates = rows(conn, '''SELECT * FROM (
      SELECT t.id*3 AS cursor,'task' AS kind,t.id,t.case_id,NULL AS document_id,t.status AS state,
             t.owner_id,t.unit_id,t.due_date,t.title,t.created_at
      FROM work_task t JOIN work_case c ON c.id=t.case_id
      WHERE (t.status IN ('proposed','todo','in_progress','for_review') OR EXISTS(SELECT 1 FROM work_decision_task dt JOIN work_decision d ON d.id=dt.decision_id WHERE dt.task_id=t.id AND d.kind='change' AND NOT EXISTS(SELECT 1 FROM work_decision n WHERE n.supersedes_id=d.id) AND NOT EXISTS(SELECT 1 FROM work_decision_resolution r WHERE r.decision_id=d.id AND r.task_id=t.id)))
        AND (t.owner_id=? OR c.lead_id=? OR t.blocker_owner_id=? OR t.status IN ('proposed','for_review') OR EXISTS(SELECT 1 FROM work_decision_task dt WHERE dt.task_id=t.id))
      UNION ALL
      SELECT a.id*3+1,'legacy',a.id,NULL,a.document_id,a.status,a.user_id,d.unit_id,a.due_date,a.action,a.created_at
      FROM document_assignment a JOIN document d ON d.id=a.document_id
      WHERE a.role='contributor' AND a.status IN ('proposed','assigned','acknowledged','in_progress','submitted')
        AND d.status NOT IN ('closed','cancelled') AND d.canonical_id IS NULL
        AND NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id)
        AND (a.user_id=? OR d.lead_id=? OR a.status IN ('proposed','submitted'))
      UNION ALL
      SELECT c.id*3+2,'lead',c.id,c.id,NULL,'proposed',NULL,c.unit_id,c.due_date,'Confirm ownership',c.created_at
      FROM work_case c WHERE c.lead_id IS NULL
    ) WHERE (created_at,cursor)<(?,?) ORDER BY created_at DESC,cursor DESC LIMIT 250''', (user['id'],user['id'],user['id'],user['id'],user['id'],boundary,cursor))
    found=[]
    for row in candidates:
        entry=_entry(conn,user,row,waiting,today)
        if entry:
            if len(found)==limit:
                return [x[1] for x in found],found[-1][0]
            found.append((row['cursor'],entry))
    return [x[1] for x in found], candidates[-1]['cursor'] if len(candidates)==250 else None


def home_rows(conn,user,today=None,*,reads=None):
    if not (reads.documents_enabled(conn, user) if reads is not None else docs.enabled(conn)):
        return []
    today = today or tz.today_local()
    items,cursor = reads.work_preview(conn, user, today) if reads is not None else page(conn,user,limit=3,today=today)
    result=[{'key':item['key'],'icon':'📋','tone':'todo','title':item['title'],
             'detail':item['context']+' · '+item['due_label']+((' · '+item['due_date']) if item['due_date'] else ''),
             'cta':item['action'],'url':item['url']} for item in items if item['can_act']]
    if cursor:
        result.append({'key':'work:more','icon':'📋','tone':'info','title':'Browse My work',
                       'detail':'Continue through your tasks and decisions.','cta':'Open My work','url':'/work/mine'})
    return result
