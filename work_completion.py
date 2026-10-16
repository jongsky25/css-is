"""Explicit case scope and completion using retained formal-document evidence."""
import hashlib
import json

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work
import work_blockers
import work_review


def required_ids(conn,case_id):
    ids={r[0] for r in conn.execute('SELECT document_id FROM work_completion_requirement WHERE case_id=? UNION SELECT document_id FROM work_legacy_document WHERE case_id=? UNION SELECT document_id FROM work_review_packet WHERE case_id=?',(case_id,case_id,case_id))}
    result=set()
    for did in ids:
        doc=work.resolved_document(conn,did)
        result.add(doc['id'] if doc else did)
    return sorted(result)


def contribution_gaps(conn,case_id):
    result=[]
    for task in rows(conn,'SELECT * FROM work_task WHERE case_id=? ORDER BY id',(case_id,)):
        if task['status'] not in ('done','cancelled'):
            result.append({'id':task['id'],'title':task['title'],'reason':'Required contribution is outstanding.' if task['mandatory'] else 'Finish or explicitly cancel this optional contribution.'})
        elif task['status']=='done' and work_blockers.waiting(conn,task):
            result.append({'id':task['id'],'title':task['title'],'reason':'Resolve the blocker, prerequisite or changed-decision review.'})
    return result


def release_gate(conn,doc):
    cases={r[0] for r in conn.execute('SELECT case_id FROM work_review_packet WHERE document_id=? UNION SELECT case_id FROM work_completion_requirement WHERE document_id=? UNION SELECT case_id FROM work_legacy_document WHERE document_id=?',(doc['id'],doc['id'],doc['id']))}
    if any(contribution_gaps(conn,cid) for cid in cases):
        raise ValueError('Resolve outstanding contributions before releasing this shared response.')


def closure_inputs_current(conn,packet):
    if conn.execute('SELECT 1 FROM work_review_invalidation WHERE packet_id=?',(packet['id'],)).fetchone():return False
    try:value,_=work_review.snapshot(conn,packet['case_id'],packet['document_id'])
    except ValueError:return False
    old=json.loads(packet['snapshot_json'])
    # Official closure and case administration follow release; they do not rewrite inputs.
    for state in (value,old):
        state.pop('case_revision',None)
        for source in state['sources']:source.pop('lifecycle',None)
    return value==old and work_review.version_matches(conn,packet,docs.raw(conn,packet['document_id']))


