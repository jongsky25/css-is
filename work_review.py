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


def latest(conn, document_id, *, details=True):
    fields='*' if details else 'id,case_id,document_id,version_id,snapshot_hash'
    found=rows(conn,f'SELECT {fields} FROM work_review_packet WHERE document_id=? ORDER BY id DESC LIMIT 1',(document_id,))
    return found[0] if found else None


def _review_source(conn,document_id):
    # Exact hash/lineage inputs only; omit unrelated registry fields.
    found=rows(conn,'''SELECT id,subject,type,sender,document_date,due_date,verification,
        policy_json,canonical_id,status,approved_version,reconcile,current_version
        FROM document WHERE id=?''',(document_id,))
    return found[0] if found else None


_SOURCE_KEYS=('id','subject','type','sender','document_date','due_date','verification','policy_json',
              'canonical_id','status','approved_version','reconcile','current_version')


def _snapshot_inputs(conn,case_id):
    case=work.raw(conn,case_id)
    linked_ids=[r[0] for r in conn.execute('SELECT document_id FROM work_document WHERE case_id=? ORDER BY document_id',(case_id,))]
    # One read for the linked records; aliases are followed locally with the same
    # loop/missing-record rules as work.resolved_document, fetching only uncached targets.
    fetched={r['id']:r for r in rows(conn,'''SELECT id,subject,type,sender,document_date,due_date,verification,
        policy_json,canonical_id,status,approved_version,reconcile,current_version
        FROM document WHERE id IN (SELECT document_id FROM work_document WHERE case_id=?)''',(case_id,))}
    def load(_conn,document_id):
        if document_id not in fetched:fetched[document_id]=_review_source(conn,document_id)
        return fetched[document_id]
    resolved=[]
    for linked_id in linked_ids:
        doc=work.resolved_document(conn,linked_id,_load=load)
        if not doc:
            raise ValueError('A linked source is unavailable. Reconcile correspondence before review.')
        resolved.append((linked_id,doc))
    directives=dict(conn.execute('SELECT document_id,MAX(id) FROM document_directive WHERE document_id IN (SELECT value FROM json_each(?)) GROUP BY document_id',
                                 (json.dumps(sorted({doc['id'] for _,doc in resolved})),)))
    # Retain only hash inputs, not unrelated registry fields.
    sources=[(linked_id,{key:doc[key] for key in _SOURCE_KEYS},directives.get(doc['id'])) for linked_id,doc in resolved]
    tasks=rows(conn,'SELECT id,title,status,revision,mandatory,owner_id,submission FROM work_task WHERE case_id=? ORDER BY id',(case_id,))
    import work_handoff
    draft=work_handoff.current(conn,case_id)
    support=rows(conn,'''SELECT id FROM work_support_file f WHERE case_id=? AND NOT EXISTS
        (SELECT 1 FROM work_support_retired r WHERE r.file_id=f.id) ORDER BY id''',(case_id,))
    return case,sources,tasks,draft,support


def _source_value(linked_id,doc,directive,target):
    """One source's hash input; only the document under review keeps its live lineage."""
    keys=('id','subject','type','sender','document_date','due_date','verification','policy_json','canonical_id')
    source={key:doc[key] for key in keys}
    source['lifecycle']=doc['status'] if not target and doc['status'] in ('closed','cancelled') else None
    source['linked_id']=linked_id
    source['approved_version']=doc['approved_version'] if not target else None
    source['reconcile']=doc['reconcile'] if not target else None
    source['current_version']=doc['current_version'] if not target else None
    source['directive_id']=directive
    return source


_NOT_LINKED='Link this outgoing document to the work item before requesting review.'


def snapshot(conn,case_id,document_id,*,_inputs=None):
    case,linked,tasks,draft,support=_inputs if _inputs is not None else _snapshot_inputs(conn,case_id)
    sources=[_source_value(linked_id,doc,directive,doc['id']==document_id) for linked_id,doc,directive in linked]
    if document_id not in {s['id'] for s in sources}:
        raise ValueError(_NOT_LINKED)
    value={'case_id':case_id,'case_revision':case['revision'],'tasks':tasks,'sources':sources,
           'draft_id':draft['id'] if draft else None,'support_ids':[f['id'] for f in support]}
    raw=json.dumps(value,sort_keys=True)
    return value,hashlib.sha256(raw.encode()).hexdigest()


