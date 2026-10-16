"""Personal discussion preferences and at-most-once email digest attempts."""
from datetime import timedelta
from urllib.parse import urlsplit

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import mailer
import storage as st
import tzutil as tz
import work
import work_updates


def preferences(conn, user):
    user = permissions.actor(conn, user)
    found = rows(conn, 'SELECT * FROM work_notification_preference WHERE user_id=?', (user['id'],))
    return found[0] if found else {'user_id': user['id'], 'routine_bell': 'show', 'digest': 'off', 'revision': 0}


def save(conn, user, revision, routine_bell, digest):
    with transaction(conn):
        current = preferences(conn, user)
        if int(revision) != current['revision']:
            raise docs.Conflict('Your preferences changed. Reload and try again.')
        if routine_bell not in ('show', 'hide') or digest not in ('off', 'daily', 'weekly'):
            raise ValueError('Choose valid notification preferences.')
        conn.execute('''INSERT INTO work_notification_preference(user_id,routine_bell,digest,revision,updated_at)
            VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET routine_bell=excluded.routine_bell,
            digest=excluded.digest,revision=excluded.revision,updated_at=excluded.updated_at''',
                     (current['user_id'], routine_bell, digest, current['revision']+1, tz.now_iso()))


def history(conn, user):
    user = permissions.actor(conn, user)
    return rows(conn, '''SELECT created_at,state FROM work_digest WHERE user_id=? ORDER BY id DESC LIMIT 10''', (user['id'],))


def eligible(conn, user):
    """IDs only: never persist copied discussion content in an email queue."""
    result = []
    for n in rows(conn, '''SELECT n.id,c.case_id FROM work_notice n JOIN work_comment c ON c.id=n.comment_id
        LEFT JOIN work_comment_read r ON r.comment_id=n.comment_id AND r.user_id=n.user_id
        WHERE n.user_id=? AND COALESCE(r.revision,0)<n.revision
        AND NOT EXISTS (SELECT 1 FROM work_digest_notice dn WHERE dn.notice_id=n.id) ORDER BY n.id''', (user['id'],)):
        if work_updates.permitted(conn, user['id'], n['case_id']):
            result.append(n['id'])
    return result


def available(conn):
    return (work.enabled(conn) and st.email_feature_enabled(conn, 'job_work_updates')
            and mailer.email_configured())


def deliver(conn, base, dry_run=False, now=None):
    """Called by the existing daily reminder sweep. Weekly delivery is Monday.

    The committed claim precedes external I/O. A crash or uncertain response is
    never automatically retried, including on later days or cadence changes.
    """
    if not available(conn) or urlsplit(base).scheme not in ('https', 'http') or not urlsplit(base).netloc:
        return 0
    now = now or tz.now_local()
    count = 0
    for pref in rows(conn, "SELECT user_id,digest FROM work_notification_preference WHERE digest<>'off' ORDER BY user_id"):
        if pref['digest'] == 'weekly' and now.weekday() != 0:
            continue
        uid = pref['user_id']
        try:
            user = permissions.actor(conn, {'id': uid})
        except permissions.Denied:
            continue
        # One daily batch regardless of cadence changes; weekly also has a period key.
        period = (now.date()-timedelta(days=now.weekday())).isoformat() if pref['digest']=='weekly' else now.date().isoformat()
        key = pref['digest'] + ':' + period
        with transaction(conn):
            current = preferences(conn, user)
            if not available(conn) or current['digest'] != pref['digest']:
                continue
            if conn.execute('SELECT 1 FROM work_digest WHERE user_id=? AND (period_key=? OR delivery_date=?)', (uid,key,now.date().isoformat())).fetchone():
                continue
            ids = eligible(conn, user)
            if not ids:
                continue
            rp = st.get_rp(conn, user['rp_id']) if user.get('rp_id') else None
            recipient = (rp.get('email') if rp else None) or user['username']
            if not recipient or '@' not in recipient:
                continue
            if dry_run:
                count += 1
                continue
            batch = conn.execute('''INSERT INTO work_digest(user_id,period_key,delivery_date,state,created_at)
                VALUES (?,?,?,'sending',?)''', (uid,key,now.date().isoformat(),now.isoformat(timespec='seconds'))).lastrowid
            conn.executemany('INSERT INTO work_digest_notice(digest_id,notice_id) VALUES (?,?)', [(batch,nid) for nid in ids])
        # Recheck account, preference, read state, source access and global switches
        # immediately before transport. Minimal mail contains only a sign-in link.
        try:
            user = permissions.actor(conn, {'id': uid})
            allowed = available(conn) and preferences(conn,user)['digest'] == pref['digest']
            live = rows(conn, '''SELECT n.id,c.case_id FROM work_digest_notice dn JOIN work_notice n ON n.id=dn.notice_id
                JOIN work_comment c ON c.id=n.comment_id LEFT JOIN work_comment_read r
                ON r.comment_id=n.comment_id AND r.user_id=n.user_id
                WHERE dn.digest_id=? AND COALESCE(r.revision,0)<n.revision''', (batch,))
            live_ids = {n['id'] for n in live if work_updates.permitted(conn,uid,n['case_id'])}
            with transaction(conn):
                for nid in ids:
                    if nid not in live_ids:
                        conn.execute('DELETE FROM work_digest_notice WHERE digest_id=? AND notice_id=?', (batch,nid))
            allowed = allowed and bool(live_ids)
            if not allowed:
                state = 'cancelled'
            else:
                rp = st.get_rp(conn, user['rp_id']) if user.get('rp_id') else None
                recipient = (rp.get('email') if rp else None) or user['username']
                subject, body = mailer.work_digest_message(base.rstrip('/')+'/work/updates')
                from send_reminders import _send
                try:
                    result = _send(conn, 'job_work_updates', recipient, subject, body)
                    state = 'sent' if result.get('sent') else 'unknown'
                except Exception:
                    state = 'unknown'
        except permissions.Denied:
            state = 'cancelled'
        except Exception:
            state = 'unknown'
        with transaction(conn):
            conn.execute('UPDATE work_digest SET state=? WHERE id=?', (state,batch))
            if state == 'cancelled':
                conn.execute('DELETE FROM work_digest_notice WHERE digest_id=?', (batch,))
        count += state == 'sent'
    return count
