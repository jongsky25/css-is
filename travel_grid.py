"""Paged owner-only claim snapshots; no deadline refresh or business mutations."""
import csv
import io
import json
import sqlite3

import storage as st
from documents_storage import transaction
from datetime import date
from math import ceil
from urllib.parse import urlencode, quote

import travel

COLUMNS = {'ref_code': 'Reference', 'kind': 'Claim type', 'act_title': 'Activity',
           'act_start': 'Recorded start', 'act_end': 'Recorded end', 'status': 'Filing status'}
SIZE = 30
MAX_EXPORT_ROWS = 10000


def parse(raw):
    q = str(raw.get('q', '')).strip()
    if len(q) > 200:
        raise ValueError('Search must be 200 characters or fewer.')
    out = {'q': q, 'kind': raw.get('kind', ''), 'status': raw.get('status', ''),
           'sort': raw.get('sort', 'act_end'), 'dir': raw.get('dir', 'desc')}
    for key, choices in [('kind', travel.KIND_LABELS), ('status', travel.STATUS_LABELS),
                         ('sort', COLUMNS), ('dir', ('asc', 'desc'))]:
        if out[key] not in choices and not (key in ('kind', 'status') and not out[key]):
            raise ValueError('Choose a valid claim filter or sort order.')
    for key in ('from', 'to'):
        value = raw.get(key, '')
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('Choose valid recorded end dates (YYYY-MM-DD).') from None
        out[key] = value
    if out['from'] and out['to'] and out['from'] > out['to']:
        raise ValueError('The end-date range must run from earlier to later.')
    try:
        page = int(raw.get('page', '1'))
        if not 1 <= page <= 100000:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Choose a page from 1 to 100000.') from None
    out['page'] = page
    return out


def url(selection, **overrides):
    params = {**selection, **overrides}
    return '/travel/table?' + urlencode({k: v for k, v in params.items() if v != ''})


def _query(conn, user_id, selection):
    where, args = ['user_id=?'], [user_id]
    for key in ('kind', 'status'):
        if selection[key]:
            where.append(f'{key}=?'); args.append(selection[key])
    if selection['q']:
        conn.create_function('travel_casefold', 1, lambda value: str(value or '').casefold(), deterministic=True)
        where.append('(instr(travel_casefold(ref_code),?)>0 OR instr(travel_casefold(act_title),?)>0)')
        args += [selection['q'].casefold()] * 2
    for key, operator in [('from', '>='), ('to', '<=')]:
        if selection[key]:
            where.append(f'act_end {operator} ?'); args.append(selection[key])
    return ' AND '.join(where), args


def _rows(records):
    data = []
    for record in records:
        row = dict(zip(COLUMNS, record))
        row['kind'] = travel.KIND_LABELS[row['kind']]
        row['status'] = travel.STATUS_LABELS[row['status']]
        row['href'] = '/travel/f/' + quote(row['ref_code'], safe='')
        data.append(row)
    return data


def snapshot(conn, user_id, selection):
    predicate, args = _query(conn, user_id, selection)
    # One snapshot for count and rows, even if another tab changes a filing meanwhile.
    conn.execute('BEGIN')
    try:
        total = conn.execute(f'SELECT count(*) FROM travel_filing WHERE {predicate}', args).fetchone()[0]
        last_page = max(1, ceil(total / SIZE)); page = min(selection['page'], last_page)
        fields = ','.join(COLUMNS)
        records = conn.execute(f'SELECT {fields} FROM travel_filing WHERE {predicate} '
            f'ORDER BY {selection["sort"]} COLLATE NOCASE {selection["dir"]}, id {selection["dir"]} '
            'LIMIT ? OFFSET ?', args + [SIZE, (page-1)*SIZE]).fetchall()
        data = _rows(records)
        return {'data': data, 'total': total, 'page': page, 'last_page': last_page,
                'last_row': total, 'selection': {**selection, 'page': page}}
    finally:
        conn.rollback()


def export_csv(conn, user_id, selection):
    """Fresh owner-selected snapshot, bounded before producing an attachment."""
    predicate, args = _query(conn, user_id, selection)
    records = conn.execute(f'SELECT {",".join(COLUMNS)} FROM travel_filing WHERE {predicate} '
        f'ORDER BY {selection["sort"]} COLLATE NOCASE {selection["dir"]}, id {selection["dir"]} LIMIT ?',
        args + [MAX_EXPORT_ROWS + 1]).fetchall()
    if len(records) > MAX_EXPORT_ROWS:
        raise ValueError('More than 10,000 filings match. Narrow the search or filters before exporting.')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(COLUMNS.values())
    for row in _rows(records):
        values = []
        for field in COLUMNS:
            value = str(row[field] or '')
            if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return '\ufeff' + stream.getvalue(), len(records)


