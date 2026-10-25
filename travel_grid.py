"""Paged owner-only claim snapshots; no deadline refresh or business mutations."""
from datetime import date
from math import ceil
from urllib.parse import urlencode, quote

import travel

COLUMNS = {'ref_code': 'Reference', 'kind': 'Claim type', 'act_title': 'Activity',
           'act_start': 'Recorded start', 'act_end': 'Recorded end', 'status': 'Filing status'}
SIZE = 30


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


def snapshot(conn, user_id, selection):
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
    predicate = ' AND '.join(where)
    # One snapshot for count and rows, even if another tab changes a filing meanwhile.
    conn.execute('BEGIN')
    try:
        total = conn.execute(f'SELECT count(*) FROM travel_filing WHERE {predicate}', args).fetchone()[0]
        last_page = max(1, ceil(total / SIZE)); page = min(selection['page'], last_page)
        fields = ','.join(COLUMNS)
        records = conn.execute(f'SELECT {fields} FROM travel_filing WHERE {predicate} '
            f'ORDER BY {selection["sort"]} COLLATE NOCASE {selection["dir"]}, id {selection["dir"]} '
            'LIMIT ? OFFSET ?', args + [SIZE, (page-1)*SIZE]).fetchall()
        data = []
        for record in records:
            row = dict(zip(COLUMNS, record))
            row['kind'] = travel.KIND_LABELS[row['kind']]
            row['status'] = travel.STATUS_LABELS[row['status']]
            row['href'] = '/travel/f/' + quote(row['ref_code'], safe='')
            data.append(row)
        return {'data': data, 'total': total, 'page': page, 'last_page': last_page,
                'last_row': total, 'selection': {**selection, 'page': page}}
    finally:
        conn.rollback()
