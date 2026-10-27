"""Owner-private named report selections, never stored survey results."""
import calendar
from datetime import date
import json
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

import auth
import documents as docs
import documents_permissions as permissions
from documents_storage import rows
import storage as st
import tzutil as tz


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: StrictStr = Field(min_length=1, max_length=60)
    report_type: Literal['csm_month', 'activity_quarter']
    year: StrictInt = Field(ge=1900, le=9998)
    month: StrictInt | None = Field(default=None, ge=1, le=12)
    quarter: StrictInt | None = Field(default=None, ge=1, le=4)

    @model_validator(mode='after')
    def exact_selection(self):
        self.name = self.name.strip()
        if not self.name or any(ord(c) < 32 or ord(c) == 127 for c in self.name):
            raise ValueError('Use a name of 1–60 characters on one line.')
        if self.report_type == 'csm_month' and (self.month is None or self.quarter is not None):
            raise ValueError('A CSM view needs one month and no quarter.')
        if self.report_type == 'activity_quarter' and (self.quarter is None or self.month is not None):
            raise ValueError('An activity view needs one quarter and no month.')
        return self


def normalize(fields):
    return Selection.model_validate(fields).model_dump(exclude_none=True)


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS report_saved_view (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      name TEXT NOT NULL COLLATE NOCASE, selection_json TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
      UNIQUE(owner_id,name));
    ''')


def actor(conn, user):
    user = permissions.actor(conn, user)
    if user.get('must_change') or not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report views are unavailable to you.')
    return user


def report_path(fields):
    values = normalize(fields)
    if values['report_type'] == 'csm_month':
        year, month = values['year'], values['month']
        query = {'type': 1, 'date_from': date(year, month, 1).isoformat(),
                 'date_to': date(year, month, calendar.monthrange(year, month)[1]).isoformat()}
    else:
        query = {'type': 2, 'period': f"quarter:{values['year']}-Q{values['quarter']}"}
    return '/reports?' + urlencode(query)


def check_new(conn, user, values):
    user = actor(conn, user)
    if conn.execute('SELECT 1 FROM report_saved_view WHERE owner_id=? AND name=?', (user['id'], values['name'])).fetchone():
        raise docs.Conflict('You already have a report view with that name. Open it or review a new name.')
    if conn.execute('SELECT COUNT(*) FROM report_saved_view WHERE owner_id=?', (user['id'],)).fetchone()[0] >= 10:
        raise docs.Conflict('This pilot supports up to ten saved report views per person.')


def _decorate(row):
    values = normalize(json.loads(row['selection_json']))
    return dict(row, selection=values, report_url=report_path(values),
                period_label=(f"{values['year']}-{values['month']:02d}" if values['report_type'] == 'csm_month'
                              else f"{values['year']} Q{values['quarter']}"),
                report_label='Bureau-wide monthly CSM' if values['report_type'] == 'csm_month' else 'Bureau-wide quarterly activity satisfaction')


def get(conn, user, view_id):
    user = actor(conn, user)
    if type(view_id) is not int or not 1 <= view_id <= 2**63-1:
        raise permissions.Denied('Saved report view not found or unavailable to you.')
    found = rows(conn, 'SELECT * FROM report_saved_view WHERE id=? AND owner_id=?', (view_id, user['id']))
    if not found:
        raise permissions.Denied('Saved report view not found or unavailable to you.')
    return _decorate(found[0])


def listing(conn, user):
    user = actor(conn, user)
    return [_decorate(row) for row in rows(conn, 'SELECT * FROM report_saved_view WHERE owner_id=? ORDER BY id DESC LIMIT 10', (user['id'],))]


def save_in_transaction(conn, user, fields, *, operation_key):
    if not conn.in_transaction:
        raise RuntimeError('A caller-owned transaction is required.')
    user = actor(conn, user)
    values = normalize(fields)
    prior = conn.execute('SELECT id FROM report_saved_view WHERE operation_key=?', (operation_key,)).fetchone()
    if prior:
        saved = get(conn, user, prior[0])
        if saved['selection'] != values:
            raise docs.Conflict('This key already saved a different report selection.')
        return saved['id']
    check_new(conn, user, values)
    view_id = conn.execute('INSERT INTO report_saved_view(owner_id,name,selection_json,operation_key,created_at) VALUES(?,?,?,?,?)',
        (user['id'], values['name'], json.dumps(values, sort_keys=True), operation_key, tz.now_iso())).lastrowid
    st.audit(conn, user['username'], 'report_view_save', target_type='report_saved_view', target_id=view_id,
             summary='Saved own report selection', commit=False)
    return view_id
