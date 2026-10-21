"""Durable document notices, proactive deadlines, escalation and shared task rows."""
from datetime import datetime, date
import documents as d
import documents_permissions as p
import documents_rules as rules
import storage as st
import tzutil as tz
import work_compat
from documents_storage import rows, transaction


def schedule(conn, now=None):
    if not d.enabled(conn):
        return 0
    now=now or tz.now_local()
    count=0
    with transaction(conn):
        for doc in rows(conn,"SELECT * FROM document WHERE status NOT IN ('closed','cancelled') AND canonical_id IS NULL AND due_date IS NOT NULL"):
            import json
            policy=json.loads(doc['policy_json'])
            if not all(k in policy for k in ('cutoff','reminder_time','escalate_chief_days','escalate_director_days')):
                continue  # No invented timing defaults while O03 is open.
            due=date.fromisoformat(doc['due_date'])
            recipients={r[0] for r in conn.execute("SELECT user_id FROM document_assignment_effective WHERE document_id=? AND status NOT IN ('completed','superseded')",(doc['id'],))}
            recipients.add(doc['lead_id'] or doc['creator_id'])
            milestones=[(rules.shift(conn,due,-3),'three_days'),(rules.shift(conn,due,-1),'one_day'),(due,'due')]
            elapsed=[(day,kind) for day,kind in milestones if datetime.fromisoformat(day.isoformat()+'T'+policy['reminder_time'])<=now]
            kind=None
            if now>datetime.fromisoformat(due.isoformat()+'T'+policy['cutoff']):
                kind='overdue'
                days=(now.date()-due).days
                for acct in rows(conn,'SELECT id FROM admin_user WHERE active=1'):
                    if days>=policy['escalate_director_days'] and p.director(conn,acct):
                        recipients.add(acct['id'])
                    elif days>=policy['escalate_chief_days'] and p.officer(conn,acct,doc):
                        recipients.add(acct['id'])
            elif elapsed:
                kind=elapsed[-1][1]  # Delayed scheduler collapses elapsed advance milestones.
            elif doc['priority']=='urgent':
                kind='urgent'
            if kind:
                for uid in recipients:
                    if not p.can_view(conn,{'id':uid},doc):
                        continue
                    # Reassignment naturally gets a recipient-specific key. Deadline
                    # changes get a fresh date; sent history is never destroyed.
                    cycle=conn.execute("SELECT COALESCE(MAX(id),0) FROM document_event WHERE document_id=? AND action='reopen'",(doc['id'],)).fetchone()[0]
                    key=f"deadline:{doc['id']}:{doc['due_date']}:{uid}:{kind}:{cycle}"
                    cur=conn.execute("INSERT INTO document_notice(document_id,user_id,kind,dedup_key,due_at) VALUES (?,?,?,?,?) ON CONFLICT(dedup_key) DO UPDATE SET state='pending',due_at=excluded.due_at WHERE document_notice.state='cancelled'",
                                     (doc['id'],uid,'deadline:'+kind,key,tz.now_iso()))
                    count+=cur.rowcount
        for assignment in rows(conn,"SELECT a.*,d.status AS document_status FROM document_assignment_effective a JOIN document d ON d.id=a.document_id WHERE a.due_date IS NOT NULL AND a.status NOT IN ('completed','superseded') AND d.status NOT IN ('closed','cancelled') AND d.canonical_id IS NULL"):
            doc=d.raw(conn,assignment['document_id'])
            import json
            policy=json.loads(doc['policy_json'])
            if 'reminder_time' not in policy:
                continue
            due=date.fromisoformat(assignment['due_date'])
            milestones=[(rules.shift(conn,due,-3),'three_days'),(rules.shift(conn,due,-1),'one_day'),(due,'due')]
            elapsed=[kind for day,kind in milestones if datetime.fromisoformat(day.isoformat()+'T'+policy['reminder_time'])<=now]
            if not elapsed:
                continue
            kind='overdue' if now.date()>due else elapsed[-1]
            for uid in {assignment['user_id'],doc['lead_id']} - {None}:
                if p.can_view(conn,{'id':uid},doc) and work_compat.can_view_assignments(conn,{'id':uid},doc['id']):
                    cycle=conn.execute("SELECT COALESCE(MAX(id),0) FROM document_event WHERE document_id=? AND action='reopen'",(doc['id'],)).fetchone()[0]
                    key=f"milestone:{assignment['id']}:{assignment['due_date']}:{uid}:{kind}:{cycle}"
                    cur=conn.execute("INSERT INTO document_notice(document_id,user_id,kind,dedup_key,due_at) VALUES (?,?,?,?,?) ON CONFLICT(dedup_key) DO UPDATE SET state='pending',due_at=excluded.due_at WHERE document_notice.state='cancelled'",
                        (doc['id'],uid,'milestone:'+kind,key,now.isoformat()))
                    count+=cur.rowcount
    return count


