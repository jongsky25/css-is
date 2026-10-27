"""Owner-private contribution comment drafts. Saving never publishes a message."""
import documents as docs
import documents_permissions as permissions
from documents_storage import rows
import storage as st
import tzutil as tz
import work
import work_discussion


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS work_comment_draft (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      case_id INTEGER NOT NULL REFERENCES work_case(id), task_id INTEGER NOT NULL REFERENCES work_task(id),
      body TEXT NOT NULL, case_revision INTEGER NOT NULL, task_revision INTEGER NOT NULL,
      operation_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS work_comment_draft_owner ON work_comment_draft(owner_id,id);
    ''')


def context(conn, user, case_id, task_id):
    if type(case_id) is not int or type(task_id) is not int or not (1 <= case_id <= 2**63-1 and 1 <= task_id <= 2**63-1):
        raise permissions.Denied('Contribution not found or unavailable to you.')
    _, case, _ = work_discussion.scope(conn, user, case_id, task_id)
    task = rows(conn, 'SELECT id,title,revision FROM work_task WHERE id=? AND case_id=?', (task_id, case_id))[0]
    return {'work_item': {k: case[k] for k in ('id', 'title', 'revision')}, 'task': task}


def normalize_body(body):
    if not isinstance(body, str):
        raise ValueError('Draft text must be plain text.')
    body = work._text(body.replace('\r\n', '\n').replace('\r', '\n'), 'Draft text', 4000)
    if any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 for c in body):
        raise ValueError('Draft text cannot contain hidden control characters.')
    return body


def get(conn, user, draft_id):
    if type(draft_id) is not int or not 1 <= draft_id <= 2**63-1:
        raise permissions.Denied('Private draft not found or unavailable to you.')
    found = rows(conn, 'SELECT * FROM work_comment_draft WHERE id=? AND owner_id=?', (draft_id, user['id']))
    if not found:
        raise permissions.Denied('Private draft not found or unavailable to you.')
    draft = found[0]
    current = context(conn, user, draft['case_id'], draft['task_id'])
    return dict(draft, context=current,
                context_changed=(current['work_item']['revision'] != draft['case_revision']
                                 or current['task']['revision'] != draft['task_revision']))


def listing(conn, user, case_id, task_id):
    if task_id is None:
        return []
    context(conn, user, case_id, task_id)
    return rows(conn, 'SELECT id,created_at FROM work_comment_draft WHERE owner_id=? AND case_id=? AND task_id=? '
                'ORDER BY id DESC LIMIT 10', (user['id'], case_id, task_id))


def save_in_transaction(conn, user, case_id, task_id, body, *, expected_context, operation_key):
    if not conn.in_transaction:
        raise RuntimeError('A caller-owned transaction is required.')
    work.writable(conn)
    current = context(conn, user, case_id, task_id)
    body = normalize_body(body)
    prior = conn.execute('SELECT id FROM work_comment_draft WHERE operation_key=?', (operation_key,)).fetchone()
    if prior:
        draft = get(conn, user, prior[0])
        if (draft['case_id'], draft['task_id'], draft['body']) != (case_id, task_id, body):
            raise docs.Conflict('This draft key was already used for a different request.')
        return draft['id']
    if current != expected_context:
        raise docs.Conflict('The contribution changed. Review a fresh draft preview.')
    draft_id = conn.execute('''INSERT INTO work_comment_draft
        (owner_id,case_id,task_id,body,case_revision,task_revision,operation_key,created_at)
        VALUES(?,?,?,?,?,?,?,?)''', (user['id'], case_id, task_id, body, current['work_item']['revision'],
                                    current['task']['revision'], operation_key, tz.now_iso())).lastrowid
    st.audit(conn, user['username'], 'work_comment_draft_save', target_type='work_comment_draft',
             target_id=draft_id, summary='Saved own private contribution comment draft', commit=False)
    return draft_id
