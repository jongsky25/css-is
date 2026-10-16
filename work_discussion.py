"""Permission-checked plain-text discussion, independent of task/document revisions."""
import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work


SELECT = '''SELECT c.*,r.body,r.revision,r.created_at AS edited_at,
            COALESCE(NULLIF(p.name,''),u.username) AS author
            FROM work_comment c JOIN admin_user u ON u.id=c.author_id
            LEFT JOIN resource_person p ON p.id=u.rp_id
            JOIN work_comment_revision r ON r.comment_id=c.id
            AND r.revision=(SELECT MAX(revision) FROM work_comment_revision WHERE comment_id=c.id)'''


def scope(conn, user, case_id, task_id=None):
    user = permissions.actor(conn, user)
    case = work.get(conn, user, case_id)
    task = None
    if task_id is not None:
        found = rows(conn, 'SELECT id,title FROM work_task WHERE id=? AND case_id=?', (task_id, case_id))
        if not found:
            raise permissions.Denied('Discussion not found or unavailable to you.')
        task = found[0]
    return user, case, task


def message(conn, case_id, task_id, comment_id):
    found = rows(conn, SELECT + ' WHERE c.id=? AND c.case_id=? AND c.task_id IS ?',
                 (comment_id, case_id, task_id))
    if not found:
        raise permissions.Denied('Message not found in this discussion.')
    return found[0]


def page(conn, user, case_id, task_id=None, before=None, focus=None):
    user, case, task = scope(conn, user, case_id, task_id)
    if focus is not None:
        message(conn, case_id, task_id, focus)
        before = focus + 1
    found = rows(conn, SELECT + ''' WHERE c.case_id=? AND c.task_id IS ? AND (? IS NULL OR c.id<?)
                                   ORDER BY c.id DESC LIMIT 31''', (case_id, task_id, before, before))
    older = found[29]['id'] if len(found) > 30 else None
    messages = list(reversed(found[:30]))
    for item in messages:
        item['parent'] = message(conn, case_id, task_id, item['parent_id']) if item['parent_id'] else None
    return {'case': case, 'task': task, 'messages': messages, 'older': older, 'viewer_id': user['id']}


def history(conn, user, case_id, task_id, comment_id, before=None):
    scope(conn, user, case_id, task_id)
    current = message(conn, case_id, task_id, comment_id)
    revisions = rows(conn, '''SELECT * FROM work_comment_revision WHERE comment_id=?
                           AND (? IS NULL OR revision<?) ORDER BY revision DESC LIMIT 31''', (comment_id, before, before))
    return current, revisions


def post(conn, user, case_id, body, task_id=None, parent_id=None, mentions=None):
    with transaction(conn):
        user, _, _ = scope(conn, user, case_id, task_id)
        work.writable(conn)
        body = work._text(body, 'Message', 4000)
        if parent_id is not None:
            message(conn, case_id, task_id, parent_id)
        import work_updates
        mentioned = work_updates.validate_mentions(conn, case_id, mentions or [])
        now = tz.now_iso()
        cid = conn.execute('''INSERT INTO work_comment(case_id,task_id,parent_id,author_id,created_at)
                              VALUES (?,?,?,?,?)''', (case_id, task_id, parent_id, user['id'], now)).lastrowid
        conn.execute('INSERT INTO work_comment_revision VALUES (?,1,?,?)', (cid, body, now))
        work_updates.record(conn, cid, 1, mentioned, new=True)
        return cid


def edit(conn, user, case_id, task_id, comment_id, revision, body, mentions=None):
    with transaction(conn):
        user, _, _ = scope(conn, user, case_id, task_id)
        work.writable(conn)
        current = message(conn, case_id, task_id, comment_id)
        if current['author_id'] != user['id']:
            raise permissions.Denied('Only the author can edit this message.')
        if current['revision'] != revision:
            raise docs.Conflict('This message was edited elsewhere. Review the latest text before saving again.')
        body = work._text(body, 'Message', 4000)
        import work_updates
        old_mentions = [m['user_id'] for m in work_updates.mentions(conn, comment_id, revision)]
        mentioned = work_updates.validate_mentions(conn, case_id, old_mentions if mentions is None else mentions)
        if body != current['body'] or mentioned != old_mentions:
            conn.execute('INSERT INTO work_comment_revision VALUES (?,?,?,?)',
                         (comment_id, revision + 1, body, tz.now_iso()))
            work_updates.record(conn, comment_id, revision + 1, mentioned)
