"""Bounded authorized registry pages and account-owned display preferences."""
import math
import csv
import io
from contextlib import contextmanager
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


GROUPS = {'': None, 'status': 'd.status', 'lead': "COALESCE(u.id,0)"}
GROUP_ORDERS = {'status': 'd.status ASC',
                'lead': "COALESCE(u.username,'Unresolved') COLLATE NOCASE ASC,COALESCE(u.id,0) ASC"}


def grouping(value):
    choice = value.get('group_by', '')
    if not isinstance(choice, str) or choice not in GROUPS:
        raise ValueError('Group by workflow, assigned lead or no grouping.')
    return choice


def group_projection(choice):
    if choice == 'lead':
        return "CAST(COALESCE(u.id,0) AS TEXT) AS group_key,COALESCE(u.username,'Unresolved') AS group_label"
    return "d.status AS group_key,REPLACE(d.status,'_',' ') AS group_label"


LEAD_DATE_FIELDS = ('lead_id', 'due_from', 'due_to')


def lead_date_filters(value):
    options = {field: value.get(field, '') for field in LEAD_DATE_FIELDS}
    if any(not isinstance(option, str) for option in options.values()):
        raise ValueError('Invalid lead or due-date filters.')
    lead = options['lead_id']
    if lead not in ('', 'unresolved') and (not lead.isascii() or not lead.isdecimal()
            or lead.startswith('0') or len(lead) > 19 or int(lead) > 9223372036854775807):
        raise ValueError('Choose a valid lead or Unresolved.')
    for field in ('due_from', 'due_to'):
        raw = options[field]
        parsed = parse_due_date(raw)
        if raw and (parsed is None or parsed.isoformat() != raw):
            raise ValueError('Use valid due dates in YYYY-MM-DD format.')
    if options['due_from'] and options['due_to'] and options['due_from'] > options['due_to']:
        raise ValueError('Due from must be on or before Due through.')
    return options


def parse_due_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def iso_due_date(value):
    parsed = parse_due_date(value)
    return parsed.isoformat() if parsed else None


@contextmanager
def selected_query(conn, user, params):
    queue, query = params.get('queue', 'all'), params.get('q', '')
    sort, direction = params.get('sort', 'registered'), params.get('dir', 'desc')
    status, verification = params.get('status', ''), params.get('verification', '')
    deadline = params.get('deadline', '')
    extra = lead_date_filters(params)
    group = grouping(params)
    if (queue not in QUEUES or sort not in SORTS or direction not in ('asc', 'desc')
            or status not in ('', *STATUSES) or verification not in ('', *VERIFICATIONS)
            or deadline not in ('', *DEADLINES) or len(query) > 120):
        raise ValueError('Invalid table options. Reset the table and try again.')
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
        if extra['due_from'] or extra['due_to']:
            conn.create_function('registry_due_date', 1, iso_due_date, deterministic=True)
        lead_where = ('u.id IS NULL' if extra['lead_id'] == 'unresolved' else
                      'd.lead_id=:grid_lead_id')
        where = ' AND '.join(['1'] + (["d.status=:grid_status"] if status else [])
                             + (["d.verification=:grid_verification"] if verification else [])
                             + ([deadline_where] if deadline else [])
                             + ([lead_where] if extra['lead_id'] else [])
                             + (['registry_due_date(d.due_date)>=:grid_due_from'] if extra['due_from'] else [])
                             + (['registry_due_date(d.due_date)<=:grid_due_to'] if extra['due_to'] else []))
        values = {**selection.params, 'grid_status': status, 'grid_verification': verification,
                  'grid_deadline': deadline, 'grid_lead_id': extra['lead_id'],
                  'grid_due_from': extra['due_from'], 'grid_due_to': extra['due_to']}
        source = (selection.read_ctes() + ' SELECT {columns} FROM registry_selected selected '
                  'JOIN document d ON d.id=selected.id LEFT JOIN admin_user u ON u.id=d.lead_id '
                  f'WHERE {where}')
        # Sort expressions/directions are allowlisted, never interpolated from user input.
        order = SORTS[sort] + ' ' + direction.upper()
        if sort == 'due_date':
            order = "(d.due_date IS NULL OR d.due_date='') ASC," + order
        order += ',selected.sort_id DESC'
        if group:
            # Group the complete authorized result before applying the page boundary.
            order = GROUP_ORDERS[group] + ',' + order
        yield selection, source, values, order, today, soon


def lead_choices(conn, user, params):
    """Offer leads from the authorized queue/search, including inactive assignees."""
    scope = {key: params.get(key, default) for key, default in (('queue', 'all'), ('q', ''))}
    with selected_query(conn, user, scope) as (_, source, values, _order, _today, _soon):
        return rows(conn, source.format(columns='DISTINCT u.id,u.username AS name') +
                    ' AND u.id IS NOT NULL ORDER BY u.username COLLATE NOCASE,u.id', values)


