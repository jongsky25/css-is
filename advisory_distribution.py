"""Frozen advisory issuance using Documents jobs/dispatch records and existing mail."""
import json
import re
import uuid

import advisory
import advisory_workflow as aw
import advisory_review as review
import documents as d
import documents_jobs as jobs
import documents_permissions as p
from documents_storage import rows, transaction, event
import storage as st
import tzutil as tz
import work

ACTIONS={'issue','retry_delivery','delivery_no_effect','delivery_accepted','publish','unpublish','revise_issued','cancel_issued','grant_release','revoke_release'}


def can_issue(conn,user,record):
    user=p.actor(conn,user)
    return user['id']==record['initiator_id'] or (p.has_role(conn,user,'records',record['unit_id']) and bool(conn.execute(
        "SELECT 1 FROM document_access WHERE document_id=? AND user_id=? AND source='advisory_release'",(record['document_id'],user['id'])).fetchone()))


def latest(conn,aid):
    found=rows(conn,'SELECT * FROM advisory_issue WHERE advisory_id=? ORDER BY id DESC LIMIT 1',(aid,))
    return found[0] if found else None


def live(conn,issue):
    return not conn.execute("SELECT 1 FROM advisory_issue_action WHERE issue_id=? AND action IN ('cancelled','superseded')",(issue['id'],)).fetchone()


