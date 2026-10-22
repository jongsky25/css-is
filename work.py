"""P1.1 shared outcomes, scoped lead confirmation, and document links.

Contribution membership is resolved from work_task; no legacy assignment migration,
document state changes, or external effects.
Every public write owns one transaction and reloads current authority.
"""
from datetime import date
import json

import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import storage as st
import tzutil as tz


def enabled(conn):
    return docs.enabled(conn) and st.get_setting(conn, 'work.enabled', '0') == '1'


def writable(conn):
    if not enabled(conn):
        raise ValueError('Shared work is not enabled. Existing permitted work remains readable.')


def raw(conn, case_id):
    found = rows(conn, 'SELECT * FROM work_case WHERE id=?', (case_id,))
    return found[0] if found else None


def officer(conn, user, case):
    return permissions.officer(conn, user, {'unit_id': case['unit_id'], 'matches_json': '{}'})


def resolved_document(conn, document_id):
    """Follow a merge without displaying metadata from an obsolete source record."""
    seen = set()
    while document_id and document_id not in seen:
        seen.add(document_id)
        doc = docs.raw(conn, document_id)
        if not doc or not doc['canonical_id']:
            return doc
        document_id = doc['canonical_id']
    return None


def _can_view(conn, user, case):
    if not case:
        return False
    tasks = rows(conn, 'SELECT owner_id,unit_id,status FROM work_task WHERE case_id=?', (case['id'],))
    participant = any((t['owner_id'] == user['id'] and t['status'] != 'cancelled') or officer(conn, user, t) for t in tasks)
    if not (user['id'] in (case['creator_id'], case['lead_id']) or officer(conn, user, case) or participant):
        return False
    for (doc_id,) in conn.execute('SELECT document_id FROM work_document WHERE case_id=?', (case['id'],)):
        if not permissions.can_view(conn, user, resolved_document(conn, doc_id)):
            return False
    return True


def get(conn, user, case_id):
    user = permissions.actor(conn, user)
    case = raw(conn, case_id)
    if not _can_view(conn, user, case):
        raise permissions.Denied('Work item not found or unavailable to you.')
    return case


def _event(conn, user, case_id, action, detail):
    payload = json.dumps(detail, sort_keys=True)
    conn.execute('INSERT INTO work_event(case_id,actor_id,action,detail_json,created_at) VALUES (?,?,?,?,?)',
                 (case_id, user['id'], action, payload, tz.now_iso()))
    st.audit(conn, user['username'], 'work_' + action, target_type='work_case', target_id=case_id,
             after=payload, commit=False)
    import work_review
    work_review.invalidate(conn,user,case_id=case_id)


def _text(value, label, maximum):
    value = str(value or '').strip()
    if not value or len(value) > maximum:
        raise ValueError(f'{label} is required and must be at most {maximum} characters.')
    return value


def _account(conn, user_id):
    account = st.get_admin_user_by_id(conn, int(user_id))
    if not account or not account['active']:
        raise ValueError('Choose an active staff account.')
    return account


def _check_revision(case, revision):
    if case['revision'] != int(revision):
        raise docs.Conflict('This work item changed. Reload it before applying your change.')


def _document_for_link(conn, user, case, document_id, kind):
    if kind != 'reference':
        raise ValueError('Only reference links are supported by this increment.')
    doc = resolved_document(conn, int(document_id))
    permissions.require_view(conn, user, doc)
    if doc.get('instruction_state')=='pending':
        raise ValueError('Wait for the Director’s routing instruction before starting shared work.')
    # Case readership is the intersection of its audience and all linked records.
    # Do not strand its creator/lead by linking something they cannot currently read.
    for uid in {case['creator_id'], case['lead_id']} - {None}:
        account = st.get_admin_user_by_id(conn, uid)
        if not account or not account['active']:
            if uid == case['lead_id']:
                raise ValueError('Confirm an active lead before adding more documents.')
            continue
        if not permissions.can_view(conn, {'id': uid}, doc):
            raise ValueError('The creator and confirmed lead must have document access before it can be linked.')
    for task in rows(conn, "SELECT owner_id,due_date FROM work_task WHERE case_id=? AND status<>'cancelled'", (case['id'],)):
        if task['owner_id'] and not permissions.can_view(conn, {'id': task['owner_id']}, doc):
            raise ValueError('Every assigned contributor needs document access before it can be linked.')
        if task['due_date'] and doc['due_date'] and task['due_date'] > doc['due_date']:
            raise ValueError('A contribution target cannot follow the linked official deadline.')
    return doc


def create(conn, user, fields):
    with transaction(conn):
        return create_in_transaction(conn, user, fields)


def create_in_transaction(conn, user, fields):
    if not conn.in_transaction:
        raise RuntimeError('An active transaction is required')
    user = permissions.actor(conn, user)
    writable(conn)
    title = _text(fields.get('title'), 'Title', 250)
    outcome = _text(fields.get('outcome'), 'Expected outcome', 4000)
    unit_id = int(fields.get('unit_id') or 0)
    if not conn.execute('SELECT 1 FROM org_unit WHERE id=?', (unit_id,)).fetchone():
        raise ValueError('Choose the concerned unit.')
    proposed = _account(conn, fields['proposed_lead_id'])['id'] if fields.get('proposed_lead_id') else None
    due = date.fromisoformat(fields['due_date']).isoformat() if fields.get('due_date') else None
    now = tz.now_iso()
    cid = conn.execute('''INSERT INTO work_case(title,outcome,unit_id,creator_id,proposed_lead_id,
                          due_date,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)''',
                       (title, outcome, unit_id, user['id'], proposed, due, now, now)).lastrowid
    case = raw(conn, cid)
    if fields.get('source_document_id'):
        doc = _document_for_link(conn, user, case, fields['source_document_id'], 'reference')
        conn.execute('INSERT INTO work_document VALUES (?,?,?,?,?)', (cid, doc['id'], 'reference', user['id'], now))
    _event(conn, user, cid, 'created', {'proposed_lead_id': proposed})
    if fields.get('source_document_id'):
        _event(conn, user, cid, 'document_linked', {'document_id': doc['id'], 'kind': 'reference'})
    return raw(conn, cid)


