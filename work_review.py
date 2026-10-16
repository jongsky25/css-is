"""Consolidation evidence for the existing formal document review workflow."""
import hashlib
import json

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, event
import tzutil as tz
import work
import work_tasks
import work_blockers
import work_decisions
import work_compat


def latest(conn, document_id):
    found=rows(conn,'SELECT * FROM work_review_packet WHERE document_id=? ORDER BY id DESC LIMIT 1',(document_id,))
    return found[0] if found else None


def snapshot(conn,case_id,document_id):
    case=work.raw(conn,case_id)
    sources=[]
    for (linked_id,) in conn.execute('SELECT document_id FROM work_document WHERE case_id=? ORDER BY document_id',(case_id,)):
        doc=work.resolved_document(conn,linked_id)
        if not doc:
            raise ValueError('A linked source is unavailable. Reconcile correspondence before review.')
        keys=('id','subject','type','sender','document_date','due_date','verification','policy_json','canonical_id')
        source={key:doc[key] for key in keys}
        source['lifecycle']=doc['status'] if doc['id']!=document_id and doc['status'] in ('closed','cancelled') else None
        source['linked_id']=linked_id
        source['approved_version']=doc['approved_version'] if doc['id']!=document_id else None
        source['reconcile']=doc['reconcile'] if doc['id']!=document_id else None
        source['current_version']=doc['current_version'] if doc['id']!=document_id else None
        source['directive_id']=conn.execute('SELECT MAX(id) FROM document_directive WHERE document_id=?',(doc['id'],)).fetchone()[0]
        sources.append(source)
    if document_id not in {s['id'] for s in sources}:
        raise ValueError('Link this outgoing document to the work item before requesting review.')
    tasks=rows(conn,'SELECT id,title,status,revision,mandatory,owner_id,submission FROM work_task WHERE case_id=? ORDER BY id',(case_id,))
    import work_handoff
    draft=work_handoff.current(conn,case_id)
    support=rows(conn,'''SELECT id FROM work_support_file f WHERE case_id=? AND NOT EXISTS
        (SELECT 1 FROM work_support_retired r WHERE r.file_id=f.id) ORDER BY id''',(case_id,))
    value={'case_id':case_id,'case_revision':case['revision'],'tasks':tasks,'sources':sources,
           'draft_id':draft['id'] if draft else None,'support_ids':[f['id'] for f in support]}
    raw=json.dumps(value,sort_keys=True)
    return value,hashlib.sha256(raw.encode()).hexdigest()


def version_matches(conn,packet,doc):
    # A signed derivative retains the approved source lineage. New drafts require review.
    vid=doc['current_version'];seen=set()
    while vid and vid not in seen:
        if vid==packet['version_id']: return True
        seen.add(vid)
        found=rows(conn,'SELECT * FROM document_file_version WHERE id=? AND document_id=?',(vid,doc['id']))
        if not found or found[0]['role']!='signed':return False
        vid=found[0]['parent_id']
    return False


def current(conn,packet):
    if conn.execute('SELECT 1 FROM work_review_invalidation WHERE packet_id=?',(packet['id'],)).fetchone():return False
    try:
        return snapshot(conn,packet['case_id'],packet['document_id'])[1]==packet['snapshot_hash'] and version_matches(conn,packet,docs.raw(conn,packet['document_id']))
    except ValueError:return False


def require_current(conn,doc,user=None):
    packet=latest(conn,doc['id'])
    if packet:
        if user is not None:work.get(conn,user,packet['case_id'])
        if not current(conn,packet):
            raise docs.Conflict('The consolidation inputs or exact draft changed. Request a new consolidation review.')
    return packet


def prepare(conn,user,doc,data,reviewer):
    """Called inside document review routing's transaction, after its authority checks."""
    previous=latest(conn,doc['id'])
    if not data.get('work_case_id'):
        if previous:
            raise ValueError('Request renewed review from the work item consolidation screen.')
        return
    work.writable(conn)
    case_id=int(data['work_case_id'])
    work.get(conn,user,case_id);work.get(conn,reviewer,case_id)
    work_compat.require_open(conn,case_id)
    value,digest=snapshot(conn,case_id,doc['id'])
    if previous and previous['case_id']!=case_id:
        raise ValueError('Keep this document with its original consolidation work item.')
    if digest!=data.get('work_snapshot') or int(data.get('version_id') or 0)!=doc['current_version']:
        raise docs.Conflict('The consolidation inputs or exact draft changed. Reload before requesting review.')
    import documents_operations as ops
    ops.version(conn,doc)
    if any(work_decisions.pending(conn,t['id']) for t in value['tasks']):
        raise ValueError('Reconcile changed work decisions before requesting formal review.')
    pid=conn.execute('''INSERT INTO work_review_packet(case_id,document_id,version_id,reviewer_id,actor_id,
        snapshot_json,snapshot_hash,reason,created_at) VALUES (?,?,?,?,?,?,?,?,?)''',
        (case_id,doc['id'],doc['current_version'],reviewer['id'],user['id'],json.dumps(value,sort_keys=True),digest,docs.reason(data.get('reason')),tz.now_iso())).lastrowid
    for source_id in {s[k] for s in value['sources'] for k in ('id','linked_id')}:
        conn.execute('INSERT INTO work_review_source VALUES (?,?)',(pid,source_id))