def recipients(conn,record):
    roster=[];missing=[];addresses=set(record['payload']['external'])
    if record['payload']['audience'] in ('internal','both'):
        for person in rows(conn,'''SELECT a.id,a.username,r.email FROM admin_user a LEFT JOIN resource_person r ON r.id=a.rp_id
            WHERE a.active=1 AND (a.rp_id IS NULL OR (r.is_internal=1 AND r.archived_at IS NULL)) ORDER BY a.id'''):
            address=(person['email'] or person['username'] or '').strip().casefold()
            valid=bool(len(address)<=254 and re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',address))
            roster.append({'id':person['id'],'address':address if valid else None})
            if valid:addresses.add(address)
            else:missing.append({'id':person['id'],'name':person['username']})
    return sorted(addresses),missing,roster


def preview(conn,user,aid):
    record=aw.get_visible(conn,user,aid);d.require(can_issue(conn,user,record))
    doc=d.raw(conn,record['document_id']);packet=review.require_current(conn,doc)
    if doc['status']!='approved' or doc['approved_version']!=packet['version_id']:
        raise ValueError('Director approval of the current revision is required before issuance.')
    approved=conn.execute('''SELECT 1 FROM advisory_decision a JOIN document_review r ON r.id=a.review_id
        WHERE a.packet_id=? AND a.stage='director' AND r.decision='approved' AND r.version_id=?''',(packet['id'],packet['version_id'])).fetchone()
    if not approved:raise d.Conflict('Director approval is missing for this exact packet.')
    if conn.execute('SELECT 1 FROM advisory_issue WHERE advisory_id=? AND revision_id=?',(aid,record['current_revision'])).fetchone():
        raise ValueError('This revision was already issued. Save a changed revision before issuing a replacement.')
    addresses,missing,roster=recipients(conn,record)
    pdf=aw.artifact(conn,user,aid,record['current_revision'],'pdf')
    snapshot={'revision':record['revision'],'revision_id':record['current_revision'],'packet':packet['id'],
              'addresses':addresses,'missing':missing,'roster':roster,'pdf_hash':aw.digest(pdf)}
    return {'record':record,'packet':packet,'recipients':addresses,'missing':missing,'roster':roster,
            'pdf_hash':snapshot['pdf_hash'],'confirmation':aw.digest(aw.encoded(snapshot))}


def _queue(conn,user,record,issue,recipient):
    operation=str(uuid.uuid4())
    payload={'advisory_issue_id':issue['id'],'recipients':[recipient],'channel':'direct_email',
             'fingerprint':issue['pdf_hash'],'sender':'configured Office Connect mail transport'}
    conn.execute('INSERT INTO document_job(id,document_id,actor_id,kind,version_id,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
        (operation,record['document_id'],user['id'],'dispatch',issue['version_id'],aw.encoded(payload),tz.now_iso(),tz.now_iso()))
    conn.execute('INSERT INTO advisory_delivery VALUES (?,?,?)',(operation,issue['id'],recipient))
    return operation


def issue_action(conn,user,issue,action,reason):
    conn.execute('INSERT INTO advisory_issue_action(issue_id,actor_id,action,reason,created_at) VALUES (?,?,?,?,?)',
                 (issue['id'],user['id'],action,reason,tz.now_iso()))


def _stop(conn,user,issue,action,reason):
    if conn.execute("SELECT 1 FROM document_job j JOIN advisory_delivery a ON a.job_id=j.id WHERE a.issue_id=? AND j.state IN ('running','unknown')",(issue['id'],)).fetchone():
        raise d.Conflict('Confirm uncertain or running delivery outcomes before cancelling or superseding this issue.')
    conn.execute("UPDATE document_job SET state='cancelled',recovery_blocked=1 WHERE state='pending' AND id IN (SELECT job_id FROM advisory_delivery WHERE issue_id=?)",(issue['id'],))
    issue_action(conn,user,issue,action,reason)


def mutate_in_transaction(conn,user,record,doc,action,data,reason):
    """Called by the shared advisory idempotent action transaction."""
    d.require(can_issue(conn,user,record))
    if action in ('grant_release','revoke_release'):
        d.require(user['id']==record['initiator_id'])
        target=st.get_admin_user_by_id(conn,int(data.get('target_id') or 0))
        if not target:raise ValueError('Choose an existing staff account.')
        if action=='grant_release':
            target=p.actor(conn,target)
            d.require(p.has_role(conn,target,'records',record['unit_id']),'Choose an account with an existing scoped Records officer grant.')
            conn.execute("INSERT OR IGNORE INTO document_access VALUES (?,?,'advisory_release')",(doc['id'],target['id']))
        else:conn.execute("DELETE FROM document_access WHERE document_id=? AND user_id=? AND source='advisory_release'",(doc['id'],target['id']))
        return review._finish(conn,user,doc,action,reason,{},record,target_id=target['id'])[1]
    if action=='issue':
        planned=preview(conn,user,record['id'])
        if data.get('confirmation')!=planned['confirmation']:raise d.Conflict('The version or audience preview changed. Review issuance again.')
        if planned['missing'] and data.get('ack_missing')!='1':raise ValueError('Acknowledge the accounts without a deliverable email address.')
        if not planned['recipients']:raise ValueError('There are no deliverable recipients. Correct the audience before issuing.')
        previous=latest(conn,record['id'])
        if previous and live(conn,previous):_stop(conn,user,previous,'superseded',reason)
        iid=conn.execute('''INSERT INTO advisory_issue(advisory_id,revision_id,packet_id,version_id,actor_id,issued_at,
            audience,recipients_json,missing_json,roster_json,pdf_hash,supersedes_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (record['id'],record['current_revision'],planned['packet']['id'],planned['packet']['version_id'],user['id'],tz.now_iso(),
             record['payload']['audience'],aw.encoded(planned['recipients']),aw.encoded(planned['missing']),aw.encoded(planned['roster']),
             planned['pdf_hash'],previous['id'] if previous else None)).lastrowid
        issued=latest(conn,record['id'])
        for recipient in planned['recipients']:_queue(conn,user,record,issued,recipient)
        # Publication never silently advances to a newly issued revision.
        if previous:conn.execute('UPDATE advisory_publication SET issue_id=NULL,actor_id=?,updated_at=? WHERE advisory_id=?',(user['id'],tz.now_iso(),record['id']))
        issue_action(conn,user,issued,'issued',reason)
        return review._finish(conn,user,doc,'issued',reason,{'status':'issued'},record,issue_id=iid,recipient_count=len(planned['recipients']))[1]
    issued=latest(conn,record['id'])
    if not issued:raise ValueError('Issue an approved advisory first.')
    if action in ('retry_delivery','delivery_no_effect','delivery_accepted'):
        operation=str(data.get('job_id') or '')
        found=rows(conn,'''SELECT j.*,a.recipient,a.issue_id FROM document_job j JOIN advisory_delivery a ON a.job_id=j.id
            JOIN advisory_issue i ON i.id=a.issue_id WHERE j.id=? AND i.advisory_id=?''',(operation,record['id']))
        if not found:raise ValueError('Choose a delivery attempt for this advisory.')
        job=found[0];target=rows(conn,'SELECT * FROM advisory_issue WHERE id=?',(job['issue_id'],))[0]
        if jobs.active(job):raise d.Conflict('This delivery is still running.')
        if action=='retry_delivery':
            if not live(conn,target) or job['state'] not in ('failed','confirmed_no_effect'):raise ValueError('Retry only a confirmed failed delivery of a current issue.')
            newer=conn.execute('SELECT 1 FROM advisory_delivery a JOIN document_job j ON j.id=a.job_id WHERE a.issue_id=? AND a.recipient=? AND j.rowid>(SELECT rowid FROM document_job WHERE id=?)',(target['id'],job['recipient'],operation)).fetchone()
            if newer:raise ValueError('Use the latest attempt for this recipient.')
            _queue(conn,user,record,target,job['recipient'])
        else:
            if job['state'] not in ('unknown','running'):raise ValueError('Only uncertain delivery needs an evidenced outcome.')
            if action=='delivery_accepted':_record_dispatch(conn,user,record,target,job,'accepted',reason)
            conn.execute("UPDATE document_job SET state=?,recovery_blocked=1,lease_owner=NULL,lease_until=NULL,result_json=?,updated_at=? WHERE id=?",
                ('confirmed' if action=='delivery_accepted' else 'confirmed_no_effect',aw.encoded({'evidence':reason}),tz.now_iso(),operation))
        return review._finish(conn,user,doc,action,reason,{},record,job_id=operation,issue_id=target['id'])[1]
    if not live(conn,issued):raise ValueError('This issue has been cancelled or superseded.')
    if action in ('publish','unpublish'):
        if action=='publish' and issued['audience']=='internal':raise ValueError('Internal-only advisories cannot be published publicly.')
        if data.get('issue_id')!=str(issued['id']):raise d.Conflict('Confirm the exact issued version before changing publication.')
        conn.execute('''INSERT INTO advisory_publication VALUES (?,?,?,?) ON CONFLICT(advisory_id) DO UPDATE
            SET issue_id=excluded.issue_id,actor_id=excluded.actor_id,updated_at=excluded.updated_at''',
            (record['id'],issued['id'] if action=='publish' else None,user['id'],tz.now_iso()))
        issue_action(conn,user,issued,action,reason)
        return review._finish(conn,user,doc,action,reason,{},record,issue_id=issued['id'])[1]
    if action=='revise_issued':
        d.require(user['id']==record['initiator_id'])
        if doc['status']!='issued':raise ValueError('There is already a replacement draft in progress.')
        return review._finish(conn,user,doc,'replacement_started',reason,{'status':'draft','approved_version':None,'signed_version':None,'reviewer_id':None},record,issue_id=issued['id'])[1]
    if action=='cancel_issued':
        _stop(conn,user,issued,'cancelled',reason)
        conn.execute('''INSERT INTO advisory_publication VALUES (?,NULL,?,?) ON CONFLICT(advisory_id)
            DO UPDATE SET issue_id=NULL,actor_id=excluded.actor_id,updated_at=excluded.updated_at''',(record['id'],user['id'],tz.now_iso()))
        return review._finish(conn,user,doc,'issue_cancelled',reason,{'status':'cancelled','approved_version':None},record,issue_id=issued['id'])[1]
    raise ValueError('Choose an issuance action.')


def _record_dispatch(conn,user,record,issue,job,outcome,evidence):
    did=conn.execute('''INSERT INTO document_dispatch(document_id,version_id,operation_id,actor_id,channel,sender,evidence,created_at)
        VALUES (?,?,?,?,?,?,?,?)''',(record['document_id'],issue['version_id'],job['id'],user['id'],'direct_email',
        'configured Office Connect mail transport',evidence,tz.now_iso())).lastrowid
    conn.execute('INSERT INTO document_dispatch_recipient(dispatch_id,recipient,outcome,evidence) VALUES (?,?,?,?)',(did,job['recipient'],outcome,evidence))
    event(conn,record['document_id'],user,'advisory_delivery_recorded',{'issue_id':issue['id'],'dispatch_id':did,'job_id':job['id'],'outcome':outcome})


def execute(conn,operation,*,token,reconcile=False):
    """One recipient per durable claim; no transport retry after uncertain execution."""
    import mailer
    with transaction(conn):
        job=jobs.owned(conn,operation,token)
        delivery=rows(conn,'SELECT * FROM advisory_delivery WHERE job_id=?',(operation,))[0]
        issue=rows(conn,'SELECT * FROM advisory_issue WHERE id=?',(delivery['issue_id'],))[0]
        record=aw.for_document(conn,job['document_id']);user=p.actor(conn,{'id':job['actor_id']})
        if reconcile:
            jobs.failed(conn,operation,token,'unknown',blocked=True,note='Check the mail service and record accepted or confirmed no effect. Do not resend an uncertain delivery.')
            return {'state':'unknown'}
        if not live(conn,issue):
            jobs.failed(conn,operation,token,'failed',blocked=True,note='This issue is cancelled or superseded.');return {'state':'failed'}
        d.get(conn,user,job['document_id']);d.require(can_issue(conn,user,record));work.writable(conn)
        if st.get_setting(conn,'documents.sending_enabled','0')!='1' or not st.email_feature_enabled(conn,'document_dispatch'):
            raise ValueError('Document sending is disabled.')
        if not mailer.email_configured():
            jobs.failed(conn,operation,token,'failed',blocked=True,note='Email transport is not configured.');return {'state':'failed'}
        pdf=aw.artifact(conn,user,record['id'],issue['revision_id'],'pdf')
        if aw.digest(pdf)!=issue['pdf_hash'] or job['version_id']!=issue['version_id']:raise d.Conflict('The issued PDF is unavailable.')
        job.update(delivery)
        conn.execute("UPDATE document_job SET state='running',updated_at=? WHERE id=?",(tz.now_iso(),operation))
    try:
        from send_reminders import _send
        result=_send(conn,'document_dispatch',delivery['recipient'],'Advisory '+record['number'],
            'Please see the attached official advisory '+record['number']+'. Issued '+issue['issued_at']+'.',
            attachments=[(advisory.filename(record['number'],'pdf'),'application/pdf',pdf)])
        if not result.get('sent'):raise ValueError('Unconfirmed delivery')
        with transaction(conn):
            jobs.owned(conn,operation,token)
            _record_dispatch(conn,user,record,issue,job,'accepted','Mail transport accepted this recipient and the issued PDF.')
            jobs.completed(conn,operation,token)
        return {'state':'confirmed'}
    except Exception:
        with transaction(conn):jobs.failed(conn,operation,token,'unknown',blocked=True,note='Mail outcome is uncertain. Check the service before recording an outcome; do not resend.')
        return {'state':'unknown'}


def public_artifact(conn,event_id,fmt):
    record=aw.for_event(conn,event_id)
    publication=conn.execute('SELECT issue_id FROM advisory_publication WHERE advisory_id=?',(record['id'],)).fetchone()
    if publication is None:return aw.existing_public(conn,event_id,fmt)
    if not publication[0]:raise ValueError('This advisory is not published.')
    issue=rows(conn,'SELECT * FROM advisory_issue WHERE id=?',(publication[0],))[0]
    if not live(conn,issue) or issue['audience']=='internal':raise ValueError('This advisory is not published.')
    artifact=rows(conn,'SELECT * FROM advisory_artifact WHERE revision_id=? AND format=?',(issue['revision_id'],fmt))
    if not artifact or aw.digest(artifact[0]['data'])!=artifact[0]['sha256']:raise ValueError('This advisory is unavailable.')
    return artifact[0]['data']


def screen(conn,user,record):
    allowed=can_issue(conn,user,record);issues=rows(conn,'SELECT * FROM advisory_issue WHERE advisory_id=? ORDER BY id DESC',(record['id'],))
    for issued in issues:
        issued['live']=live(conn,issued);issued['missing']=json.loads(issued['missing_json']) if allowed else []
        issued['deliveries']=rows(conn,'''SELECT a.job_id,a.recipient,j.state,j.recovery_note,j.lease_until,
            NOT EXISTS(SELECT 1 FROM advisory_delivery newer JOIN document_job n ON n.id=newer.job_id
              WHERE newer.issue_id=a.issue_id AND newer.recipient=a.recipient AND n.rowid>j.rowid) AS latest
            FROM advisory_delivery a JOIN document_job j ON j.id=a.job_id WHERE a.issue_id=? ORDER BY j.rowid DESC''',(issued['id'],)) if allowed else []
    publication=conn.execute('SELECT issue_id FROM advisory_publication WHERE advisory_id=?',(record['id'],)).fetchone()
    releasers=rows(conn,"SELECT u.id,u.username FROM document_access a JOIN admin_user u ON u.id=a.user_id WHERE a.document_id=? AND a.source='advisory_release'",(record['document_id'],))
    can_assign=user['id']==record['initiator_id']
    choices=[person for person in rows(conn,'SELECT id,username FROM admin_user WHERE active=1 ORDER BY username') if can_assign and p.has_role(conn,person,'records',record['unit_id'])]
    choices += [person for person in releasers if person['id'] not in {candidate['id'] for candidate in choices}]
    return {'can_assign':can_assign,'release_choices':choices,'allowed':allowed,'issues':issues,'publication':publication[0] if publication else None,'releasers':releasers}


def issued_for_user(conn,user,before=0):
    user=p.actor(conn,user);scope=p.RegistryScope(conn,user)
    return rows(conn,f'''SELECT i.id,i.issued_at,i.revision_id,a.number,json_extract(v.payload_json,'$.content.headline') AS subject FROM advisory_issue i
        JOIN advisory_record a ON a.id=i.advisory_id JOIN document d ON d.id=a.document_id
        JOIN advisory_revision v ON v.id=i.revision_id
        WHERE ({scope.view_sql('d')} OR EXISTS(SELECT 1 FROM json_each(i.roster_json) r WHERE json_extract(r.value,'$.id')=:registry_actor))
        AND NOT EXISTS(SELECT 1 FROM advisory_issue_action x WHERE x.issue_id=i.id AND x.action IN ('cancelled','superseded'))
        AND (:before=0 OR i.id<:before) ORDER BY i.id DESC LIMIT 31''',{**scope.params,'before':max(0,before)})


def issued_artifact(conn,user,iid,fmt):
    user=p.actor(conn,user)
    found=rows(conn,'SELECT * FROM advisory_issue WHERE id=?',(iid,))
    if not found or fmt not in ('pdf','png'):raise p.Denied('Issued advisory unavailable.')
    issue=found[0];record=aw.for_document(conn,conn.execute('SELECT document_id FROM advisory_record WHERE id=?',(issue['advisory_id'],)).fetchone()[0])
    permitted=p.can_view(conn,user,d.raw(conn,record['document_id']))
    if not permitted and (not live(conn,issue) or not any(r['id']==user['id'] for r in json.loads(issue['roster_json']))):
        raise p.Denied('Issued advisory unavailable.')
    artifact=rows(conn,'SELECT * FROM advisory_artifact WHERE revision_id=? AND format=?',(issue['revision_id'],fmt))[0]
    if aw.digest(artifact['data'])!=artifact['sha256']:raise ValueError('Issued file unavailable.')
    return artifact['data']
