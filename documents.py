"""Document lifecycle. All public writes authenticate and own one immediate transaction.

No module operation sends mail, signs, or reads Drive implicitly. Durable external
operations live in documents_operations; human confirmation gates every transition.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo
import json
import uuid
import storage as st
import tzutil as tz
import documents_permissions as p
import documents_rules as rules
from documents_storage import rows, transaction, event


class Conflict(ValueError):
    pass


def enabled(conn):
    return st.get_setting(conn, 'documents.enabled', '0') == '1'


def writable(conn):
    if not enabled(conn):
        raise ValueError('Documents is disabled. Existing permitted records remain readable.')


def raw(conn, doc_id):
    found = rows(conn, 'SELECT * FROM document WHERE id=?', (doc_id,))
    return found[0] if found else None


def get(conn, user, doc_id):
    doc = raw(conn, doc_id)
    p.require_view(conn, user, doc)
    return doc


def list_visible(conn, user, query='', queue='all'):
    user = p.actor(conn,user)
    result = []
    for doc in rows(conn, 'SELECT * FROM document ORDER BY id DESC'):
        if not p.can_view(conn,user,doc):
            continue
        refs=' '.join(r[0] for r in conn.execute('SELECT value FROM document_reference WHERE document_id=?',(doc['id'],)))
        if query and rules.normalize(query) not in rules.normalize(doc['number']+' '+doc['subject']+' '+doc['sender']+' '+refs):
            continue
        if doc['canonical_id']:
            if query:
                canonical=get(conn,user,doc['canonical_id'])
                if canonical not in result:
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
        if queue == 'unassigned' and doc['lead_id']:
            continue
        if doc not in result:
            result.append(doc)
    return result


def check(conn, user, doc_id, revision):
    writable(conn)
    user = p.actor(conn,user)
    doc = get(conn,user,doc_id)
    if doc['canonical_id']:
        raise Conflict('This receipt was merged. Open the canonical record.')
    if conn.execute("SELECT 1 FROM document_job WHERE document_id=? AND kind IN ('sign','dispatch') AND state IN ('running','unknown')", (doc_id,)).fetchone():
        raise Conflict('An external operation is running or uncertain. Reconcile its outcome before editing.')
    if doc['revision'] != int(revision):
        raise Conflict(f"This record changed at {doc['updated_at']}; reload revision {doc['revision']} before resubmitting.")
    return user, doc


def reason(value):
    value = str(value or '').strip()
    if not value or len(value)>4000:
        raise ValueError('A reason or evidence (up to 4000 characters) is required.')
    return value


def require(ok, message='You are not authorized for this action.'):
    if not ok:
        raise p.Denied(message)


def active_account(conn, uid):
    return p.actor(conn, {'id':int(uid)})


def setup_operator(conn, user):
    user = p.actor(conn, user)
    require(user['role'] == 'admin', 'Only an active system administrator can perform initial setup.')
    return user


def setup_blocker(conn):
    if (st.get_setting(conn, 'documents.admin_setup_completed', '') or
            conn.execute("SELECT 1 FROM document_role_grant WHERE role='grant_admin' LIMIT 1").fetchone()):
        return 'Initial administrator setup is complete. Further role changes belong to the designated Documents grant administrators.'
    if (st.get_setting(conn, 'documents.enabled', '0') != '0' or
            st.get_setting(conn, 'documents.sending_enabled', '0') != '0'):
        return 'Initial setup requires Documents and document sending to be disabled.'
    return ''


def preview_admin_setup(conn, user, usernames, authorization):
    setup_operator(conn, user)
    if setup_blocker(conn):
        raise Conflict(setup_blocker(conn))
    authorization = reason(authorization)
    names = list(dict.fromkeys(str(usernames).replace(',', '\n').lower().split()))
    if not 1 <= len(names) <= 20:
        raise ValueError('Enter between 1 and 20 existing account emails, one per line.')
    accounts = []
    for name in names:
        found = rows(conn, 'SELECT id,username,active FROM admin_user WHERE lower(username)=?', (name,))
        if len(found) != 1 or not found[0]['active']:
            raise ValueError('No unique active account matches ' + name + '. Check Users before continuing.')
        accounts.append({'id': found[0]['id'], 'username': found[0]['username']})
    return {'accounts': accounts, 'authorization': authorization}


def bootstrap_admins(conn, user, preview):
    """One-time, explicitly confirmed grants; never infer document authority from app roles."""
    with transaction(conn):
        user = setup_operator(conn, user)
        if setup_blocker(conn):
            raise Conflict(setup_blocker(conn))
        accounts = preview['accounts']
        current = preview_admin_setup(conn, user, '\n'.join(a['username'] for a in accounts), preview['authorization'])
        if current != preview:
            raise Conflict('An account changed after preview. Review the accounts again.')
        now = tz.now_iso()
        for account in accounts:
            for role in ('grant_admin', 'workflow_admin'):
                if not conn.execute('SELECT 1 FROM document_role_grant WHERE user_id=? AND role=? AND unit_id IS NULL AND revoked_at IS NULL',
                                    (account['id'], role)).fetchone():
                    conn.execute('INSERT INTO document_role_grant(user_id,role,granted_by,created_at) VALUES (?,?,?,?)',
                                 (account['id'], role, user['id'], now))
        conn.execute('INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     ('documents.admin_setup_completed', now))
        event(conn, None, user, 'bootstrap_grants', {**current, 'roles': ['grant_admin', 'workflow_admin'], 'method': 'administrator setup page'})
        return current


def set_module_enabled(conn, user, turn_on, expected_revision, authorization):
    """Explicit module control; enabling never enables delivery."""
    with transaction(conn):
        user = setup_operator(conn, user)
        if turn_on:
            require(p.has_role(conn, user, 'grant_admin'),
                    'Enabling Documents requires an explicit permissions-administrator grant across all units.')
        authorization = reason(authorization)
        revision = st.get_setting(conn, 'documents.settings_revision', '0')
        if str(expected_revision) != revision:
            raise Conflict('Documents settings changed. Reload this page before confirming again.')
        before = {'enabled': st.get_setting(conn, 'documents.enabled', '0'),
                  'sending_enabled': st.get_setting(conn, 'documents.sending_enabled', '0')}
        if turn_on and before['sending_enabled'] != '0':
            raise ValueError('Disable Documents and sending before enabling for testing.')
        after = {'enabled': '1' if turn_on else '0', 'sending_enabled': '0'}
        for key, value in {**{'documents.' + k: v for k, v in after.items()},
                           'documents.settings_revision': str(int(revision) + 1)}.items():
            conn.execute('INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        event(conn, None, user, 'module_enabled' if turn_on else 'module_disabled',
              {'before': before, 'after': after, 'authorization': authorization})


def notify(conn, doc, eid, kind, extra=()):
    recipients = {doc['creator_id'], doc['lead_id']} | set(extra)
    recipients |= {r[0] for r in conn.execute("SELECT user_id FROM document_assignment WHERE document_id=? AND status<>'superseded'",(doc['id'],))}
    recipients |= {r[0] for r in conn.execute('SELECT user_id FROM document_access WHERE document_id=?',(doc['id'],))}
    for acct in rows(conn,'SELECT id FROM admin_user WHERE active=1'):
        a = p.actor(conn,acct)
        if p.officer(conn,a,doc):
            recipients.add(a['id'])
    for uid in recipients - {None}:
        if p.can_view(conn,{'id':uid},doc):
            conn.execute('INSERT OR IGNORE INTO document_notice(document_id,event_id,user_id,kind,dedup_key,due_at) VALUES (?,?,?,?,?,?)',
                         (doc['id'],eid,uid,kind,f'event:{eid}:{uid}',tz.now_iso()))


def finish(conn, user, doc, action, detail, changes=None, extra=()):
    changes = {**(changes or {}), 'revision':doc['revision']+1, 'updated_at':tz.now_iso()}
    conn.execute('UPDATE document SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',(*changes.values(),doc['id']))
    doc = raw(conn,doc['id'])
    if action in ('deadline','milestone','assign','lead','reopen','close','cancel'):
        conn.execute("UPDATE document_notice SET state='cancelled' WHERE document_id=? AND state='pending' AND (kind LIKE 'deadline:%' OR kind LIKE 'milestone:%')",(doc['id'],))
    eid = event(conn,doc['id'],user,action,detail)
    notify(conn,doc,eid,action,extra)
    return doc


def apply_route(conn, doc, evaluation):
    for uid in set(evaluation['leads'] + evaluation['assignees']):
        active_account(conn,uid)
        conn.execute('INSERT OR IGNORE INTO document_access VALUES (?,?,?)',(doc['id'],uid,'routing'))
        internal_due = None
        if doc['due_date'] and 'buffer_days' in evaluation['policy']:
            internal_due = rules.shift(conn,doc['due_date'],-evaluation['policy']['buffer_days']).isoformat()
        conn.execute('INSERT INTO document_assignment(document_id,user_id,role,action,due_date,created_at) VALUES (?,?,?,?,?,?)',
                     (doc['id'],uid,'lead' if uid in evaluation['leads'] else 'contributor','Preliminary coordination',internal_due,tz.now_iso()))


def register(conn, user, fields, now=None):
    with transaction(conn):
        writable(conn)
        user = p.actor(conn,user)
        direction = fields.get('direction','IN')
        if direction not in ('IN','OUT'):
            raise ValueError('Choose Incoming or Outgoing.')
        subject, typ = str(fields.get('subject','')).strip(), str(fields.get('type','')).strip()
        if not subject or len(subject)>500 or not typ or len(typ)>100:
            raise ValueError('Subject (up to 500 characters) and type (up to 100) are required.')
        unit = int(fields['unit_id']) if fields.get('unit_id') else None
        if unit and not conn.execute('SELECT 1 FROM org_unit WHERE id=?',(unit,)).fetchone():
            raise ValueError('Unknown unit.')
        # Registration instant, not issue date, governs permanent annual numbering.
        now = now or datetime.now(ZoneInfo('Asia/Manila'))
        if now.tzinfo is None:
            raise ValueError('Registration clock must include a timezone.')
        local = now.astimezone(ZoneInfo('Asia/Manila'))
        seq = conn.execute('INSERT INTO document_sequence(year,direction,value) VALUES (?,?,1) ON CONFLICT(year,direction) DO UPDATE SET value=value+1 RETURNING value',
                           (local.year,direction)).fetchone()[0]
        number = f'BLHSD-{direction}-{local.year}-{seq:06d}'
        timestamp = local.replace(tzinfo=None).isoformat(timespec='seconds')
        due = date.fromisoformat(fields['due_date']).isoformat() if fields.get('due_date') else None
        issued = date.fromisoformat(fields['document_date']).isoformat() if fields.get('document_date') else None
        received = str(fields.get('received_at') or timestamp)
        receipt_time=datetime.fromisoformat(received)
        if receipt_time.tzinfo is not None:
            receipt_time=receipt_time.astimezone(ZoneInfo('Asia/Manila')).replace(tzinfo=None)
        received=receipt_time.isoformat(timespec='seconds')
        sender = str(fields.get('sender','')).strip()[:500]
        evaluation = rules.evaluate(conn,{'subject':subject,'type':typ,'sender':sender})
        policy = evaluation['policy']
        source = 'explicit' if due else None
        if not due and 'default_days' in policy and 'anchor' in policy:
            anchor = received[:10] if policy['anchor']=='receipt' else timestamp[:10]
            due = rules.shift(conn,anchor,policy['default_days']).isoformat()
            source = 'default'
        lead = evaluation['leads'][0] if len(evaluation['leads'])==1 and len(evaluation.get('lead_units',[]))<=1 else None
        doc_id = conn.execute('''INSERT INTO document(number,direction,subject,type,sender,document_date,received_at,
            creator_id,unit_id,lead_id,status,priority,due_date,original_due_date,due_source,policy_json,matches_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (number,direction,subject,typ,sender,issued,received,user['id'],unit,lead,'registered' if direction=='IN' else 'draft',
             'urgent' if fields.get('priority')=='urgent' else 'normal',due,due,source,json.dumps(policy),json.dumps(evaluation),timestamp,timestamp)).lastrowid
        doc = raw(conn,doc_id)
        for ref in str(fields.get('references','')).splitlines():
            if ref.strip():
                conn.execute('INSERT INTO document_reference(document_id,kind,value) VALUES (?,?,?)',(doc_id,'external',ref.strip()[:500]))
        if direction=='IN':
            conn.execute('INSERT INTO document_receipt(document_id,channel,sender,received_at,evidence) VALUES (?,?,?,?,?)',
                         (doc_id,str(fields.get('channel') or 'unspecified')[:100],sender,received,str(fields.get('evidence',''))[:4000]))
        apply_route(conn,doc,evaluation)
        eid = event(conn,doc_id,user,'registered',{'number':number,'routing':evaluation,'scan_missing':not fields.get('drive_url')})
        if fields.get('drive_url'):
            from documents_operations import validate_drive_url
            url, file_id = validate_drive_url(fields['drive_url'])
            conn.execute('INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at) VALUES (?,?,?,?,?,?,?)',
                         (doc_id,url,file_id,'','reference',user['id'],timestamp))
        notify(conn,doc,eid,'registered')
        return doc


def rule_save(conn,user,name,body, rule_id=None, revision=None, state='draft'):
    with transaction(conn):
        writable(conn)
        user=p.actor(conn,user)
        require(p.has_role(conn,user,'workflow_admin'))
        rules.validate(body)
        if state not in ('draft','active','disabled') or not str(name).strip():
            raise ValueError('A name and valid rule state are required.')
        for uid in set(body.get('assignees',[]) + ([body['lead_id']] if body.get('lead_id') else [])):
            active_account(conn,uid)
        for unit_id in set(body.get('unit_ids',[]) + ([body['lead_unit_id']] if body.get('lead_unit_id') else [])):
            if not conn.execute('SELECT 1 FROM org_unit WHERE id=?',(unit_id,)).fetchone():
                raise ValueError('Unknown routing unit.')
        family=None
        if rule_id:
            old=rows(conn,'SELECT * FROM document_rule_version WHERE id=?',(rule_id,))
            if not old or old[0]['revision'] != int(revision):
                raise Conflict('Rule changed; reload it first.')
            family=old[0]['family_id'] or old[0]['id']
            conn.execute("UPDATE document_rule_version SET state=CASE WHEN ?='draft' THEN state ELSE 'disabled' END,revision=revision+1 WHERE id=? OR family_id=?",(state,family,family))
        # Rollback activates a new copy of a chosen old version, keeping history immutable.
        rid=conn.execute('INSERT INTO document_rule_version(name,family_id,body_json,state,actor_id,created_at) VALUES (?,?,?,?,?,?)',
                         (name,family,json.dumps(body,sort_keys=True),state,user['id'],tz.now_iso())).lastrowid
        event(conn,None,user,'rule_saved',{'id':rid,'replaces':rule_id,'state':state,'body':body})
        return rid


def grant(conn,user,target,role,unit=None,revoke_id=None):
    with transaction(conn):
        writable(conn)
        user=p.actor(conn,user)
        require(p.has_role(conn,user,'grant_admin',unit))
        active_account(conn,target)
        if role not in ('records','workflow_admin','grant_admin','signatory'):
            raise ValueError('Unknown document role.')
        if revoke_id:
            found=rows(conn,'SELECT * FROM document_role_grant WHERE id=?',(revoke_id,))
            require(found and p.has_role(conn,user,'grant_admin',found[0]['unit_id']))
            conn.execute('UPDATE document_role_grant SET revoked_at=? WHERE id=?',(tz.now_iso(),revoke_id))
        else:
            conn.execute('INSERT INTO document_role_grant(user_id,role,unit_id,granted_by,created_at) VALUES (?,?,?,?,?)',
                         (target,role,unit,user['id'],tz.now_iso()))
        event(conn,None,user,'grant_changed',{'target':target,'role':role,'unit':unit,'revoked_id':revoke_id})


def mutate(conn,user,doc_id,revision,action,data):
    with transaction(conn):
        user,doc=check(conn,user,doc_id,revision)
        officer=p.officer(conn,user,doc)
        work=p.can_work(conn,user,doc)
        coordinator=officer or doc['lead_id']==user['id']
        changes={}
        if doc['status'] in ('closed','cancelled') and action not in ('reopen','receipt','relate'):
            raise ValueError('Reopen this record before further work.')
        if action=='confirmed_fields':
            require(work)
            if doc['status'] in ('released','awaiting_acknowledgment'):
                raise ValueError('Use a linked follow-up to correct a released document.')
            reason(data.get('reason'))
            subject,typ=str(data.get('subject','')).strip(),str(data.get('type','')).strip()
            if not subject or len(subject)>500 or not typ or len(typ)>100:
                raise ValueError('Subject and document type are required within their field limits.')
            changes={'subject':subject,'type':typ,'sender':str(data.get('sender',''))[:500],
                     'verification':'pending','approved_version':None,'signed_version':None,'reconcile':1}
            if doc['direction']=='OUT':
                changes['status']='draft'
        elif action=='verify':
            require(officer)
            value=data.get('verification')
            if value not in ('verified','needs_correction'):
                raise ValueError('Choose Verified or Needs correction.')
            reason(data.get('reason'))
            changes={'verification':value,'visibility':doc['visibility'] if doc['visibility']=='restricted' else ('bureau' if value=='verified' else 'preverification')}
        elif action=='access':
            require(officer)
            if data.get('visibility') not in ('restricted','bureau'):
                raise ValueError('Choose a visibility.')
            reason(data.get('reason'))
            viewers={int(i) for i in data.get('viewers',[])}
            viewers.add(user['id'])
            for uid in viewers:
                active_account(conn,uid)
            conn.execute('DELETE FROM document_access WHERE document_id=?',(doc_id,))
            for uid in viewers:
                conn.execute('INSERT INTO document_access VALUES (?,?,?)',(doc_id,uid,'explicit'))
            changes={'visibility':data['visibility'] if doc['verification']=='verified' or data['visibility']=='restricted' else 'preverification'}
        elif action in ('assign','lead'):
            require(officer)
            uid=int(data['user_id']); active_account(conn,uid)
            reason(data.get('reason'))
            # Restricted content never becomes visible merely through an assignment.
            require(p.can_view(conn,{'id':uid},doc) or doc['visibility']!='restricted','Grant restricted access before assigning this person.')
            conn.execute('INSERT OR IGNORE INTO document_access VALUES (?,?,?)',(doc_id,uid,'assignment'))
            if action=='lead':
                changes['lead_id']=uid
            if data.get('supersede_id'):
                conn.execute("UPDATE document_assignment SET status='superseded' WHERE id=? AND document_id=?",(int(data['supersede_id']),doc_id))
            due=date.fromisoformat(data['due_date']).isoformat() if data.get('due_date') else None
            if due and doc['due_date'] and due>doc['due_date']:
                raise ValueError('A contributor deadline cannot follow the document deadline.')
            conn.execute("INSERT INTO document_assignment(document_id,user_id,role,action,status,due_date,mandatory,created_at) VALUES (?,?,?,?,'assigned',?,?,?)",
                         (doc_id,uid,'lead' if action=='lead' else 'contributor',reason(data.get('task')),due,int(data.get('mandatory',True)),tz.now_iso()))
        elif action=='contribution':
            item=rows(conn,'SELECT * FROM document_assignment WHERE id=? AND document_id=?',(int(data['assignment_id']),doc_id))
            require(item and (coordinator if data.get('status')=='completed' else
                              (item[0]['user_id']==user['id'] or officer)))
            if item[0]['status']=='superseded' or data.get('status') not in ('acknowledged','in_progress','submitted','completed'):
                raise ValueError('Invalid contribution transition.')
            if data['status']=='completed':
                require(coordinator,'The lead or concerned officer confirms completion.')
            outcome=reason(data.get('outcome'))
            conn.execute('UPDATE document_assignment SET status=?,outcome=? WHERE id=?',(data['status'],outcome,item[0]['id']))
        elif action=='directive':
            require(p.director(conn,user))
            conn.execute('INSERT INTO document_directive(document_id,actor_id,text,created_at) VALUES (?,?,?,?)',(doc_id,user['id'],reason(data.get('reason')),tz.now_iso()))
            changes={'reconcile':1,'approved_version':None,'signed_version':None}
            if doc['direction']=='OUT':
                changes['status']='changes_requested'
        elif action=='reconcile':
            require(coordinator)
            reason(data.get('reason')); changes={'reconcile':0}
        elif action=='deadline':
            require(officer)
            reason(data.get('reason'))
            due=date.fromisoformat(data['due_date']).isoformat()
            changes={'due_date':due,'due_source':'authorized_extension'}
            conn.execute("UPDATE document_notice SET state='cancelled' WHERE document_id=? AND state='pending' AND kind LIKE 'deadline:%'",(doc_id,))
        elif action=='milestone':
            require(coordinator)
            reason(data.get('reason'))
            due=date.fromisoformat(data['due_date']).isoformat()
            if doc['due_date'] and due>doc['due_date']:
                raise ValueError('Contributor deadline is after the document deadline.')
            cur=conn.execute('UPDATE document_assignment SET due_date=? WHERE id=? AND document_id=? AND status<>\'superseded\'',(due,int(data['assignment_id']),doc_id))
            if not cur.rowcount:
                raise ValueError('Assignment not found.')
        elif action in ('in_action','awaiting_external'):
            require(work)
            if doc['direction']!='IN':
                raise ValueError('This action applies to incoming documents.')
            reason(data.get('reason')); changes={'status':action}
        elif action=='review_route':
            require(officer)
            if doc['direction']!='OUT' or doc['status'] in ('released','awaiting_acknowledgment'):
                raise ValueError('Only unreleased outgoing drafts can enter review.')
            klass=data.get('review_class')
            if klass not in ('routine','director'):
                raise ValueError('Choose routine authority or Director approval.')
            reviewer=active_account(conn,int(data['reviewer_id']))
            require(p.can_view(conn,reviewer,doc),'Reviewer needs document access.')
            require(p.director(conn,reviewer) if klass=='director' else any(s['level'] in ('division','bureau') and (s['level']=='bureau' or p.scope_contains(conn,s['id'],doc['unit_id'])) for s in p.seats(conn,reviewer)), 'Reviewer does not hold the required directory authority.')
            if json.loads(doc['policy_json']).get('approval')=='director' and klass!='director':
                raise ValueError('This policy requires Director approval.')
            if not doc['current_version'] or doc['verification']!='verified' or doc['reconcile']:
                raise ValueError('Verify, reconcile directives, and attach an exact version before review.')
            reason(data.get('reason'))
            changes={'review_class':klass,'reviewer_id':reviewer['id'],'status':'in_review','approved_version':None,'signed_version':None}
        elif action=='review':
            require(doc['reviewer_id']==user['id'])
            require(p.director(conn,user) if doc['review_class']=='director' else any(s['level']=='bureau' or p.scope_contains(conn,s['id'],doc['unit_id']) for s in p.seats(conn,user)))
            if doc['status']!='in_review' or doc['reconcile'] or not doc['current_version']:
                raise ValueError('This document is not ready for review.')
            decision=data.get('decision')
            if decision not in ('approved','changes_requested'):
                raise ValueError('Choose approval or return for revision.')
            conn.execute('INSERT INTO document_review(document_id,version_id,actor_id,decision,reason,delegation_json,created_at) VALUES (?,?,?,?,?,?,?)',
                         (doc_id,doc['current_version'],user['id'],decision,reason(data.get('reason')),json.dumps(p.seats(conn,user)),tz.now_iso()))
            changes={'status':decision,'approved_version':doc['current_version'] if decision=='approved' else None,'signed_version':None}
        elif action=='receipt':
            require(officer)
            conn.execute('INSERT INTO document_receipt(document_id,channel,sender,received_at,evidence) VALUES (?,?,?,?,?)',
                         (doc_id,reason(data.get('channel')),reason(data.get('sender')),datetime.fromisoformat(data['received_at']).isoformat(),reason(data.get('evidence'))))
        elif action=='relate':
            require(work)
            target=get(conn,user,int(data['target_id']))
            if target['id']==doc_id or data.get('kind') not in ('reply','follow_up','related'):
                raise ValueError('Choose a different record and valid relationship.')
            conn.execute('INSERT OR IGNORE INTO document_relation VALUES (?,?,?)',(doc_id,target['id'],data['kind']))
        elif action=='close':
            require(coordinator)
            policy=json.loads(doc['policy_json'])
            if 'closure' not in policy:
                raise ValueError('A workflow administrator must configure closure evidence for this type.')
            evidence=data.get('evidence',{})
            if not isinstance(evidence,dict) or any(not str(evidence.get(k,'')).strip() for k in policy['closure']):
                raise ValueError('Supply all required closure evidence.')
            if 'released_reply' in policy['closure']:
                replies=rows(conn,"SELECT x.* FROM document x JOIN document_relation r ON r.source_id=x.id WHERE r.target_id=? AND r.kind='reply'",(doc_id,))
                if not replies or any(x['status'] not in ('released','awaiting_acknowledgment','closed') for x in replies):
                    raise ValueError('A linked outgoing reply must be released before closure.')
            if doc['reconcile'] or not doc['lead_id'] or doc['verification']!='verified':
                raise ValueError('Resolve ownership, verification and directives before closure.')
            if conn.execute("SELECT 1 FROM document_assignment WHERE document_id=? AND mandatory=1 AND status NOT IN ('completed','superseded')",(doc_id,)).fetchone():
                raise ValueError('Mandatory contributions are incomplete.')
            if doc['direction']=='OUT' and doc['status'] not in ('released','awaiting_acknowledgment'):
                raise ValueError('Release the outgoing document before closure.')
            if policy.get('ack_required') and conn.execute('SELECT 1 FROM document_dispatch_recipient r JOIN document_dispatch d ON d.id=r.dispatch_id WHERE d.document_id=? AND r.acknowledged_at IS NULL',(doc_id,)).fetchone():
                raise ValueError('Required recipient acknowledgment is missing.')
            changes={'status':'closed'}
        elif action=='reopen':
            require(coordinator)
            if doc['status'] not in ('closed','cancelled'):
                raise ValueError('Only closed or cancelled records can be reopened.')
            reason(data.get('reason'))
            if not data.get('due_date'):
                raise ValueError('Confirm a new deadline when reopening.')
            changes={'status':'in_action' if doc['direction']=='IN' else 'draft','due_date':date.fromisoformat(data['due_date']).isoformat(),
                     'approved_version':None,'signed_version':None,'reconcile':1}
        elif action=='cancel':
            require(officer); reason(data.get('reason'))
            if doc['status'] in ('released','awaiting_acknowledgment'):
                raise ValueError('A recorded dispatch cannot be cancelled; record a follow-up instead.')
            changes={'status':'cancelled'}
            conn.execute("UPDATE document_job SET state='cancelled' WHERE document_id=? AND state='pending'",(doc_id,))
        elif action=='reevaluate':
            require(officer)
            evaluation=rules.evaluate(conn,doc)
            if data.get('preview')!=evaluation:
                raise Conflict('Preview current rules before applying the routing diff.')
            reason(data.get('reason'))
            # Prior work/history is retained; proposed assignments are superseded explicitly.
            conn.execute("UPDATE document_assignment SET status='superseded' WHERE document_id=? AND status='proposed'",(doc_id,))
            if doc['visibility']=='restricted':
                for uid in evaluation['leads']+evaluation['assignees']:
                    require(p.can_view(conn,{'id':uid},doc),'Grant restricted access before reevaluation.')
            apply_route(conn,doc,evaluation)
            changes={'matches_json':json.dumps(evaluation),'policy_json':json.dumps(evaluation['policy']),
                     'lead_id':evaluation['leads'][0] if len(evaluation['leads'])==1 and len(evaluation.get('lead_units',[]))<=1 else None,'reconcile':1,
                     'approved_version':None,'signed_version':None}
            if doc['direction']=='OUT':
                changes['status']='changes_requested'
        else:
            raise ValueError('Unknown document action.')
        return finish(conn,user,doc,action,data,changes)


def duplicate_candidates(conn,user,doc_id):
    doc=get(conn,user,doc_id)
    refs={r[0] for r in conn.execute('SELECT value FROM document_reference WHERE document_id=?',(doc_id,))}
    files={r[0] for r in conn.execute('SELECT file_id FROM document_file_version WHERE document_id=?',(doc_id,))}
    return [d for d in list_visible(conn,user) if d['id']!=doc_id and (
        (rules.normalize(d['subject'])==rules.normalize(doc['subject']) and d['sender']==doc['sender'] and d['document_date']==doc['document_date']) or
        refs.intersection(r[0] for r in conn.execute('SELECT value FROM document_reference WHERE document_id=?',(d['id'],))) or
        files.intersection(r[0] for r in conn.execute('SELECT file_id FROM document_file_version WHERE document_id=?',(d['id'],))))]


def merge_preview(conn,user,source_id,target_id):
    source,target=get(conn,user,source_id),get(conn,user,target_id)
    require(source_id!=target_id and not source['canonical_id'] and not target['canonical_id'])
    require(p.officer(conn,p.actor(conn,user),source) and p.officer(conn,p.actor(conn,user),target))
    return {'source_id':source_id,'target_id':target_id,'source_revision':source['revision'],'target_revision':target['revision'],
            'source_lead':source['lead_id'],'target_lead':target['lead_id'],'source_due':source['due_date'],'target_due':target['due_date']}


def merge(conn,user,preview,note):
    with transaction(conn):
        writable(conn); user=p.actor(conn,user); reason(note)
        current=merge_preview(conn,user,preview['source_id'],preview['target_id'])
        if current!=preview:
            raise Conflict('Merge preview is stale.')
        source,target=raw(conn,preview['source_id']),raw(conn,preview['target_id'])
        if source['lead_id']!=target['lead_id'] or source['due_date']!=target['due_date']:
            raise ValueError('Resolve different leads and deadlines before merging.')
        # Retain originals as immutable receipt history. Canonical visibility is the
        # intersection, never union, of prior readership, including pending records.
        viewers=[r['id'] for r in rows(conn,'SELECT id FROM admin_user WHERE active=1') if p.can_view(conn,r,source) and p.can_view(conn,r,target)]
        require(user['id'] in viewers)
        conn.execute('DELETE FROM document_access WHERE document_id=?',(target['id'],))
        for uid in viewers:
            conn.execute('INSERT INTO document_access VALUES (?,?,?)',(target['id'],uid,'merge'))
        conn.execute('INSERT INTO document_relation VALUES (?,?,?)',(source['id'],target['id'],'merged'))
        finish(conn,user,target,'merge_received',{'source':source['id'],'reason':note},{'visibility':'restricted'})
        return finish(conn,user,source,'merged',{'target':target['id'],'reason':note},{'canonical_id':target['id']})


def reverse_merge(conn,user,source_id,note):
    """Correct a merge without restoring old broad visibility or deleting history."""
    with transaction(conn):
        writable(conn); user=p.actor(conn,user); reason(note)
        source=get(conn,user,source_id)
        if not source['canonical_id']:
            raise ValueError('This record is not merged.')
        target=get(conn,user,source['canonical_id'])
        require(p.officer(conn,user,source) and p.officer(conn,user,target))
        viewers=[r['id'] for r in rows(conn,'SELECT id FROM admin_user WHERE active=1') if p.can_view(conn,r,target)]
        conn.execute('DELETE FROM document_access WHERE document_id=?',(source_id,))
        for uid in viewers:
            conn.execute('INSERT INTO document_access VALUES (?,?,?)',(source_id,uid,'merge_correction'))
        finish(conn,user,target,'merge_corrected',{'source':source_id,'reason':note})
        return finish(conn,user,source,'merge_reversed',{'former_canonical':target['id'],'reason':note},
                      {'canonical_id':None,'visibility':'restricted','reconcile':1})


def metrics(conn,documents,today=None):
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
        counts['unacknowledged']+=bool(conn.execute("SELECT 1 FROM document_assignment WHERE document_id=? AND status IN ('proposed','assigned')",(doc['id'],)).fetchone())
        if doc['status']=='closed':
            closed=conn.execute("SELECT occurred_at FROM document_event WHERE document_id=? AND action='close' ORDER BY id DESC LIMIT 1",(doc['id'],)).fetchone()
            if closed:
                durations.append((datetime.fromisoformat(closed[0])-datetime.fromisoformat(doc['created_at'])).total_seconds()/86400)
            else:
                counts['unknown_turnaround']+=1
    counts['known_turnaround']=len(durations)
    counts['average_calendar_days']=round(sum(durations)/len(durations),2) if durations else None
    return counts
