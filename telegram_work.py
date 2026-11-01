"""Private, current-authority task/work metadata lookup; no business writes."""
from contextlib import nullcontext
from datetime import timedelta
import re

import documents_permissions as permissions
from documents_storage import rows, transaction
import telegram_calendar as common
import telegram_links as links
import work
import work_reads

USAGE = ('Use /my_tasks [all|overdue|upcoming|review] [BEFORE_ID], /my_work [BEFORE_ID], '
         '/task_status WORK_ID TASK_ID, or /work_status WORK_ID, or /my_summary. Read only.')
COMMANDS = ('/my_tasks', '/my_work', '/task_status', '/work_status', '/my_summary')


def parse(text):
    parts = text.split()
    if not parts or parts[0] not in COMMANDS:
        raise ValueError(USAGE)
    command, args = parts[0], parts[1:]
    filter_ = None
    if command == '/my_tasks' and args and args[0] in ('all', 'overdue', 'upcoming', 'review'):
        filter_, args = args[0], args[1:]
    if not ((command in COMMANDS[:2] and len(args) <= 1)
            or (command == '/task_status' and len(args) == 2)
            or (command == '/work_status' and len(args) == 1)
            or (command == '/my_summary' and not args)):
        raise ValueError(USAGE)
    if any(not re.fullmatch('[1-9][0-9]{0,18}', arg) or int(arg) > 9223372036854775807 for arg in args):
        raise ValueError(USAGE)
    query = {'command': command, 'ids': [int(arg) for arg in args]}
    if filter_:
        query['filter'] = filter_
    return query


def validate(query):
    if query == {'error': 'usage'}:
        return True
    if not isinstance(query, dict) or set(query) not in ({'command', 'ids'}, {'command', 'ids', 'filter'}) or not isinstance(query['ids'], list):
        return False
    if any(type(i) is not int for i in query['ids']):
        return False
    try:
        return parse(str(query['command']) + ' ' + (str(query['filter']) + ' ' if 'filter' in query else '') + ' '.join(map(str, query['ids']))) == query
    except ValueError:
        return False


def descriptor(projection, bot):
    return (isinstance(projection, dict) and set(projection) == {'kind', 'bot', 'fingerprint', 'query'}
            and projection['kind'] == 'work' and projection['bot'] == bot[0]
            and projection['fingerprint'] == bot[2] and validate(projection['query']))


def actor(conn, delivery, bot):
    user = common.actor(conn, delivery, bot, action='work.read')
    return user if user and work.enabled(conn) else None


def owned_tasks(conn, user, before=0, filter_='all', today=None):
    # Apply both ownership and the canonical source-document visibility policy
    # before LIMIT, so a hidden linked document cannot leak through a task.
    scope = permissions.RegistryScope(conn, user)
    policies = {'all': '1', 'review': "t.status='for_review'",
                'overdue': "t.status NOT IN ('done','cancelled') AND t.due_date<:today",
                'upcoming': "t.status NOT IN ('done','cancelled') AND t.due_date BETWEEN :today AND :end"}
    condition = policies[filter_]
    return rows(conn, f'''SELECT t.* FROM work_task t JOIN work_case wc ON wc.id=t.case_id
        WHERE t.owner_id=:registry_actor AND {scope.work_view_sql('wc')}
        AND {condition} AND (:before=0 OR t.id<:before) ORDER BY t.id DESC LIMIT 11''',
        {**scope.params, 'before': before, 'today': today.isoformat() if today else None,
         'end': (today+timedelta(days=7)).isoformat() if today else None})


def task_line(row):
    return ('Task ' + str(row['id']) + ' · Work ' + str(row['case_id']) + '\n'
            + common.clip(row['title'], 160) + '\nStatus: ' + row['status'].replace('_', ' ')
            + ' · Due: ' + common.clip(row['due_date'] or 'not set', 32))


def work_line(row):
    # Work cases have no authoritative overall status column. Do not invent one.
    return ('Work ' + str(row['id']) + ' · ' + common.clip(row['title'], 160)
            + '\nDue: ' + common.clip(row['due_date'] or 'not set', 32))


