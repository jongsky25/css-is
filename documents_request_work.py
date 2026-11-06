"""Explicit, atomic proposals from reviewed requests; no automatic assignments."""
import hashlib
import json

import documents as docs
import documents_understanding as understanding
import documents_permissions as permissions
from documents_storage import transaction, rows
import work
import work_tasks
import tzutil as tz


def source(conn, doc_id, index):
    if not isinstance(index, int) or not 0 <= index < understanding.MAX_REQUESTS:
        raise ValueError('Choose a saved request.')
    values = understanding.read(conn, doc_id)
    prefix = f'need_{index}_'
    return {key: value for key, value in values.items()
            if key.startswith(prefix) or key.startswith('focus_') or key == 'needs_status'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def existing(conn, user, doc_id, index):
    docs.get(conn, user, doc_id)
    items = rows(conn, 'SELECT * FROM document_request_work WHERE document_id=? AND request_index=?', (doc_id, index))
    if not items:
        return None
    item = items[0]
    work.get(conn, user, item['case_id'])
    item['values'] = json.loads(item['source_json'])
    item['changed'] = digest(source(conn, doc_id, index)) != item['source_hash']
    return item


def propose(conn, user, doc_id, index, fields):
    with transaction(conn):
        user = permissions.actor(conn, user)
        doc = docs.get(conn, user, doc_id)
        work.writable(conn)
        docs.require(understanding.can_edit(conn, user, doc))
        if fields.get('confirmed') != 'yes':
            raise ValueError('Confirm the proposed work after checking the source.')
        for key in ('title', 'expected_output', 'unit_id', 'due_date', 'source_hash', 'revision'):
            if not isinstance(fields.get(key, ''), str):
                raise ValueError('Invalid proposal field. Reload the proposal.')
        payload = {key: fields.get(key, '').strip() for key in ('title', 'expected_output', 'unit_id', 'due_date')}
        if not payload['unit_id'].isascii() or not payload['unit_id'].isdigit() or len(payload['unit_id'])>10:
            raise ValueError('Choose the concerned unit.')
        saved = existing(conn, user, doc_id, index)
        if saved:
            if saved['payload_hash'] != digest(payload) or saved['source_hash'] != fields.get('source_hash'):
                raise docs.Conflict('This request already has proposed work. Open it to reconcile changes.')
            return saved
        revision = fields.get('revision', '')
        if not revision.isascii() or not revision.isdigit() or len(revision)>10:
            raise ValueError('Invalid document revision. Reload the proposal.')
        user, doc = docs.check(conn, user, doc_id, int(revision))
        values = source(conn, doc_id, index)
        prefix = f'need_{index}_'
        if (values.get('needs_status') != 'requests' or not values.get(prefix+'action')
                or values.get(prefix+'confirmed') != 'yes' or values.get(prefix+'kind') not in ('explicit','inferred','manual')):
            raise ValueError('Review and confirm an actionable request before proposing work.')
        if fields.get('source_hash') != digest(values):
            raise docs.Conflict('The saved request changed. Reload and review the proposal.')
        case = work.create_in_transaction(conn, user, {**payload, 'outcome': payload['expected_output'], 'source_document_id': doc_id})
        task = work_tasks.create_in_transaction(conn, user, case['id'], payload)
        conn.execute('''INSERT INTO document_request_work
            (document_id,request_index,source_json,source_hash,payload_hash,case_id,task_id,actor_id,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)''', (doc_id,index,json.dumps(values),digest(values),digest(payload),case['id'],task['id'],user['id'],tz.now_iso()))
        docs.finish(conn,user,doc,'request_work_proposed',{'request_index':index,'case_id':case['id'],'task_id':task['id']})
        return existing(conn,user,doc_id,index)


def task_source(conn, user, task_id):
    item = conn.execute('SELECT document_id,request_index FROM document_request_work WHERE task_id=?', (task_id,)).fetchone()
    if not item:
        return None
    try:
        return existing(conn, user, item[0], item[1])
    except permissions.Denied:
        return None


def comparison(conn, user, doc_id, index):
    """Read-only comparison; both document and case access are checked afresh."""
    saved = existing(conn, user, doc_id, index)
    if not saved:
        return None
    current = source(conn, doc_id, index)
    tasks = rows(conn, '''SELECT t.*,u.name AS unit_name FROM work_task t
        JOIN org_unit u ON u.id=t.unit_id WHERE t.id=? AND t.case_id=?''',
        (saved['task_id'], saved['case_id']))
    if not tasks:
        raise ValueError('The original contribution is unavailable.')
    task = tasks[0]
    prefix = f'need_{index}_'
    fields = [(prefix+key, label, target) for key,label,target in (
        ('action','Requested action','title'), ('output','Expected output','expected_output'),
        ('deadline','Request deadline / work target','due_date'),
        ('recipient','Requested from',None), ('submission','Where / how to submit',None),
        ('evidence','Supporting passage',None), ('page','Source location',None),
        ('kind','Interpretation',None), ('confirmed','Request confirmed',None))]
    fields += [(key,label,None) for key,label in (
        ('needs_status','Request status'), ('focus_primary','Primary focus'),
        ('focus_secondary','Secondary focus'), ('focus_evidence','Focus evidence'),
        ('focus_confirmed','Focus confirmed'))]
    def display(key, value):
        if not value:
            return 'Not recorded'
        if key in ('focus_primary','focus_secondary'):
            return understanding.FOCUS_AREAS.get(value,value)
        if key.endswith('_confirmed'):
            return 'Yes' if value=='yes' else 'Not confirmed'
        return value.replace('_',' ') if key in ('needs_status',prefix+'kind') else value
    result=[]
    for key,label,target in fields:
        before=saved['values'].get(key,'')
        after=current.get(key,'')
        result.append({'label':label, 'before':display(key,before), 'after':display(key,after),
                       'changed':before!=after, 'work':(task[target] or 'Not set') if target else None,
                       'different':bool(target and (task[target] or '')!=after)})
    return {'rows':result, 'changed_count':sum(row['changed'] for row in result),
            'removed':not current.get(prefix+'action'), 'task':task,
            'task_status':work_tasks.LABELS.get(task['status'],task['status']),
            'case':work.get(conn,user,saved['case_id'])}


def overview(conn, user, doc_id):
    """Document-scoped summary; work details retain their separate access checks."""
    doc = docs.get(conn, user, doc_id)
    if doc['direction'] != 'IN':
        return None
    values = understanding.read(conn, doc_id)
    editable = work.enabled(conn) and understanding.can_edit(conn, user, doc)
    items=[]
    for index in range(understanding.MAX_REQUESTS):
        prefix=f'need_{index}_'
        action=values.get(prefix+'action','')
        receipt=conn.execute('SELECT case_id,task_id FROM document_request_work WHERE document_id=? AND request_index=?', (doc_id,index)).fetchone()
        accessible=None
        if receipt:
            try:
                work.get(conn,user,receipt[0])
                accessible=existing(conn,user,doc_id,index)
            except permissions.Denied:
                pass
        # A cleared source position remains discoverable only to its work readers.
        if not action and not accessible:
            continue
        missing=[label for key,label in (
            ('output','Expected output'),('recipient','Requested from'),('deadline','Request deadline'),
            ('submission','Submission instructions'),('evidence','Supporting passage'),('page','Source location'))
            if not values.get(prefix+key)] if action else []
        confirmed=bool(action and values.get(prefix+'confirmed')=='yes'
                       and values.get(prefix+'kind') in ('explicit','inferred','manual')
                       and values.get('needs_status')=='requests')
        task=None
        if accessible:
            tasks=rows(conn,'SELECT status FROM work_task WHERE id=? AND case_id=?',(receipt[1],receipt[0]))
            if tasks:
                task={'status':work_tasks.LABELS.get(tasks[0]['status'],tasks[0]['status']),
                      'changed':accessible['changed']}
        items.append({'index':index,'action':action,'removed':not action,'confirmed':confirmed,
                      'missing':missing,'task':task,
                      'url':f'/documents/{doc_id}/requests/{index}/work' if accessible or (not receipt and editable and confirmed) else None,
                      'can_propose':not receipt and editable and confirmed})
    focus=values.get('focus_primary','')
    return {'items':items,'request_count':sum(not item['removed'] for item in items),
            'needs_review':sum(not item['confirmed'] and not item['removed'] for item in items),
            'visible_work_count':sum(bool(item['task']) for item in items),
            'focus':understanding.FOCUS_AREAS.get(focus,''),
            'focus_confirmed':values.get('focus_confirmed')=='yes',
            'status':values.get('needs_status') or 'Not reviewed'}
