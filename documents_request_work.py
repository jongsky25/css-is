"""Explicit, atomic proposals from reviewed requests; no automatic assignments."""
import hashlib
import json
from datetime import date

import documents as docs
import documents_understanding as understanding
import documents_permissions as permissions
from documents_storage import transaction, rows
import storage as st
import work
import work_compat
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
    current = digest(source(conn, doc_id, index))
    found = rows(conn, 'SELECT * FROM document_request_work_review WHERE document_id=? AND request_index=? ORDER BY id DESC LIMIT 1',
                 (doc_id, index))
    item['acknowledgement'] = found[0] if found else None
    # The source differs from what the work was proposed from, whether or not anyone reviewed it.
    item['changed_since_proposal'] = current != item['source_hash']
    # Needs attention: it differs from the last reviewed source (or the proposal if none was
    # reviewed) and has not simply returned to the proposed source.
    baseline = item['acknowledgement']['source_hash'] if item['acknowledgement'] else item['source_hash']
    item['changed'] = current != baseline and current != item['source_hash']
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


def latest_acknowledgement(conn, user, doc_id, index):
    """Newest acknowledgement for a request's work, after fresh document and work access checks."""
    if not existing(conn, user, doc_id, index):
        return None
    found = rows(conn, 'SELECT * FROM document_request_work_review WHERE document_id=? AND request_index=? ORDER BY id DESC LIMIT 1',
                 (doc_id, index))
    return found[0] if found else None


HISTORY_LIMIT = 20


def acknowledgement_history(conn, saved, limit=HISTORY_LIMIT):
    """Newest-first reviews of source changes for a request's work; never writes.

    `saved` comes from existing(), which already checked current document and work access,
    so this helper takes no user and cannot be used to read another request's history.
    """
    key = (saved['document_id'], saved['request_index'])
    entries = rows(conn, 'SELECT * FROM document_request_work_review WHERE document_id=? AND request_index=? ORDER BY id DESC LIMIT ?',
                   (*key, int(limit)))
    total = conn.execute('SELECT COUNT(*) FROM document_request_work_review WHERE document_id=? AND request_index=?', key).fetchone()[0]
    return {'entries': entries, 'total': total, 'older': max(0, total - len(entries))}


def acknowledgement_state(conn, user, saved):
    """What the comparison screen needs to offer the acknowledge form; never writes."""
    case = work.get(conn, user, saved['case_id'])
    allowed = work.enabled(conn) and can_acknowledge(user, case, conn)
    if allowed:
        try:
            work_compat.require_open(conn, case['id'])
        except ValueError:
            allowed = False
    task = conn.execute('SELECT revision FROM work_task WHERE id=? AND case_id=?', (saved['task_id'], case['id'])).fetchone()
    return {'allowed': bool(allowed and task), 'task_revision': task[0] if task else 0,
            'source_hash': digest(source(conn, saved['document_id'], saved['request_index']))}


def suggested_target(conn, user, saved):
    """A date the person may apply with the existing "Adjust internal target" action, or None.

    Never writes. Offered only when the request's deadline changed since the proposal, is a
    valid date different from the work's current target, the work is open, shared work is
    enabled, and the same predicate that shows the target form would show it to this person.
    """
    user = permissions.actor(conn, user)
    key = f"need_{saved['request_index']}_deadline"
    current = source(conn, saved['document_id'], saved['request_index']).get(key, '')
    if not current or len(current) != 10 or not current.isascii():
        return None
    try:
        date.fromisoformat(current)
    except ValueError:
        return None
    if current == saved['values'].get(key, ''):
        return None
    found = rows(conn, 'SELECT * FROM work_task WHERE id=? AND case_id=?', (saved['task_id'], saved['case_id']))
    if not found or (found[0]['due_date'] or '') == current or not work.enabled(conn):
        return None
    case = work.get(conn, user, saved['case_id'])
    try:
        work_compat.require_open(conn, case['id'])
    except ValueError:
        return None
    if 'milestone' not in work_tasks.actions(conn, user, case, found[0]):
        return None
    return {'date': current, 'task_id': found[0]['id'], 'case_id': case['id']}


def can_acknowledge(user, case, conn):
    """The existing work decision authority: the case lead or an authorized unit officer."""
    return case['lead_id'] == user['id'] or work.officer(conn, user, case)


def acknowledge(conn, user, doc_id, index, fields):
    """Record that a named person reviewed the current source change; changes no work field.

    Deliberately does not use work._event (it invalidates formal reviews) and does not
    touch the document revision, reconcile flag, notices or any work row.
    """
    with transaction(conn):
        user = permissions.actor(conn, user)
        saved = existing(conn, user, doc_id, index)
        if not saved:
            raise ValueError('Choose a saved request that already has proposed work.')
        work.writable(conn)
        case = work.get(conn, user, saved['case_id'])
        work_compat.require_open(conn, case['id'])
        docs.require(can_acknowledge(user, case, conn),
                     'Only the work item lead or an authorized unit officer can acknowledge a source change.')
        if fields.get('confirmed') != 'yes':
            raise ValueError('Confirm that you checked the source change against the work.')
        submitted = fields.get('source_hash', '')
        revision = fields.get('task_revision', '')
        note = fields.get('note', '')
        if not all(isinstance(value, str) for value in (submitted, revision, note)):
            raise ValueError('Invalid acknowledgement field. Reload the comparison.')
        note = note.strip()
        if len(note) > 500:
            raise ValueError('The note can be at most 500 characters.')
        if len(submitted) != 64 or not all(c in '0123456789abcdef' for c in submitted):
            raise ValueError('Invalid source reference. Reload the comparison.')
        if not revision.isascii() or not revision.isdigit() or len(revision) > 10:
            raise ValueError('Invalid work revision. Reload the comparison.')
        repeat = rows(conn, 'SELECT * FROM document_request_work_review WHERE document_id=? AND request_index=? AND source_hash=?',
                      (doc_id, index, submitted))
        if repeat:
            return repeat[0]  # A retry or double click returns the same record.
        if submitted == saved['source_hash']:
            raise ValueError('This request has not changed since the work was proposed.')
        current = digest(source(conn, doc_id, index))
        if submitted != current:
            raise docs.Conflict('The saved request changed again. Reload the comparison before acknowledging.')
        task = conn.execute('SELECT revision FROM work_task WHERE id=? AND case_id=?', (saved['task_id'], case['id'])).fetchone()
        if not task or task[0] != int(revision):
            raise docs.Conflict('This contribution changed. Reload the comparison before acknowledging.')
        understanding_revision = conn.execute(
            'SELECT MAX(revision) FROM document_understanding_revision WHERE document_id=?', (doc_id,)).fetchone()[0] or 0
        now = tz.now_iso()
        identifier = conn.execute('''INSERT INTO document_request_work_review
            (document_id,request_index,source_hash,understanding_revision,task_revision,case_id,task_id,actor_id,note,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)''', (doc_id, index, submitted, understanding_revision, task[0], case['id'],
                                                saved['task_id'], user['id'], note, now)).lastrowid
        st.audit(conn, user['username'], 'document_request_work_acknowledged', target_type='document', target_id=doc_id,
                 after=json.dumps({'request_index': index, 'case_id': case['id'], 'task_id': saved['task_id'],
                                   'source_hash': submitted, 'understanding_revision': understanding_revision}, sort_keys=True),
                 commit=False)
        return rows(conn, 'SELECT * FROM document_request_work_review WHERE id=?', (identifier,))[0]


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
