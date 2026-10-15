"""Drive/extraction/signing/dispatch boundary with durable, reconcilable operations.

The optional signed relay implements the contract in DOCUMENT_MANAGEMENT_SETUP.md.
It receives metadata only; binary documents and transient OCR remain in Drive/relay.
A successful transport is never itself evidence of a signed or dispatched document.
"""
import hashlib
import base64
import json
import re
import uuid
from urllib.parse import urlparse
import storage as st
import tzutil as tz
import documents as d
import documents_permissions as p
from documents_storage import rows, transaction, event


from documents_workspace import WorkspaceRelay, Unconfigured


def validate_drive_url(value):
    url=urlparse(str(value).strip())
    if url.scheme!='https' or url.hostname not in ('drive.google.com','docs.google.com') or url.username or url.password or url.port not in (None,443):
        raise ValueError('Use an HTTPS Google Drive, Docs, Sheets or Slides file link.')
    match=re.search(r'/d/([A-Za-z0-9_-]{10,200})(?:/|$)',url.path)
    if not match and url.path=='/open':
        from urllib.parse import parse_qs
        fid=parse_qs(url.query).get('id',[''])[0]
    else:
        fid=match.group(1) if match else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',fid):
        raise ValueError('The Drive link does not identify a supported file.')
    return f'https://drive.google.com/file/d/{fid}/view',fid


# Alias retained for callers; transport uses the already-configured Workspace relays.
Relay = WorkspaceRelay


def get_adapter():
    return WorkspaceRelay()


def version(conn,doc):
    found=rows(conn,'SELECT * FROM document_file_version WHERE id=? AND document_id=?',(doc['current_version'],doc['id']))
    if not found or not found[0]['fingerprint']:
        raise ValueError('A confirmed exact Drive version is required.')
    return found[0]


def metadata(url,actor,adapter=None):
    url,fid=validate_drive_url(url)
    result=(adapter or get_adapter()).call('inspect',{'file_id':fid,'actor_id':actor['id'],'max_bytes':20*1024*1024},str(uuid.uuid4()))
    if result.get('file_id')!=fid or not result.get('fingerprint') or result.get('accessible') is not True:
        raise ValueError('Drive access or exact version could not be confirmed for the adapter identity.')
    if not isinstance(result.get('size'),int) or not 0<=result['size']<=20*1024*1024:
        raise ValueError('Drive file size is unknown or exceeds 20 MiB.')
    return {'url':url,'file_id':fid,'fingerprint':str(result['fingerprint'])[:500]}


def attach(conn,user,doc_id,revision,url,classification,note,adapter=None):
    # External I/O precedes the writer transaction; revision checked again afterward.
    user=p.actor(conn,user); doc=d.get(conn,user,doc_id); d.writable(conn)
    d.require(p.can_work(conn,user,doc)); d.reason(note)
    meta=metadata(url,user,adapter)
    with transaction(conn):
        user,doc=d.check(conn,user,doc_id,revision)
        d.require(p.can_work(conn,user,doc))
        if doc['status'] in ('closed','cancelled','released','awaiting_acknowledgment'):
            raise ValueError('Create a linked follow-up for a released or closed document.')
        if classification not in ('material','minor'):
            raise ValueError('Classify the revision as material or minor.')
        if classification=='minor':
            d.require(p.officer(conn,user,doc),'Only a concerned officer may classify an approval-preserving edit.')
            if not doc['approved_version']:
                raise ValueError('There is no approval lineage to preserve.')
        vid=conn.execute('INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,parent_id,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?)',
                         (doc_id,meta['url'],meta['file_id'],meta['fingerprint'],'draft',doc['current_version'],user['id'],tz.now_iso())).lastrowid
        changes={'current_version':vid,'signed_version':None,'approved_version':vid if classification=='minor' else None}
        if doc['direction']=='OUT':
            changes['status']='approved' if classification=='minor' else 'draft'
        return d.finish(conn,user,doc,'version_added',{'classification':classification,'reason':note,'previous':doc['current_version'],'version':vid},changes)


