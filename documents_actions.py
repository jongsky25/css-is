"""Permission filtered next steps for the Documents workspace."""
import tzutil
import documents_permissions as permissions
from documents_storage import rows


LIVE = "d.archived_at IS NULL AND d.canonical_id IS NULL AND d.status NOT IN ('closed','cancelled')"


def _date_label(due, today):
    if not due:
        return 'Deadline unknown'
    if due < today:
        return 'Overdue · ' + due
    if due == today:
        return 'Due today · ' + due
    return 'Due ' + due


def _card(doc, kind, action, due, today, url, detail=''):
    return {'document_id': doc['id'], 'number': doc['number'], 'subject': doc['subject'],
            'kind': kind, 'action': action, 'detail': detail, 'due': due,
            'due_label': _date_label(due, today), 'url': url,
            'overdue': bool(due and due < today)}


def _order(card, today):
    priority = {'Instruction': 0, 'Director routing': 1, 'Review': 2,
                'Reconciliation': 3, 'Contribution': 4, 'Lead follow-up': 5,
                'Division follow-up': 6}
    due = card['due']
    return (0 if due and due < today else 1 if due == today else 2 if due else 3,
            due or '9999-12-31', priority.get(card['kind'], 9), -card['document_id'])


def personal(conn, user, today=None):
    """Return each concrete personal step, including distinct unread instructions."""
    user = permissions.actor(conn, user)
    today = str(today or tzutil.today_local())
    uid = user['id']
    cards = []
    director = permissions.director(conn, user)
    documents = rows(conn, f'''SELECT d.* FROM document d WHERE {LIVE} AND (
        d.lead_id=? OR d.reviewer_id=? OR
        EXISTS(SELECT 1 FROM document_assignment a WHERE a.document_id=d.id AND a.user_id=?
            AND a.status IN ('assigned','acknowledged','in_progress')
            AND NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=d.id)) OR
        EXISTS(SELECT 1 FROM document_instruction_recipient r
            JOIN document_directive x ON x.id=r.directive_id
            LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
            WHERE x.document_id=d.id AND r.user_id=? AND seen.directive_id IS NULL
            AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id)) OR
        (?=1 AND d.instruction_state='pending')) ORDER BY d.id DESC''',
                     (uid, uid, uid, uid, int(director)))
    for doc in documents:
        if not permissions.can_view(conn, user, doc):
            continue
        base = f"/documents/{doc['id']}"
        for instruction in rows(conn, '''SELECT x.id,x.text FROM document_directive x
            JOIN document_instruction_recipient r ON r.directive_id=x.id
            LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
            WHERE x.document_id=? AND r.user_id=? AND seen.directive_id IS NULL
              AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id)
            ORDER BY x.id DESC''', (doc['id'], uid)):
            cards.append(_card(doc, 'Instruction', 'Read and acknowledge instruction', doc['due_date'], today,
                               base + f"#instruction-{instruction['id']}", instruction['text'][:240]))
        if director and doc['instruction_state'] == 'pending':
            cards.append(_card(doc, 'Director routing', 'Send routing instruction', doc['due_date'], today, base))
        if doc['status'] == 'in_review' and doc['reviewer_id'] == uid:
            cards.append(_card(doc, 'Review', 'Review current version', doc['due_date'], today, base))
        if doc['lead_id'] == uid and doc['reconcile']:
            cards.append(_card(doc, 'Reconciliation', 'Reconcile changed instruction or policy', doc['due_date'], today, base))
        for assignment in rows(conn, '''SELECT a.id,a.action,a.status,a.due_date FROM document_assignment a
            WHERE a.document_id=? AND a.user_id=? AND a.status IN ('assigned','acknowledged','in_progress')
              AND NOT EXISTS(SELECT 1 FROM work_legacy_document m WHERE m.document_id=a.document_id)
            ORDER BY a.id''', (doc['id'], uid)):
            action = {'assigned': 'Acknowledge contribution', 'acknowledged': 'Start or submit contribution',
                      'in_progress': 'Submit contribution'}[assignment['status']]
            cards.append(_card(doc, 'Contribution', action, assignment['due_date'] or doc['due_date'], today,
                               base + f"#assignment-{assignment['id']}", assignment['action']))
        if doc['lead_id'] == uid and not doc['reconcile'] and doc['instruction_state'] != 'pending':
            cards.append(_card(doc, 'Lead follow-up', 'Check progress and deadline', doc['due_date'], today, base))
    return sorted(cards, key=lambda card: _order(card, today))


def division_units(conn, user):
    user = permissions.actor(conn, user)
    return [seat['id'] for seat in permissions.seats(conn, user) if seat['level'] == 'division']


def team(conn, user, today=None):
    """Division exceptions only; every record is checked against current access."""
    user = permissions.actor(conn, user)
    units = division_units(conn, user)
    if not units:
        return []
    today = str(today or tzutil.today_local())
    cards = []
    for doc in rows(conn, f'SELECT d.* FROM document d WHERE {LIVE} ORDER BY d.id DESC'):
        if not doc['unit_id'] or not any(permissions.scope_contains(conn, unit, doc['unit_id']) for unit in units):
            continue
        if not permissions.can_view(conn, user, doc):
            continue
        reasons = []
        if not doc['lead_id']:
            reasons.append('Lead unresolved')
        if doc['reconcile']:
            reasons.append('Instruction needs reconciliation')
        if doc['due_date'] and doc['due_date'] < today:
            reasons.append('Document overdue')
        pending = conn.execute('''SELECT COUNT(*) FROM document_assignment_effective
            WHERE document_id=? AND status IN ('proposed','assigned','submitted')''', (doc['id'],)).fetchone()[0]
        if pending:
            reasons.append(f'{pending} contribution(s) need follow-up')
        late = conn.execute('''SELECT COUNT(*) FROM document_assignment_effective
            WHERE document_id=? AND status NOT IN ('completed','superseded')
              AND due_date IS NOT NULL AND due_date<?''', (doc['id'], today)).fetchone()[0]
        if late:
            reasons.append(f'{late} internal target(s) overdue')
        if reasons:
            cards.append(_card(doc, 'Division follow-up', 'Check division progress', doc['due_date'], today,
                               f"/documents/{doc['id']}", ' · '.join(reasons)))
    return sorted(cards, key=lambda card: _order(card, today))