def document_evidence(conn,doc,seen=None):
    seen=set(seen or ())
    if doc['id'] in seen:
        return {'issues':['Circular follow-up references cannot satisfy completion.']}
    seen.add(doc['id'])
    issues=[]
    followed_by=None
    review_evidence=None;version_evidence=None;signatures=[]
    jobs=rows(conn,"SELECT id,kind,state FROM document_job WHERE document_id=? AND kind IN ('sign','dispatch') AND state IN ('pending','running','unknown')",(doc['id'],))
    if jobs:issues.append('Resolve pending, running or uncertain signing/delivery operations; do not resend blindly.')
    events=rows(conn,"SELECT * FROM document_event WHERE document_id=? AND action IN ('close','cancel') ORDER BY id DESC",(doc['id'],))
    policy=json.loads(doc['policy_json'])
    if doc['status']=='cancelled':
        if not events or events[0]['action']!='cancel' or not json.loads(events[0]['detail_json']).get('reason'):
            issues.append('Cancellation authority and reason are missing.')
        return {'doc':doc,'issues':issues,'jobs':jobs,'dispatches':[],'recipients':[],'closure':events[0] if events else None}
    if doc['status']!='closed':issues.append('Close this official record in Documents after meeting its requirements.')
    if doc['verification']!='verified' or doc['reconcile'] or not doc['lead_id']:
        issues.append('Resolve document verification, ownership and directives.')
    closure=next((e for e in events if e['action']=='close'),None)
    evidence=json.loads(closure['detail_json']).get('evidence',{}) if closure else {}
    if 'closure' not in policy or not closure or any(not str(evidence.get(key,'')).strip() for key in policy.get('closure',[])):
        issues.append('Retained closure evidence does not meet the current policy.')
    if conn.execute("SELECT 1 FROM document_assignment_effective WHERE document_id=? AND mandatory=1 AND status NOT IN ('completed','superseded')",(doc['id'],)).fetchone():
        issues.append('Mandatory document contributions are incomplete.')
    dispatches=[];recipients=[]
    if doc['direction']=='OUT':
        if any(k not in policy for k in ('signature_required','ack_required','release')):
            issues.append('Configure signature, acknowledgment and release policy.')
        if not doc['current_version'] or doc['approved_version']!=doc['current_version']:
            issues.append('The current version has no valid approval lineage.')
        # Follow signed/minor version lineage to an actual retained approval.
        versions=rows(conn,'SELECT * FROM document_file_version WHERE document_id=?',(doc['id'],))
        by_id={v['id']:v for v in versions};vid=doc['current_version'];lineage_seen=set();approved=False
        version_evidence=by_id.get(vid)
        signatures=rows(conn,'SELECT * FROM document_signature WHERE document_id=? AND version_id=?',(doc['id'],vid))
        while vid and vid not in lineage_seen:
            lineage_seen.add(vid)
            approvals=rows(conn,"SELECT * FROM document_review WHERE document_id=? AND version_id=? AND decision='approved' ORDER BY id DESC LIMIT 1",(doc['id'],vid))
            if approvals:review_evidence=approvals[0];approved=True;break
            version=by_id.get(vid);vid=version['parent_id'] if version else None
        if not approved:issues.append('Retained formal approval evidence is missing.')
        if policy.get('signature_required') and (doc['signed_version']!=doc['current_version'] or not conn.execute('SELECT 1 FROM document_signature WHERE document_id=? AND version_id=?',(doc['id'],doc['current_version'])).fetchone()):
            issues.append('Required signature evidence is missing for this version.')
        packet=work_review.latest(conn,doc['id'])
        if packet and not closure_inputs_current(conn,packet):
            for followup in rows(conn,"SELECT d.* FROM document d JOIN document_relation r ON r.source_id=d.id WHERE r.target_id=? AND r.kind='follow_up' AND d.direction='OUT' AND d.status='closed'",(doc['id'],)):
                next_packet=work_review.latest(conn,followup['id'])
                if next_packet and next_packet['case_id']==packet['case_id'] and not document_evidence(conn,followup,seen)['issues']:
                    followed_by={'id':followup['id'],'number':followup['number']};break
            if not followed_by:issues.append('Consolidation inputs changed after review; close an explicitly linked, reviewed follow-up before completion.')
        dispatches=rows(conn,'SELECT * FROM document_dispatch WHERE document_id=? AND version_id=? ORDER BY id',(doc['id'],doc['current_version']))
        attempts=rows(conn,'''SELECT r.*,d.created_at,d.channel FROM document_dispatch_recipient r
            JOIN document_dispatch d ON d.id=r.dispatch_id WHERE d.document_id=? AND d.version_id=? ORDER BY d.id,r.recipient''',(doc['id'],doc['current_version']))
        latest={r['recipient']:r for r in attempts};recipients=list(latest.values())
        if not dispatches or not recipients:issues.append('Recorded delivery and recipient evidence are required.')
        for recipient in recipients:
            if recipient['outcome']!='accepted':issues.append('Confirm delivery for every intended recipient; failed or uncertain delivery remains unresolved.')
            elif policy.get('ack_required') and not recipient['acknowledged_at']:issues.append('Required recipient acknowledgment is missing.')
        if any(not d['evidence'] for d in dispatches):issues.append('Delivery evidence is missing.')
    return {'doc':doc,'issues':list(dict.fromkeys(issues)),'jobs':jobs,'dispatches':dispatches,'recipients':recipients,'closure':closure,'followed_by':followed_by,'review':review_evidence,'version':version_evidence,'signatures':signatures}


def report(conn,case):
    gaps=contribution_gaps(conn,case['id']);requirements=[];issues=[]
    if case['status']=='open':
        try:work.get(conn,{'id':case['lead_id']},case['id'])
        except permissions.Denied:issues.append('Confirm an active accountable lead with access to the linked records.')
    ids=required_ids(conn,case['id'])
    if case['completion_mode']=='undecided':issues.append('The concerned officer must confirm the completion scope.')
    if case['completion_mode']=='internal' and ids:issues.append('Formal records are now required; the officer must confirm formal completion scope.')
    if case['completion_mode']=='formal' and not ids:issues.append('Select at least one official record requiring closure.')
    for did in ids:
        doc=work.resolved_document(conn,did)
        if not doc:issues.append('A required official record is unavailable.');continue
        requirements.append(document_evidence(conn,doc))
    if gaps:issues.append('Resolve all outstanding contributions before completion.')
    if any(d['issues'] for d in requirements):issues.append('Required official records still need attention.')
    return {'gaps':gaps,'requirements':requirements,'issues':issues}


def state(conn,case):
    result=report(conn,case)
    snapshot={'case_revision':case['revision'],'lead_id':case['lead_id'],'mode':case['completion_mode'],
        'tasks':rows(conn,'SELECT id,revision,status FROM work_task WHERE case_id=? ORDER BY id',(case['id'],)),
        'requirements':result['requirements'],'issues':result['issues']}
    raw=json.dumps(snapshot,sort_keys=True)
    return result,snapshot,hashlib.sha256(raw.encode()).hexdigest()


def page(conn,user,case_id):
    user=permissions.actor(conn,user);case=work.get(conn,user,case_id)
    result,_,digest=state(conn,case)
    return {'case':case,**result,'digest':digest,'scope_officer':work.officer(conn,user,case),
        'coordinator':work.officer(conn,user,case) or case['lead_id']==user['id'],
        'documents':work.linked_documents(conn,user,case_id),
        'completions':rows(conn,'SELECT * FROM work_completion WHERE case_id=? ORDER BY id DESC LIMIT 30',(case_id,))}


