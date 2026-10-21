"""Read-only next-step guidance from the current, permission-filtered detail snapshot.

Links open existing controls. Submissions retain their own fresh authorization,
revision, exact-version and external-operation checks; a link is never approval.
"""
import documents as docs
import documents_permissions as permissions
import work_completion


def build(conn, user, values):
    doc=values['doc']
    policy=values['policy']
    officer=values['officer']
    can_work=values['can_work']
    coordinator=officer or doc['lead_id']==user['id']
    lead=doc['lead_id']
    cases=values['work_cases']  # Already filtered through work visibility.
    case_link='/work/'+str(cases[0]['id']) if cases else None
    contributions=[{'label':a['progress_choices'][0][1]+': '+a['action'],
                    'href':'#document-contribution-'+str(a['id'])}
                   for a in values['assignments'] if a['progress_choices']][:4]

    def result(stage, title, message, *, owner=lead, role='Document lead', action=None,
               label=None, allowed=False, href=None, blocker=None, personal=False):
        link=({'label':label,'href':href or '#document-action-'+action}
              if allowed and label and (href or action) else None)
        return {'stage':stage,'title':title,'message':message,'owner_id':owner,
                'owner_role':role,'action':link,'blocker':blocker,
                'contributions':contributions if personal else []}

    def closure():
        blockers=docs.closure_blockers(conn,doc,policy)
        if blockers:
            first=blockers[0]
            code=first['code']
            if code=='policy':
                return result('closure_policy','Confirm the closure requirements',
                    'Ask the workflow administrator to configure closure evidence for this document type.',
                    owner=None,role='Workflow administrator',blocker=first['message'])
            if code=='acknowledgment':
                return result('acknowledgment','Record recipient acknowledgment',
                    'Check the recipient outcomes and record acknowledgment evidence for each required recipient.',
                    owner=None,role='Records officer or authorized contributor',
                    action='acknowledge',label='Record acknowledgment',allowed=values['can_release'],
                    blocker=first['message'])
            if code=='contributions':
                return result('contributions','Finish the required contributions',
                    'Contributors submit their work; the lead or records officer confirms completion. Open shared work for migrated assignments.',
                    href=case_link,label='Open shared work',allowed=bool(case_link),
                    blocker=first['message'],personal=True)
            if code=='reply':
                return result('reply','Release and link the outgoing reply',
                    'Complete the outgoing reply and link it to this incoming record before closing it.',
                    action='relate',label='Link the reply',allowed=can_work,
                    blocker=first['message'],personal=True)
            return result('closure_blocked','Resolve the remaining closure requirements',
                'Ask the document lead or records officer to review the record.',blocker=first['message'])
        return result('close','Record the outcome and close',
            'Check that the work is complete, then supply the required closure evidence. Closing this document does not complete a linked work item.',
            action='close',label='Review closure requirements',allowed=coordinator)

    if not docs.enabled(conn):
        return result('disabled','This record is read-only','Documents is disabled. Existing records and their history remain readable.',owner=None,role='Workflow administrator')
    if doc['archived_at']:
        return result('archived','Restore before making changes','The archived record and its history are retained. A workflow administrator can restore it with a reason.',
            owner=None,role='Workflow administrator',action='restore',label='Restore this record',allowed=values['can_archive'])
    if doc['status'] in ('closed','cancelled'):
        return result('complete','This record is '+doc['status'],
            'History is retained. If more work is required, the lead or records officer can reopen it with a reason and a new deadline.',
            action='reopen',label='Reopen with a new deadline',allowed=coordinator)
    uncertain=[j for j in values['jobs'] if j['kind'] in ('sign','dispatch') and j['state'] in ('pending','running','unknown')]
    if uncertain:
        job=uncertain[-1]
        return result('operation','Check the existing signing or delivery request',
            'The request is pending, running or awaiting a confirmed outcome. Check its progress and service receipt before making another request; do not resend an uncertain delivery.',
            owner=job['actor_id'],role='Person who requested the operation',href='#document-operations',
            label='View operation progress',allowed=True,
            blocker='The external operation has not reached a confirmed final outcome.')
    if doc['verification']=='needs_correction':
        return result('correction','Correct the document details',
            'Check the source and correct the fields, then ask the records officer to verify them again.',
            owner=lead or doc['creator_id'],action='confirmed_fields',label='Correct document fields',allowed=can_work,
            blocker='The verification decision requests a correction.')
    if doc['verification']!='verified':
        return result('verification','Verify the source and document details',
            'The records officer checks the source, type, sender and other details before recording a verification decision.',
            owner=None,role='Concerned records officer',action='verify',label='Verify or request correction',allowed=officer,
            blocker='Document verification is pending.')
    if doc['instruction_state']=='pending':
        return result('instruction','Confirm the initial instruction and routing',
            'The Director or bureau OIC gives the instruction and identifies the responsible lead.',
            owner=None,role='Director or bureau OIC',action='route_instruction',label='Give the routing instruction',
            allowed=permissions.director(conn,user),blocker='The initial routing instruction is pending.')
    if not lead:
        return result('lead','Identify the responsible lead',
            'The records officer confirms ownership. Migrated assignments are managed in shared work.',
            owner=None,role='Concerned records officer',action='lead',href=case_link if values['assignments_migrated'] else None,
            label='Open shared work' if values['assignments_migrated'] else 'Confirm the lead',
            allowed=bool(case_link) if values['assignments_migrated'] else officer,
            blocker='No document lead has been confirmed.')
    if doc['reconcile']:
        return result('reconcile','Reconcile the changed instructions',
            'The lead or records officer explains how the existing work addresses the changed instruction or policy before review continues.',
            action='reconcile',label='Reconcile instructions',allowed=coordinator,
            blocker='Changed instructions or policy need reconciliation.')
    if doc['direction']=='IN':
        if doc['status']=='awaiting_external':
            return result('external_wait','Follow up the external response',
                'The document deadline continues while waiting. When a response arrives, record its receipt and resume internal action.',
                action='in_action',label='Resume internal action',allowed=can_work,personal=True)
        return closure()
    if doc['status'] in ('released','awaiting_acknowledgment'):
        return closure()
    current=next((v for v in values['versions'] if v['id']==doc['current_version']),None)
    if not current or not current['fingerprint']:
        return result('draft','Attach an exact draft for review',
            'Prepare the outgoing draft and attach a checked Drive version so the reviewer can approve the exact content.',
            action='attach',label='Attach the draft',allowed=can_work,personal=True)
    consolidation=values['consolidation']
    packet_exists=conn.execute('SELECT 1 FROM work_review_packet WHERE document_id=?',(doc['id'],)).fetchone()
    if packet_exists and (not consolidation or not consolidation['current']):
        href='/work/'+str(consolidation['case']['id'])+'/consolidation' if consolidation else None
        return result('consolidation','Request renewed shared-work review',
            'Ask the lead to check the shared-work inputs and request review of the current exact draft.',
            href=href,label='Open consolidation review',allowed=bool(href),
            blocker='The shared-work review is unavailable to you or its inputs have changed.',personal=True)
    if doc['status']=='changes_requested':
        return result('revision','Revise the returned draft',
            'Read the review feedback, revise the draft and attach its exact new version. The revised version needs renewed approval.',
            action='attach',label='Attach the revised draft',allowed=can_work,
            blocker='The reviewer returned the draft for revision.',personal=True)
    if doc['status']=='in_review':
        try:
            reviewer=permissions.actor(conn,{'id':doc['reviewer_id']})
            authority=permissions.review_authority(conn,reviewer,doc) and permissions.can_view(conn,reviewer,doc)
        except permissions.Denied:
            authority=False
        if not authority:
            return result('review_authority','Confirm current review authority',
                'The assigned reviewer no longer has the required active authority or document access. Ask the records officer to confirm the reviewer.',
                owner=None,role='Concerned records officer',action='review_route',label='Confirm the reviewer',
                allowed=officer and not consolidation,blocker='Current reviewer authority needs confirmation.')
        return result('review','Review the exact current draft',
            'The assigned reviewer approves this version or returns it with a reason. Approval does not sign or send it.',
            owner=doc['reviewer_id'],role='Assigned reviewer',action='review',label='Review this exact version',
            allowed=doc['reviewer_id']==user['id'],personal=True)
    if doc['approved_version']!=doc['current_version']:
        href='/work/'+str(consolidation['case']['id'])+'/consolidation' if consolidation else None
        return result('approval','Request approval of the current draft',
            'The records officer confirms review authority and requests approval of this exact version.',
            owner=None,role='Concerned records officer',href=href,action='review_route',
            label='Open consolidation review' if href else 'Request review',allowed=bool(href) or officer,personal=True)
    if any(key not in policy for key in ('signature_required','release','ack_required')):
        return result('release_policy','Confirm the release requirements',
            'Ask the workflow administrator to configure signing, release evidence and acknowledgment requirements for this type.',
            owner=None,role='Workflow administrator',blocker='The release policy is incomplete.')
    if policy['signature_required'] and doc['signed_version']!=doc['current_version']:
        return result('signature','Sign the approved exact version',
            'An authorized signatory checks and signs the approved content, or records their matching externally signed copy. Signing does not dispatch it.',
            owner=None,role='Authorized signatory',action='sign_preview' if can_work else 'external_signature',
            label='Review signing options',allowed=values['signatory'])
    try:
        work_completion.release_gate(conn,doc)
    except ValueError:
        return result('release_contributions','Finish shared-work contributions before release',
            'Ask the lead to resolve outstanding contributions and changed-input blockers.',
            href=case_link,label='Open shared work',allowed=bool(case_link),
            blocker='Shared-work contributions are not ready for release.',personal=True)
    dispatch_ids={x['id'] for x in values['dispatches'] if x['version_id']==doc['current_version']}
    outcomes=[r for r in values['recipient_outcomes'] if r['dispatch_id'] in dispatch_ids]
    if any(r['outcome']=='unknown' for r in outcomes):
        return result('delivery_unknown','Check the uncertain delivery outcome',
            'Check the original service receipt with the records officer. Do not resend to recipients whose delivery is accepted or uncertain.',
            owner=None,role='Concerned records officer',href='#document-recipient-outcomes',
            label='Review recipient outcomes',allowed=True,blocker='At least one delivery outcome is uncertain.')
    if outcomes:
        return result('delivery_partial','Review delivery for each recipient',
            'Accepted deliveries remain recorded. Review the evidence before retrying only confirmed failed recipients; do not resend to accepted recipients.',
            owner=None,role='Records officer or authorized contributor',href='#document-recipient-outcomes',
            label='Review recipient outcomes',allowed=True,blocker='Delivery is not yet complete for all recipients.')
    return result('release','Prepare release and record delivery evidence',
        'An authorized records officer or contributor records an existing email or physical dispatch with its recipients and required evidence. Official mailbox sending is also available when configured. Approval and signing alone are not delivery.',
        owner=None,role='Records officer or authorized contributor',action='record_dispatch',label='Review release requirements',allowed=values['can_release'])
