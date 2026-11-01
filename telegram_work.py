"""Private, current-authority task/work metadata lookup; no business writes."""
from contextlib import nullcontext
import re

import documents_permissions as permissions
from documents_storage import rows, transaction
import telegram_calendar as common
import telegram_links as links
import work
import work_reads

USAGE = ('Use /my_tasks [BEFORE_ID], /my_work [BEFORE_ID], '
         '/task_status WORK_ID TASK_ID, or /work_status WORK_ID. Read only.')
COMMANDS = ('/my_tasks', '/my_work', '/task_status', '/work_status')


def parse(text):
    parts = text.split()
    if not parts or parts[0] not in COMMANDS:
        raise ValueError(USAGE)
    command, args = parts[0], parts[1:]
    if not ((command in COMMANDS[:2] and len(args) <= 1)
            or (command == '/task_status' and len(args) == 2)
            or (command == '/work_status' and len(args) == 1)):
        raise ValueError(USAGE)
    if any(not re.fullmatch('[1-9][0-9]{0,18}', arg) or int(arg) > 9223372036854775807 for arg in args):
        raise ValueError(USAGE)
    return {'command': command, 'ids': [int(arg) for arg in args]}


def validate(query):
    if query == {'error': 'usage'}:
        return True
    if not isinstance(query, dict) or set(query) != {'command', 'ids'} or not isinstance(query['ids'], list):
        return False
    if any(type(i) is not int for i in query['ids']):
        return False
    try:
        return parse(str(query['command']) + ' ' + ' '.join(map(str, query['ids']))) == query
    except ValueError:
        return False


def descriptor(projection, bot):
    return (isinstance(projection, dict) and set(projection) == {'kind', 'bot', 'fingerprint', 'query'}
            and projection['kind'] == 'work' and projection['bot'] == bot[0]
            and projection['fingerprint'] == bot[2] and validate(projection['query']))


def actor(conn, delivery, bot):
    user = common.actor(conn, delivery, bot, action='work.read')
    return user if user and work.enabled(conn) else None


def owned_tasks(conn, user, before=0):
    # Apply both ownership and the canonical source-document visibility policy
    # before LIMIT, so a hidden linked document cannot leak through a task.
    scope = permissions.RegistryScope(conn, user)
    return rows(conn, f'''SELECT t.* FROM work_task t JOIN work_case wc ON wc.id=t.case_id
        WHERE t.owner_id=:registry_actor AND {scope.work_view_sql('wc')}
        AND (:before=0 OR t.id<:before) ORDER BY t.id DESC LIMIT 11''',
        {**scope.params, 'before': before})


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
                    text += '\nTasks: ' + (', '.join(str(r['n']) + ' ' + r['status'].replace('_', ' ') for r in counts) or 'none')
                return text + '\n' + links.origin() + '/work/' + str(ids[0])
            except permissions.Denied:
                return 'Task or work item unavailable to this account.'
        before = ids[0] if ids else 0
        if command == '/my_tasks':
            records = owned_tasks(conn, user, before)
            more = len(records) > 10
            records = records[:10]
            line = task_line
            text = 'My assigned tasks (newest first)'
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
            text += '\nNext page: ' + command + ' ' + str(shown[-1]['id'])
        return text + '\n\nOpen shared work: ' + links.origin() + '/work'
