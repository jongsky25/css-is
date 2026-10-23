"""Bounded authorized registry pages and account-owned display preferences."""
import math
import json
from datetime import date

import documents_permissions as permissions
import documents_rules as rules
import tzutil as tz
from documents_registry import PAGE_SIZE, Selection, snapshot
from documents_storage import rows, transaction


QUEUES = {'all', 'IN', 'OUT', 'verification', 'review', 'release', 'mine',
          'mentions', 'unassigned', 'archived', 'gmail', 'gmail_review', 'instruction'}
STATUSES = ('registered', 'draft', 'in_action', 'in_review', 'changes_requested',
            'approved', 'ready_to_release', 'released', 'awaiting_acknowledgment',
            'awaiting_external', 'closed', 'cancelled')
VERIFICATIONS = ('pending', 'verified', 'needs_correction')
DEADLINES = ('overdue', 'due_today', 'due_soon', 'unknown')
SORTS = {'registered': 'selected.sort_id', 'number': 'd.number COLLATE NOCASE',
         'subject': 'd.subject COLLATE NOCASE', 'verification': 'd.verification',
         'status': 'd.status', 'due_date': 'NULLIF(d.due_date,\'\')',
         'lead': "COALESCE(u.username,'') COLLATE NOCASE"}


def page(conn, user, params):
    queue, query = params.get('queue', 'all'), params.get('q', '')
    sort, direction = params.get('sort', 'registered'), params.get('dir', 'desc')
    status, verification = params.get('status', ''), params.get('verification', '')
    deadline = params.get('deadline', '')
    if (queue not in QUEUES or sort not in SORTS or direction not in ('asc', 'desc')
            or status not in ('', *STATUSES) or verification not in ('', *VERIFICATIONS)
            or deadline not in ('', *DEADLINES) or len(query) > 120):
        raise ValueError('Invalid table options. Reset the table and try again.')
    try:
        number = int(params.get('page', '1'))
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid table page.') from None
    if not 1 <= number <= 1_000_000:
        raise ValueError('Invalid table page.')

    with snapshot(conn):
        selection = Selection(conn, user, '' if queue == 'instruction' else query, queue)
        if queue == 'instruction' and not selection.scope.is_director:
            raise permissions.Denied('This inbox is for the Director or bureau OIC.')
        today = tz.today_local()
        soon = rules.shift(conn, today, 3)
        # Share the exact date parser/classifier with badges, including malformed dates.
        # SQLite filters/counts before LIMIT; no unbounded records reach the client.
        if deadline:
            conn.create_function('registry_deadline_state', 2,
                lambda status, due: deadline_state(status, due, today, soon), deterministic=True)
        deadline_where = ("registry_deadline_state(d.status,d.due_date) IN ('due_today','due_soon')"
                          if deadline == 'due_soon' else
                          'registry_deadline_state(d.status,d.due_date)=:grid_deadline')
        where = ' AND '.join(['1'] + (["d.status=:grid_status"] if status else [])
                             + (["d.verification=:grid_verification"] if verification else [])
                             + ([deadline_where] if deadline else []))
        values = {**selection.params, 'grid_status': status, 'grid_verification': verification,
                  'grid_deadline': deadline}
        source = (selection.read_ctes() + ' SELECT {columns} FROM registry_selected selected '
                  'JOIN document d ON d.id=selected.id LEFT JOIN admin_user u ON u.id=d.lead_id '
                  f'WHERE {where}')
        total = conn.execute(source.format(columns='COUNT(*)'), values).fetchone()[0]
        last_page = max(1, math.ceil(total / PAGE_SIZE))
        # A concurrent deletion or permission change may remove the requested last page.
        number = min(number, last_page)
        values.update(grid_limit=PAGE_SIZE, grid_offset=(number - 1) * PAGE_SIZE)
        # Sort expressions/directions are allowlisted, never interpolated from user input.
        order = SORTS[sort] + ' ' + direction.upper()
        if sort == 'due_date':
            order = "(d.due_date IS NULL OR d.due_date='') ASC," + order
        order += ',selected.sort_id DESC'
        columns = '''d.id,d.number,d.subject,d.verification,d.status,d.due_date,
            d.archived_at,d.reconcile,COALESCE(u.username,'Unresolved') AS lead,
            selected.sort_id AS registry_sort_id,
            EXISTS (SELECT 1 FROM document_email_import i WHERE i.document_id=d.id) AS gmail_imported'''
        documents = rows(conn, source.format(columns=columns) +
                         f' ORDER BY {order} LIMIT :grid_limit OFFSET :grid_offset', values)
        # Reuse the registry's page-only snippets and current indexed-file access checks.
        if documents and selection.expression:
            selection._snippets(conn, documents)
        for doc in documents:
            doc['registered'] = doc.pop('registry_sort_id')
        decorate_deadlines(conn, documents, today=today, soon=soon)
        return {'data': documents, 'last_page': last_page, 'last_row': total, 'page': number}


def deadline_state(status, value, today, soon):
    """One classifier for filtering and labels; inactive records never signal urgency."""
    if status in ('closed', 'cancelled'):
        return 'inactive'
    try:
        due = date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        due = None
    if due is None:
        return 'unknown'
    if due < today:
        return 'overdue'
    if due == today:
        return 'due_today'
    return 'due_soon' if due <= soon else 'scheduled'


