"""Durable in-app notices. Eligibility is checked at creation AND each delivery."""
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work
import work_discussion as discussion


def permitted(conn, user_id, case_id):
    try:
        work.get(conn, {'id': user_id}, case_id)
        return True
    except permissions.Denied:
        return False


def candidates(conn, user, case_id):
    work.get(conn, user, case_id)
    return [p for p in rows(conn, '''SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name
        FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.active=1 ORDER BY name,u.id''')
            if permitted(conn, p['id'], case_id)]


def validate_mentions(conn, case_id, values):
    if not isinstance(values, (list, tuple)) or len(values) > 20:
        raise ValueError('Choose up to 20 people to mention.')
    ids = sorted({int(v) for v in values})
    if any(not permitted(conn, uid, case_id) for uid in ids):
        raise ValueError('A selected person no longer has access. Remove that mention and try again.')
    return ids


def mentions(conn, comment_id, revision):
    return rows(conn, '''SELECT m.user_id,COALESCE(NULLIF(r.name,''),u.username) AS name FROM work_mention m
        JOIN admin_user u ON u.id=m.user_id LEFT JOIN resource_person r ON r.id=u.rp_id
        WHERE m.comment_id=? AND m.revision=? ORDER BY m.user_id''', (comment_id, revision))


def record(conn, comment_id, revision, mentioned, new=False):
    """Called inside the message transaction; one notice per recipient/message."""
    if not conn.in_transaction:
        raise RuntimeError('An active transaction is required')
    c = rows(conn, 'SELECT * FROM work_comment WHERE id=?', (comment_id,))[0]
    recipients = {}
    if new:
        for uid, in conn.execute('SELECT user_id FROM work_follow WHERE case_id=? AND (task_id IS NULL OR task_id IS ?)', (c['case_id'], c['task_id'])):
            recipients[uid] = 'following'
        if c['parent_id']:
            uid = conn.execute('SELECT author_id FROM work_comment WHERE id=?', (c['parent_id'],)).fetchone()[0]
            recipients[uid] = 'reply'
    for uid in mentioned:
        conn.execute('INSERT INTO work_mention VALUES (?,?,?)', (comment_id, revision, uid))
        recipients[uid] = 'mention'
    for uid, reason in recipients.items():
        if uid != c['author_id'] and permitted(conn, uid, c['case_id']):
            conn.execute('''INSERT INTO work_notice(comment_id,user_id,revision,reason,created_at) VALUES (?,?,?,?,?)
                ON CONFLICT(comment_id,user_id) DO UPDATE SET reason=excluded.reason
                WHERE work_notice.reason='following' AND excluded.reason IN ('mention','reply')''',
                         (comment_id, uid, revision, reason, tz.now_iso()))
    # Authors have already seen their own saved version.
    conn.execute('INSERT INTO work_comment_read VALUES (?,?,?) ON CONFLICT(comment_id,user_id) DO UPDATE SET revision=MAX(revision,excluded.revision)',
                 (comment_id, c['author_id'], revision))


def following(conn, user, case_id, task_id=None):
    discussion.scope(conn, user, case_id, task_id)
    return bool(conn.execute('SELECT 1 FROM work_follow WHERE case_id=? AND user_id=? AND task_id IS ?',
                             (case_id, user['id'], task_id)).fetchone())


def follow(conn, user, case_id, task_id=None, enabled=True):
    with transaction(conn):
        user, _, _ = discussion.scope(conn, user, case_id, task_id)
        work.writable(conn)
        if enabled:
            conn.execute('INSERT OR IGNORE INTO work_follow VALUES (?,?,?,?)', (case_id, user['id'], task_id, tz.now_iso()))
        else:
            conn.execute('DELETE FROM work_follow WHERE case_id=? AND user_id=? AND task_id IS ?', (case_id, user['id'], task_id))


def read_revision(conn, user_id, comment_id):
    row = conn.execute('SELECT revision FROM work_comment_read WHERE comment_id=? AND user_id=?', (comment_id,user_id)).fetchone()
    return row[0] if row else 0


def mark_read(conn, user, case_id, task_id, observed):
    """Record only displayed revisions. A concurrent edit stays unread."""
    with transaction(conn):
        mark_read_in_transaction(conn, user, case_id, task_id, observed)


def mark_read_in_transaction(conn, user, case_id, task_id, observed):
    """Shared UI/MCP mutation; caller owns the transaction and receipt."""
    if not conn.in_transaction:
        raise RuntimeError('An active transaction is required')
    user, _, _ = discussion.scope(conn, user, case_id, task_id)
    if not isinstance(observed, list) or len(observed) > 30:
        raise ValueError('Mark at most 30 displayed messages at a time.')
    for pair in observed:
        cid, revision = map(int, pair)
        current = discussion.message(conn, case_id, task_id, cid)
        if not 1 <= revision <= current['revision']:
            raise ValueError('Invalid displayed message revision.')
        conn.execute('INSERT INTO work_comment_read VALUES (?,?,?) ON CONFLICT(comment_id,user_id) DO UPDATE SET revision=MAX(revision,excluded.revision)',
                     (cid, user['id'], revision))


def inbox(conn, user, before=None, limit=25, category="all", *, metadata_only=False):
    if category not in ("all", "direct", "following"):
        raise ValueError("Choose a valid update category.")
    user = permissions.actor(conn, user)
    result = []
    scanned = rows(conn, '''SELECT n.*,c.case_id,c.task_id FROM work_notice n
        JOIN work_comment c ON c.id=n.comment_id
        LEFT JOIN work_comment_read r ON r.comment_id=n.comment_id AND r.user_id=n.user_id
        WHERE n.user_id=? AND COALESCE(r.revision,0)<n.revision AND (? IS NULL OR n.id<?)
        AND (?='all' OR (?='direct' AND n.reason IN ('mention','reply')) OR (?='following' AND n.reason='following'))
        ORDER BY n.id DESC LIMIT 251''', (user['id'],before,before,category,category,category))
    cursor = None
    for n in scanned[:250]:
        cursor = n['id']
        if not permitted(conn, user['id'], n['case_id']):
            continue
        case = work.get(conn, user, n['case_id'])
        if not metadata_only:
            message = discussion.message(conn,n['case_id'],n['task_id'],n['comment_id'])
            n.update(title=case['title'], author=message['author'], body=message['body'])
        n.update(url=f"/work/{n['case_id']}/discussion?focus={n['comment_id']}" + (f"&task_id={n['task_id']}" if n['task_id'] else '') + f"#message-{n['comment_id']}")
        result.append(n)
        if len(result) == limit:
            return result, cursor
    return result, cursor if len(scanned)>250 else None


def bell_rows(conn, user):
    from work_digests import preferences
    category = "all" if preferences(conn, user)["routine_bell"] == "show" else "direct"
    cursor = None
    while True:
        notices, cursor = inbox(conn, user, before=cursor, limit=1, category=category)
        if notices:
            return [{'text':'Unread discussion updates', 'url':'/work/updates', 'count':1}]
        if cursor is None:
            return []
