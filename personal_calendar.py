"""Constrained personal calendar creation through the existing domain service."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

import calendar_actions
import documents_permissions as permissions
import office_calendar as oc
import storage as st


class Entry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: StrictStr = Field(min_length=1, max_length=200)
    start_date: StrictStr = Field(min_length=10, max_length=10)
    end_date: StrictStr | None = Field(default=None, min_length=10, max_length=10)
    start_time: StrictStr | None = Field(default=None, min_length=5, max_length=5)
    end_time: StrictStr | None = Field(default=None, min_length=5, max_length=5)
    venue: StrictStr = Field(default='', max_length=200)
    note: StrictStr = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def exact_entry(self):
        self.title, self.venue, self.note = self.title.strip(), self.venue.strip(), self.note.strip()
        if not self.title or any(ord(c) < 32 or ord(c) == 127 for c in self.title + self.venue):
            raise ValueError('Use a title and venue on one line.')
        if any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 for c in self.note):
            raise ValueError('Remove control characters from the note.')
        for value in (self.start_date, self.end_date):
            if value is not None and (len(value) != 10 or date.fromisoformat(value).isoformat() != value):
                raise ValueError('Use YYYY-MM-DD dates.')
        end = self.end_date or self.start_date
        if not 0 <= (date.fromisoformat(end) - date.fromisoformat(self.start_date)).days <= 366:
            raise ValueError('Choose an end date within 366 days of the start.')
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError('Provide both times, or neither for an all-day entry.')
        st.cal_validate(self.title, self.start_date, end_date=self.end_date,
                        start_time=self.start_time, end_time=self.end_time)
        if self.start_time is not None and (end, self.end_time) <= (self.start_date, self.start_time):
            raise ValueError('The end must be after the start.')
        if self.end_date == self.start_date:
            self.end_date = None
        return self


def normalize(fields):
    return Entry.model_validate(fields).model_dump(exclude_none=True)


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS personal_calendar_save (
      operation_key TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      entry_id INTEGER NOT NULL UNIQUE, entry_uid TEXT NOT NULL UNIQUE);''')


def actor(conn, user):
    user = permissions.actor(conn, user)
    try:
        return calendar_actions.actor(conn, user)
    except ValueError:
        raise permissions.Denied('Personal calendar entries are unavailable to you.') from None


def check_new(conn, user, values):
    user = actor(conn, user)
    # The same active-person eligibility as the ordinary calendar form.
    if user['id'] not in {p['user_id'] for p in oc.people_choices(conn)}:
        raise permissions.Denied('A current calendar person account is required.')
    normalize(values)


def get(conn, user, entry_id):
    user = actor(conn, user)
    saved = conn.execute('SELECT operation_key,entry_uid FROM personal_calendar_save WHERE entry_id=? AND owner_id=?',
                         (entry_id, user['id'])).fetchone()
    entry = oc.viewable_entry(conn, user, entry_id) if saved else None
    if not entry or entry['uid'] != saved[1]:
        raise permissions.Denied('The original personal calendar entry is unavailable.')
    return dict(entry, operation_key=saved[0])


def save_in_transaction(conn, user, fields, *, operation_key):
    if not conn.in_transaction:
        raise RuntimeError('A caller-owned transaction is required.')
    user = actor(conn, user)
    values = normalize(fields)
    prior = conn.execute('SELECT entry_id FROM personal_calendar_save WHERE operation_key=?', (operation_key,)).fetchone()
    if prior:
        return get(conn, user, prior[0])['id']
    check_new(conn, user, values)
    # No units, guests, recurrence, room, linked activity, Meet, travel or relay.
    calendar_fields = dict(values, kind='meeting', status='tentative', audience='people',
                           owner_org_id=None, extra_org_ids=[])
    entry_id = calendar_actions.create_in_transaction(conn, user, calendar_fields,
        [(user['id'], 'attending')], [], audit_it=False)
    entry = st.cal_get(conn, entry_id)
    conn.execute('INSERT INTO personal_calendar_save VALUES (?,?,?,?)',
                 (operation_key, user['id'], entry_id, entry['uid']))
    st.audit(conn, user['username'], 'integration_personal_calendar_save', target_type='calendar_entry',
             target_id=entry_id, summary='Saved own tentative calendar entry', commit=False)
    return entry_id
