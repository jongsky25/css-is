"""M4.1: a confirmed lead accepts another person's exact submitted contribution."""
import hashlib
import json

import documents_permissions as permissions
from documents_storage import rows
import storage as st
import work
import work_compat
import work_reads
import work_tasks


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def _event(conn,case_id,task_id,action):
    found=rows(conn,"""SELECT * FROM work_event WHERE case_id=? AND action=?
        AND json_extract(detail_json,'$.task_id')=? ORDER BY id DESC LIMIT 1""",(case_id,action,task_id))
    return found[0] if found else None


def source(conn,user,case_id,task_id,*,for_write=True):
    user=permissions.actor(conn,user);case=work.get(conn,user,case_id)
    task=work_reads.task(conn,user,case_id,task_id)
    # Technical administration/officer rank alone cannot make an MCP decision.
    if case['lead_id']!=user['id']:
        raise permissions.Denied('Only the current confirmed work-item lead can use this acceptance pilot.')
    founding=_event(conn,case_id,task_id,'task_proposed')
    if not founding:raise ValueError('Use the ordinary work screen for imported or unverified task history.')
    identity={'case_created_at':case['created_at'],'task_created_at':task['created_at'],'task_origin_event_id':founding['id']}
    if not for_write:return user,case,task,identity
    work.writable(conn);work_compat.require_open(conn,case_id)
    submitted=_event(conn,case_id,task_id,'task_submit')
    detail=json.loads(submitted['detail_json']) if submitted else {}
    if (task['owner_id']==user['id'] or not submitted or submitted['actor_id']==user['id']):
        raise permissions.Denied('The assigned owner and submitting actor cannot accept their own contribution through this pilot.')
    if 'accept' not in work_tasks.actions(conn,user,case,task):
        raise ValueError('Review the submitted task, open work item, prerequisites and blockers before acceptance.')
    if (detail.get('revision')!=task['revision'] or detail.get('status')!='for_review'
            or detail.get('owner_id')!=task['owner_id'] or detail.get('submission')!=task['submission']):
        raise ValueError('Review a fresh canonical submission before accepting.')
    work_tasks._owner(conn,case_id,task['owner_id'])
    linked=rows(conn,'SELECT * FROM work_document WHERE case_id=? ORDER BY document_id LIMIT 26',(case_id,))
    if len(linked)>25:raise ValueError('Use the ordinary work screen for more than 25 linked records.')
    documents=[work.resolved_document(conn,r['document_id']) for r in linked]
    downstream=rows(conn,"""SELECT t.id,t.title,t.status,t.revision FROM work_dependency d
        JOIN work_task t ON t.id=d.task_id WHERE d.prerequisite_id=?
        AND t.status NOT IN ('done','cancelled') ORDER BY t.id LIMIT 26""",(task_id,))
    if len(downstream)>25:raise ValueError('Use the ordinary work screen for more than 25 dependent contributions.')
    notices=list(conn.execute("""SELECT COUNT(*),MAX(id) FROM document_notice
        WHERE state='pending' AND (kind LIKE 'deadline:%' OR kind LIKE 'milestone:%')
        AND document_id IN (SELECT document_id FROM work_legacy_document WHERE case_id=?)""",(case_id,)).fetchone())
    reviewer={'id':user['id'],'name':st._account_display_name(conn,user['id']) or user['username'],'role':user['role']}
    owner=st.get_admin_user_by_id(conn,task['owner_id'])
    owner_info={'id':owner['id'],'name':st._account_display_name(conn,owner['id']) or owner['username']}
    submitter=st.get_admin_user_by_id(conn,submitted['actor_id'])
    if not submitter or not submitter['active']:raise ValueError('Review the submitting account in the ordinary work screen.')
    submitter_info={'id':submitter['id'],'name':st._account_display_name(conn,submitter['id']) or submitter['username']}
    revision=digest([case,task,identity,submitted,linked,documents,downstream,notices,reviewer,owner_info,submitter_info])
    return user,case,task,dict(identity,expected_revision=revision,submitted_event_id=submitted['id'],
            submission_note=detail.get('reason',''),reviewer=reviewer,owner=owner_info,submitter=submitter_info,
            linked_record_count=len(linked),dependent_tasks=downstream,pending_legacy_notice_count=notices[0])


def accept_in_transaction(conn,user,work_item_id,task_id,revision,expected_revision,reason):
    if not conn.in_transaction:raise RuntimeError('Task acceptance requires a caller-owned transaction.')
    user,case,task,info=source(conn,user,work_item_id,task_id)
    if task['revision']!=revision or info['expected_revision']!=expected_revision:
        raise ValueError('The submitted contribution or review context changed.')
    updated=work_tasks.mutate_in_transaction(conn,user,work_item_id,task_id,revision,'accept',{'reason':reason})
    accepted=_event(conn,work_item_id,task_id,'task_accept')
    return {**{k:info[k] for k in ('case_created_at','task_created_at','task_origin_event_id')},
            'result_revision':updated['revision'],'acceptance_event_id':accepted['id'],
            'submitted_event_id':info['submitted_event_id'],'owner_id':task['owner_id'],
            'next_actor':{'role':'work_item_lead_coordinate_remaining_work','lead_id':str(user['id'])}}