class SnapshotDigests:
    """Exact snapshot() digests for every document of one case, serialized once.

    The canonical JSON is sort_keys output with default separators; the case-wide
    fields and each source (as reviewed document or as another source) are
    serialized once and joined, producing byte-for-byte the same text and hash.
    Lives only inside a caller-held read batch for a single case's inputs.
    """
    def __init__(self,case_id,inputs):
        case,linked,tasks,draft,support=inputs
        self.linked=linked;self.ids={doc['id'] for _,doc,_ in linked};self.memo={};self.others=None;self.positions=None
        self.head=('{"case_id": '+json.dumps(case_id)+', "case_revision": '+json.dumps(case['revision'])
                   +', "draft_id": '+json.dumps(draft['id'] if draft else None)+', "sources": [')
        self.tail=('], "support_ids": '+json.dumps([f['id'] for f in support])
                   +', "tasks": '+json.dumps(tasks,sort_keys=True)+'}')

    def _fragment(self,n,target):
        key=(n,target)
        part=self.memo.get(key)
        if part is None:
            linked_id,doc,directive=self.linked[n]
            part=self.memo[key]=json.dumps(_source_value(linked_id,doc,directive,target),sort_keys=True)
        return part

    def digest(self,document_id):
        if document_id not in self.ids:raise ValueError(_NOT_LINKED)
        if self.others is None:
            self.others=[self._fragment(n,False) for n in range(len(self.linked))]
            self.positions={}
            for n,(_,doc,_) in enumerate(self.linked):self.positions.setdefault(doc['id'],[]).append(n)
        parts=list(self.others)
        for n in self.positions[document_id]:parts[n]=self._fragment(n,True)
        return hashlib.sha256((self.head+', '.join(parts)+self.tail).encode()).hexdigest()


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


def current(conn,packet,*,_inputs=None,_digests=None,_invalidation_checked=False):
    if not _invalidation_checked and conn.execute('SELECT 1 FROM work_review_invalidation WHERE packet_id=?',(packet['id'],)).fetchone():return False
    try:
        digest=(_digests.digest(packet['document_id']) if _digests is not None
                else snapshot(conn,packet['case_id'],packet['document_id'],_inputs=_inputs)[1])
        if digest!=packet['snapshot_hash']:
            return False
        # The held read snapshot already resolved this source, including its
        # actual current version. Avoid fetching the full registry record again.
        doc=(next(doc for _,doc,_ in _inputs[1] if doc['id']==packet['document_id'])
             if _inputs is not None else docs.raw(conn,packet['document_id']))
        return version_matches(conn,packet,doc)
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
        result[doc['id']]=_summary_value(conn,packet,case,current(conn,packet))
    return result


class ReadBatch:
    """Reuse one case within a caller-held, read-only SQLite snapshot only."""
    def __init__(self,conn,user,*,scope=None):
        if scope is not None and scope.uid!=user['id']:
            raise ValueError('Review read scope must belong to the current actor.')
        self.conn=conn;self.user=user;self.scope=scope
        self.case_id=None;self.case=None;self.inputs=None;self.digests=None

    def summary(self,doc,*,details=True,packet=None):
        # `packet` may be this document's newest compact packet, read with its
        # invalidation flag in the same held snapshot (see documents_actions._load).
        conn=self.conn;packet=packet if packet is not None else latest(conn,doc['id'],details=details)
        if not packet:return None
        cid=packet['case_id']
        if cid!=self.case_id:
            # Keep only one case, never an actor-wide cache of source/work bodies.
            self.case_id=None;self.case=None;self.inputs=None;self.digests=None
            if self.scope is None:
                try:case=work.get(conn,self.user,cid)
                except permissions.Denied:return None
            else:
                # The caller constructed this current actor scope in the same
                # read snapshot. Reuse its shared work visibility predicate.
                found=rows(conn,f'SELECT w.* FROM work_case w WHERE w.id=:review_case AND {self.scope.work_view_sql("w")}',
                           {**self.scope.params,'review_case':cid})
                if not found:return None
                case=found[0]
            self.case=case;self.case_id=cid
        valid=False
        invalidated=(packet['invalidated'] if 'invalidated' in packet else
                     bool(conn.execute('SELECT 1 FROM work_review_invalidation WHERE packet_id=?',(packet['id'],)).fetchone()))
        if not invalidated:
            try:
                if self.inputs is None:
                    self.inputs=_snapshot_inputs(conn,cid);self.digests=SnapshotDigests(cid,self.inputs)
                valid=current(conn,packet,_inputs=self.inputs,_digests=self.digests,_invalidation_checked=True)
            except ValueError:pass
        if not details:return {'case':self.case,'current':valid}
        return _summary_value(conn,packet,self.case,valid)


def _summary_value(conn,packet,case,is_current):
    value=json.loads(packet['snapshot_json'])
    version=rows(conn,'SELECT * FROM document_file_version WHERE id=?',(packet['version_id'],))[0]
    return {'case':case,'packet':packet,'version':version,'current':is_current,
            'accepted':sum(t['status']=='done' for t in value['tasks']),
            'missing':sum(t['mandatory'] and t['status'] not in ('done','cancelled') for t in value['tasks'])}
