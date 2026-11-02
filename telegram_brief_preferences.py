"""Saved daily-brief choices only; deliberately no scheduling or delivery hooks."""
import re

from documents_storage import rows, transaction
import telegram_links as links
from telegram_preferences import Conflict

SECTIONS = ('calendar', 'work', 'requests')


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS telegram_brief_preference(
        user_id INTEGER PRIMARY KEY REFERENCES admin_user(id) ON DELETE CASCADE,
        reminder_requested INTEGER NOT NULL DEFAULT 0 CHECK(reminder_requested IN (0,1)),
        local_time TEXT NOT NULL DEFAULT '08:00',
        calendar INTEGER NOT NULL DEFAULT 1 CHECK(calendar IN (0,1)),
        work INTEGER NOT NULL DEFAULT 1 CHECK(work IN (0,1)),
        requests INTEGER NOT NULL DEFAULT 1 CHECK(requests IN (0,1)),
        revision INTEGER NOT NULL DEFAULT 0, updated_at TEXT);
    ''')


def get(conn, uid):
    found = rows(conn, 'SELECT * FROM telegram_brief_preference WHERE user_id=?', (uid,))
    return found[0] if found else dict(user_id=uid, reminder_requested=0, local_time='08:00',
                                     calendar=1, work=1, requests=1, revision=0)


def save(conn, payload, revision, values, now):
    import storage as st
    if (set(values) != {'reminder_requested', 'local_time', *SECTIONS}
            or any(type(values[k]) is not bool for k in ('reminder_requested', *SECTIONS))
            or not isinstance(values['local_time'], str)
            or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', values['local_time'])
            or not re.fullmatch('[0-9]{1,18}', str(revision))
            or not any(values[k] for k in SECTIONS)):
        raise ValueError('Choose at least one brief section and a valid Manila time.')
    with transaction(conn):
        user = links.current(conn, payload)
        old = get(conn, user['id'])
        if old['revision'] != int(revision):
            raise Conflict('Daily brief settings changed. Review and save again.')
        conn.execute('''INSERT INTO telegram_brief_preference
            (user_id,reminder_requested,local_time,calendar,work,requests,revision,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            reminder_requested=excluded.reminder_requested,local_time=excluded.local_time,
            calendar=excluded.calendar,work=excluded.work,requests=excluded.requests,
            revision=excluded.revision,updated_at=excluded.updated_at''',
            (user['id'], int(values['reminder_requested']), values['local_time'],
             *(int(values[k]) for k in SECTIONS), old['revision']+1, links.stamp(now)))
        st.audit(conn, user['username'], 'telegram_brief_preferences', target_type='admin_user',
                 target_id=user['id'], summary='Saved daily brief choices; scheduled delivery remains unavailable.',
                 after='revision='+str(old['revision']+1), commit=False)
