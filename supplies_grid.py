"""Read-only, bounded Supplies inventory with account-owned display preferences."""
import csv
import io
import json
import math
import sqlite3
from contextlib import contextmanager

import supplies_permissions as permissions
import supplies_stock as stock
from supplies_notify import classify, LABELS
from supplies_storage import Conflict, Invalid, rows
import tzutil as tz

PAGE_SIZE = 30
MAX_EXPORT_ROWS = 10_000
MAX_VIEWS = 10
COLUMNS = {'code': 'Code', 'description': 'Description', 'unit': 'Unit',
           'on_hand': 'On hand', 'reserved': 'Reserved', 'available': 'Available',
           'critical_level': 'Critical level', 'target_level': 'Target level',
           'physical': 'Physical stock', 'availability': 'Availability', 'active': 'Catalog status'}
QUANTITIES = ('on_hand', 'reserved', 'available', 'critical_level', 'target_level')
PHYSICAL = ('unrecorded', 'inactive', 'out_of_stock', 'critical', 'normal')
AVAILABLE = ('unrecorded', 'inactive', 'out_of_stock', 'fully_reserved', 'low_available', 'available')
FILTERS = ('q', 'unit', 'physical', 'availability', 'active')


def options(value):
    result = {field: value.get(field, 'active' if field == 'active' else '') for field in FILTERS}
    if (any(not isinstance(v, str) for v in result.values()) or len(result['q']) > 200
            or len(result['unit']) > 40 or result['physical'] not in ('', *PHYSICAL)
            or result['availability'] not in ('', *AVAILABLE)
            or result['active'] not in ('active', 'all', 'inactive')):
        raise Invalid('Choose valid inventory filters.')
    result.update(sort=value.get('sort', 'code'), dir=value.get('dir', 'asc'))
    if (not isinstance(result['sort'], str) or result['sort'] not in COLUMNS
            or result['dir'] not in ('asc', 'desc')):
        raise Invalid('Choose a valid inventory sort.')
    return result


def require_scope(conn, user, values):
    actor = permissions.require_actor(conn, user)
    if values['active'] != 'active':
        permissions.require_stock_reader(conn, actor)
    return actor


@contextmanager
def selected_query(conn, user, params):
    values = options(params)
    with stock._snapshot(conn):
        require_scope(conn, user, values)
        # Share the established classifier; an unposted item is never a confirmed zero.
        for field in ('physical', 'availability'):
            conn.create_function('inventory_' + field, 5,
                lambda on_hand, reserved, critical, recorded, active, field=field:
                    classify(on_hand, reserved, critical, recorded=recorded, active=active)[
                        'physical_state' if field == 'physical' else 'availability_state'], deterministic=True)
        source = """WITH totals AS (
          SELECT i.id,i.code,i.description,i.unit,i.critical_level,i.target_level,i.active,
            COALESCE(m.on_hand,0) AS on_hand,COALESCE(m.movement_count,0) AS movement_count,
            COALESCE(r.reserved,0) AS reserved
          FROM supply_item i
          LEFT JOIN (SELECT item_id,SUM(quantity_delta) AS on_hand,COUNT(*) AS movement_count
            FROM supply_stock_movement GROUP BY item_id) m ON m.item_id=i.id
          LEFT JOIN (SELECT item_id,SUM(reserved_quantity) AS reserved FROM supply_reservation GROUP BY item_id) r ON r.item_id=i.id
        ), inventory AS (
          SELECT id,code,description,unit,critical_level,target_level,active,
            CASE WHEN movement_count>0 THEN on_hand END AS on_hand,
            CASE WHEN movement_count>0 THEN reserved END AS reserved,
            CASE WHEN movement_count>0 THEN on_hand-reserved END AS available,
            inventory_physical(on_hand,reserved,critical_level,movement_count>0,active) AS physical,
            inventory_availability(on_hand,reserved,critical_level,movement_count>0,active) AS availability
          FROM totals
        ) SELECT {columns} FROM inventory WHERE """
        clauses = ['(instr(lower(code),lower(:q))>0 OR instr(lower(description),lower(:q))>0)']
        if values['active'] != 'all':
            clauses.append('active=' + ('1' if values['active'] == 'active' else '0'))
        for field in ('unit', 'physical', 'availability'):
            if values[field]:
                clauses.append(field + '=:' + field)
        source += ' AND '.join(clauses)
        field = values['sort']
        expression = field + (' COLLATE NOCASE' if field not in QUANTITIES and field != 'active' else '')
        order = f"({field} IS NULL) ASC,{expression} {values['dir'].upper()},id ASC"
        yield source, {**values, 'q': values['q'].strip()}, order


