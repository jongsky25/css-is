"""Display facts from an already authorised travel filing and its current checklist."""
import travel_rules as rules


def filing(f, items, flags, *, owner, can_verify=False, review_required=False, reviewer=''):
    base = f"/travel/f/{f['ref_code']}"
    status = f.get('status')
    blockers = rules.readiness(f, items, flags) if status in ('open', 'ready') else []
    action = None
    actor = 'The traveller'
    if status == 'submitted':
        state, heading = 'submitted', 'Paper submission recorded'
        step = 'Keep the submitted papers and follow up with the receiving office. This records your handover; it does not confirm receipt, approval or payment.'
        action = {'url':base+'/ready', 'label':'View submitted print list'}
    elif status == 'withdrawn':
        state, heading = 'closed', 'Filing withdrawn'
        step = 'This filing is closed. Earlier files remain in Drive; check with the receiving office about any papers already handed over.'
    elif status not in ('open','ready'):
        state, heading = 'attention', 'Check this filing with the Administrative Section'
        step = 'The saved filing status is not recognised; check the record before continuing.'
    elif f.get('gen_state') == 'running':
        state, heading, actor = 'waiting', 'Forms are being made', 'The form service, then the traveller'
        step = 'Check the latest form progress. An earlier copy may still be linked while a replacement is being made.'
        action = {'url':base+'/prepare', 'label':'Check form progress'} if owner else None
    else:
        needed = [it for it in items if it.get('requirement') == 'required' and it.get('state') != 'na']
        attachments = [it for it in needed if it.get('handling') in ('upload','carry')
            and not (it.get('drive_url') or (it.get('handling') == 'carry' and it.get('note')))]
        forms = [it for it in needed if it.get('handling') == 'generate' and not it.get('doc_url')]
        rejected = any(fl.get('state') == 'rejected' for fl in flags)
        waiting = any(fl.get('state') == 'open' for fl in flags)
        failed = any((it.get('doc_state') or '').startswith('failed:') for it in items if it.get('handling') == 'generate')
        if attachments:
            state, heading = 'action', 'Add the missing documents'
            step = 'Add the required attachments or mark only those that do not apply. FMIS rows and optional documents do not block readiness.'
            action = {'url':'#item-'+attachments[0]['code'], 'label':'Add '+attachments[0]['label']} if owner else None
        elif forms or failed:
            state, heading = 'attention' if failed else 'action', 'Review the forms' if failed else 'Prepare the missing forms'
            step = ('A form attempt failed. Read its message and check any earlier linked copy before choosing to make another copy.'
                    if failed else 'Review the travel details, then make the applicable forms or add links to your own completed copies.')
            action = {'url':base+'/prepare', 'label':'Review form progress and details' if failed else 'Prepare the missing forms'} if owner else None
        elif rejected:
            state, heading = 'attention', 'A flagged item needs correction'
            step = 'Read the Administrative Section’s reason below. Correct the travel details on the prepare page or discuss the recorded decision with them.'
            action = {'url':'#travel-flags', 'label':'Review the flag and reason'}
        elif waiting:
            state, heading, actor = 'waiting', 'Waiting for flag review', 'Administrative Section'
            step = 'The flagged facts need a recorded verification. That check does not approve or pay the claim.'
            action = {'url':'/travel/verify', 'label':'Open flag review queue'} if can_verify else {'url':'#travel-flags', 'label':'View the waiting flags'}
        elif blockers:
            state, heading = 'action', 'Complete the claim details'
            step = 'Review the remaining checklist requirements below before marking this filing ready.'
            action = {'url':'#travel-answers', 'label':'Complete claim details'} if owner else None
        elif status == 'open' and review_required and f.get('review_state') != 'approved':
            rs = f.get('review_state') or ''
            if rs == 'requested':
                state, heading, actor = 'waiting', 'Waiting for the reviewer', reviewer or 'The assigned reviewer'
                step = 'The reviewer is checking the generated and uploaded documents. You will get an email when they send notes back or approve. This does not approve or pay the claim.'
                action = {'url':'#travel-review', 'label':'View the review'}
            elif rs == 'changes':
                state, heading = 'attention', 'The reviewer sent notes back'
                step = 'Read each note below, fix or add the document it names, then ask for the review again. Paper submission waits for the approval.'
                action = {'url':'#travel-review', 'label':'Read the notes and ask again'} if owner else None
            else:
                state, heading = 'action', 'Ask an admin to review your papers'
                step = 'Every required form and attachment is in. Choose a reviewer from the Administrative Section to check them for completeness before you mark the claim ready.'
                action = {'url':'#travel-review', 'label':'Choose a reviewer'} if owner else None
        elif status == 'ready':
            state, heading = 'ready', 'Ready to print and sign'
            step = 'Print the listed copies and sign where indicated. Mark submitted only after handing in the papers; this app does not send them for you.'
            action = {'url':base+'/ready', 'label':'Print list and record handover'}
        else:
            state, heading = 'ready', 'Checklist complete — review before marking ready'
            step = 'Check the saved forms and attachments, then mark ready to see the print and signature requirements.'
            action = {'url':base+'/ready', 'label':'Review and mark ready'}
    if not owner and action and action['url'].startswith('#item-'):
        action = None
    if action and action['url'].startswith('#'):
        action['url'] = base + action['url']
    return {'state':state, 'heading':heading, 'actor':actor, 'step':step, 'action':action,
            'blockers':blockers, 'can_submit':owner and status == 'ready' and not blockers,
            'viewer_note':None if owner else 'Administrative Section view: the traveller owns checklist changes; authorised section members record flag reviews in the verify queue.'}
