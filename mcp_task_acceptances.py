"""M4.1 exact browser-confirmed acceptance by the current confirmed work-item lead."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import task_acceptance as acceptance
import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE='work:task:accept'
FLAG='CSS_MCP_TASK_ACCEPTANCES_ENABLED'


class AcceptanceFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    work_item_id: StrictInt = Field(ge=1,le=2**63-1)
    task_id: StrictInt = Field(ge=1,le=2**63-1)
    revision: StrictInt = Field(ge=1,le=2**63-2)
    expected_revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    reason: StrictStr = Field(min_length=1,max_length=2000)


def normalize(fields):
    from mcp_task_submissions import SubmissionFields
    values=AcceptanceFields.model_validate(fields).model_dump()
    values['reason']=SubmissionFields.exact_reason(values['reason'])
    return values


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_task_acceptances (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      case_id INTEGER NOT NULL, task_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_task_acceptances_expiry ON mcp_task_acceptances(expires_at) WHERE payload_json IS NOT NULL;''')


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1':
        raise actions.ActionError('not_available','Task acceptance through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_task_acceptances SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_task_acceptances WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def _source(conn,user,case_id,task_id,*,for_write=True):
    try:return acceptance.source(conn,user,case_id,task_id,for_write=for_write)
    except permissions.Denied:raise
    except ValueError:
        raise actions.ActionError('acceptance_unavailable','Review the open work item, canonical submission, active owner/submitter, linked access and resolved blockers in the ordinary work screen.') from None


def context(conn,user,values):
    user,case,task,info=_source(conn,user,values['work_item_id'],values['task_id'])
    if task['revision']!=values['revision'] or info['expected_revision']!=values['expected_revision']:
        raise actions.ActionError('revision_conflict','The submitted task or current review context changed. Read fresh context and prepare a new preview.')
    return {'case_id':case['id'],'case_title':case['title'],'task_id':task['id'],'task_title':task['title'],
            'task_revision':task['revision'],'expected_output':task['expected_output'],'submission':task['submission'],
            'due_date':task['due_date'],'mandatory':task['mandatory'],**info}


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_task_acceptances WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Task acceptance operation not found or unavailable to you.')
    return found[0]


def _check(conn,user,op,resource):
    _enabled();actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Task acceptance operation not found or unavailable to you.')
    if op['completed_at']:
        result=json.loads(op['result_json'])
        _,case,task,identity=_source(conn,user,op['case_id'],op['task_id'],for_write=False)
        if any(identity[k]!=result[k] for k in identity):
            raise permissions.Denied('The original task source is unavailable.')
        accepted=rows(conn,"SELECT * FROM work_event WHERE id=? AND case_id=? AND actor_id=? AND action='task_accept'",
                      (result['acceptance_event_id'],op['case_id'],user['id']))
        detail=json.loads(accepted[0]['detail_json']) if accepted else {}
        if detail.get('task_id')!=op['task_id'] or detail.get('revision')!=result['result_revision']:
            raise permissions.Denied('Original acceptance evidence unavailable.')
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This task-acceptance preview expired. Prepare a new operation.')
    try:
        values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if normalize(values)!=values or _digest(values)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored task-acceptance preview changed. Prepare a new operation.') from None
    if context(conn,user,values)!=snapshot:
        raise actions.ActionError('revision_conflict','The submitted task changed. Read fresh context and prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','case_id','task_id')])


def _result(op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    return {'operation_id':op['operation_id'],'action':'prepare_task_acceptance',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'work_item_id':str(op['case_id']),'task_id':str(op['task_id']),
            'result_status':'done' if result else None,'result_revision':result['result_revision'] if result else None,
            'next_actor':result['next_actor'] if result else None,
            'notification_status':'no_direct_send',
            'web_url':origin+'/work/'+str(op['case_id'])+'#task-'+str(op['task_id']),
            'confirmation_url':origin+'/account/integrations/mcp/task-acceptances/'+op['operation_id'],
            'instruction':('The exact submitted contribution was accepted as Done by the confirmed lead. This is the original result; open the work item for current state. The work item and official documents are not completed, approved, signed or dispatched by this action.'
                           if result else 'Review the exact saved submission, submitter/owner, expected output, decision note and effects in Office Connect and confirm acceptance. No decision has been made yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,work_item_id,task_id):
    for value in (work_item_id,task_id):
        if type(value) is not int or not 1<=value<=2**63-1:raise ValueError('Use positive integer work-item and task IDs.')
    with transaction(conn):
        _enabled();user,_=actions.token_actor(conn,token,resource,SCOPE)
        _,case,task,info=_source(conn,user,work_item_id,task_id)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_task_acceptances',target_id=task_id,summary='MCP confirmed-lead acceptance context',commit=False)
        return {'work_item_id':str(case['id']),'task_id':str(task['id']),'revision':task['revision'],
                'expected_revision':info['expected_revision'],'result_status_if_confirmed':'done',
                'web_url':origin+'/work/'+str(case['id'])+'#task-'+str(task['id'])}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=normalize(fields)
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled();user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_task_acceptances WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different task acceptance or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(op,origin)
        snapshot=context(conn,user,values)
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_task_acceptances WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The task-acceptance preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_task_acceptances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS,values['work_item_id'],values['task_id']))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_task_acceptances',target_id=operation_id,summary='MCP confirmed-lead task acceptance preview',commit=False)
        return _result(_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Task acceptance operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_task_acceptances',target_id=operation_id,summary='MCP own task-acceptance receipt read',commit=False)
        return _result(op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this task acceptance.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this task acceptance.')
            if not op['completed_at']:
                values=json.loads(op['payload_json'])
                try:result=acceptance.accept_in_transaction(conn,user,**values)
                except permissions.Denied:raise
                except ValueError:
                    raise actions.ActionError('revision_conflict','The submitted task or review context changed. Read fresh context and prepare a new preview.') from None
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_task_acceptances SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_task_acceptances',target_id=operation_id,summary='MCP task accepted by confirmed lead',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