def page(conn, user, params):
    try:
        number = int(params.get('page', '1'))
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid table page.') from None
    if not 1 <= number <= 1_000_000:
        raise ValueError('Invalid table page.')

    with selected_query(conn, user, params) as (selection, source, values, order, today, soon):
        total = conn.execute(source.format(columns='COUNT(*)'), values).fetchone()[0]
        group = grouping(params)
        groups = (rows(conn, source.format(columns=group_projection(group) + ',COUNT(*) AS count') +
                       f' GROUP BY {GROUPS[group]} ORDER BY {GROUP_ORDERS[group]}', values) if group else [])
        last_page = max(1, math.ceil(total / PAGE_SIZE))
        # A concurrent deletion or permission change may remove the requested last page.
        number = min(number, last_page)
        values.update(grid_limit=PAGE_SIZE, grid_offset=(number - 1) * PAGE_SIZE)
        columns = '''d.id,d.number,d.subject,d.verification,d.status,d.due_date,
            d.archived_at,d.reconcile,COALESCE(u.username,'Unresolved') AS lead,
            selected.sort_id AS registry_sort_id,
            EXISTS (SELECT 1 FROM document_email_import i WHERE i.document_id=d.id) AS gmail_imported'''
        if group:
            columns += ',' + group_projection(group)
        documents = rows(conn, source.format(columns=columns) +
                         f' ORDER BY {order} LIMIT :grid_limit OFFSET :grid_offset', values)
        # Reuse the registry's page-only snippets and current indexed-file access checks.
        if documents and selection.expression:
            selection._snippets(conn, documents)
        for doc in documents:
            doc['registered'] = doc.pop('registry_sort_id')
        decorate_deadlines(conn, documents, today=today, soon=soon)
        return {'data': documents, 'last_page': last_page, 'last_row': total, 'page': number,
                'group_by': group, 'groups': groups}


EXPORT_COLUMNS = {
    'number': ('Number', 'd.number'),
    'subject': ('Subject', 'd.subject'),
    'verification': ('Verification', 'd.verification'),
    'status': ('Workflow', 'd.status'),
    'due_date': ('Due date', 'd.due_date'),
    'lead': ('Lead', "COALESCE(u.username,'Unresolved')"),
}
MAX_EXPORT_ROWS = 10_000


def export_csv(conn, user, params):
    """Export all authorized matches, with a declared bound and no silent truncation."""
    fields = params.get('columns', ','.join(EXPORT_COLUMNS)).split(',')
    if (not fields or len(fields) > len(EXPORT_COLUMNS) or 'number' not in fields
            or len(set(fields)) != len(fields) or any(field not in EXPORT_COLUMNS for field in fields)):
        raise ValueError('Choose valid export columns, including Number.')
    with selected_query(conn, user, params) as (_, source, values, order, _today, _soon):
        group = grouping(params)
        projection = ','.join(EXPORT_COLUMNS[field][1] + ' AS ' + field for field in fields)
        if group:
            projection += ',' + group_projection(group)
        records = rows(conn, source.format(columns=projection) +
                       f' ORDER BY {order} LIMIT :export_limit', {**values, 'export_limit': MAX_EXPORT_ROWS + 1})
        if len(records) > MAX_EXPORT_ROWS:
            raise ValueError('More than 10,000 records match. Narrow the queue, search or filters before exporting.')
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow((['Group: ' + ('Workflow' if group == 'status' else 'Assigned lead')] if group else []) +
                        [EXPORT_COLUMNS[field][0] for field in fields])
        for record in records:
            values_out = []
            for field in (['group_label'] if group else []) + fields:
                value = str(record[field] or ('Unknown' if field == 'due_date' else ''))
                if field == 'verification':
                    value = 'Awaiting verification' if value == 'pending' else value.replace('_', ' ')
                elif field == 'status':
                    value = value.replace('_', ' ')
                # CSV quoting preserves text; an apostrophe stops spreadsheet execution.
                if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                    value = "'" + value
                values_out.append(value)
            writer.writerow(values_out)
        return '\ufeff' + stream.getvalue(), len(records)


def deadline_state(status, value, today, soon):
    """One classifier for filtering and labels; inactive records never signal urgency."""
    if status in ('closed', 'cancelled'):
        return 'inactive'
    due = parse_due_date(value)
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
    optional = {'deadline', 'group_by', *LEAD_DATE_FIELDS}
    if (not isinstance(value, dict) or not keys <= set(value) or set(value) - keys - optional
            or type(value['schema']) is not int or value['schema'] != 1):
        raise ValueError('Unsupported saved view. Reset the table and save a new view.')
    # Older schema-1 views gain unrestricted defaults without rewriting stored preferences.
    result = {key: value[key] for key in keys - {'columns'}}
    result['deadline'] = value.get('deadline', '')
    result['group_by'] = grouping(value)
    if any(not isinstance(result[key], str) for key in (keys | {'deadline'}) - {'columns', 'schema'}):
        raise ValueError('Invalid saved view options.')
    if (result['queue'] not in QUEUES or len(result['q']) > 120
            or result['status'] not in ('', *STATUSES)
            or result['verification'] not in ('', *VERIFICATIONS)
            or result['deadline'] not in ('', *DEADLINES)
            or result['sort'] not in SORTS or result['dir'] not in ('asc', 'desc')):
        raise ValueError('Invalid saved view options.')
    result.update(lead_date_filters(value))
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
