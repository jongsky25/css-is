"""Shared pinned-update saving and bounded first-publication policy."""
import hashlib
import json

import activity_permissions
import documents_permissions as permissions
from documents_storage import rows,transaction
import storage as st
import tzutil as tz


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def install(conn):
    # Deliberately independent of event deletion: a cleared/reused source cannot
    # make an already-published original eligible for another MCP publication.
    conn.executescript('''CREATE TABLE IF NOT EXISTS activity_announcement_publication (
      event_token TEXT PRIMARY KEY, event_id INTEGER NOT NULL, event_created_at TEXT,
      operation_key TEXT NOT NULL UNIQUE, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      text_digest TEXT NOT NULL, published_at TEXT NOT NULL);''')


def source(conn,user,event_id,*,for_write=True):
    user=permissions.actor(conn,user)
    found=rows(conn,'SELECT * FROM event WHERE id=?',(event_id,))
    if not found or not activity_permissions.can_manage(user,found[0],conn):
        raise permissions.Denied('Activity not found or unavailable to you.')
    ev=found[0]
    if not for_write:return user,ev,None
    forms=rows(conn,'SELECT f.* FROM event_form ef JOIN form_instance f ON f.id=ef.form_instance_id WHERE ef.event_id=? ORDER BY f.id LIMIT 26',(event_id,))
    if (ev.get('event_kind','bureau')!='bureau' or ev['event_date']<tz.today_local().isoformat()
            or not forms or len(forms)>25 or not any(not f.get('archived') for f in forms)):
        raise ValueError('Use a current or upcoming bureau activity with 1–25 survey forms, at least one active.')
    if (ev.get('announcement') or '').strip() or conn.execute('SELECT 1 FROM activity_announcement_publication WHERE event_token=?',(ev['event_token'],)).fetchone():
        raise ValueError('Use ordinary Manage for an existing or previously published pinned update.')
    rp=st.get_rp(conn,user['rp_id']) if user.get('rp_id') else None
    authority=[user['id'],user['username'],user['role'],rp,st.team_scope_for_user(conn,user),st.event_scope_paths(conn,event_id)]
    audience=list(conn.execute('SELECT COUNT(*),MAX(id) FROM attendee WHERE event_id=?',(event_id,)).fetchone())
    return user,ev,{'expected_revision':digest([ev,forms,authority,audience]),'registered_count':audience[0]}


def normalize_text(text):
    if not isinstance(text,str) or not 1<=len(text)<=st.ANNOUNCEMENT_MAX or not text.strip():
        raise ValueError('Use 1–1000 characters of nonempty pinned-update text.')
    if any(ord(c)<32 and c not in '\n\t\r' for c in text) or '\x7f' in text:
        raise ValueError('Pinned-update text contains unsupported control characters.')
    return text.strip()


def save_in_transaction(conn,user,event_id,text,*,ip=None):
    """Existing normal UI semantics, including edit/clear, with atomic audit."""
    if not conn.in_transaction:raise RuntimeError('Pinned updates require a caller-owned transaction.')
    user,ev,_=source(conn,user,event_id,for_write=False)
    text=(text or '').strip()[:st.ANNOUNCEMENT_MAX]
    st.set_event_announcement(conn,event_id,text,tz.now_iso()[:16],commit=False)
    st.audit(conn,user['username'],'event_announcement_set',target_type='event',target_id=event_id,
             ip=ip,summary=f'Posted a pinned update ({len(text)} chars).' if text else 'Removed the pinned update.',commit=False)


def publish_in_transaction(conn,user,event_id,expected_revision,announcement,*,operation_key):
    if not conn.in_transaction:raise RuntimeError('Pinned publication requires a caller-owned transaction.')
    text=normalize_text(announcement);user,ev,info=source(conn,user,event_id)
    if info['expected_revision']!=expected_revision:raise ValueError('Activity or publication context changed.')
    save_in_transaction(conn,user,event_id,text)
    published=tz.now_iso()
    conn.execute('INSERT INTO activity_announcement_publication VALUES (?,?,?,?,?,?,?)',
                 (ev['event_token'],event_id,ev['created_at'],operation_key,user['id'],digest(text),published))
    return {'event_id':event_id,'event_token':ev['event_token'],'created_at':ev['created_at'],
            'published_at':published,'text_digest':digest(text),'registered_count':info['registered_count']}


def save(conn,user,event_id,text,*,ip=None):
    with transaction(conn):save_in_transaction(conn,user,event_id,text,ip=ip)