def decorate_deadlines(conn, documents, *, today=None, soon=None):
    """Use the register's calendar-day overdue and three-working-day soon rules."""
    if not documents:
        return
    today = today or tz.today_local()
    soon = soon or rules.shift(conn, today, 3)
    labels = {'overdue': 'Overdue', 'due_today': 'Due today',
              'due_soon': 'Due soon', 'unknown': 'Unknown deadline'}
    for doc in documents:
        state = deadline_state(doc['status'], doc.get('due_date'), today, soon)
        doc.update(deadline_state=state, deadline_label=labels.get(state, ''))


VISIBLE_COLUMNS = ('number', 'subject', 'verification', 'status', 'due_date', 'lead')
MAX_VIEWS = 10


class ViewConflict(ValueError):
    pass


def view_state(value):
    """Persist only versioned display options, never records or access authority."""
    keys = {'schema', 'queue', 'q', 'status', 'verification', 'sort', 'dir', 'columns'}
    if not isinstance(value, dict) or set(value) not in (keys, keys | {'deadline'}) or type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError('Unsupported saved view. Reset the table and save a new view.')
    # Schema 1 views saved before deadline filters default to all deadlines.
    result = {key: value[key] for key in keys - {'columns'}}
    result['deadline'] = value.get('deadline', '')
    if any(not isinstance(result[key], str) for key in (keys | {'deadline'}) - {'columns', 'schema'}):
        raise ValueError('Invalid saved view options.')
    if (result['queue'] not in QUEUES or len(result['q']) > 120
            or result['status'] not in ('', *STATUSES)
            or result['verification'] not in ('', *VERIFICATIONS)
            or result['deadline'] not in ('', *DEADLINES)
            or result['sort'] not in SORTS or result['dir'] not in ('asc', 'desc')):
        raise ValueError('Invalid saved view options.')
    if result['queue'] == 'instruction':
        result['q'] = ''
    columns = value['columns']
    if not isinstance(columns, dict) or set(columns) != set(VISIBLE_COLUMNS):
        raise ValueError('Invalid saved columns.')
    result['columns'] = {}
    for field, options in columns.items():
        if (not isinstance(options, dict) or set(options) - {'visible', 'width'}
                or type(options.get('visible')) is not bool
                or (field == 'number' and not options['visible'])):
            raise ValueError('The Number column must remain visible; check saved columns.')
        width = options.get('width')
        if width is not None and (type(width) is not int or not 75 <= width <= 4096):
            raise ValueError('Column widths must be between 75 and 4096 pixels.')
        result['columns'][field] = {'visible': options['visible']}
        if width is not None:
            result['columns'][field]['width'] = width
    return result


def views(conn, user):
    owner = permissions.actor(conn, user)
    found = rows(conn, 'SELECT id,name,revision,state_json FROM document_registry_view '
                      'WHERE user_id=? ORDER BY name,id', (owner['id'],))
    for view in found:
        view['state'] = view_state(json.loads(view.pop('state_json')))
    return found


def save_view(conn, user, data):
    if not isinstance(data, dict) or set(data) - {'action', 'id', 'revision', 'name', 'state'}:
        raise ValueError('Invalid saved view request.')
    action = data.get('action')
    if action not in ('create', 'update', 'delete'):
        raise ValueError('Choose a saved view action.')
    if action != 'create' and any(type(data.get(key)) is not int or not 1 <= data[key] <= 9223372036854775807
                                  for key in ('id', 'revision')):
        raise ValueError('Choose a saved view and reload its current revision.')
    if action != 'delete':
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError('Use a view name of 1–60 characters on one line.')
        name = name.strip()
        state = view_state(data.get('state'))
    with transaction(conn):
        owner = permissions.actor(conn, user)
        if action != 'delete' and state['queue'] == 'instruction' and not permissions.director(conn, owner):
            raise permissions.Denied('This inbox is for the Director or bureau OIC.')
        saved_id = None
        if action != 'create':
            current = conn.execute('SELECT revision FROM document_registry_view WHERE id=? AND user_id=?',
                                   (data['id'], owner['id'])).fetchone()
            if not current:
                raise ValueError('Saved view not found or unavailable to you.')
            if current[0] != data['revision']:
                raise ViewConflict('This saved view changed in another tab. Reload the page before changing it.')
        if action == 'delete':
            conn.execute('DELETE FROM document_registry_view WHERE id=? AND user_id=?', (data['id'], owner['id']))
        else:
            duplicate = conn.execute('SELECT id FROM document_registry_view WHERE user_id=? AND name=? AND id<>?',
                                     (owner['id'], name, data.get('id') if action == 'update' else -1)).fetchone()
            if duplicate:
                raise ValueError('You already have a view with that name. Choose another name or update it.')
            now, encoded = tz.now_iso(), json.dumps(state, sort_keys=True)
            if action == 'create':
                count = conn.execute('SELECT COUNT(*) FROM document_registry_view WHERE user_id=?', (owner['id'],)).fetchone()[0]
                if count >= MAX_VIEWS:
                    raise ValueError('You can save up to 10 views. Delete one before adding another.')
                saved_id = conn.execute('INSERT INTO document_registry_view(user_id,name,state_json,created_at,updated_at) '
                                        'VALUES (?,?,?,?,?)', (owner['id'], name, encoded, now, now)).lastrowid
            else:
                saved_id = data['id']
                conn.execute('UPDATE document_registry_view SET name=?,state_json=?,revision=revision+1,updated_at=? '
                             'WHERE id=? AND user_id=?', (name, encoded, now, saved_id, owner['id']))
    return {'views': views(conn, user), 'saved_id': saved_id}
