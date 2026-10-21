"""Frozen pre-pagination registry behavior, for independent equivalence tests."""
from datetime import datetime, date
import documents_permissions as p
import documents_rules as rules
from documents_storage import rows
from documents import get
import tzutil as tz

def legacy_visible(conn, user, query='', queue='all'):
    import documents_search as search
    user = p.actor(conn,user)
    result = []
    if queue == 'instruction' and not p.director(conn,user):
        return []
    text_matches = search.matches(conn,query,user['id']) if query else {}
    predicate = "WHERE d.instruction_state='pending' AND d.archived_at IS NULL AND d.status NOT IN ('closed','cancelled')" if queue == 'instruction' else ''
    for doc in rows(conn, '''SELECT d.*, EXISTS(SELECT 1 FROM document_email_import i
            WHERE i.document_id=d.id) AS gmail_imported FROM document d ''' + predicate + ' ORDER BY d.id DESC'):

        if not p.can_view(conn,user,doc):
            continue
        if queue == 'archived':
            if not doc['archived_at'] or not p.has_role(conn,user,'workflow_admin',doc['unit_id']):
                continue
        elif doc['archived_at']:
            continue
        refs=' '.join(r[0] for r in conn.execute('SELECT value FROM document_reference WHERE document_id=?',(doc['id'],))) if query else ''
        metadata_match = query and rules.normalize(query) in rules.normalize(doc['number']+' '+doc['subject']+' '+doc['sender']+' '+refs)
        text_match = text_matches.get(doc['id']) if not doc['canonical_id'] else None
        if query and not (metadata_match or text_match):
            continue
        if queue in ('gmail','gmail_review') and (not doc['gmail_imported'] or doc['canonical_id']):
            continue
        if queue == 'gmail_review' and (doc['verification']=='verified' or
                doc['status'] in ('closed','cancelled') or not p.officer(conn,user,doc)):
            continue
        if doc['canonical_id']:
            if query:
                canonical=get(conn,user,doc['canonical_id'])
                if not any(item['id']==canonical['id'] for item in result):
                    canonical['gmail_imported']=bool(conn.execute('SELECT 1 FROM document_email_import WHERE document_id=?',(canonical['id'],)).fetchone())
                    result.append(canonical)
            continue
        if queue in ('IN','OUT') and doc['direction'] != queue:
            continue
        if queue == 'verification' and not (doc['verification'] != 'verified' and p.officer(conn,user,doc)):
            continue
        if queue == 'review' and not (doc['status']=='in_review' and doc['reviewer_id']==user['id']):
            continue
        if queue == 'release' and not (doc['status'] in ('approved','ready_to_release') and p.can_release(conn,user,doc)):
            continue
        if queue == 'mine' and not (p.can_work(conn,user,doc) and doc['status'] not in ('closed','cancelled')):
            continue
        if queue == 'mentions' and not conn.execute('''SELECT 1 FROM document_directive x
            JOIN document_instruction_recipient r ON r.directive_id=x.id
            LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
            WHERE x.document_id=? AND r.user_id=? AND seen.directive_id IS NULL
              AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id)''',
            (doc['id'],user['id'])).fetchone():
            continue
        if queue == 'unassigned' and doc['lead_id']:
            continue
        if not any(item['id']==doc['id'] for item in result):
            if text_match:
                doc['search_source'] = search.LABELS[text_match[0]]
                doc['search_excerpt'] = search.excerpt(text_match[1],query)
            result.append(doc)
    return result

def legacy_metrics(conn,documents,today=None):
    today=today or tz.today_local()
    counts={'unassigned':0,'unacknowledged':0,'due_soon':0,'overdue':0,'review':0,'release':0,'unknown_deadline':0,'known_turnaround':0,'unknown_turnaround':0}
    durations=[]
    for doc in documents:
        live=doc['status'] not in ('closed','cancelled')
        counts['unassigned']+=live and not doc['lead_id']
        counts['unknown_deadline']+=live and not doc['due_date']
        counts['review']+=doc['status']=='in_review'
        counts['release']+=doc['status'] in ('approved','ready_to_release')
        if live and doc['due_date']:
            due=date.fromisoformat(doc['due_date'])
            counts['overdue']+=due<today
            counts['due_soon']+=today<=due<=rules.shift(conn,today,3)
        counts['unacknowledged']+=bool(conn.execute("SELECT 1 FROM document_assignment_effective WHERE document_id=? AND status IN ('proposed','assigned')",(doc['id'],)).fetchone())
        if doc['status']=='closed':
            closed=conn.execute("SELECT occurred_at FROM document_event WHERE document_id=? AND action='close' ORDER BY id DESC LIMIT 1",(doc['id'],)).fetchone()
            if closed:
                durations.append((datetime.fromisoformat(closed[0])-datetime.fromisoformat(doc['created_at'])).total_seconds()/86400)
            else:
                counts['unknown_turnaround']+=1
    counts['known_turnaround']=len(durations)
    counts['average_calendar_days']=round(sum(durations)/len(durations),2) if durations else None
    return counts
