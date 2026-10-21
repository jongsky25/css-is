"""Unnumbered Drive intake and retry-safe filing. No binary files are stored."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import re
import uuid
import httpx
import errno
import socket
import ssl
from documents_workspace import WorkspaceError, Unconfigured, BudgetAdapter

import documents as d
import documents_permissions as p
import documents_operations as ops
from documents_storage import rows, transaction, event
import storage as st
import tzutil as tz

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
        import documents_sync
        user = reviewer(conn, user)
        d.require(p.has_role(conn, user, 'workflow_admin'))
        if documents_sync.active(documents_sync.state(conn)):
            raise d.Conflict('A Drive check is running. Wait for it to finish before changing its settings.')
        current = settings(conn)
        enabled = fields.get('enabled') == 'yes'
        inbox, filed = str(fields.get('inbox','')).strip(), str(fields.get('filed','')).strip()
        if enabled and (not all(re.fullmatch(r'[A-Za-z0-9_-]{10,200}', x) for x in (inbox,filed)) or inbox == filed):
            raise ValueError('Choose different To Review and Filed folder IDs.')
        if (inbox,filed) != (current['inbox'],current['filed']) and conn.execute(
                "SELECT 1 FROM document_intake WHERE state IN ('waiting','attention') OR filing_state IN ('pending','running','error') LIMIT 1").fetchone():
            raise ValueError('Finish or dismiss queued scans and complete pending filing before changing folders.')
        for key,value in {'intake_enabled':'1' if enabled else '0','inbox':inbox,'filed':filed,
                          'actor_id':str(user['id']),'cursor':''}.items():
            _setting(conn,key,value)
        conn.execute("UPDATE document_intake_sync SET lease_owner=NULL,lease_until=NULL,state='pending',next_check_at=?,blocked=0,failures=0 WHERE id=1",(tz.now_iso(),))
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


def direction_from_sender(sender):
    """Office rule: BLHSD correspondence is outgoing, other named sources incoming."""
    normalized=re.sub(r'[^a-z0-9]+',' ',str(sender or '').casefold()).strip()
    if not normalized:
        return ''
    if (re.search(r'\bbureau of local health systems development\b',normalized)
            or re.search(r'\bblhsd\b',normalized)):
        return 'OUT'
    return 'IN'


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
    if item['suggestions']:
        suggested=item['suggestions'].get('suggestions',{})
        direction=direction_from_sender(suggested.get('sender'))
        if direction: suggested['direction']=direction
        item['suggestions']['warnings']=[w for w in item['suggestions'].get('warnings',[])
            if not w.startswith('Confirm Incoming or Outgoing')]
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
    draft=json.dumps({'direction':direction_from_sender(payload['sender']),'subject':payload['subject'],'sender':payload['sender'],
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
        i.claim_until,i.document_id,i.filing_state,i.filing_attempts,i.filing_next_at,i.filing_last_at,i.filing_blocked,i.error,i.email_id,e.subject AS email_subject,u.username AS reviewer
        FROM document_intake i LEFT JOIN admin_user u ON u.id=i.claimed_by
        LEFT JOIN document_intake_email e ON e.id=i.email_id LEFT JOIN document d ON d.id=i.document_id WHERE ''' + visible +
        ' AND i.state=? ORDER BY i.id LIMIT 31 OFFSET ?',(user['id'],state,(page-1)*30))
    counts=dict(conn.execute('SELECT i.state,COUNT(*) FROM document_intake i LEFT JOIN document d ON d.id=i.document_id WHERE '+visible+' GROUP BY i.state',(user['id'],)))

    return items[:30],len(items)>30,counts


def discover(conn, config, result, *, owner=None):
    files=result.get('files')
    if not isinstance(files,list) or len(files)>100 or result.get('inbox') != config['inbox']:
        raise ValueError('Drive returned an invalid intake listing.')
    with transaction(conn):
        if owner:
            import documents_sync
            documents_sync.owned(conn,owner)
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
    clean['direction']=direction_from_sender(clean['sender']) or clean['direction']
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


def extract(conn,user,item_id,revision,adapter=None,force=False):
    user,item=_editable(conn,user,item_id,revision)
    if item['mime_type'] not in OCR_MIMES:
        raise ValueError('OCR supports PDFs, images and text. Review this attachment in Drive and enter details manually.')
    if item['fingerprint']=='pending':
        raise ValueError('Check Drive to load attachment metadata before OCR.')
    if not force and item['suggestion_key']==item['content_key'] and item['suggestions']:
        return item
    adapter=adapter or ops.get_adapter()
    config=_active(conn)
    result=adapter.call('extract',{'file_id':item['file_id'],'fingerprint':item['fingerprint'],
                                  'intake':True,'inbox':config['inbox'],'content_key':item['content_key'],
                                  'actor_id':user['id']},str(uuid.uuid4()))
    if result.get('state')!='confirmed': raise ValueError('OCR was not confirmed. Enter details manually or retry.')
    if result.get('file_id') is None or result.get('content_key') is None or not result.get('fingerprint'):
        raise ValueError('Update documents_relay.gs in the Docs/travel project and deploy a new version of the existing web app to use content-checked intake OCR.')
    if result['file_id']!=item['file_id'] or result['content_key']!=item['content_key']:
        raise d.Conflict('The OCR source does not match this intake file. Refresh Drive and review its contents again.')
    sanitized=ops.sanitize_extraction(result)
    # Persist suggestions only: no full text, excerpts, or binary copies.
    cached={'suggestions':sanitized['suggestions'],'warnings':sanitized['warnings']}
    with transaction(conn):
        user,current=_editable(conn,user,item_id,revision)
        if _active(conn)['inbox']!=config['inbox']: raise d.Conflict('The intake folder changed during reading. Reload this review.')
        if current['content_key']!=item['content_key']: raise d.Conflict('The scan changed during reading.')
        conn.execute('''UPDATE document_intake SET suggestions_json=?,suggestion_key=?,fingerprint=?,revision=revision+1
                        WHERE id=?''',(json.dumps(cached),item['content_key'],str(result['fingerprint'])[:500],item_id))
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
    if prior['email_id']:
        if attachments: raise ValueError('Email attachments are already grouped; register other correspondence separately.')
        attachments=[(f['id'],f['revision']) for f in prior['email_files'] if f['id']!=int(item_id)]
    picks=[(int(item_id),int(revision))]+[(int(i),int(r)) for i,r in attachments]
    if len(picks)>20 or len({i for i,r in picks})!=len(picks): raise ValueError('Choose up to 20 distinct scans.')
    items=[]
    adapter=BudgetAdapter(adapter or ops.get_adapter())
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
    """One filing attempt, coordinated with discovery across all workers."""
    import documents_sync
    return documents_sync.sync(conn,adapter,filing_only=True)


def relay_network_failure(exc):
    """Classify transport causes without persisting raw URLs, headers or proxy data."""
    causes=[]
    current=exc
    while current is not None and len(causes)<12 and id(current) not in {id(c) for c in causes}:
        causes.append(current)
        current=current.__cause__ or current.__context__
    # Some transports retain only the message from the underlying OS exception.
    # Inspect it for known conditions, but never return or log its contents.
    descriptions=' '.join(str(c)[:2000] for c in causes).lower()
    try:
        reply=exc.request.url.host=='script.googleusercontent.com'
    except (AttributeError, RuntimeError):
        reply=False
    target='Google’s reply service' if reply else 'the Google Docs web-app service'
    if isinstance(exc,httpx.DecodingError):
        return 'The response from '+target+' could not be decoded. Check the application response handling and relay reply format. [relay_decoding]'
    if isinstance(exc,httpx.ProxyError):
        return 'The hosting network proxy could not connect to '+target+'. Check the proxy settings or access policy for this host. [relay_proxy]'
    if any(isinstance(c,ssl.SSLCertVerificationError) for c in causes) or 'certificate_verify_failed' in descriptions or 'certificate verify failed' in descriptions:
        return 'The application could not verify the TLS certificate from '+target+'. Check the hosting certificate trust and any HTTPS proxy; keep certificate verification enabled. [relay_tls_certificate]'
    if any(isinstance(c,ssl.SSLError) for c in causes):
        return 'The TLS connection to '+target+' failed. Check the hosting HTTPS/proxy configuration. [relay_tls]'
    if any(isinstance(c,socket.gaierror) for c in causes) or any(t in descriptions for t in ('name or service not known','temporary failure in name resolution','nodename nor servname','getaddrinfo failed')):
        return 'The hosting DNS service could not resolve '+target+'. Check DNS and outbound network access on the host. [relay_dns]'
    numbers={getattr(c,'errno',None) for c in causes}
    if numbers & {errno.ENETUNREACH,errno.EHOSTUNREACH}:
        return 'The hosting network has no route to '+target+'. Check outbound HTTPS access and proxy configuration. [relay_network_route]'
    if errno.ECONNREFUSED in numbers:
        return 'The network connection to '+target+' was refused. Check the hosting proxy and outbound HTTPS access. [relay_connection_refused]'
    if numbers & {errno.ECONNRESET,errno.EPIPE}:
        return 'The network connection to '+target+' was reset. Check hosting/proxy logs before retrying. [relay_connection_reset]'
    if isinstance(exc,httpx.RemoteProtocolError):
        return target+' closed or returned an invalid network response. Check hosting/proxy logs. [relay_remote_protocol]'
    if isinstance(exc,httpx.LocalProtocolError):
        return 'The application could not send a valid network request. Check the configured Docs relay address and hosting/proxy settings. [relay_local_protocol]'
    if isinstance(exc,httpx.ConnectError):
        return 'The application could not establish a connection to '+target+'. Check hosting/proxy logs for the connection failure. [relay_connect]'
    if isinstance(exc,httpx.ReadError):
        return 'The connection to '+target+' failed while reading its response. Check hosting/proxy logs. [relay_read]'
    if isinstance(exc,httpx.WriteError):
        return 'The connection to '+target+' failed while sending the request. Check hosting/proxy logs. [relay_write]'
    return 'The application’s network request to '+target+' failed. Check hosting network access and the relay address. [relay_unreachable]'


def sync_failure(exc, phase):
    """Describe only known causes; credentials, URLs and provider bodies stay private."""
    if isinstance(exc, Unconfigured):
        return 'The application Docs relay URL or secret is missing. Check CSS_DOCS_RELAY_URL and CSS_DOCS_RELAY_SECRET in the hosting settings. [relay_not_configured]'
    if isinstance(exc, WorkspaceError):
        messages={
            'invalid_endpoint':'The application Docs relay URL must be the existing Apps Script web-app address ending in /exec.',
            'unauthorized':'The deployed Docs relay rejected the signature. Check that the application Docs relay secret matches SHARED_SECRET in that project, and check the clocks.',
            'unknown_action':'The application reached a relay that does not recognize intake. Update Code.gs and documents_relay.gs in the Docs project and deploy a new version of the existing web app.',
            'not_configured':'The intake folder in the application does not match DOCUMENTS_INTAKE_FOLDER_ID in the deployed Docs project, or that property is missing.',
            'bad_folder':'The deployed Docs relay could not use the intake folder. Check its ID, folder type and access for the web-app execution account.',
            'unexpected_redirect':'Google returned an unexpected redirect. Check that the existing Docs web app executes as the office account and allows access without an interactive sign-in.',
            'no_json':'The Docs relay returned a page instead of a confirmed reply. Check the web-app URL, access settings and deployment version.',
            'receipt_mismatch':'The reply does not identify this intake request. Check that the application uses the updated Docs web-app deployment, rather than the mail relay or an older deployment.',
            'response_too_large':'The Docs relay returned too much metadata. Check the deployed listing operation and page size.',
            'bad_request':'The deployed Docs relay rejected the intake request format. Check that both Docs script files are the matching updated versions.',
            'unconfirmed':'The deployed Docs script could not complete the listing. Check its web-app execution permissions and execution log; an editor test alone does not verify the deployed version.',
            'busy':'The Docs relay is busy. Retry the Drive check shortly.',
            'timeout':'The Docs relay did not confirm the result in time. Check its execution log and operation status before retrying.'}
        if exc.code in messages:
            return messages[exc.code]+' ['+exc.code+']'
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return 'The Docs relay timed out. Check its execution log, then retry the Drive check. [relay_timeout]'
    if isinstance(exc, httpx.HTTPStatusError):
        code=exc.response.status_code
        return 'The Docs relay returned HTTP '+str(code)+'. Check the deployed web-app URL and access settings. [relay_http]'
    if isinstance(exc, httpx.RequestError):
        return relay_network_failure(exc)
    if isinstance(exc, p.Denied):
        return 'The account saved in intake settings no longer has active records authority. Have an authorized records/workflow administrator save the intake settings again. [sync_account]'
    messages={
        'settings':'Check that Documents and Drive intake are enabled and that both folder IDs are saved.',
        'account':'The saved sync account could not be validated. Have an authorized records/workflow administrator save the intake settings again.',
        'relay':'The relay request did not complete. Check the updated Docs deployment and its execution log.',
        'listing':'The relay reply could not be saved as an intake listing. Check matching script/application versions and refresh Drive.',
        'filing':'The listing was saved, but the filing worker could not start. Check the saved records account and intake settings.'}
    return messages.get(phase,'Drive check failed. Queued reviews are retained.')+' ['+phase+']'


def sync(conn, adapter=None):
    import documents_sync
    return documents_sync.sync(conn,adapter)


async def worker(get_conn):
    import documents_sync
    await documents_sync.worker(get_conn)
