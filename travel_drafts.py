"""Own unsubmitted reimbursement filings using the normal travel domain service."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

import documents as docs
import documents_permissions as permissions
import storage as st
import travel
import travel_checklist as checklist
import travel_rules as rules
import tzutil as tz


class ReimbursementAnswers(BaseModel):
    model_config = ConfigDict(extra='forbid')
    flew: StrictBool = False
    boat_bus: StrictBool = False
    terminal_fee: StrictBool = False
    taxi_receipt: StrictBool = False
    ride_hailing: StrictBool = False
    gov_vehicle: StrictBool = False
    rfid: StrictBool = False
    lodging_claimed: StrictBool = False
    per_diem_claimed: StrictBool = False
    extra_expenses: StrictBool = False
    jo_cos: StrictBool = False
    representative_signs: StrictBool = False
    exceeds_daily_rate: StrictBool = False
    cert_of_appearance_available: StrictBool = False


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: StrictStr = Field(min_length=1, max_length=200)
    start_date: StrictStr = Field(min_length=10, max_length=10)
    end_date: StrictStr = Field(min_length=10, max_length=10)
    venue: StrictStr = Field(default='', max_length=200)
    dpo_no: StrictStr = Field(min_length=1, max_length=60)
    dpo_date: StrictStr | None = Field(default=None, min_length=10, max_length=10)
    role: Literal['participant', 'secretariat', 'resource_person', 'technical_support']
    answers: ReimbursementAnswers

    @model_validator(mode='after')
    def exact_draft(self):
        for key in ('title', 'venue', 'dpo_no'):
            value = getattr(self, key).strip()
            if (key != 'venue' and not value) or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError('Use a non-empty title and DPO number, with text on one line.')
            setattr(self, key, value)
        self.title = " ".join(self.title.split())
        for value in (self.start_date, self.end_date, self.dpo_date):
            if value is not None and date.fromisoformat(value).isoformat() != value:
                raise ValueError('Use YYYY-MM-DD dates.')
        # Leave headroom for the normal five-working-day deadline calculation.
        if not 1900 <= date.fromisoformat(self.start_date).year <= 9998 or not 1900 <= date.fromisoformat(self.end_date).year <= 9998:
            raise ValueError('Choose activity dates in years 1900–9998.')
        if not 0 <= (date.fromisoformat(self.end_date) - date.fromisoformat(self.start_date)).days <= 366:
            raise ValueError('Choose an end date within 366 days of the start.')
        return self


def normalize(fields):
    return Draft.model_validate(fields).model_dump(exclude_none=True)


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS travel_draft_save (
      operation_key TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      filing_id INTEGER NOT NULL UNIQUE REFERENCES travel_filing(id) ON DELETE CASCADE,
      ref_code TEXT NOT NULL, opened_at TEXT NOT NULL);''')


def actor(conn, user):
    user = permissions.actor(conn, user)
    if user.get('must_change') or user['role'] not in ('viewer', 'encoder', 'section_manager', 'admin'):
        raise permissions.Denied('Travel drafts are unavailable to you.')
    if not travel.enabled(conn):
        raise docs.Conflict('Travel filing is disabled.')
    return user


def snapshot(conn, user, fields):
    actor(conn, user)
    values = normalize(fields)
    due, rule = rules.deadline_for(conn, 'reimbursement', values['end_date'], tz.today_local())
    answers = travel.clean_answers({**values['answers'], 'role': values['role']}, 'reimbursement')
    items = rules.build_checklist('reimbursement', answers)
    return {'deadline_date': due, 'deadline_rule': rule, 'checklist_revision': checklist.CHECKLIST_REV,
            'items': [{'code': i.code, 'label': i.label, 'requirement': i.requirement, 'handling': i.handling,
                       'copies': i.copies, 'note': i.note} for i in items]}


def get(conn, user, filing_id):
    user = actor(conn, user)
    saved = conn.execute('SELECT operation_key,ref_code,opened_at FROM travel_draft_save WHERE filing_id=? AND owner_id=?',
                         (filing_id, user['id'])).fetchone()
    filing = travel.get_filing(conn, filing_id) if saved else None
    if (not travel.is_owner(user, filing) or filing['ref_code'] != saved[1]
            or filing['opened_at'] != saved[2] or filing.get('purged_at')):
        raise permissions.Denied('The original travel draft is unavailable.')
    return dict(filing, operation_key=saved[0])


def save_in_transaction(conn, user, fields, *, operation_key, expected_snapshot):
    if not conn.in_transaction:
        raise RuntimeError('A caller-owned transaction is required.')
    user = actor(conn, user)
    values = normalize(fields)
    prior = conn.execute('SELECT filing_id FROM travel_draft_save WHERE operation_key=?', (operation_key,)).fetchone()
    if prior:
        return get(conn, user, prior[0])['id']
    if snapshot(conn, user, values) != expected_snapshot:
        raise docs.Conflict('The deadline or checklist changed. Prepare a new draft preview.')
    source = travel.resolve_source(conn, user, tz.today_local())
    source.update(title=values['title'], start=values['start_date'], end=values['end_date'], venue=values['venue'])
    filing = travel.create_filing(conn, user, kind='reimbursement', source=source, answers=values['answers'],
        role=values['role'], dpo_no=values['dpo_no'], dpo_date=values.get('dpo_date', ''),
        mc114_format='none', today=tz.today_local(), commit=False)
    conn.execute('INSERT INTO travel_draft_save VALUES (?,?,?,?,?)',
                 (operation_key, user['id'], filing['id'], filing['ref_code'], filing['opened_at']))
    st.audit(conn, user['username'], 'integration_travel_draft_save', target_type='travel_filing',
             target_id=filing['id'], summary='Opened own unsubmitted reimbursement checklist', commit=False)
    return filing['id']


def questions(fields):
    return [{'label': label, 'answer': fields['answers'][key]} for key, label, kinds in checklist.ANSWER_KEYS
            if 'reimbursement' in kinds]