def units(conn, user):
    with stock._snapshot(conn):
        actor = permissions.require_actor(conn, user)
        privileged = permissions.has_role(conn, actor, 'custodian') or permissions.has_role(conn, actor, 'auditor')
        return [r[0] for r in conn.execute('SELECT DISTINCT unit FROM supply_item' +
                ('' if privileged else ' WHERE active=1') + ' ORDER BY unit COLLATE NOCASE,unit')]


def page(conn, user, params):
    raw = params.get('page', '1')
    if type(raw) not in (str, int) or not str(raw).isascii() or not str(raw).isdecimal() or len(str(raw)) > 7 or not 1 <= int(raw) <= 1_000_000:
        raise Invalid('Choose a valid inventory page.')
    with selected_query(conn, user, params) as (source, values, order):
        total = conn.execute(source.format(columns='COUNT(*)'), values).fetchone()[0]
        last = max(1, math.ceil(total / PAGE_SIZE))
        number = min(int(raw), last)
        data = rows(conn, source.format(columns='id,' + ','.join(COLUMNS)) +
                    f' ORDER BY {order} LIMIT :limit OFFSET :offset',
                    {**values, 'limit':PAGE_SIZE, 'offset':(number-1)*PAGE_SIZE})
        # SQLite sorts integers; the browser receives exact decimal strings even above 2**53.
        for item in data:
            item['id'] = str(item['id'])
            for field in QUANTITIES:
                if item[field] is not None:
                    item[field] = str(item[field])
        return {'data':data, 'last_row':total, 'last_page':last, 'page':number}


def display(field, value):
    if field in ('physical', 'availability'):
        return LABELS[value]
    if field == 'active':
        return 'Active' if value else 'Inactive'
    if value is None:
        return 'Not set' if field == 'target_level' else 'Not recorded'
    return str(value)


def export_csv(conn, user, params):
    raw = params.get('columns', ','.join(COLUMNS))
    if not isinstance(raw, str):
        raise Invalid('Choose valid export columns, including Code.')
    fields = raw.split(',')
    if ('code' not in fields or len(fields) > len(COLUMNS) or len(set(fields)) != len(fields)
            or any(field not in COLUMNS for field in fields)):
        raise Invalid('Choose valid export columns, including Code.')
    with selected_query(conn, user, params) as (source, values, order):
        data = rows(conn, source.format(columns=','.join(fields)) +
                    f' ORDER BY {order} LIMIT :limit', {**values, 'limit':MAX_EXPORT_ROWS+1})
        if len(data) > MAX_EXPORT_ROWS:
            raise Invalid('More than 10,000 items match. Narrow the search or filters before exporting.')
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow([COLUMNS[field] for field in fields])
        for item in data:
            row = []
            for field in fields:
                value = display(field, item[field])
                if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                    value = "'" + value
                row.append(value)
            writer.writerow(row)
        return '\ufeff' + stream.getvalue(), len(data)


