"""Shared plain bureau creation and retained one-time creation from private drafts."""
import hashlib
import json

import activity_drafts as drafts
import activity_permissions
import documents_permissions as permissions
import mailer
from documents_storage import rows,transaction
import storage as st
import tzutil as tz


class AlreadyCreated(ValueError):pass
class DuplicateActivity(ValueError):pass


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS activity_draft_creation (
      draft_key TEXT PRIMARY KEY REFERENCES activity_draft_save(operation_key),
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_key TEXT NOT NULL UNIQUE,
      event_id INTEGER NOT NULL, event_token TEXT NOT NULL, event_created_at TEXT,
      form_id INTEGER NOT NULL, form_token TEXT NOT NULL, created_at TEXT NOT NULL);''')


def plain_fields_supported(conn,user,fields):
    try:drafts.context(conn,user,fields)
    except (ValueError,KeyError):return False
    return True


def create_bureau_in_transaction(conn,user,fields,*,expected_section=None):
    """Same F2/event services as Create; no mail, links to other work or commits."""
    if not conn.in_transaction:raise RuntimeError('Bureau activity creation requires a caller-owned transaction.')
    user=drafts.actor(conn,user);values=drafts.normalize(fields);context=drafts.context(conn,user,values)
    section=context['section']
    if expected_section is not None and section!=expected_section:raise ValueError('The organizing section changed.')
    fid=st.create_form_instance(conn,2,'F2',values['event_date'],venue=values['venue'] or None,modality='f2f',
        topic=values['activity_name'],lead_org_id=section['id'],created_by=user['username'],commit=False)
    ev=st.create_event(conn,values['activity_name'],values['event_date'],venue=values['venue'] or None,modality='f2f',
        organizer=section['name']+' (internal)',lead_org_id=section['id'],form_instance_ids=[fid],created_by=user['username'],commit=False)
    st.audit(conn,user['username'],'event_create',target_type='event',target_id=ev['id'],summary='Created plain bureau activity with one event-review form',commit=False)
    return ev,fid


def create_bureau(conn,user,fields):
    with transaction(conn):return create_bureau_in_transaction(conn,user,fields)


def recipients(conn,owner_id,section_id):
    result=[]
    candidates=[(owner_id,'event_created')]+[(uid,'event_section_notify') for uid in st.org_unit_chiefs(conn,section_id) if uid!=owner_id]
    for uid,feature in candidates:
        account=st.get_admin_user_by_id(conn,uid)
        if account and account['active']:
            result.append({'id':uid,'feature':feature,'email':account['username'],
                           'name':st._account_display_name(conn,uid) or account['username']})
    if len(result)>25:raise ValueError('Use the normal Create screen for this recipient count.')
    return sorted(result,key=lambda r:(r['feature'],r['id']))


def lookup(conn,user,draft_key):
    user=drafts.actor(conn,user);drafts.get(conn,user,draft_key)
    found=rows(conn,'SELECT * FROM activity_draft_creation WHERE draft_key=? AND owner_id=?',(draft_key,user['id']))
    return found[0] if found else None


def context(conn,user,draft_key):
    user=drafts.actor(conn,user);saved=drafts.get(conn,user,draft_key)
    if conn.execute('SELECT 1 FROM activity_draft_creation WHERE draft_key=?',(draft_key,)).fetchone():
        raise AlreadyCreated('This draft already created a live activity through confirmed creation. Inspect its original source.')
    fields=drafts.normalize(saved['fields']);current=drafts.context(conn,user,fields)
    if fields['event_date']<tz.today_local().isoformat():raise ValueError('This creation pilot requires today or a future activity date.')
    original=conn.execute('SELECT request_digest FROM activity_draft_save WHERE operation_key=?',(draft_key,)).fetchone()
    if not original or original[0]!=digest(fields):raise ValueError('The original private draft changed.')
    matches=st.find_similar_events(conn,fields['activity_name'],fields['event_date'],event_kind='bureau',venue=fields['venue'] or None)
    if any(m['strength']=='strong' for m in matches):
        raise DuplicateActivity('A strong activity duplicate exists. Review ordinary Create/Monitor; this pilot cannot override it.')
    targets=recipients(conn,user['id'],fields['section_id'])
    return {'draft_key':draft_key,'draft_id':saved['id'],'draft_created_at':saved['created_at'],'fields':fields,
            'section_at_save':saved['section'],'current':current,'recipients':targets,
            'email_enabled':{f:st.email_feature_enabled(conn,f) for f in ('event_created','event_section_notify')},
            'weak_duplicate_count':len(matches),'duplicate_digest':digest([{k:m[k] for k in ('id','title','event_date','end_date','strength','created_at')} for m in matches])}


def revision(snapshot):return digest(snapshot)


def notice_message(feature,payload):
    if feature=='event_created':
        return mailer.event_created_message(payload['creator_name'],payload['title'],payload['event_date'],payload['link'])
    if feature=='event_section_notify':
        return mailer.event_section_notify_message(payload['recipient_name'],payload['creator_name'],payload['title'],payload['event_date'],payload['link'])
    raise ValueError('Unknown creation notice feature.')


def live_source(conn,user,creation):
    user=drafts.actor(conn,user)
    if creation['owner_id']!=user['id']:raise permissions.Denied('Original created activity unavailable.')
    found=rows(conn,'SELECT * FROM event WHERE id=?',(creation['event_id'],))
    form=rows(conn,'''SELECT f.* FROM form_instance f JOIN event_form ef ON ef.form_instance_id=f.id
        WHERE ef.event_id=? AND f.id=?''',(creation['event_id'],creation['form_id']))
    if (not found or not form or found[0]['event_token']!=creation['event_token'] or found[0]['created_at']!=creation['event_created_at']
            or form[0]['qr_token']!=creation['form_token'] or not activity_permissions.can_manage(user,found[0],conn)):
        raise permissions.Denied('Original created activity unavailable.')
    return found[0],form[0]


def create_from_draft_in_transaction(conn,user,draft_key,expected_revision,*,operation_key):
    if not conn.in_transaction:raise RuntimeError('Draft creation requires a caller-owned transaction.')
    user=drafts.actor(conn,user)
    snapshot=context(conn,user,draft_key)
    if revision(snapshot)!=expected_revision:raise ValueError('The private draft or creation routing changed.')
    ev,fid=create_bureau_in_transaction(conn,user,snapshot['fields'],expected_section=snapshot['current']['section'])
    event=rows(conn,'SELECT * FROM event WHERE id=?',(ev['id'],))[0]
    form=rows(conn,'SELECT * FROM form_instance WHERE id=?',(fid,))[0]
    conn.execute('''INSERT INTO activity_draft_creation
        (draft_key,owner_id,operation_key,event_id,event_token,event_created_at,form_id,form_token,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (draft_key,user['id'],operation_key,ev['id'],ev['event_token'],event['created_at'],fid,form['qr_token'],tz.now_iso()))
    st.audit(conn,user['username'],'activity_draft_create',target_type='event',target_id=ev['id'],summary='Created live activity from own private draft',commit=False)
    return snapshot,lookup(conn,user,draft_key),digest([event,form])