def deliver(conn,base,dry_run=False):
    import mailer
    if not d.enabled(conn) or st.get_setting(conn,'documents.sending_enabled','0')!='1' or not st.email_feature_enabled(conn,'job_documents'):
        return 0
    if not dry_run:
        schedule(conn)
    count=0
    for notice in rows(conn,"SELECT * FROM document_notice WHERE state='pending' AND due_at<=? ORDER BY id",(tz.now_iso(),)):
        user=st.get_admin_user_by_id(conn,notice['user_id'])
        doc=d.raw(conn,notice['document_id'])
        if (not user or not p.can_view(conn,user,doc) or
                (notice['kind'].startswith('milestone:') and not work_compat.can_view_assignments(conn,user,doc['id']))):
            if not dry_run:
                conn.execute("UPDATE document_notice SET state='revoked' WHERE id=?",(notice['id'],)); conn.commit()
            continue
        if dry_run:
            count+=1; continue
        with transaction(conn):
            changed=conn.execute("UPDATE document_notice SET state='sending',attempts=attempts+1 WHERE id=? AND state='pending'",(notice['id'],)).rowcount
        if not changed:
            continue
        # Minimal email details: no titles, sender, deadlines or attachment links.
        subject,body,html=mailer.document_notice_message(base+'/documents/'+str(doc['id']))
        try:
            from send_reminders import _send
            rp=st.get_rp(conn,user['rp_id']) if user.get('rp_id') else None
            recipient=(rp.get('email') if rp else None) or user['username']
            result=_send(conn,'job_documents',recipient,subject,body,html=html)
            state='sent' if result.get('sent') else 'unknown'
        except Exception:
            state='unknown'
        conn.execute('UPDATE document_notice SET state=?,sent_at=?,error=? WHERE id=?',
                     (state,tz.now_iso() if state=='sent' else None,'' if state=='sent' else 'Delivery needs review.',notice['id']))
        conn.commit()
        count+=state=='sent'
    return count


def bell_rows(conn,user_id,today=None,*,reads=None):
    if not (reads.documents_enabled(conn, {'id': user_id}) if reads is not None else d.enabled(conn)):
        return []
    import work_inbox
    user = p.actor(conn, {'id': user_id})
    today = today or tz.today_local()
    items, cursor = (reads.work_preview(conn, user, today) if reads is not None else
                     work_inbox.page(conn, user, limit=3, today=today))
    result = [{'text':item['action'] + ': ' + item['title'], 'url':item['url'], 'count':1}
              for item in items if item['can_act']]
    if cursor:
        result.append({'text':'Browse My work', 'url':'/work/mine', 'count':0})
    reviews = reads.document_reviews(conn, user) if reads is not None else d.count_visible(conn, user, queue='review')
    if reviews:
        result.append({'text':f'{reviews} document reviews awaiting your decision', 'url':'/approvals', 'count':reviews})
    mentions = rows(conn, '''SELECT x.document_id FROM document_directive x
        JOIN document_instruction_recipient r ON r.directive_id=x.id
        LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
        WHERE r.user_id=? AND seen.directive_id IS NULL
          AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id)
        ORDER BY x.id DESC LIMIT 20''', (user_id,))
    visible = [item for item in mentions if p.can_view(conn,user,d.raw(conn,item['document_id']))]
    if visible:
        result.append({'text':f'{len(visible)} unread document instructions',
                       'url':'/documents?queue=mentions', 'count':len(visible)})
    return result


def home_task(conn,user):
    # Compatibility for callers expecting one card. The home page uses the full
    # personal provider and its existing approvals provider instead.
    import work_inbox
    items = work_inbox.home_rows(conn,user)
    return items[0] if items else None


def retry(conn,user,doc_id,notice_id,note):
    with transaction(conn):
        d.writable(conn); user=p.actor(conn,user); doc=d.get(conn,user,doc_id)
        notice=rows(conn,'SELECT * FROM document_notice WHERE id=? AND document_id=?',(notice_id,doc_id))
        d.require(notice and (notice[0]['user_id']==user['id'] or p.officer(conn,user,doc)))
        if notice[0]['state'] not in ('failed','unknown','sending'):
            raise ValueError('Only unresolved delivery attempts can be retried.')
        d.reason(note)
        conn.execute("UPDATE document_notice SET state='pending',error='' WHERE id=?",(notice_id,))
        from documents_storage import event
        event(conn,doc_id,user,'notice_retry',{'notice_id':notice_id,'reason':note})