def view_state(value):
    keys = {'schema', *FILTERS, 'sort', 'dir', 'columns'}
    if (not isinstance(value, dict) or set(value) != keys
            or type(value['schema']) is not int or value['schema'] != 1):
        raise Invalid('Unsupported inventory view. Reset the table and save a new view.')
    result = {'schema':1, **options(value), 'columns':{}}
    columns = value['columns']
    if not isinstance(columns, dict) or set(columns) != set(COLUMNS):
        raise Invalid('Choose valid saved columns.')
    for field, setting in columns.items():
        if (not isinstance(setting, dict) or set(setting) - {'visible', 'width'}
                or type(setting.get('visible')) is not bool or (field == 'code' and not setting['visible'])):
            raise Invalid('Code must stay visible; check saved columns.')
        width = setting.get('width')
        if width is not None and (type(width) is not int or not 75 <= width <= 4096):
            raise Invalid('Column widths must be between 75 and 4096 pixels.')
        result['columns'][field] = dict(setting)
    return result


@contextmanager
def preference_transaction(conn):
    # Display preferences must not run the stock transaction's notice projector.
    if conn.in_transaction:
        raise RuntimeError('Inventory preferences require a clean connection.')
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield
        conn.commit()
    except BaseException as exc:
        conn.rollback()
        if isinstance(exc, sqlite3.OperationalError) and ('locked' in str(exc) or 'busy' in str(exc)):
            raise Conflict('Inventory views are busy. Try again.') from exc
        raise


def views(conn, user):
    owner = permissions.require_actor(conn, user)
    found = rows(conn, 'SELECT id,name,revision,state_json FROM supply_inventory_view '
                      'WHERE user_id=? ORDER BY name,id', (owner['id'],))
    for view in found:
        view['state'] = view_state(json.loads(view.pop('state_json')))
    return found


def save_view(conn, user, data):
    if not isinstance(data, dict) or set(data) - {'action', 'id', 'revision', 'name', 'state'}:
        raise Invalid('Invalid saved view request.')
    action = data.get('action')
    if action not in ('create', 'update', 'delete'):
        raise Invalid('Choose a saved view action.')
    if action != 'create' and any(type(data.get(key)) is not int or not 1 <= data[key] <= 9223372036854775807
                                  for key in ('id', 'revision')):
        raise Invalid('Choose a saved view and reload its current revision.')
    if action != 'delete':
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise Invalid('Use a view name of 1–60 characters on one line.')
        name = name.strip()
        state = view_state(data.get('state'))
    with preference_transaction(conn):
        owner = permissions.require_actor(conn, user)
        if action != 'delete':
            require_scope(conn, owner, state)
        saved_id = None
        if action != 'create':
            current = conn.execute('SELECT revision FROM supply_inventory_view WHERE id=? AND user_id=?',
                                   (data['id'], owner['id'])).fetchone()
            if not current:
                raise Invalid('Saved view not found or unavailable to you.')
            if current[0] != data['revision']:
                raise Conflict('This saved view changed in another tab. Reload the page before changing it.')
        if action == 'delete':
            conn.execute('DELETE FROM supply_inventory_view WHERE id=? AND user_id=?', (data['id'], owner['id']))
        else:
            duplicate = conn.execute('SELECT id FROM supply_inventory_view WHERE user_id=? AND name=? AND id<>?',
                                     (owner['id'], name, data.get('id') if action == 'update' else -1)).fetchone()
            if duplicate:
                raise Invalid('You already have a view with that name. Choose another name or update it.')
            now, encoded = tz.now_iso(), json.dumps(state, sort_keys=True)
            if action == 'create':
                count = conn.execute('SELECT COUNT(*) FROM supply_inventory_view WHERE user_id=?', (owner['id'],)).fetchone()[0]
                if count >= MAX_VIEWS:
                    raise Invalid('You can save up to 10 views. Delete one before adding another.')
                saved_id = conn.execute('INSERT INTO supply_inventory_view(user_id,name,state_json,created_at,updated_at) '
                                        'VALUES (?,?,?,?,?)', (owner['id'], name, encoded, now, now)).lastrowid
            else:
                saved_id = data['id']
                conn.execute('UPDATE supply_inventory_view SET name=?,state_json=?,revision=revision+1,updated_at=? '
                             'WHERE id=? AND user_id=?', (name, encoded, now, saved_id, owner['id']))
    return {'views': views(conn, user), 'saved_id': saved_id}