def release_gate(conn,user,doc,data):
    d.require(p.can_release(conn,user,doc))
    if doc['direction']!='OUT' or doc['status'] not in ('approved','ready_to_release') or doc['verification']!='verified' or doc['reconcile']:
        raise ValueError('A verified, authorized outgoing document is required.')
    v=version(conn,doc)
    if doc['approved_version']!=v['id']:
        raise ValueError('The current version has not been approved.')
    policy=json.loads(doc['policy_json'])
    if 'signature_required' not in policy or 'release' not in policy or 'ack_required' not in policy:
        raise ValueError('Configure signature, acknowledgment and release evidence requirements for this type.')
    if policy['signature_required'] and doc['signed_version']!=v['id']:
        raise ValueError('The approved version must be signed before release.')
    evidence=data.get('checklist',{})
    if not isinstance(evidence,dict) or any(not str(evidence.get(k,'')).strip() for k in policy['release']):
        raise ValueError('Complete all release checklist evidence.')
    recipients=data.get('recipients',[])
    if not isinstance(recipients,list) or not 1<=len(recipients)<=100 or any(not isinstance(r,str) or not r.strip() or len(r)>254 for r in recipients):
        raise ValueError('Provide between 1 and 100 recipients.')
    recipients=[r.strip().casefold() if data.get('channel') in ('email','direct_email') else r.strip() for r in recipients]
    data['recipients']=recipients
    if len(set(recipients))!=len(recipients):
        raise ValueError('Remove repeated recipients.')
    if data.get('channel') in ('email','direct_email') and any(not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',r) for r in recipients):
        raise ValueError('Provide valid recipient email addresses.')
    for recipient in recipients:
        if conn.execute('''SELECT 1 FROM document_dispatch_recipient r JOIN document_dispatch x ON x.id=r.dispatch_id
            WHERE x.document_id=? AND x.version_id=? AND r.recipient=? AND r.outcome IN ('accepted','unknown')''',
            (doc['id'],v['id'],recipient)).fetchone():
            raise ValueError('A recipient already has an accepted or uncertain dispatch of this version. Select only confirmed failed recipients.')
    return v


def queue(conn,user,doc_id,revision,kind,data):
    with transaction(conn):
        user,doc=d.check(conn,user,doc_id,revision)
        d.require(p.can_work(conn,user,doc))
        if kind not in ('extract','sign','dispatch'):
            raise ValueError('Unknown operation.')
        if doc['status'] in ('closed','cancelled'):
            raise ValueError('Reopen the record before requesting an operation.')
        if conn.execute("SELECT 1 FROM document_job WHERE document_id=? AND kind=? AND state IN ('pending','running','unknown')",(doc_id,kind)).fetchone():
            raise d.Conflict('An operation is already pending or needs reconciliation.')
        payload={}
        vid=doc['current_version']
        if kind=='extract':
            url,fid=validate_drive_url(data['url'])
            payload={'url':url,'file_id':fid,'max_bytes':20*1024*1024,'transient':True}
        elif kind=='sign':
            d.require(p.has_role(conn,user,'signatory',doc['unit_id']))
            if doc['status']!='approved' or doc['approved_version']!=doc['current_version'] or doc['reconcile']:
                raise ValueError('Approve the exact final version before signing.')
            v=version(conn,doc)
            if data.get('confirmed_fingerprint')!=v['fingerprint']:
                raise ValueError('Preview and explicitly confirm the final fingerprint.')
            signature=st.user_signature(conn,user['id'])
            if not signature or signature[1] not in ('image/png','image/jpeg') or len(signature[0])>512*1024:
                raise ValueError('Save your PNG or JPEG signature (up to 512 KiB) in My profile before signing.')
            payload={'file_id':v['file_id'],'fingerprint':v['fingerprint'],'signatory_id':user['id'],
                     'signature_hash':hashlib.sha256(signature[0]).hexdigest()}
        else:
            v=release_gate(conn,user,doc,data)
            payload={**data,'file_id':v['file_id'],'fingerprint':v['fingerprint'],'channel':'direct_email',
                     'subject':doc['number']+' — '+doc['subject'],
                     'message':str(data.get('message') or 'Please see the attached official correspondence.')[:4000]}
            sender=st.get_setting(conn,'documents.official_sender','')
            if not sender:
                raise Unconfigured('The official sender mailbox has not been configured.')
            payload['sender']=sender
        operation=str(uuid.uuid4())
        conn.execute('INSERT INTO document_job(id,document_id,actor_id,kind,version_id,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                     (operation,doc_id,user['id'],kind,vid,json.dumps(payload),tz.now_iso(),tz.now_iso()))
        d.finish(conn,user,doc,kind+'_queued',{'operation_id':operation})
        return operation


def persist_signature(conn,user,doc,meta,method,evidence,operation):
    previous=version(conn,doc)
    vid=conn.execute('INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,parent_id,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (doc['id'],meta['url'],meta['file_id'],meta['fingerprint'],'signed',previous['id'],user['id'],tz.now_iso())).lastrowid
    conn.execute('INSERT INTO document_signature(document_id,version_id,signatory_id,method,operation_id,evidence,created_at) VALUES (?,?,?,?,?,?,?)',
                 (doc['id'],vid,user['id'],method,operation,evidence,tz.now_iso()))
    return d.finish(conn,user,doc,'signed',{'method':method,'operation_id':operation,'source_version':previous['id'],'signed_version':vid},
                    {'current_version':vid,'approved_version':vid,'signed_version':vid,'status':'ready_to_release'})


def external_signature(conn,user,doc_id,revision,url,source_fingerprint,evidence,adapter=None):
    user=p.actor(conn,user); doc=d.get(conn,user,doc_id); d.writable(conn)
    d.require(p.has_role(conn,user,'signatory',doc['unit_id']))
    meta=metadata(url,user,adapter); d.reason(evidence)
    with transaction(conn):
        user,doc=d.check(conn,user,doc_id,revision)
        d.require(p.has_role(conn,user,'signatory',doc['unit_id']))
        if doc['status']!='approved' or doc['reconcile'] or doc['approved_version']!=doc['current_version'] or version(conn,doc)['fingerprint']!=source_fingerprint:
            raise ValueError('The reviewed source changed. Review and sign the current version.')
        return persist_signature(conn,user,doc,meta,'external',evidence,str(uuid.uuid4()))


def persist_dispatch(conn,user,doc,payload,operation,outcomes,evidence):
    did=conn.execute('INSERT INTO document_dispatch(document_id,version_id,operation_id,actor_id,channel,sender,evidence,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (doc['id'],doc['current_version'],operation,user['id'],payload['channel'],payload['sender'],evidence,tz.now_iso())).lastrowid
    for recipient in payload['recipients']:
        outcome=outcomes.get(recipient,{})
        conn.execute('INSERT INTO document_dispatch_recipient(dispatch_id,recipient,outcome,evidence) VALUES (?,?,?,?)',
                     (did,recipient,outcome.get('outcome','unknown'),str(outcome.get('evidence',''))[:4000]))
    complete=all(outcomes.get(r,{}).get('outcome')=='accepted' for r in payload['recipients'])
    status=('awaiting_acknowledgment' if json.loads(doc['policy_json']).get('ack_required') else 'released') if complete else 'ready_to_release'
    return d.finish(conn,user,doc,'dispatch_recorded',{'dispatch_id':did,'operation_id':operation,'complete':complete},{'status':status})


def record_dispatch(conn,user,doc_id,revision,data,adapter=None):
    user=p.actor(conn,user); doc=d.get(conn,user,doc_id); d.writable(conn)
    v=release_gate(conn,user,doc,data)
    current=metadata(v['url'],user,adapter)
    if current['fingerprint']!=v['fingerprint']:
        raise ValueError('The final Drive artifact changed. Attach and review the new version.')
    with transaction(conn):
        user,doc=d.check(conn,user,doc_id,revision)
        release_gate(conn,user,doc,data)
        if data.get('channel') not in ('email','physical','other'):
            raise ValueError('Choose existing email, physical, or other dispatch.')
        d.reason(data.get('sender')); evidence=d.reason(data.get('evidence'))
        # Operation ID is client-held for duplicate submission protection.
        operation=str(uuid.UUID(data['operation_id']))
        outcomes={r:{'outcome':'accepted','evidence':evidence} for r in data['recipients']}
        return persist_dispatch(conn,user,doc,data,operation,outcomes,evidence)


def execute(conn,operation,adapter=None,*,reconcile=False):
    adapter=adapter or get_adapter()
    transient={}
    with transaction(conn):
        d.writable(conn)
        job=rows(conn,'SELECT * FROM document_job WHERE id=?',(operation,))
        allowed=('running','unknown') if reconcile else ('pending',)
        if not job or job[0]['state'] not in allowed:
            raise d.Conflict('Operation is not pending; reconcile unknown outcomes before retrying.')
        job=job[0]; user=p.actor(conn,{'id':job['actor_id']}); doc=d.get(conn,user,job['document_id'])
        payload=json.loads(job['payload_json']); v=None
        if job['kind']=='dispatch':
            if st.get_setting(conn,'documents.sending_enabled','0')!='1':
                raise ValueError('Document sending is disabled.')
            v=release_gate(conn,user,doc,payload)
        elif job['kind']=='sign':
            d.require(p.has_role(conn,user,'signatory',doc['unit_id']))
            v=version(conn,doc)
            if doc['status']!='approved' or doc['approved_version']!=v['id'] or doc['reconcile']:
                raise ValueError('Signing approval is no longer current.')
            if not reconcile:
                signature=st.user_signature(conn,user['id'])
                if not signature or hashlib.sha256(signature[0]).hexdigest()!=payload.get('signature_hash'):
                    raise ValueError('Your stored signature changed. Cancel the unexecuted request and confirm again.')
                transient={'signature_base64':base64.b64encode(signature[0]).decode('ascii'),'signature_mime':signature[1]}
        else:
            d.require(p.can_work(conn,user,doc))
        if v and job['version_id']!=v['id']:
            raise d.Conflict('The queued source version is stale.')
        conn.execute("UPDATE document_job SET state='running',updated_at=? WHERE id=?",(tz.now_iso(),operation))
    # Relay must atomically compare fingerprint before sign/send. An inspect call
    # alone has a TOCTOU gap and cannot authorize an external effect.
    try:
        result=adapter.call('status' if reconcile else job['kind'],{**payload,**transient,'kind':job['kind'],'actor_id':user['id']},operation)
        if result.get('state')!='confirmed':
            raise ValueError('The relay did not confirm the effect.')
        if job['kind']=='sign':
            url,fid=validate_drive_url(result['url'])
            if result.get('source_fingerprint')!=payload['fingerprint'] or result.get('signatory_id')!=user['id'] or not result.get('fingerprint'):
                raise ValueError('Signature lineage was not confirmed.')
        if job['kind']=='dispatch':
            outcomes=result.get('recipients',{})
            if set(outcomes)!=set(payload['recipients']) or any(x.get('outcome') not in ('accepted','failed') or not x.get('evidence') for x in outcomes.values()):
                raise ValueError('Recipient-level outcomes were not confirmed.')
            if result.get('fingerprint')!=payload['fingerprint'] or result.get('sender')!=payload['sender']:
                raise ValueError('Released version or sender was not confirmed.')
        if job['kind']=='extract':
            extracted=sanitize_extraction(result)
        with transaction(conn):
            doc=d.raw(conn,job['document_id'])
            if job['kind']!='extract' and doc['current_version']!=job['version_id']:
                raise d.Conflict('Document changed during the external operation; reconcile the result.')
            if job['kind']=='sign':
                persist_signature(conn,user,doc,{'url':url,'file_id':fid,'fingerprint':result['fingerprint']},'stored',str(result.get('evidence','')),operation)
            elif job['kind']=='dispatch':
                persist_dispatch(conn,user,doc,payload,operation,outcomes,str(result.get('evidence','')))
            else:
                # Excerpts are transient: only completion metadata is retained.
                event(conn,doc['id'],user,'extraction_finished',{'operation_id':operation})
            conn.execute("UPDATE document_job SET state='confirmed',result_json=?,updated_at=? WHERE id=?",(json.dumps({'confirmed':True}),tz.now_iso(),operation))
        return extracted if job['kind']=='extract' else {'state':'confirmed'}
    except Exception as exc:
        with transaction(conn):
            conn.execute("UPDATE document_job SET state=?,result_json=?,updated_at=? WHERE id=?",('failed' if job['kind']=='extract' or isinstance(exc,Unconfigured) else 'unknown',json.dumps({'error':'The adapter did not provide a confirmed result. Reconcile before retry.'}),tz.now_iso(),operation))
        raise


def sanitize_extraction(result):
    fields=result.get('suggestions',{})
    allowed={'subject','sender','references','type','due_date','keywords'}
    if not isinstance(fields,dict):
        raise ValueError('Extraction returned invalid suggestions.')
    return {'suggestions':{k:str(v)[:1000] for k,v in fields.items() if k in allowed},
            'excerpts':[str(v)[:1000] for v in result.get('excerpts',[])[:10]],
            'warnings':[str(v)[:500] for v in result.get('warnings',[])[:10]],
            'notice':'Untrusted suggestions only. Check the source and confirm each value before applying.'}


def reconcile(conn,user,operation,outcome,evidence):
    with transaction(conn):
        d.writable(conn); user=p.actor(conn,user)
        job=rows(conn,'SELECT * FROM document_job WHERE id=?',(operation,))
        if not job or job[0]['state'] not in ('running','unknown','failed','pending'):
            raise ValueError('This operation does not need reconciliation.')
        job=job[0]; doc=d.get(conn,user,job['document_id'])
        d.require(p.officer(conn,user,doc) or (job['actor_id']==user['id'] and job['kind']!='dispatch'))
        if outcome=='cancelled' and job['state']!='pending':
            raise ValueError('Only an unexecuted pending request may be cancelled.')
        if outcome not in ('confirmed_no_effect','cancelled'):
            raise ValueError('Confirm no external effect before another attempt. Record a confirmed send/signature separately with evidence.')
        d.reason(evidence)
        conn.execute('UPDATE document_job SET state=?,result_json=?,updated_at=? WHERE id=?',(outcome,json.dumps({'evidence':evidence}),tz.now_iso(),operation))
        d.finish(conn,user,doc,'operation_reconciled',{'operation_id':operation,'outcome':outcome,'evidence':evidence})


def acknowledge(conn,user,doc_id,revision,dispatch_id,recipient,evidence):
    with transaction(conn):
        user,doc=d.check(conn,user,doc_id,revision)
        d.require(p.can_release(conn,user,doc)); d.reason(evidence)
        cur=conn.execute('UPDATE document_dispatch_recipient SET acknowledged_at=?,evidence=evidence || ? WHERE dispatch_id=? AND recipient=? AND outcome=\'accepted\' AND dispatch_id IN (SELECT id FROM document_dispatch WHERE document_id=?)',
                         (tz.now_iso(),'\nAcknowledgment: '+evidence,dispatch_id,recipient,doc_id))
        if not cur.rowcount:
            raise ValueError('Dispatched recipient not found.')
        return d.finish(conn,user,doc,'acknowledgment',{'dispatch_id':dispatch_id,'recipient':recipient,'evidence':evidence})


def signature_preview(conn,user,doc_id,adapter=None):
    """Read-only placement check against the exact approved source."""
    d.writable(conn)
    user=p.actor(conn,user); doc=d.get(conn,user,doc_id)
    d.require(p.has_role(conn,user,'signatory',doc['unit_id']))
    v=version(conn,doc)
    if doc['status']!='approved' or doc['approved_version']!=v['id'] or doc['reconcile']:
        raise ValueError('Approve the current source before previewing a signature.')
    signature=st.user_signature(conn,user['id'])
    if not signature:
        raise ValueError('Save your own signature in My profile first.')
    result=(adapter or get_adapter()).call('preview',{'file_id':v['file_id'],'fingerprint':v['fingerprint'],
                                                    'actor_id':user['id']},str(uuid.uuid4()))
    if result.get('state')!='confirmed' or result.get('fingerprint')!=v['fingerprint']:
        raise ValueError('The source or signature position could not be confirmed.')
    # Use our already-validated source link, not an arbitrary provider URL.
    return {'fingerprint':v['fingerprint'],'url':v['url'],'marker':'{{OFFICE_CONNECT_SIGNATURE}}'}