def invalidate(conn,user,case_id=None,document_id=None):
    """Atomically retire stale approvals, including downstream consolidation chains."""
    queue=[(case_id,document_id)];seen=set()
    while queue:
        cid,did=queue.pop()
        candidates=rows(conn,'''SELECT p.* FROM work_review_packet p
            WHERE NOT EXISTS(SELECT 1 FROM work_review_packet newer WHERE newer.document_id=p.document_id AND newer.id>p.id)
            AND (p.case_id=? OR p.document_id=? OR EXISTS(SELECT 1 FROM work_review_source s WHERE s.packet_id=p.id AND s.document_id=?))''',(cid,did,did))
        for packet in candidates:
            if packet['id'] in seen:continue
            doc=docs.raw(conn,packet['document_id'])
            if doc['status'] in ('closed','cancelled','released','awaiting_acknowledgment') or current(conn,packet):continue
            if conn.execute('SELECT 1 FROM work_review_invalidation WHERE packet_id=?',(packet['id'],)).fetchone():continue
            if conn.execute("SELECT 1 FROM document_job WHERE document_id=? AND kind IN ('sign','dispatch') AND state IN ('running','unknown')",(doc['id'],)).fetchone():
                raise docs.Conflict('A dependent formal review has an external operation running or uncertain. Reconcile that operation before changing its inputs.')
            seen.add(packet['id'])
            note='Consolidation inputs or the reviewed draft changed; renewed review is required.'
            conn.execute('INSERT INTO work_review_invalidation VALUES (?,?,?,?)',(packet['id'],user['id'],note,tz.now_iso()))
            conn.execute("UPDATE document SET approved_version=NULL,signed_version=NULL,status='changes_requested',revision=revision+1,updated_at=? WHERE id=?",(tz.now_iso(),doc['id']))
            eid=event(conn,doc['id'],user,'consolidation_changed',{'packet_id':packet['id'],'reason':note})
            docs.notify(conn,docs.raw(conn,doc['id']),eid,'consolidation_changed')
            queue.append((None,doc['id']))


def page(conn,user,case_id):
    user=permissions.actor(conn,user);case=work.get(conn,user,case_id)
    tasks=work_tasks.list_for_case(conn,user,case_id)
    for task in tasks:
        task['waiting']=work_blockers.waiting(conn,task)
    outgoing=[]
    for doc in work.linked_documents(conn,user,case_id):
        if doc['direction']!='OUT':continue
        versions=rows(conn,'SELECT * FROM document_file_version WHERE document_id=? AND id=?',(doc['id'],doc['current_version']))
        outgoing.append({'doc':doc,'version':versions[0] if versions else None,
                         'snapshot':snapshot(conn,case_id,doc['id'])[1],
                         'officer':permissions.officer(conn,user,doc),'packet':latest(conn,doc['id'])})
    history=rows(conn,'''SELECT p.*,i.reason AS invalidation FROM work_review_packet p
        LEFT JOIN work_review_invalidation i ON i.packet_id=p.id WHERE p.case_id=? ORDER BY p.id DESC LIMIT 30''',(case_id,))
    for packet in history:
        captured=json.loads(packet['snapshot_json'])
        packet['inputs']=captured['tasks']
        packet['sources']=[s for s in captured['sources'] if s['id']!=packet['document_id']]
        packet['version']=rows(conn,'SELECT * FROM document_file_version WHERE id=?',(packet['version_id'],))[0]
        packet['reviews']=rows(conn,'SELECT * FROM document_review WHERE work_packet_id=? ORDER BY id',(packet['id'],))
    blocked=''
    try:work_compat.require_open(conn,case_id)
    except ValueError as e:blocked=str(e)
    return {'case':case,'tasks':tasks,'outgoing':outgoing,'review_history':history,'blocked':blocked,
            'accepted':[t for t in tasks if t['status']=='done'],
            'missing':[t for t in tasks if t['mandatory'] and t['status'] not in ('done','cancelled')]}


def summaries(conn,user,documents):
    result={}
    for doc in documents:
        packet=latest(conn,doc['id'])
        if not packet:continue
        try:case=work.get(conn,user,packet['case_id'])
        except permissions.Denied:continue
        value=json.loads(packet['snapshot_json'])
        version=rows(conn,'SELECT * FROM document_file_version WHERE id=?',(packet['version_id'],))[0]
        result[doc['id']]={'case':case,'packet':packet,'version':version,'current':current(conn,packet),
            'accepted':sum(t['status']=='done' for t in value['tasks']),
            'missing':sum(t['mandatory'] and t['status'] not in ('done','cancelled') for t in value['tasks'])}
    return result
