"""Unnumbered Drive intake and retry-safe filing. No binary files are stored."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import json
import re
import threading
import uuid

import documents as d
import documents_permissions as p
import documents_operations as ops
from documents_storage import rows, transaction, event
import storage as st
import tzutil as tz

_SYNC_LOCK = threading.Lock()
FIELDS = ('direction','subject','type','sender','document_date','received_at','references','due_date','priority')
OCR_MIMES = {'application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'text/plain'}
MIMES = OCR_MIMES | {'application/msword','application/vnd.ms-excel','application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'}


def reviewer(conn, user):
    user = p.actor(conn, user)
    d.require(p.has_role(conn, user, 'records'), 'The intake queue requires a bureau-wide records grant.')
    return user


def can_review(conn, user):
    return p.has_role(conn, user, 'records')


def settings(conn):
    return {key: st.get_setting(conn, 'documents.drive_' + key, '')
            for key in ('intake_enabled','inbox','filed','actor_id','cursor','last_sync','sync_error')}


def configure(conn, user, fields):
    with transaction(conn):
        user = reviewer(conn, user)
        d.require(p.has_role(conn, user, 'workflow_admin'))
        current = settings(conn)
        enabled = fields.get('enabled') == 'yes'
        inbox, filed = str(fields.get('inbox','')).strip(), str(fields.get('filed','')).strip()
        if enabled and (not all(re.fullmatch(r'[A-Za-z0-9_-]{10,200}', x) for x in (inbox,filed)) or inbox == filed):
            raise ValueError('Choose different To Review and Filed folder IDs.')
        if (inbox,filed) != (current['inbox'],current['filed']) and conn.execute(
                "SELECT 1 FROM document_intake WHERE state IN ('waiting','attention') OR filing_state IN ('pending','error') LIMIT 1").fetchone():
            raise ValueError('Finish or dismiss queued scans and complete pending filing before changing folders.')
        for key,value in {'intake_enabled':'1' if enabled else '0','inbox':inbox,'filed':filed,
                          'actor_id':str(user['id']),'cursor':''}.items():
            _setting(conn,key,value)
        if enabled:
            # Sticky migration: pausing Drive must never resume direct Gmail registration.
            conn.execute("INSERT INTO app_setting(key,value) VALUES ('documents.gmail_review_queue_enabled','1') ON CONFLICT(key) DO UPDATE SET value='1'")
        event(conn,None,user,'drive_intake_configured',{'enabled':enabled,'inbox':inbox,'filed':filed})


def _setting(conn, key, value):
    conn.execute('INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 ('documents.drive_'+key,str(value)))


def _active(conn):
    d.writable(conn)
    config = settings(conn)
    if config['intake_enabled'] != '1':
        raise ValueError('Drive intake is not enabled. Ask the Documents administrator to configure it.')
    return config


def get(conn, user, item_id):
    reviewer(conn,user)
    found = rows(conn,'SELECT * FROM document_intake WHERE id=?',(item_id,))
    if not found:
        raise p.Denied('Intake file unavailable.')
    item = found[0]
    if item['document_id']:
        d.get(conn,user,item['document_id'])
    for key in ('draft','suggestions'):
        item[key] = json.loads(item[key+'_json'])
    item['email'] = None
    item['email_files'] = []
    if item['email_id']:
        item['email'] = rows(conn,'SELECT * FROM document_intake_email WHERE id=?',(item['email_id'],))[0]
        item['email_files'] = rows(conn,"SELECT id,file_id,current_name,revision FROM document_intake WHERE email_id=? AND file_id NOT LIKE 'email-body:%' ORDER BY id",(item['email_id'],))
    return item


def stage_email(conn, actor, payload, digest):
    """Called inside the signed intake transaction; no network calls or numbering."""
    config=settings(conn)
    if not config['inbox'] or not config['filed']:
        raise ValueError('Configure the office intake folders before queuing email.')
    now=tz.now_iso()
    eid=conn.execute('''INSERT INTO document_intake_email(mailbox,message_id,payload_hash,subject,sender,
        received_at,attachments_json,created_at) VALUES (?,?,?,?,?,?,?,?)''',
        (payload['mailbox'],payload['message_id'],digest,payload['subject'],payload['sender'],
         payload['received_at'],json.dumps(payload['attachments']),now)).lastrowid
    draft=json.dumps({'direction':'IN','subject':payload['subject'],'sender':payload['sender'],
        'type':'Unclassified','received_at':datetime.fromisoformat(payload['received_at']).astimezone(ZoneInfo('Asia/Manila')).replace(tzinfo=None).isoformat(timespec='minutes')})
    conn.execute('UPDATE document_intake_email SET body_text=? WHERE id=?',(payload.get('body_text',''),eid))
    primary=None
    if not payload['attachments']:
        # Internal source key only; never sent to Drive or added as a file version.
        primary=conn.execute('''INSERT INTO document_intake(file_id,source_folder,original_name,current_name,
            mime_type,fingerprint,content_key,discovered_at,updated_at,draft_json,email_id)
            VALUES (?,'',?,?,'message/rfc822',?,?,?,?,?,?)''',
            ('email-body:'+str(eid),payload['subject'],payload['subject'],digest,digest,now,now,draft,eid)).lastrowid
    for index,attachment in enumerate(payload['attachments']):
        fid=attachment['file_id']
        if conn.execute('SELECT 1 FROM document_file_version WHERE file_id=? LIMIT 1',(fid,)).fetchone():
            raise d.Conflict('An email attachment already belongs to a registered record.')
        old=conn.execute('SELECT id,email_id,state,claimed_by FROM document_intake WHERE file_id=?',(fid,)).fetchone()
        if old and (old[1] or old[2] not in ('waiting','attention') or old[3]):
            raise d.Conflict('An email attachment is already being handled; resolve its intake entry first.')
        name=payload['subject'] if index==0 else 'Email attachment '+str(index+1)
        if old:
            iid=old[0]
            conn.execute('UPDATE document_intake SET email_id=?,email_primary=?,draft_json=?,revision=revision+1 WHERE id=?',
                         (eid,int(index==0),draft,iid))
        else:
            iid=conn.execute('''INSERT INTO document_intake(file_id,source_folder,original_name,current_name,mime_type,
                fingerprint,content_key,discovered_at,updated_at,state,error,draft_json,email_id,email_primary)
                VALUES (?,?,?,?,'','pending',?,?,?,'waiting',?,?,?,?)''',
                (fid,config['inbox'],name,name,'pending:'+fid,now,now,
                 'Waiting for Drive metadata. Check Drive before registering.',draft,eid,int(index==0))).lastrowid
        if index==0: primary=iid
    conn.execute('UPDATE document_intake_email SET primary_intake_id=? WHERE id=?',(primary,eid))
    event(conn,None,actor,'gmail_queued',{'intake_id':primary,'message_id':payload['message_id'],'attachment_count':len(payload['attachments'])})
    return {'intake_id':primary,'state':'queued','duplicate':False}


def list_page(conn, user, state='waiting', page=1):
    user=reviewer(conn,user)
    if state not in ('waiting','attention','registered','dismissed'):
        state='waiting'
    page=max(1,min(int(page),100000))
    # Only small metadata is loaded; drafts/OCR do not travel with queue listings.
    visible="""i.email_primary=1 AND (i.document_id IS NULL OR (d.canonical_id IS NULL AND
        (d.visibility<>'restricted' OR EXISTS(SELECT 1 FROM document_access a WHERE a.document_id=d.id AND a.user_id=?))))"""
    items=rows(conn,'''SELECT i.id,i.original_name,i.discovered_at,i.state,i.revision,i.claimed_by,
        i.claim_until,i.document_id,i.filing_state,i.error,i.email_id,e.subject AS email_subject,u.username AS reviewer
        FROM document_intake i LEFT JOIN admin_user u ON u.id=i.claimed_by
        LEFT JOIN document_intake_email e ON e.id=i.email_id LEFT JOIN document d ON d.id=i.document_id WHERE ''' + visible +
        ' AND i.state=? ORDER BY i.id LIMIT 31 OFFSET ?',(user['id'],state,(page-1)*30))
    counts=dict(conn.execute('SELECT i.state,COUNT(*) FROM document_intake i LEFT JOIN document d ON d.id=i.document_id WHERE '+visible+' GROUP BY i.state',(user['id'],)))

    return items[:30],len(items)>30,counts


def discover(conn, config, result):
    files=result.get('files')
    if not isinstance(files,list) or len(files)>100 or result.get('inbox') != config['inbox']:
        raise ValueError('Drive returned an invalid intake listing.')
    with transaction(conn):
        actor=reviewer(conn,{'id':int(config['actor_id'])})
        if _active(conn)['inbox']!=config['inbox']:
            raise d.Conflict('The intake folder changed during discovery.')
        for item in files:
            fid=item.get('id','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',str(fid)):
                raise ValueError('Drive returned an invalid file ID.')
            if item.get('email_receipt'): continue
            old=conn.execute('SELECT id,content_key,state,fingerprint FROM document_intake WHERE file_id=?',(fid,)).fetchone()
            # Importer owns email grouping; do not expose half-uploaded messages.
            if not old and (item.get('email_attachment') or conn.execute('SELECT 1 FROM document_file_version WHERE file_id=? LIMIT 1',(fid,)).fetchone()):
                continue
            name=str(item.get('name',''))[:500]
            fp=str(item.get('fingerprint',''))[:500]
            key=str(item.get('content_key',''))[:500]
            mime=str(item.get('mime_type',''))[:150]
            if not fp or not key or not name:
                raise ValueError('Drive file metadata is incomplete.')
            error='' if mime in MIMES and 0 <= int(item.get('size',0)) <= 20*1024*1024 else 'Unsupported format or file exceeds 20 MiB. Replace it with a smaller PDF or image.'
            now=tz.now_iso()
            if not old:
                iid=conn.execute('''INSERT INTO document_intake(file_id,source_folder,original_name,current_name,
                    mime_type,fingerprint,content_key,discovered_at,updated_at,state,error) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (fid,config['inbox'],name,name,mime,fp,key,now,now,'attention' if error else 'waiting',error)).lastrowid
                event(conn,None,actor,'intake_discovered',{'intake_id':iid,'file_id':fid})
            elif old[2] in ('waiting','attention'):
                if old[3]=='pending':
                    conn.execute('''UPDATE document_intake SET original_name=?,current_name=?,mime_type=?,fingerprint=?,content_key=?,
                        revision=revision+1,updated_at=?,state=?,error=? WHERE id=?''',
                        (name,name,mime,fp,key,now,'attention' if error else 'waiting',error,old[0]))
                elif old[1] != key:
                    conn.execute('''UPDATE document_intake SET current_name=?,mime_type=?,fingerprint=?,content_key=?,
                        suggestions_json='{}',suggestion_key=NULL,revision=revision+1,updated_at=?,
                        state=?,error=? WHERE id=?''',(name,mime,fp,key,now,'attention',error or 'The source scan changed. Recheck saved details against the new file.',old[0]))
                    event(conn,None,actor,'intake_source_changed',{'intake_id':old[0],'file_id':fid})
                else:
                    conn.execute('UPDATE document_intake SET current_name=?,fingerprint=? WHERE id=?',(name,fp,old[0]))
            if old and old[2] in ('waiting','attention') and (old[3]=='pending' or old[1]!=key):
                # A changed sibling must invalidate a review of the whole message.
                note='Attachment details loaded. Check all attachments before registering.' if old[3]=='pending' else 'An email attachment changed. Recheck all attachments before registering.'
                conn.execute('''UPDATE document_intake SET revision=revision+1,error=?
                    WHERE email_primary=1 AND id<>? AND email_id=(SELECT email_id FROM document_intake WHERE id=?)''',(note,old[0],old[0]))
        cursor=str(result.get('next_cursor') or '')
        if len(cursor)>4096: raise ValueError('Invalid Drive continuation token.')
        _setting(conn,'cursor',cursor)
        _setting(conn,'last_sync',tz.now_iso())
        _setting(conn,'sync_error','')


def _editable(conn, user, item_id, revision, *, claim=True):
    user=reviewer(conn,user); d.writable(conn)
    item=get(conn,user,item_id)
    if not item['email_primary'] and claim:
        raise d.Conflict('Review this attachment from its email intake entry.')
    if item['state'] not in ('waiting','attention'):
        raise d.Conflict('This file has already left the review queue.')
    if item['revision'] != int(revision):
        raise d.Conflict('This review changed. Reload it before saving.')
    if item['claimed_by'] not in (None,user['id']) and (item['claim_until'] or '')>tz.now_iso():
        raise d.Conflict('Another staff member is reviewing this file. Try again after they release it.')
    if claim and (item['claimed_by'] != user['id'] or (item['claim_until'] or '')<=tz.now_iso()):
        raise d.Conflict('Start or resume your review before saving.')
    return user,item


def claim(conn,user,item_id,revision):
    with transaction(conn):
        user,item=_editable(conn,user,item_id,revision,claim=False)
        if not item['email_primary']:
            raise d.Conflict('Review this attachment from its email intake entry.')
        until=(datetime.fromisoformat(tz.now_iso())+timedelta(minutes=30)).isoformat(timespec='seconds')
        conn.execute('UPDATE document_intake SET claimed_by=?,claim_until=?,revision=revision+1 WHERE id=?',
                     (user['id'],until,item_id))
    return get(conn,user,item_id)


def requeue(conn,user,item_id,revision):
    with transaction(conn):
        user=reviewer(conn,user);d.writable(conn)
        item=get(conn,user,item_id)
        if not item['email_primary']: raise d.Conflict('Restore the email intake entry instead.')
        if item['state']!='dismissed' or item['revision']!=int(revision):
            raise d.Conflict('Only an unchanged dismissed scan can return to the queue.')
        conn.execute("UPDATE document_intake SET state='waiting',error='',revision=revision+1 WHERE id=?",(item_id,))
        if item['email_id']:
            conn.execute("UPDATE document_intake SET state='waiting',error='',revision=revision+1 WHERE email_id=? AND id<>?",(item['email_id'],item_id))
        event(conn,None,user,'intake_restored',{'intake_id':item_id})


def clean_fields(fields):
    clean={key:str(fields.get(key,'')).strip() for key in FIELDS}
    if any(len(v)>4000 for v in clean.values()):
        raise ValueError('A review field is too long.')
    return clean


def save(conn,user,item_id,revision,fields,action='save'):
    with transaction(conn):
        user,item=_editable(conn,user,item_id,revision)
        values=clean_fields(fields)
        state='attention' if action=='attention' else 'dismissed' if action=='dismiss' else 'waiting'
        note=str(fields.get('note','')).strip()[:1000]
        if action in ('attention','dismiss') and not note:
            raise ValueError('Explain why this scan needs attention or is being dismissed.')
        until=(datetime.fromisoformat(tz.now_iso())+timedelta(minutes=30)).isoformat(timespec='seconds')
        conn.execute('''UPDATE document_intake SET draft_json=?,state=?,error=?,revision=revision+1,
                        updated_at=?,claimed_by=?,claim_until=? WHERE id=?''',
                     (json.dumps(values),state,note,tz.now_iso(),None if action!='save' else user['id'],
                      None if action!='save' else until,item_id))
        if item['email_id']:
            conn.execute('UPDATE document_intake SET state=?,error=?,revision=revision+1 WHERE email_id=? AND id<>?',
                         (state,note,item['email_id'],item_id))
        event(conn,None,user,'intake_'+action,{'intake_id':item_id,'reason':note})
    return get(conn,user,item_id)


def extract(conn,user,item_id,revision,adapter=None):
    user,item=_editable(conn,user,item_id,revision)
    if item['mime_type'] not in OCR_MIMES:
        raise ValueError('OCR supports PDFs, images and text. Review this attachment in Drive and enter details manually.')
    if item['fingerprint']=='pending':
        raise ValueError('Check Drive to load attachment metadata before OCR.')
    if item['suggestion_key']==item['content_key'] and item['suggestions']:
        return item
    adapter=adapter or ops.get_adapter()
    result=adapter.call('extract',{'file_id':item['file_id'],'fingerprint':item['fingerprint'],
                                  'actor_id':user['id']},str(uuid.uuid4()))
    if result.get('state')!='confirmed': raise ValueError('OCR was not confirmed. Enter details manually or retry.')
    sanitized=ops.sanitize_extraction(result)
    # Persist suggestions only: no full text, excerpts, or binary copies.
    cached={'suggestions':sanitized['suggestions'],'warnings':sanitized['warnings']}
    with transaction(conn):
        user,current=_editable(conn,user,item_id,revision)
        if current['content_key']!=item['content_key']: raise d.Conflict('The scan changed during reading.')
        conn.execute('''UPDATE document_intake SET suggestions_json=?,suggestion_key=?,revision=revision+1
                        WHERE id=?''',(json.dumps(cached),item['content_key'],item_id))
        event(conn,None,user,'intake_read',{'intake_id':item_id})
    return get(conn,user,item_id)


def register(conn,user,item_id,revision,fields,attachments=(),adapter=None):
    user=reviewer(conn,user); d.writable(conn)
    prior=get(conn,user,item_id)
    if prior['document_id']:
        return d.get(conn,user,prior['document_id'])
    if fields.get('confirmed')!='yes': raise ValueError('Confirm that you checked the source and document details.')
    config=_active(conn)
    values=clean_fields(fields)
    if values['direction'] not in ('IN','OUT'): raise ValueError('Choose Incoming or Outgoing.')
    if not values['received_at']: raise ValueError('Enter the actual received date and time.')
    # Validate dates before allocating a number, including draft outgoing intake.
    datetime.fromisoformat(values['received_at'])
    body_only=bool(prior['email_id'] and prior['email']['body_text'] and not prior['email_files'])
    if prior['email_id'] and values['direction']!='IN':
        raise ValueError('Received email must be registered as Incoming.')
    if prior['email_id']:
        if attachments: raise ValueError('Email attachments are already grouped; register other correspondence separately.')
        attachments=[(f['id'],f['revision']) for f in prior['email_files'] if f['id']!=int(item_id)]
    picks=[(int(item_id),int(revision))]+[(int(i),int(r)) for i,r in attachments]
    if len(picks)>20 or len({i for i,r in picks})!=len(picks): raise ValueError('Choose up to 20 distinct scans.')
    items=[]
    adapter=adapter or ops.get_adapter()
    for iid,rev in picks:
        _,item=_editable(conn,user,iid,rev,claim=iid==int(item_id))
        if item['email_id'] != prior['email_id']:
            raise ValueError('Keep each email and its attachments in its own review.')
        if body_only:
            items.append(item)
            continue
        if item['mime_type'] not in MIMES: raise ValueError('Choose a supported document format.')
        result=adapter.call('intake_check',{'file_id':item['file_id'],'fingerprint':item['fingerprint'],
                         'inbox':config['inbox'],'actor_id':user['id']},str(uuid.uuid4()))
        if result.get('state')!='confirmed' or result.get('fingerprint')!=item['fingerprint']:
            raise d.Conflict('A source scan changed or left the intake folder. Refresh Drive and review it again.')
        items.append(item)
    with transaction(conn):
        if _active(conn)['inbox']!=config['inbox']:
            raise d.Conflict('The intake folder changed. Reload this review.')
        for iid,rev in picks: _editable(conn,user,iid,rev,claim=iid==int(item_id))
        doc=d.register_in_transaction(conn,user,{**values,'drive_url':'' if body_only else f"https://drive.google.com/file/d/{items[0]['file_id']}/view",
                                                'channel':'gmail' if prior['email_id'] else 'office_drive',
                                                'evidence':'Gmail message '+prior['email']['message_id'] if prior['email_id'] else ''},suppress_assignments=True,defer_rules=values['direction']=='IN')
        conn.execute("UPDATE document SET verification='verified',instruction_state=? WHERE id=?",
                     ('pending' if doc['direction']=='IN' else 'not_required',doc['id']))
        for index,item in enumerate(items):
            if body_only:
                conn.execute('''UPDATE document_intake SET state='registered',document_id=?,draft_json=?,
                    revision=revision+1,claimed_by=NULL,claim_until=NULL,error='',updated_at=? WHERE id=?''',
                    (doc['id'],json.dumps(values),tz.now_iso(),item['id']))
                continue
            if index:
                conn.execute('''INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at)
                    VALUES (?,?,?,'','reference',?,?)''',(doc['id'],f"https://drive.google.com/file/d/{item['file_id']}/view",item['file_id'],user['id'],tz.now_iso()))
            payload={'file_id':item['file_id'],'fingerprint':item['fingerprint'],'inbox':config['inbox'],
                     'filed':config['filed'],'number':doc['number'],'year':doc['created_at'][:4],
                     'direction':doc['direction'],'ordinal':index+1,'actor_id':user['id']}
            conn.execute('''UPDATE document_intake SET state='registered',document_id=?,filing_state='pending',
                filing_operation=?,filing_payload=?,draft_json=?,suggestions_json='{}',suggestion_key=NULL,
                revision=revision+1,claimed_by=NULL,claim_until=NULL,error='',updated_at=? WHERE id=?''',
                (doc['id'],str(uuid.uuid4()),json.dumps(payload),json.dumps(values),tz.now_iso(),item['id']))
        if prior['email_id']:
            email=prior['email']
            conn.execute('UPDATE document_intake_email SET document_id=? WHERE id=?',(doc['id'],email['id']))
            conn.execute('''INSERT INTO document_email_import(mailbox,message_id,payload_hash,document_id,received_at,attachments_json,created_at)
                VALUES (?,?,?,?,?,?,?)''',(email['mailbox'],email['message_id'],email['payload_hash'],doc['id'],email['received_at'],email['attachments_json'],tz.now_iso()))
            event(conn,doc['id'],user,'gmail_imported',{'message_id':email['message_id'],'attachment_count':len(prior['email_files'])})
        event(conn,doc['id'],user,'intake_confirmed',{'intake_ids':[i['id'] for i in items],'director_first':doc['direction']=='IN'})
        return d.raw(conn,doc['id'])


def file_pending(conn, adapter):
    config=_active(conn)
    actor=reviewer(conn,{'id':int(config['actor_id'])})
    pending=rows(conn,"SELECT * FROM document_intake WHERE filing_state IN ('pending','error') ORDER BY updated_at,id LIMIT 5")
    for item in pending:
        try:
            payload=json.loads(item['filing_payload'])
            # Revalidate the original registration actor; revocation stops their operation.
            original_actor=reviewer(conn,{'id':payload['actor_id']})
            d.get(conn,original_actor,item['document_id'])
            result=adapter.call('intake_file',payload,item['filing_operation'])
            if result.get('state')!='confirmed' or result.get('file_id')!=item['file_id'] or not result.get('fingerprint'):
                raise ValueError('Filing not confirmed.')
            with transaction(conn):
                _active(conn)
                conn.execute("UPDATE document_intake SET filing_state='complete',error='',updated_at=? WHERE id=?",
                             (tz.now_iso(),item['id']))
                conn.execute("UPDATE document_file_version SET fingerprint=? WHERE document_id=? AND file_id=? AND role='reference' AND fingerprint=''",
                             (str(result['fingerprint'])[:500],item['document_id'],item['file_id']))
                event(conn,item['document_id'],actor,'drive_filed',{'intake_id':item['id'],'file_id':item['file_id']})
        except Exception:
            with transaction(conn):
                conn.execute("UPDATE document_intake SET filing_state='error',error=?,updated_at=? WHERE id=?",
                             ('Drive filing needs attention; the registered record is saved. Check relay permissions and source changes.',tz.now_iso(),item['id']))


def sync(conn, adapter=None):
    if not _SYNC_LOCK.acquire(blocking=False): return
    try:
        config=_active(conn)
        actor=reviewer(conn,{'id':int(config['actor_id'])})
        adapter=adapter or ops.get_adapter()
        result=adapter.call('intake_list',{'inbox':config['inbox'],'cursor':config['cursor'],
                                         'actor_id':actor['id']},str(uuid.uuid4()))
        discover(conn,config,result)
        file_pending(conn,adapter)
    except Exception:
        if conn.in_transaction: conn.rollback()
        with transaction(conn):
            _setting(conn,'cursor','')
            _setting(conn,'sync_error','Drive check failed. Verify intake settings, relay deployment and folder access; queued reviews are retained.')
    finally:
        _SYNC_LOCK.release()


async def worker(get_conn):
    def tick():
        conn=get_conn()
        try:
            if d.enabled(conn) and settings(conn)['intake_enabled']=='1': sync(conn)
        finally: conn.close()
    while True:
        await asyncio.sleep(180)
        try: await asyncio.to_thread(tick)
        except Exception: pass  # Per-operation failures are exposed in intake status.
