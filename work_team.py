"""Shared contribution views over the existing task store and current case ACLs."""
from urllib.parse import urlencode

import documents_permissions as permissions
from documents_storage import rows
import tzutil as tz
import work
import work_tasks as tasks
import work_blockers as blockers
import work_decisions as decisions
import work_compat


MAX_ID = 9223372036854775807


def filters(values):
    result = {key: str(values.get(key) or default).strip() for key, default in
              {'view':'list', 'status':'active', 'owner':'', 'unit':'', 'q':'',
               'attention':'', 'before':''}.items()}
    if result['view'] not in ('list','board') or result['status'] not in ('active','all',*tasks.LABELS):
        raise ValueError('Choose a valid team view and contribution status.')
    if result['attention'] not in ('','waiting','overdue','no_date') or len(result['q']) > 120:
        raise ValueError('Choose a valid attention filter and search of at most 120 characters.')
    for key in ('unit','owner','before'):
        if result[key] and not (key=='owner' and result[key] in ('mine','unassigned')):
            try:
                value = int(result[key])
                if not 1 <= value <= MAX_ID:
                    raise ValueError()
                result[key] = str(value)
            except ValueError:
                raise ValueError('Choose a valid team filter or page.') from None
    return result


def url(selection, **changes):
    return '/work/team?' + urlencode({k:v for k,v in filters({**selection, **changes}).items() if v})


def present(conn, user, task, case=None):
    case = case or work.get(conn,user,task['case_id'])
    task = dict(task)
    task['case'] = case
    task['pending_decisions'] = decisions.pending(conn,task['id'])
    task['waiting_on'] = [t for t in blockers.dependencies(conn,task['id']) if t['status']!='done']
    task['waiting'] = bool(task['blocker_reason'] or task['waiting_on'] or task['pending_decisions'])
    task['read_only'] = ''
    try:
        work_compat.require_open(conn,case['id'])
    except ValueError as e:
        task['read_only'] = str(e)
    task['actions'] = tasks.actions(conn,user,case,task) if work.enabled(conn) and not task['read_only'] else []
    task['owner_warning'] = ''
    if task['owner_id'] and task['status']!='cancelled':
        try:
            tasks._owner(conn,case['id'],task['owner_id'])
        except ValueError as e:
            task['owner_warning'] = str(e)
            task['actions'] = [a for a in task['actions'] if a in ('reassign','cancel','milestone')]
    task['overdue'] = bool(task['due_date'] and task['due_date'] < tz.today_local().isoformat()
                           and task['status'] not in ('done','cancelled'))
    return task


def one(conn,user,case_id,task_id):
    user = permissions.actor(conn,user)
    case = work.get(conn,user,case_id)
    found = rows(conn,'SELECT * FROM work_task WHERE id=? AND case_id=?',(task_id,case_id))
    if not found:
        raise permissions.Denied('Contribution unavailable.')
    return present(conn,user,found[0],case)


def page(conn,user,selection,limit=25):
    user = permissions.actor(conn,user)
    selection = filters(selection)
    if not 1 <= limit <= 25:
        raise ValueError('Invalid team page size.')
    clauses = ['t.id < ?']
    args = [int(selection['before'] or MAX_ID)]
    state = selection['status']
    if state=='active':
        clauses.append("t.status NOT IN ('done','cancelled')")
    elif state!='all':
        clauses.append('t.status=?');args.append(state)
    if selection['unit']:
        clauses.append('t.unit_id=?');args.append(int(selection['unit']))
    owner = selection['owner']
    if owner=='unassigned':
        clauses.append('t.owner_id IS NULL')
    elif owner:
        clauses.append('t.owner_id=?');args.append(user['id'] if owner=='mine' else int(owner))
    if selection['q']:
        clauses.append('(instr(lower(t.title),lower(?))>0 OR instr(lower(c.title),lower(?))>0)')
        args.extend([selection['q']]*2)
    if selection['attention']=='no_date':
        clauses.append('t.due_date IS NULL')
    elif selection['attention']=='overdue':
        clauses.append("t.due_date < ? AND t.status NOT IN ('done','cancelled')")
        args.append(tz.today_local().isoformat())
    candidates = rows(conn,'''SELECT t.* FROM work_task t JOIN work_case c ON c.id=t.case_id
        WHERE '''+' AND '.join(clauses)+' ORDER BY t.id DESC LIMIT 250',args)
    found=[]
    cases={}
    for task in candidates:
        cid=task['case_id']
        if cid not in cases:
            try: cases[cid]=work.get(conn,user,cid)
            except permissions.Denied: cases[cid]=None
        if not cases[cid]:
            continue
        item=present(conn,user,task,cases[cid])
        if selection['attention']=='waiting' and not item['waiting']:
            continue
        if len(found)==limit:
            return found,found[-1]['id']
        found.append(item)
    # Bounded scans can yield empty permitted pages. Continue without exposing totals.
    return found,candidates[-1]['id'] if len(candidates)==250 else None
