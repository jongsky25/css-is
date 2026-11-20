"""Advisory policy adapter for shared Documents decisions and Work discussion."""
import json
import uuid

import advisory_workflow as aw
import documents as d
import documents_permissions as p
from documents_storage import rows, transaction, event
import storage as st
import tzutil as tz
import work
import work_discussion

POLICY={'version':1,'stages':['chief','director'],'signature_required':False,'self_review':False}
ACTIONS={'submit','endorse','approve','return','withdraw','reroute','comment','resolve','reopen_concern','cancel','notice_retry'}


def effective_chief(conn, unit_id):
    oic=conn.execute('SELECT admin_user_id FROM section_oic WHERE org_unit_id=?',(unit_id,)).fetchone()
    candidates=[oic[0]] if oic else st.org_unit_chiefs(conn,unit_id)
    if len(candidates)!=1:
        raise ValueError('The owning division needs exactly one current Division Chief or designated OIC.')
    return p.actor(conn,{'id':candidates[0]})['id']


def effective_director(conn):
    acting=rows(conn,"SELECT o.admin_user_id FROM section_oic o JOIN org_unit u ON u.id=o.org_unit_id WHERE u.level='bureau'")
    candidates=[r['admin_user_id'] for r in acting] if acting else st._org_accounts_at_rank(conn,3)
    if len(candidates)!=1:
        raise ValueError('Exactly one current Director or designated bureau OIC is required.')
    return p.actor(conn,{'id':candidates[0]})['id']


def routing(conn, record):
    chief=effective_chief(conn,record['unit_id']); director=effective_director(conn)
    if len({chief,director,record['initiator_id']})!=3:
        raise ValueError('Preparer, Division Chief reviewer and Director approver must be different people. Correct the formal routing first.')
    return chief,director


def packet(conn, record):
    found=rows(conn,'SELECT * FROM advisory_review_packet WHERE id=? AND advisory_id=?',(record.get('active_packet'),record['id']))
    return found[0] if found else None


def require_current(conn,doc):
    record=aw.for_document(conn,doc['id']); review=packet(conn,record)
    if not review:raise d.Conflict('Submit this advisory for Division Chief review first.')
    revision=rows(conn,'SELECT * FROM advisory_revision WHERE id=? AND advisory_id=?',(record['current_revision'],record['id']))[0]
    if (review['revision_id']!=revision['id'] or review['version_id']!=doc['current_version'] or
            review['digest']!=revision['payload_hash'] or review['unit_id']!=record['unit_id'] or
            json.loads(review['policy_json'])['policy']!=POLICY):
        raise d.Conflict('The reviewed version or policy changed. Renew Division Chief review.')
    artifacts=rows(conn,'SELECT data,sha256 FROM advisory_artifact WHERE revision_id=?',(revision['id'],))
    if len(artifacts)!=2:raise d.Conflict('The reviewed artifacts are unavailable.')
    for artifact in artifacts:
        if aw.digest(artifact['data'])!=artifact['sha256']:raise d.Conflict('The reviewed artifact is unavailable.')
    return review


def stage_authority(conn,user,record,stage):
    expected=effective_chief(conn,record['unit_id']) if stage=='chief' else effective_director(conn)
    return user['id']==expected and user['id']!=record['initiator_id']


def _case(conn,user,record):
    if record.get('case_id'):return record['case_id']
    case=work.create_in_transaction(conn,user,{'title':'Advisory '+record['number'],
        'outcome':'Review and issue the approved advisory','unit_id':record['unit_id']})
    work.link_document_in_transaction(conn,user,case['id'],case['revision'],record['document_id'])
    conn.execute('UPDATE advisory_record SET case_id=? WHERE id=?',(case['id'],record['id']))
    return case['id']


def _finish(conn,user,doc,action,reason,changes,record,**detail):
    updated=d.finish(conn,user,doc,'advisory_'+action,{'advisory_id':record['id'],
        'packet_id':record.get('active_packet'),'revision_id':record['current_revision'],'reason':reason,**detail},changes)
    eid=conn.execute('SELECT MAX(id) FROM document_event WHERE document_id=?',(doc['id'],)).fetchone()[0]
    return updated,eid