VIEW_FIELDS = ('q', 'kind', 'status', 'from', 'to', 'sort', 'dir')
MAX_VIEWS = 10


class ViewConflict(ValueError):
    pass


def view_state(value):
    if (not isinstance(value, dict) or set(value) != {'schema', *VIEW_FIELDS}
            or type(value['schema']) is not int or value['schema'] != 1
            or any(not isinstance(value[key], str) for key in VIEW_FIELDS)):
        raise ValueError('Unsupported saved selection. Return to the table and save a new view.')
    selected = parse(value)
    return {'schema': 1, **{key: selected[key] for key in VIEW_FIELDS}}


def _identifier(raw):
    try:
        value = int(raw)
        if not 1 <= value <= 9223372036854775807:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Choose a saved view and its current revision.') from None
    return value


def views(conn, owner_id):
    return [dict(zip(('id', 'name', 'revision'), row)) for row in conn.execute(
        'SELECT id,name,revision FROM travel_claim_view WHERE user_id=? ORDER BY name_key,id', (owner_id,))]


def open_view(conn, owner_id, raw_id):
    row = conn.execute('SELECT state_json FROM travel_claim_view WHERE id=? AND user_id=?',
                       (_identifier(raw_id), owner_id)).fetchone()
    if not row:
        raise ValueError('Saved view not found or unavailable to you.')
    try:
        return view_state(json.loads(row[0]))
    except (ValueError, TypeError):
        raise ValueError('This saved view is unavailable. Return to the table to replace or delete it.') from None


def save_view(conn, token, data, *, audit=None):
    if set(data) - {'action', 'id', 'revision', 'name', 'state'}:
        raise ValueError('Invalid saved view request.')
    action = data.get('action')
    if action not in ('create', 'update', 'delete'):
        raise ValueError('Choose a saved view action.')
    if action != 'create':
        identifier, revision = _identifier(data.get('id')), _identifier(data.get('revision'))
    if action != 'delete':
        name = data.get('name', '').strip()
        if not 1 <= len(name) <= 60 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError('Use a view name of 1–60 characters on one line.')
        try:
            state = view_state(json.loads(data.get('state', '')))
        except (ValueError, TypeError):
            raise ValueError('Invalid saved selection. Return to the table and try again.') from None
    try:
        with transaction(conn):
            owner = st.session_actor(conn, token) if token else None
            if owner is None or not travel.enabled(conn):
                raise PermissionError('Travel saved views are unavailable. Sign in and check that Travel filing is enabled.')
            if action != 'create':
                row = conn.execute('SELECT revision FROM travel_claim_view WHERE id=? AND user_id=?',
                                   (identifier, owner['id'])).fetchone()
                if not row:
                    raise ValueError('Saved view not found or unavailable to you.')
                if row[0] != revision:
                    raise ViewConflict('This saved view changed in another tab. Reload the table before changing it.')
            if action == 'delete':
                conn.execute('DELETE FROM travel_claim_view WHERE id=? AND user_id=?', (identifier, owner['id']))
            elif action == 'create':
                count = conn.execute('SELECT count(*) FROM travel_claim_view WHERE user_id=?', (owner['id'],)).fetchone()[0]
                if count >= MAX_VIEWS:
                    raise ValueError('You can save up to 10 views. Delete one before adding another.')
                identifier = conn.execute('INSERT INTO travel_claim_view(user_id,name,name_key,state_json) VALUES (?,?,?,?)',
                             (owner['id'], name, name.casefold(), json.dumps(state, sort_keys=True))).lastrowid
            else:
                conn.execute('UPDATE travel_claim_view SET name=?,name_key=?,state_json=?,revision=revision+1 '
                             'WHERE id=? AND user_id=?',
                             (name, name.casefold(), json.dumps(state, sort_keys=True), identifier, owner['id']))
            if audit is not None:
                audit(identifier, action)
            else:
                st.audit(conn, owner['username'], 'travel_view_save', target_type='travel_claim_view',
                         target_id=identifier, summary=action + ' private filter/sort preference', commit=False)
    except sqlite3.IntegrityError as error:
        if error.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise
        raise ValueError('You already have a view with that name. Choose another name or replace it.') from None
    return state if action != 'delete' else None
