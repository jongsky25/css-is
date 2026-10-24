"""Opt-in discussion digests with independent, at-most-once channel attempts."""
from datetime import timedelta
from uuid import uuid4

import apprise_transport as transport
import documents as docs
import documents_permissions as permissions
from documents_storage import rows,transaction
import email_params
import tzutil as tz
import work
import work_updates

CHANNEL=transport.CHANNEL
MAX_NOTICES=1000
MAX_ATTEMPTS=5


def preferences(conn,user):
    user=permissions.actor(conn,user)
    found=rows(conn,'SELECT * FROM work_channel_preference WHERE user_id=? AND channel=?',(user['id'],CHANNEL))
    return found[0] if found else {'user_id':user['id'],'channel':CHANNEL,'binding':None,'cadence':'off','revision':0}


def save(conn,user,revision,cadence,action='save'):
    raw=str(revision)
    if len(raw)>20 or not raw.isascii() or not raw.isdecimal():raise ValueError('Reload your notification preferences and try again.')
    if action not in ('save','disconnect') or cadence not in ('off','daily','weekly'):
        raise ValueError('Choose a valid Telegram digest preference.')
    with transaction(conn):
        current=preferences(conn,user)
        if int(raw)!=current['revision']:raise docs.Conflict('Your Telegram preferences changed. Reload and try again.')
        binding=uuid4().hex if action=='disconnect' or not current['binding'] else current['binding']
        conn.execute('''INSERT INTO work_channel_preference(user_id,channel,binding,cadence,revision,updated_at)
            VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,channel) DO UPDATE SET binding=excluded.binding,
            cadence=excluded.cadence,revision=excluded.revision,updated_at=excluded.updated_at''',
            (current['user_id'],CHANNEL,binding,'off' if action=='disconnect' else cadence,current['revision']+1,tz.now_iso()))


def available(conn,pref,base):
    return bool(work.enabled(conn) and transport.enabled() and transport.link(base) and transport.target(pref['binding']))


def status(conn,user,base):
    pref=preferences(conn,user)
    return {'ready':available(conn,pref,base),'binding':pref['binding'],'cadence':pref['cadence'],'revision':pref['revision']}


def history(conn,user):
    user=permissions.actor(conn,user)
    return rows(conn,'''SELECT created_at,state FROM work_channel_digest WHERE user_id=? AND channel=?
                       ORDER BY id DESC LIMIT 10''',(user['id'],CHANNEL))


def eligible(conn,user):
    found=[]
    for identifier,case_id in conn.execute('''SELECT n.id,c.case_id FROM work_notice n JOIN work_comment c ON c.id=n.comment_id
        LEFT JOIN work_comment_read r ON r.comment_id=n.comment_id AND r.user_id=n.user_id
        WHERE n.user_id=? AND COALESCE(r.revision,0)<n.revision AND NOT EXISTS
        (SELECT 1 FROM work_channel_digest_notice dn WHERE dn.notice_id=n.id AND dn.channel=?) ORDER BY n.id''',
        (user['id'],CHANNEL)):
        if work_updates.permitted(conn,user['id'],case_id):
            found.append(identifier)
            if len(found)==MAX_NOTICES:break
    return found


def _live(conn,uid,batch):
    notices=rows(conn,'''SELECT n.id,c.case_id FROM work_channel_digest_notice dn JOIN work_notice n ON n.id=dn.notice_id
        JOIN work_comment c ON c.id=n.comment_id LEFT JOIN work_comment_read r
        ON r.comment_id=n.comment_id AND r.user_id=n.user_id
        WHERE dn.digest_id=? AND n.user_id=? AND COALESCE(r.revision,0)<n.revision''',(batch,uid))
    return {n['id'] for n in notices if work_updates.permitted(conn,uid,n['case_id'])}


def deliver(conn,base,*,dry_run=False,now=None,hour=7):
    """Bounded scheduler tick from the morning hour; durable claims precede I/O.

    Five attempts per tick let subsequent ticks drain other users without blocking
    the scheduler for an unbounded number of network calls. Uncertain attempts
    and crash-left sending rows are never automatically retried.
    """
    now=now or tz.now_local();url=transport.link(base)
    if not work.enabled(conn) or not transport.enabled() or not url or now.hour<hour:return 0
    weekday=email_params.param(conn,'work_digest_weekday')
    candidates=rows(conn,'''SELECT p.* FROM work_channel_preference p WHERE p.channel=? AND p.cadence<>'off'
        AND NOT EXISTS (SELECT 1 FROM work_channel_digest d WHERE d.user_id=p.user_id AND d.channel=p.channel
                        AND d.delivery_date=?) ORDER BY p.user_id''',(CHANNEL,now.date().isoformat()))
    sent=attempts=0
    for original in candidates:
        if attempts>=MAX_ATTEMPTS:break
        cadence=original['cadence']
        if cadence=='weekly' and now.weekday()!=weekday:continue
        try:
            with transaction(conn):
                user=permissions.actor(conn,{'id':original['user_id']});uid=user['id']
                pref=preferences(conn,user)
                if pref['cadence']!=cadence or not available(conn,pref,base):continue
                value=transport.target(pref['binding']);signature=transport.fingerprint(value,pref['binding'])
                period=(now.date()-timedelta(days=now.weekday())).isoformat() if cadence=='weekly' else now.date().isoformat()
                key=cadence+':'+period
                if conn.execute('''SELECT 1 FROM work_channel_digest WHERE user_id=? AND channel=?
                    AND (period_key=? OR delivery_date=?)''',(uid,CHANNEL,key,now.date().isoformat())).fetchone():continue
                ids=eligible(conn,user)
                if not ids:continue
                if dry_run:
                    sent+=1;attempts+=1;continue
                batch=conn.execute('''INSERT INTO work_channel_digest(user_id,channel,period_key,delivery_date,
                    destination_hash,state,created_at) VALUES (?,?,?,?,?,'sending',?)''',
                    (uid,CHANNEL,key,now.date().isoformat(),signature,now.isoformat(timespec='seconds'))).lastrowid
                conn.executemany('INSERT INTO work_channel_digest_notice(digest_id,notice_id,channel) VALUES (?,?,?)',
                                 [(batch,nid,CHANNEL) for nid in ids])
        except permissions.Denied:
            continue
        attempts+=1
        # Fresh account/preference/read/access/config checks immediately before transport.
        try:
            with transaction(conn):
                user=permissions.actor(conn,{'id':uid});current=preferences(conn,user)
                live=_live(conn,uid,batch)
                value=transport.target(current['binding'])
                allowed=(current['cadence']==cadence and current['binding']==pref['binding']
                         and available(conn,current,base) and transport.fingerprint(value,current['binding'])==signature and bool(live))
                for nid in ids:
                    if nid not in live:conn.execute('DELETE FROM work_channel_digest_notice WHERE digest_id=? AND notice_id=?',(batch,nid))
            state=('sent' if transport.send(value,url) else 'unknown') if allowed else 'cancelled'
        except permissions.Denied:
            state='cancelled'
        except Exception:
            state='unknown'
        with transaction(conn):
            changed=conn.execute("UPDATE work_channel_digest SET state=? WHERE id=? AND destination_hash=? AND state='sending'",
                                 (state,batch,signature)).rowcount
            if state=='cancelled' and changed:conn.execute('DELETE FROM work_channel_digest_notice WHERE digest_id=?',(batch,))
        sent+=state=='sent'
    return sent