def render(conn, delivery, projection, bot, now, *, commit=True):
    if not descriptor(projection, bot):
        return None
    if not commit and not conn.in_transaction:
        raise RuntimeError('Caller-owned rendering requires a transaction')
    with transaction(conn) if commit else nullcontext():
        user = actor(conn, delivery, bot)
        if not user:
            return None
        query = projection['query']
        if query == {'error': 'usage'}:
            return USAGE
        command, ids = query['command'], query['ids']
        if command == '/my_summary':
            return summary(conn,user,now)
        if command in ('/task_status', '/work_status'):
            try:
                item = work.get(conn, user, ids[0])
                if command == '/task_status':
                    task = work_reads.task(conn, user, ids[0], ids[1])
                    if task['owner_id'] != user['id']:
                        return 'Task or work item unavailable to this account.'
                    text = task_line(task)
                else:
                    text = work_line(item)
                    counts = rows(conn, 'SELECT status,count(*) AS n FROM work_task WHERE case_id=? GROUP BY status ORDER BY status', (ids[0],))
                    total = sum(r['n'] for r in counts)
                    done = sum(r['n'] for r in counts if r['status']=='done')
                    text += '\nCompleted: ' + str(done) + '/' + str(total) + ' tasks'
                    text += '\nTasks: ' + (', '.join(str(r['n']) + ' ' + r['status'].replace('_', ' ') for r in counts) or 'none')
                return text + '\n' + links.origin() + '/work/' + str(ids[0])
            except permissions.Denied:
                return 'Task or work item unavailable to this account.'
        before = ids[0] if ids else 0
        if command == '/my_tasks':
            records = owned_tasks(conn, user, before, query.get('filter', 'all'), now.astimezone(common.ZONE).date())
            more = len(records) > 10
            records = records[:10]
            line = task_line
            text = 'My assigned tasks (newest first) · ' + query.get('filter', 'all')
            if query.get('filter') == 'upcoming':
                text += '\nDue today through the next 7 days · Asia/Manila'
        else:
            records, next_before = work_reads.page(conn, user, before=before, limit=10)
            more = next_before is not None
            line = work_line
            text = 'My accessible work (newest first)'
        shown = []
        for row in records:
            entry = line(row) + '\n' + links.origin() + '/work/' + str(row.get('case_id', row['id']))
            if common.units(text + '\n\n' + entry) > 3000:
                break
            text += '\n\n' + entry
            shown.append(row)
        if not records:
            text += '\nNo items on this page.'
        if shown and (more or len(shown) < len(records)):
            text += '\nNext page: ' + command + ' ' + (query['filter']+' ' if 'filter' in query else '') + str(shown[-1]['id'])
        return text + '\n\nOpen shared work: ' + links.origin() + '/work'


def summary(conn,user,now):
    today=now.astimezone(common.ZONE).date()
    scope=permissions.RegistryScope(conn,user)
    params={**scope.params,'today':today.isoformat(),'end':(today+timedelta(days=7)).isoformat()}
    counts=rows(conn,f"""SELECT
        COALESCE(sum(t.owner_id=:registry_actor AND t.status NOT IN ('done','cancelled') AND t.due_date<:today),0) AS overdue,
        COALESCE(sum(t.owner_id=:registry_actor AND t.status NOT IN ('done','cancelled') AND t.due_date BETWEEN :today AND :end),0) AS upcoming,
        COALESCE(sum(t.owner_id=:registry_actor AND t.status='for_review'),0) AS review,
        count(DISTINCT CASE WHEN t.status='for_review' THEN wc.id END) AS work_review
        FROM work_task t JOIN work_case wc ON wc.id=t.case_id WHERE {scope.work_view_sql('wc')}""",params)[0]
    return ('My work summary · Asia/Manila · '+today.isoformat()
            +'\nOverdue tasks: '+str(counts['overdue'])+' · /my_tasks overdue'
            +'\nTask deadlines today through '+params['end']+': '+str(counts['upcoming'])+' · /my_tasks upcoming'
            +'\nMy tasks awaiting review: '+str(counts['review'])+' · /my_tasks review'
            +'\nAccessible work awaiting review: '+str(counts['work_review'])+' · /my_work'
            +'\nCounts use current permitted records.\n'+links.origin()+'/work')
