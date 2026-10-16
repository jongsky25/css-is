"""Read-only support metrics over currently authorized, actively managed work."""
from datetime import datetime, timedelta
import json
from urllib.parse import urlencode

import documents_permissions as permissions
from documents_storage import rows
import tzutil as tz
import work
import work_blockers
import work_decisions
import work_completion

METRICS = {
    'risk': ('Outcomes needing support', 'work items', 'Open work with a recorded ownership, waiting or date signal; each item counts once.'),
    'no_lead': ('Lead confirmation needed', 'work items', 'Open work without a confirmed lead.'),
    'case_no_date': ('No work-item target', 'work items', 'Open work without an internal target date; not counted as overdue.'),
    'unassigned': ('Unassigned contributions', 'contributions', 'Active contributions without a confirmed owner, including proposals.'),
    'owner_unavailable': ('Owner access needs attention', 'contributions', 'Active contributions whose confirmed owner is inactive or cannot access the work.'),
    'waiting': ('Blocked or waiting', 'contributions', 'Active contributions with a blocker, an unaccepted prerequisite or a changed decision awaiting review.'),
    'review': ('Contribution review waits', 'contributions', 'Contributions submitted for acceptance. Calendar-day age uses the latest recorded submission.'),
    'overdue': ('Overdue contribution targets', 'contributions', 'Active contributions with an internal target before today. Due today is not overdue.'),
    'no_date': ('No contribution target', 'contributions', 'Active contributions without an internal target date; not counted as overdue.'),
    'formal_review': ('Formal review waits', 'documents', 'Distinct linked official records currently in review; shared links count once.'),
}


def selection(values):
    metric = str(values.get('metric') or 'risk')
    if metric not in METRICS:
        raise ValueError('Choose a valid support category.')
    unit = str(values.get('unit') or '')
    page = str(values.get('page') or '1')
    if (unit and (not unit.isdecimal() or not 1 <= int(unit) <= 9223372036854775807)) or not page.isdecimal() or not 1 <= int(page) <= 1000000:
        raise ValueError('Choose a valid unit or page.')
    return {'metric':metric, 'unit':str(int(unit)) if unit else '', 'page':int(page)}


def url(chosen, **changes):
    return '/work/support?' + urlencode(selection({**chosen, **changes}))


def age(value, today):
    try:
        days = (today - datetime.fromisoformat(value).date()).days
        return days if days >= 0 else None
    except (ValueError, TypeError):
        return None


def account_available(conn, uid, case_id):
    try:
        work.get(conn, {'id':uid}, case_id)
        return True
    except permissions.Denied:
        return False