def mutate(conn,user,advisory_id,revision,action,data):
    import advisory_distribution
    if action not in ACTIONS | advisory_distribution.ACTIONS:raise ValueError('Choose an advisory action.')
    user=p.actor(conn,user)
    try: key=str(uuid.UUID(str(data.get('operation_key','')))); revision=int(revision)
    except (ValueError,TypeError):raise ValueError('Reload the advisory action form.') from None
    request_hash=aw.digest(aw.encoded([advisory_id,revision,action,data]))
    reason=str(data.get('reason') or '').strip()
    if not reason or len(reason)>4000:raise ValueError('Provide a reason or comment, up to 4000 characters.')
    with transaction(conn):
        record=aw.get_visible(conn,user,advisory_id); work.writable(conn)
        user=p.actor(conn,user)
        receipt=rows(conn,'SELECT * FROM advisory_action_request WHERE actor_id=? AND operation_key=?',(user['id'],key))
        if receipt:
            if receipt[0]['advisory_id']!=advisory_id or receipt[0]['payload_hash']!=request_hash:
                raise d.Conflict('This action key was used for different contents. Reload.')
            return record
        user,doc=d.check(conn,user,record['document_id'],revision,allow_advisory=True)
        is_author=user['id']==record['initiator_id']
        if action in advisory_distribution.ACTIONS:
            eid=advisory_distribution.mutate_in_transaction(conn,user,record,doc,action,data,reason)
        elif action in ('submit','reroute'):
            d.require(is_author)
            if doc['status'] not in (('in_review',) if action=='reroute' else ('draft','changes_requested')):
                raise ValueError('Return or withdraw the current submission before submitting again.')
            chief,director=routing(conn,record)
            _case(conn,user,record)
            conn.execute("DELETE FROM document_access WHERE document_id=? AND source='advisory_routing'",(doc['id'],))
            for uid in (chief,director):conn.execute('INSERT OR IGNORE INTO document_access VALUES (?,?,?)',(doc['id'],uid,'advisory_routing'))
            saved=rows(conn,'SELECT * FROM advisory_revision WHERE id=?',(record['current_revision'],))[0]
            policy={'policy':POLICY,'chief_seats':p.seats(conn,{'id':chief}),'director_seats':p.seats(conn,{'id':director})}
            pid=conn.execute('''INSERT INTO advisory_review_packet(advisory_id,revision_id,version_id,chief_id,director_id,
                unit_id,digest,policy_json,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (record['id'],saved['id'],saved['version_id'],chief,director,record['unit_id'],saved['payload_hash'],aw.encoded(policy),user['id'],tz.now_iso())).lastrowid
            record['active_packet']=pid
            conn.execute('UPDATE advisory_record SET active_packet=? WHERE id=?',(pid,record['id']))
            _,eid=_finish(conn,user,doc,'submitted' if action=='submit' else 'rerouted',reason,
                {'status':'in_review','review_class':'chief','reviewer_id':chief,'approved_version':None,
                 'signed_version':None,'verification':'verified','lead_id':record['initiator_id']},record)
        elif action in ('endorse','approve','return'):
            review=require_current(conn,doc); stage=doc['review_class']
            if routing(conn,record)!=(review['chief_id'],review['director_id']):
                raise d.Conflict('Routing changed. The initiator must reroute this submission.')
            d.require(doc['status']=='in_review' and doc['reviewer_id']==user['id'])
            d.require(stage in ('chief','director') and stage_authority(conn,user,record,stage),'Your current directory authority does not match this review stage.')
            if action=='endorse' and stage!='chief' or action=='approve' and stage!='director':
                raise ValueError('Use the action for the current review stage.')
            if stage=='director' and not conn.execute('''SELECT 1 FROM advisory_decision a JOIN document_review r ON r.id=a.review_id
                WHERE a.packet_id=? AND a.stage='chief' AND r.decision='endorsed' ''',(review['id'],)).fetchone():
                raise d.Conflict('Division Chief endorsement of this exact packet is required.')
            if action=='endorse' and effective_director(conn)!=review['director_id']:
                raise d.Conflict('The Director assignment changed. Ask the initiator to reroute this submission.')
            decision={'endorse':'endorsed','approve':'approved','return':'changes_requested'}[action]
            rid=d.record_review_in_transaction(conn,user,doc,decision,reason,delegation=p.seats(conn,user))
            conn.execute('INSERT INTO advisory_decision VALUES (?,?,?)',(rid,review['id'],stage))
            changes=({'review_class':'director','reviewer_id':review['director_id'],'approved_version':None} if action=='endorse' else
                {'status':'approved','approved_version':doc['current_version'],'reviewer_id':None} if action=='approve' else
                {'status':'changes_requested','approved_version':None,'signed_version':None,'reviewer_id':None})
            _,eid=_finish(conn,user,doc,{'endorse':'endorsed','approve':'approved','return':'returned'}[action],reason,changes,record,review_id=rid,stage=stage)
        elif action in ('withdraw','cancel'):
            d.require(is_author)
            if action=='cancel' and advisory_distribution.latest(conn,record['id']):
                raise ValueError('Use Cancel issued advisory to preserve its delivery and publication history.')
            allowed=('in_review','approved','changes_requested') if action=='withdraw' else ('draft','in_review','approved','changes_requested')
            if doc['status'] not in allowed:raise ValueError('This action is unavailable in the current state.')
            _,eid=_finish(conn,user,doc,'withdrawn' if action=='withdraw' else 'cancelled',reason,
                {'status':'draft' if action=='withdraw' else 'cancelled','approved_version':None,'signed_version':None,'reviewer_id':None},record)
        elif action=='notice_retry':
            import documents_notify
            eid=documents_notify.retry_in_transaction(conn,user,doc,int(data.get('notice_id') or 0),reason)
        elif action=='comment':
            if doc['status'] in ('cancelled','superseded'):raise ValueError('This advisory is read-only.')
            case_id=record.get('case_id')
            if not case_id:raise ValueError('Submit the advisory before starting its review discussion.')
            parent=int(data.get('parent_id') or 0) or None
            target=int(data.get('revision_id') or record['current_revision'])
            if not conn.execute('SELECT 1 FROM advisory_revision WHERE id=? AND advisory_id=?',(target,record['id'])).fetchone():
                raise ValueError('Choose a revision belonging to this advisory.')
            if parent:
                binding=conn.execute('SELECT revision_id FROM advisory_comment WHERE comment_id=? AND advisory_id=?',(parent,record['id'])).fetchone()
                if not binding or binding[0]!=target:raise ValueError('Reply in the original revision thread.')
            cid=work_discussion.post_in_transaction(conn,user,case_id,reason,parent_id=parent,advisory_revision_id=target,notify=False)
            conn.execute('INSERT INTO advisory_comment VALUES (?,?,?)',(cid,record['id'],target))
            eid=event(conn,doc['id'],user,'advisory_comment',{'comment_id':cid,'revision_id':target})
        else:
            if doc['status'] in ('cancelled','superseded'):raise ValueError('This advisory is read-only.')
            cid=int(data.get('comment_id') or 0)
            root=rows(conn,'''SELECT c.* FROM work_comment c JOIN advisory_comment a ON a.comment_id=c.id
                WHERE c.id=? AND a.advisory_id=? AND c.parent_id IS NULL''',(cid,record['id']))
            if not root:raise ValueError('Choose a concern on this advisory.')
            d.require(stage_authority(conn,user,record,'chief') or stage_authority(conn,user,record,'director'),
                      'Only a current reviewer or approver may resolve or reopen a concern.')
            conn.execute('INSERT INTO advisory_concern_event(comment_id,actor_id,disposition,reason,created_at) VALUES (?,?,?,?,?)',
                (cid,user['id'],'resolved' if action=='resolve' else 'open',reason,tz.now_iso()))
            eid=event(conn,doc['id'],user,'advisory_concern_'+action,{'comment_id':cid,'reason':reason})
        conn.execute('INSERT INTO advisory_action_request VALUES (?,?,?,?,?)',(user['id'],key,record['id'],request_hash,eid))
        return aw.get_visible(conn,user,record['id'])


def notify(conn,doc,eid,kind):
    record=aw.for_document(conn,doc['id'])
    if kind in ('advisory_submitted','advisory_rerouted','advisory_endorsed'):targets=[doc['reviewer_id']]
    elif kind in ('advisory_returned','advisory_approved'):
        targets=[record['initiator_id']]
        if kind=='advisory_approved':
            targets += [r[0] for r in conn.execute("SELECT user_id FROM document_access WHERE document_id=? AND source='advisory_release'",(doc['id'],)) if p.has_role(conn,{'id':r[0]},'records',record['unit_id'])]
    else:return
    for uid in set(targets)-{None}:
        if p.can_view(conn,{'id':uid},doc):
            conn.execute('''INSERT OR IGNORE INTO document_notice(document_id,event_id,user_id,kind,dedup_key,due_at)
                VALUES (?,?,?,?,?,?)''',(doc['id'],eid,uid,kind,f'advisory:{eid}:{uid}',tz.now_iso()))


def notice_current(conn,doc,notice):
    record=aw.for_document(conn,doc['id'])
    detail=conn.execute('SELECT detail_json FROM document_event WHERE id=?',(notice['event_id'],)).fetchone()
    if not record or not detail or json.loads(detail[0]).get('packet_id')!=record['active_packet']:return False
    kind=notice['kind']
    if kind in ('advisory_submitted','advisory_rerouted','advisory_endorsed'):
        try:
            current=packet(conn,record)
            if routing(conn,record)!=(current['chief_id'],current['director_id']):return False
        except ValueError:return False
        return doc['status']=='in_review' and doc['reviewer_id']==notice['user_id']
    return doc['status']==('approved' if kind=='advisory_approved' else 'changes_requested')


def screen(conn,user,record,comments_before=0,actions_before=0):
    doc=d.get(conn,user,record['document_id']); review=packet(conn,record)
    actions=[];problem=''
    if user['id']==record['initiator_id']:
        if doc['status'] in ('draft','changes_requested'):actions.append(('submit','Submit to Division Chief'))
        if doc['status'] in ('in_review','approved','changes_requested'):actions.append(('withdraw','Withdraw for revision'))
        if doc['status']=='in_review':actions.append(('reroute','Resolve routing and restart review'))
        if doc['status'] in ('draft','in_review','approved','changes_requested'):actions.append(('cancel','Cancel advisory'))
    if doc['status']=='in_review':
        try:
            chief,director=routing(conn,record)
            if review and (chief!=review['chief_id'] or director!=review['director_id']):problem='Routing changed. The initiator must reroute this submission.'
            if not problem and user['id']==doc['reviewer_id']:
                actions += [('endorse','Endorse to Director')] if doc['review_class']=='chief' else [('approve','Approve this revision')]
                actions.append(('return','Return for changes'))
        except ValueError as error:problem=str(error)
    discussion=[]
    if record.get('case_id'):
        discussion=rows(conn,'''SELECT a.revision_id,c.id,c.parent_id,u.username AS author,r.body,c.created_at,
            COALESCE((SELECT disposition FROM advisory_concern_event e WHERE e.comment_id=c.id ORDER BY id DESC LIMIT 1),'open') AS concern
            FROM advisory_comment a JOIN work_comment c ON c.id=a.comment_id JOIN admin_user u ON u.id=c.author_id
            JOIN work_comment_revision r ON r.comment_id=c.id AND r.revision=(SELECT MAX(revision) FROM work_comment_revision WHERE comment_id=c.id)
            WHERE a.advisory_id=? AND (?=0 OR c.id<?) ORDER BY c.id DESC LIMIT 31''',(record['id'],comments_before,comments_before))
    can_resolve=False
    try:can_resolve=stage_authority(conn,user,record,'chief') or stage_authority(conn,user,record,'director')
    except ValueError:pass
    timeline=rows(conn,'''SELECT e.id,e.action,e.detail_json,e.occurred_at,u.username AS author FROM document_event e
        LEFT JOIN admin_user u ON u.id=e.actor_id WHERE document_id=? AND (?=0 OR e.id<?) ORDER BY e.id DESC LIMIT 31''',(doc['id'],actions_before,actions_before))
    for entry in timeline:entry['detail']=json.loads(entry['detail_json'])
    notices=rows(conn,'''SELECT n.id,n.state,n.kind,u.username AS recipient FROM document_notice n
        JOIN admin_user u ON u.id=n.user_id WHERE n.document_id=? ORDER BY n.id DESC LIMIT 30''',(doc['id'],))
    return {'notices':notices,'actions':actions,'routing_problem':problem,'stage':doc['review_class'] if doc['status']=='in_review' else None,
            'discussion':discussion[:30],'older_comments':discussion[29]['id'] if len(discussion)>30 else None,
            'can_resolve':can_resolve,'timeline':timeline[:30],'older_actions':timeline[29]['id'] if len(timeline)>30 else None,'status':doc['status'],
            'can_comment':bool(record.get('case_id')) and doc['status'] not in ('cancelled','superseded')}


def guidance(conn,user,doc):
    record=aw.for_document(conn,doc['id'])
    owner=doc['reviewer_id'] if doc['status']=='in_review' else record['initiator_id']
    title={'draft':'Prepare the advisory','changes_requested':'Address review feedback',
           'approved':'Prepare issuance','cancelled':'Advisory cancelled'}.get(doc['status'],'Review the advisory')
    role=('Division Chief' if doc['review_class']=='chief' else 'Director') if doc['status']=='in_review' else 'Initiator'
    import advisory_distribution
    if doc['status']=='approved' and advisory_distribution.can_issue(conn,user,record):owner=user['id'];role='Authorized issuer'
    stage='review' if doc['status']=='in_review' else doc['status']
    if doc['status']=='issued':
        attention=conn.execute("SELECT 1 FROM advisory_delivery a JOIN document_job j ON j.id=a.job_id WHERE j.document_id=? AND j.state IN ('failed','unknown') AND NOT EXISTS (SELECT 1 FROM advisory_delivery newer JOIN document_job n ON n.id=newer.job_id WHERE newer.issue_id=a.issue_id AND newer.recipient=a.recipient AND n.rowid>j.rowid)",(doc['id'],)).fetchone()
        stage='delivery_partial' if attention else 'complete'
        title='Check advisory delivery' if attention else 'Advisory issued'
    enabled=aw.available(conn)
    allowed=enabled and owner==user['id'] and doc['status'] not in ('cancelled','superseded') and stage!='complete'
    return {'stage':stage, 'title':title,
            'message':'Open the advisory to see its exact revision, feedback and available actions.',
            'owner_id':owner,'owner_role':role,'action':({'label':'Open advisory','href':'/advisories/'+str(record['id'])} if allowed else None),
            'blocker':None,'contributions':[]}