def configure(conn,user,case_id,revision,mode,document_ids,note):
    with transaction(conn):
        user=permissions.actor(conn,user);case=work.get(conn,user,case_id);work.writable(conn);work._check_revision(case,revision)
        if not work.officer(conn,user,case):raise permissions.Denied('Only the concerned officer confirms completion scope.')
        if case['status']!='open':raise ValueError('Reopen the work item before changing its completion scope.')
        if mode not in ('internal','formal'):raise ValueError('Choose internal work or formal correspondence.')
        ids={int(i) for i in document_ids};linked={d['id'] for d in work.linked_documents(conn,user,case_id)}
        if not ids<=linked:raise permissions.Denied('Choose only linked correspondence you can read.')
        existing=required_ids(conn,case_id)
        if mode=='internal' and (ids or existing or case['completion_mode']=='formal'):
            raise ValueError('Formal requirements cannot be removed through an internal-work declaration.')
        if mode=='formal' and not (ids or existing):raise ValueError('Select an official record requiring closure.')
        note=work._text(note,'Scope authority and reason',4000)
        for did in ids:
            conn.execute('INSERT OR IGNORE INTO work_completion_requirement VALUES (?,?,?,?,?)',(case_id,did,user['id'],note,tz.now_iso()))
        conn.execute('UPDATE work_case SET completion_mode=?,revision=revision+1,updated_at=? WHERE id=?',(mode,tz.now_iso(),case_id))
        work._event(conn,user,case_id,'completion_scope',{'mode':mode,'document_ids':sorted(ids),'reason':note})


def complete(conn,user,case_id,revision,digest,evidence):
    with transaction(conn):
        user=permissions.actor(conn,user);case=work.get(conn,user,case_id);work.writable(conn);work._check_revision(case,revision)
        if not (work.officer(conn,user,case) or case['lead_id']==user['id']):raise permissions.Denied('Only the accountable lead or concerned officer completes work.')
        if case['status']!='open':raise docs.Conflict('This work item is already completed.')
        if not case['lead_id']:raise ValueError('Confirm an accountable lead before completion.')
        work.get(conn,{'id':case['lead_id']},case_id)
        result,snapshot,current=state(conn,case)
        if digest!=current:raise docs.Conflict('Contributions or formal evidence changed. Reload the completion checklist.')
        if result['issues']:raise ValueError(' '.join(result['issues']))
        evidence=work._text(evidence,'Outcome and closure evidence',4000)
        conn.execute('INSERT INTO work_completion(case_id,actor_id,evidence,snapshot_json,created_at) VALUES (?,?,?,?,?)',
            (case_id,user['id'],evidence,json.dumps(snapshot,sort_keys=True),tz.now_iso()))
        conn.execute("UPDATE work_case SET status='completed',revision=revision+1,updated_at=? WHERE id=?",(tz.now_iso(),case_id))
        work._event(conn,user,case_id,'completed',{'reason':evidence})


def reopen(conn,user,case_id,revision,note):
    with transaction(conn):
        user=permissions.actor(conn,user);case=work.get(conn,user,case_id);work.writable(conn);work._check_revision(case,revision)
        if not (work.officer(conn,user,case) or case['lead_id']==user['id']):raise permissions.Denied('Only the accountable lead or concerned officer reopens work.')
        if case['status']!='completed':raise ValueError('Only completed work can be reopened.')
        note=work._text(note,'Reason for reopening',4000)
        conn.execute("UPDATE work_case SET status='open',revision=revision+1,updated_at=? WHERE id=?",(tz.now_iso(),case_id))
        work._event(conn,user,case_id,'reopened',{'reason':note})


def invalidate(conn,user,document_id):
    # Required records can be reopened in Documents independently; retain the old
    # completion as history, and make the case active again if its gates no longer hold.
    target=work.resolved_document(conn,document_id)
    target_id=target['id'] if target else document_id
    candidates=rows(conn,"""WITH RECURSIVE aliases(id) AS (
        SELECT ? UNION SELECT d.id FROM document d JOIN aliases a ON d.canonical_id=a.id
    ), required(case_id,document_id) AS (
        SELECT case_id,document_id FROM work_completion_requirement UNION
        SELECT case_id,document_id FROM work_legacy_document UNION
        SELECT case_id,document_id FROM work_review_packet
    ) SELECT DISTINCT c.* FROM work_case c JOIN required r ON r.case_id=c.id
        JOIN aliases a ON a.id=r.document_id WHERE c.status='completed'""",(target_id,))
    for case in candidates:
        if report(conn,case)['issues']:
            conn.execute("UPDATE work_case SET status='open',revision=revision+1,updated_at=? WHERE id=?",(tz.now_iso(),case['id']))
            work._event(conn,user,case['id'],'completion_invalidated',{'reason':'A required official record changed; review completion again.','document_id':document_id})
