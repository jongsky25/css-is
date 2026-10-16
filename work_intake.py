"""Reviewed correspondence intake; one transaction for numbering and work selection."""
import uuid

import documents as docs
import documents_operations as operations
import documents_permissions as permissions
from documents_storage import transaction
import work
import work_tasks

SCENARIOS = {
    'response': {'label':'Prepare a response', 'outcome':'Prepare a supported response for the appropriate review.',
                 'tasks':[('Prepare response draft','Draft the response with supporting references.')],
                 'guidance':'Confirm the recipient, gather inputs, and prepare a draft. Route formal approval in Documents when ready.'},
    'inputs': {'label':'Provide inputs or data', 'outcome':'Provide validated inputs with their supporting sources.',
               'tasks':[('Validate requested inputs','Compile requested data, check the figures, and cite the sources.')],
               'guidance':'Confirm the request and scope, validate the data, and submit the evidence to the lead.'},
    'activity': {'label':'Attend or organize an activity', 'outcome':'Coordinate the activity requirements and record the agreed follow-up.',
                 'tasks':[('Confirm activity arrangements','Confirm participants, schedule, and required outputs.'),
                          ('Record activity follow-up','Summarize outcomes and agreed follow-up actions.')],
                 'guidance':'Confirm arrangements and expected outputs. Calendar bookings, attendance, and travel claims retain their own workflows.'},
    'reference': {'label':'For information or reference', 'outcome':'', 'tasks':[],
                  'guidance':'Keep an official correspondence record without creating an assignment or contribution.'},
}


def choices(conn,user):
    # Bounded readable case choices; recheck current authority when submitted.
    cases,_ = work.list_page(conn,user)
    return [case for case in cases if work.can_link(conn,user,case)]


def preview(conn,user,url,adapter=None):
    user=permissions.actor(conn,user)
    docs.writable(conn)
    adapter=adapter or operations.get_adapter()
    meta=operations.metadata(url,user,adapter)
    result=adapter.call('extract',{'url':meta['url'],'file_id':meta['file_id'],
                       'fingerprint':meta['fingerprint'],'actor_id':user['id'],
                       'max_bytes':20*1024*1024,'transient':True,'kind':'extract'},str(uuid.uuid4()))
    if result.get('state')!='confirmed':
        raise ValueError('Extraction was not confirmed. Continue with manual entry.')
    # No document, sequence, job, or excerpts are persisted before human confirmation.
    return operations.sanitize_extraction(result)


def register(conn,user,fields):
    with transaction(conn):
        user=permissions.actor(conn,user)
        if fields.get('confirmed')!='yes':
            raise ValueError('Check the source and confirm the entered fields before registration.')
        scenario=fields.get('scenario','reference')
        mode=fields.get('work_mode','reference')
        if scenario not in SCENARIOS or mode not in ('reference','new','existing'):
            raise ValueError('Choose a supported scenario and work destination.')
        if (scenario=='reference') != (mode=='reference'):
            raise ValueError('For information/reference uses reference-only intake. Choose an action scenario for shared work.')
        if mode!='reference':
            work.writable(conn)
        if mode=='new' and not fields.get('unit_id'):
            raise ValueError('Choose the concerned unit to start shared work.')
        existing=None
        if mode=='existing':
            selection=str(fields.get('case_selection','')).split(':')
            cid,revision=selection if len(selection)==2 else (fields.get('case_id') or 0,fields.get('case_revision') or 0)
            existing=work.get(conn,user,int(cid))
            work._check_revision(existing,int(revision))
            if not work.can_link(conn,user,existing):
                raise permissions.Denied('The creator, lead, or concerned officer links correspondence.')
        # Suppress automatic preliminary assignments in this guided flow: reference
        # records need none, and shared work owns its explicit proposed contributions.
        doc=docs.register_in_transaction(conn,user,fields,suppress_assignments=True)
        case=None
        if mode=='new':
            case=work.create_in_transaction(conn,user,{'title':fields.get('work_title') or doc['subject'],
                'outcome':fields.get('outcome'),'unit_id':fields['unit_id'],
                'proposed_lead_id':fields.get('proposed_lead_id'),'source_document_id':doc['id']})
            if fields.get('propose_steps')=='yes':
                for title,output in SCENARIOS[scenario]['tasks']:
                    work_tasks.create_in_transaction(conn,user,case['id'],{'title':title,'expected_output':output,
                                                                          'unit_id':fields['unit_id']})
        elif mode=='existing':
            case=work.link_document_in_transaction(conn,user,existing['id'],existing['revision'],doc['id'])
        docs.event(conn,doc['id'],user,'intake_confirmed',{'scenario':scenario,'work_mode':mode,
                   'case_id':case['id'] if case else None,'proposed_steps':fields.get('propose_steps')=='yes' and mode=='new'})
        return doc,case