def _report(conn, user, chosen, today):
    user = permissions.actor(conn,user)
    buckets = {key:[] for key in METRICS}
    units = {}
    managed = []
    # Exact totals and matching lists share this database read snapshot. Never
    # use a bounded scan's partial count as a bureau-wide total.
    for candidate in rows(conn,"SELECT * FROM work_case WHERE status='open' ORDER BY id DESC"):
        if not (candidate['lead_id']==user['id'] or work.officer(conn,user,candidate)):
            continue
        try:
            item = work.get(conn,user,candidate['id'])
        except permissions.Denied:
            continue
        if conn.execute("SELECT 1 FROM work_legacy_document l JOIN document d ON d.id=l.document_id WHERE l.case_id=? AND (d.status IN ('closed','cancelled') OR d.canonical_id IS NOT NULL)", (item['id'],)).fetchone():
            continue
        units[item['unit_id']] = conn.execute('SELECT name FROM org_unit WHERE id=?',(item['unit_id'],)).fetchone()[0]
        if not chosen['unit'] or item['unit_id']==int(chosen['unit']):
            managed.append(item)
    formal_seen = set()
    for item in managed:
        cid=item['id']
        base={'id':cid,'title':item['title'],'url':f'/work/{cid}', 'case_title':'',
              'due_date':item['due_date'], 'reasons':[], 'wait_days':None, 'waiting_since':None}
        reasons=[]
        if not item['lead_id']:
            buckets['no_lead'].append(dict(base,reasons=['Confirm an accountable lead.']))
            reasons.append('No confirmed lead')
        elif not account_available(conn,item['lead_id'],cid):
            reasons.append('Lead inactive or without source access')
        if not item['due_date']:
            buckets['case_no_date'].append(dict(base,reasons=['No internal work-item target recorded.']))
        elif item['due_date'] < today.isoformat():
            reasons.append('Work-item target overdue')
        elif item['due_date'] <= (today+timedelta(days=7)).isoformat():
            reasons.append('Work-item target within 7 calendar days (including today)')
        submissions={}
        for event in rows(conn,"SELECT detail_json,created_at FROM work_event WHERE case_id=? AND action='task_submit' ORDER BY id",(cid,)):
            submissions[json.loads(event['detail_json']).get('task_id')]=event['created_at']
        for task in rows(conn,"SELECT * FROM work_task WHERE case_id=? AND status NOT IN ('done','cancelled') ORDER BY id DESC",(cid,)):
            entry={'id':task['id'],'title':task['title'],'url':f"/work/{cid}#task-{task['id']}",
                   'case_title':item['title'],'due_date':task['due_date'],'reasons':[],
                   'wait_days':None,'waiting_since':None}
            if not task['owner_id']:
                buckets['unassigned'].append(dict(entry,reasons=['Awaiting owner confirmation.']))
                reasons.append('Unassigned contribution')
            elif not account_available(conn,task['owner_id'],cid):
                buckets['owner_unavailable'].append(dict(entry,reasons=['Confirm an active owner with access to all linked records.']))
                reasons.append('Contribution owner unavailable')
            waits=[]
            if task['blocker_reason']:waits.append('Blocker: '+task['blocker_reason'])
            if any(t['status']!='done' for t in work_blockers.dependencies(conn,task['id'])):waits.append('Prerequisite not yet accepted')
            if work_decisions.pending(conn,task['id']):waits.append('Changed decision awaiting review')
            if waits:
                buckets['waiting'].append(dict(entry,reasons=waits))
                reasons.append('Blocked or waiting contribution')
            if task['status']=='for_review':
                since=submissions.get(task['id'])
                buckets['review'].append(dict(entry,reasons=['Awaiting contribution acceptance.'],waiting_since=since,wait_days=age(since,today)))
            if not task['due_date']:
                buckets['no_date'].append(dict(entry,reasons=['No internal contribution target recorded.']))
            elif task['due_date'] < today.isoformat():
                buckets['overdue'].append(dict(entry,reasons=['Internal target overdue.']))
                reasons.append('Overdue contribution target')
        for doc_id in work_completion.required_ids(conn,cid):
            doc=work.resolved_document(conn,doc_id)
            if doc and permissions.can_view(conn,user,doc) and doc['status'] not in ('closed','cancelled') and doc['due_date'] and doc['due_date'] < today.isoformat():
                reasons.append('Required official record deadline overdue')
        for doc in work.linked_documents(conn,user,cid):
            if doc['status']!='in_review' or doc['id'] in formal_seen:continue
            formal_seen.add(doc['id'])
            event=conn.execute("SELECT recorded_at FROM document_event WHERE document_id=? AND action='review_route' ORDER BY id DESC LIMIT 1",(doc['id'],)).fetchone()
            since=event[0] if event else None
            buckets['formal_review'].append({'id':doc['id'],'title':doc['number']+' · '+doc['subject'],
                'url':f"/documents/{doc['id']}",'case_title':'','due_date':doc['due_date'],
                'reasons':['Awaiting formal document review.'],'waiting_since':since,'wait_days':age(since,today)})
        if reasons:buckets['risk'].append(dict(base,reasons=list(dict.fromkeys(reasons))))
    # Longest known review waits first; missing timestamps stay explicitly unknown.
    for key in ('review','formal_review'):
        buckets[key].sort(key=lambda r:(r['wait_days'] is None,-(r['wait_days'] or 0),-r['id']))
    selected=buckets[chosen['metric']]
    offset=(chosen['page']-1)*25
    return {'selection':chosen,'today':today.isoformat(),'managed_count':len(managed),
            'support_units':[{'id':uid,'name':name} for uid,name in sorted(units.items(),key=lambda p:p[1])],
            'metrics':[{'key':key,'label':label,'kind':kind,'definition':definition,'count':len(buckets[key]),
                        'url':url(chosen,metric=key,page=1)} for key,(label,kind,definition) in METRICS.items()],
            'selected_label':METRICS[chosen['metric']][0], 'selected_kind':METRICS[chosen['metric']][1],
            'selected_definition':METRICS[chosen['metric']][2], 'total':len(selected),'items':selected[offset:offset+25],
            'next_url':url(chosen,page=chosen['page']+1) if offset+25<len(selected) else None,
            'previous_url':url(chosen,page=chosen['page']-1) if chosen['page']>1 else None}


def report(conn,user,values=None,today=None):
    chosen=selection(values or {})
    if conn.in_transaction:raise RuntimeError('Support overview requires a clean connection')
    conn.execute('BEGIN')
    try:
        return _report(conn,user,chosen,today or tz.today_local())
    finally:
        conn.rollback()  # read snapshot only; no read markers or business changes