def confirm_lead(conn, user, case_id, revision, lead_id, reason):
    with transaction(conn):
        user = permissions.actor(conn, user)
        case = get(conn, user, case_id)
        writable(conn)
        _check_revision(case, revision)
        if not officer(conn, user, case):
            raise permissions.Denied('The concerned officer must confirm the lead.')
        import work_compat
        work_compat.require_open(conn, case_id)
        lead = _account(conn, lead_id)
        reason = _text(reason, 'Reason', 2000)
        for (doc_id,) in conn.execute('SELECT document_id FROM work_document WHERE case_id=?', (case_id,)):
            if not permissions.can_view(conn, lead, resolved_document(conn, doc_id)):
                raise ValueError('Grant the proposed lead access to every linked document before confirming them.')
        conn.execute('UPDATE work_case SET lead_id=?,revision=revision+1,updated_at=? WHERE id=?',
                     (lead['id'], tz.now_iso(), case_id))
        for (did,) in conn.execute('SELECT document_id FROM work_legacy_document WHERE case_id=?', (case_id,)):
            doc = docs.raw(conn, did)
            docs.finish(conn, user, doc, 'lead', {'reason': reason, 'case_id': case_id}, {'lead_id': lead['id']})
        _event(conn, user, case_id, 'lead_confirmed', {'previous_lead_id': case['lead_id'], 'lead_id': lead['id'], 'reason': reason})
        return raw(conn, case_id)


def link_document(conn, user, case_id, revision, document_id, kind='reference'):
    with transaction(conn):
        return link_document_in_transaction(conn, user, case_id, revision, document_id, kind)


def link_document_in_transaction(conn, user, case_id, revision, document_id, kind='reference'):
    if not conn.in_transaction:
        raise RuntimeError('An active transaction is required')
    user = permissions.actor(conn, user)
    case = get(conn, user, case_id)
    writable(conn)
    import work_compat
    work_compat.require_open(conn,case_id)
    if not can_link(conn, user, case):
        raise permissions.Denied('The creator, lead, or concerned officer links correspondence.')
    _check_revision(case, revision)
    doc = _document_for_link(conn, user, case, document_id, kind)
    previous = None
    for link in rows(conn, 'SELECT document_id,kind FROM work_document WHERE case_id=?', (case_id,)):
        resolved = resolved_document(conn, link['document_id'])
        if resolved and resolved['id'] == doc['id']:
            previous = (link['kind'],)
            break
    if previous:
        if previous[0] == kind:
            return case  # Repeat submission does not create another link/event.
        raise ValueError('This document is already linked. Its existing link is retained.')
    conn.execute('INSERT INTO work_document VALUES (?,?,?,?,?)', (case_id, doc['id'], kind, user['id'], tz.now_iso()))
    conn.execute('UPDATE work_case SET revision=revision+1,updated_at=? WHERE id=?', (tz.now_iso(), case_id))
    _event(conn, user, case_id, 'document_linked', {'document_id': doc['id'], 'kind': kind})
    return raw(conn, case_id)


def can_link(conn, user, case):
    return user['id'] in (case['creator_id'], case['lead_id']) or officer(conn, user, case)


def list_page(conn, user, before=None, limit=25):
    """Permission-filtered keyset page shared by UI and supported API reads."""
    import work_reads
    return work_reads.page(conn, user, before=before or 0, limit=limit)


def linked_documents(conn, user, case_id):
    get(conn, user, case_id)
    result = []
    seen = set()
    for link in rows(conn, 'SELECT * FROM work_document WHERE case_id=? ORDER BY created_at,document_id', (case_id,)):
        doc = resolved_document(conn, link['document_id'])
        permissions.require_view(conn, user, doc)
        if doc['id'] in seen:
            continue
        seen.add(doc['id'])
        result.append({**doc, 'link_kind': link['kind']})
    return result


def cases_for_document(conn, user, document_id):
    user = permissions.actor(conn, user)
    target = resolved_document(conn, document_id)
    if not permissions.can_view(conn, user, target):
        return []
    candidates = rows(conn, '''WITH RECURSIVE aliases(id) AS (
                                 SELECT id FROM document WHERE id=?
                                 UNION SELECT d.id FROM document d JOIN aliases a ON d.canonical_id=a.id)
                              SELECT DISTINCT w.* FROM work_case w JOIN work_document d ON d.case_id=w.id
                              JOIN aliases a ON a.id=d.document_id ORDER BY w.id DESC''', (target['id'],))
    return [case for case in candidates if _can_view(conn, user, case)]


def document_choices(conn, user, query=''):
    """A bounded lookup; hidden titles and raw result counts never reach the UI."""
    user = permissions.actor(conn, user)
    query = str(query or '').strip()
    result = []
    # instr treats user input literally (including % and _), not as a LIKE pattern.
    for doc in rows(conn, '''SELECT * FROM document WHERE canonical_id IS NULL
                            AND (?='' OR instr(lower(number||' '||subject),lower(?))>0)
                            ORDER BY id DESC LIMIT 250''', (query, query)):
        if permissions.can_view(conn, user, doc):
            result.append(doc)
            if len(result) == 25:
                break
    return result
