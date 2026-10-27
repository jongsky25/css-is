"""M4.2 exact browser-confirmed full-quantity supply approval and reservation."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import supply_approval as approval
import supplies_storage as domain
import supplies
import documents_permissions as permissions
from supplies_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE='supplies:request:approve'
FLAG='CSS_MCP_SUPPLY_APPROVALS_ENABLED'


class ApprovalFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: StrictInt = Field(ge=1,le=2147483647)
    revision: StrictInt = Field(ge=1,le=2147483646)
    expected_revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    reason: StrictStr = Field(min_length=1,max_length=2000)


def normalize(fields):
    from mcp_task_submissions import SubmissionFields
    values=ApprovalFields.model_validate(fields).model_dump()
    values['reason']=SubmissionFields.exact_reason(values['reason'])
    return values


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_supply_approvals (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      request_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_supply_approvals_expiry ON mcp_supply_approvals(expires_at) WHERE payload_json IS NOT NULL;''')


def _enabled(conn):
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1' or not supplies.enabled(conn):
        raise actions.ActionError('not_available','Supply approvals through ChatGPT are disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_supply_approvals SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_supply_approvals WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def _source(conn,user,request_id,*,for_write=True):
    try:return approval.source(conn,user,request_id,for_write=for_write)
    except domain.Denied:raise
    except ValueError:
        raise actions.ActionError('approval_unavailable','Review the submitted request, active requester, catalog, approval scope and normal allocation queue in Supplies.') from None


def context(conn,user,values):
    user,request,header,info=_source(conn,user,values['request_id'])
    if request['revision']!=values['revision'] or info['expected_revision']!=values['expected_revision']:
        raise actions.ActionError('revision_conflict','The request, current authority, catalog or reservation effects changed. Read fresh context and prepare a new preview.')
    return {'request_id':request['id'],'revision':request['revision'],'submitted_revision':header['revision'],
            'control_number':request['control_number'],'purpose':header['purpose'],'date_needed':header['date_needed'],
            'requester_snapshot':header['requester_snapshot'],'requester_id':request['requester_id'],
            'unit_snapshot':header['unit_snapshot'],'unit_id':header['unit_id'],
            'approver':info['approver'],'lines':info['lines'],'expected_revision':info['expected_revision']}


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_supply_approvals WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Supply approval operation not found or unavailable to you.')
    return found[0]


def _check(conn,user,op,resource):
    _enabled(conn);actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Supply approval operation not found or unavailable to you.')
    if op['completed_at']:
        result=json.loads(op['result_json']);_,request,header,_=_source(conn,user,op['request_id'],for_write=False)
        saved=result['decision']
        original=rows(conn,'SELECT * FROM supply_request_revision WHERE id=? AND request_id=?',
                      (result['submitted_revision_id'],op['request_id']))
        prior=rows(conn,'SELECT * FROM supply_operation WHERE operation_key=?',(op['domain_key'],))
        evidence=rows(conn,'SELECT * FROM supply_request_decision WHERE id=? AND operation_key=?',(saved['decision_id'],op['domain_key']))
        if (request['created_at']!=result['request_created_at'] or not original
                or original[0]['operation_key']!=result['submission_operation_key'] or not prior or not evidence
                or prior[0]['actor_id']!=user['id'] or prior[0]['action']!='request_decide'
                or json.loads(prior[0]['result_json'])!=saved or evidence[0]['decided_by']!=user['id']
                or saved['id']!=op['request_id'] or evidence[0]['revision_id']!=result['submitted_revision_id']
                or evidence[0]['request_id']!=op['request_id'] or evidence[0]['decision']!='approved'):
            raise permissions.Denied('Original supply approval evidence unavailable.')
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This supply-approval preview expired. Prepare a new operation.')
    try:
        values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if normalize(values)!=values or _digest(values)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored supply-approval preview changed. Prepare a new operation.') from None
    if context(conn,user,values)!=snapshot:
        raise actions.ActionError('revision_conflict','The supply approval context changed. Read fresh context and prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','request_id')])


def _result(op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    return {'operation_id':op['operation_id'],'action':'prepare_supply_request_approval',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'request_id':str(op['request_id']),'approval_status':'approved' if result else None,
            'result_revision':result['decision']['revision'] if result else None,
            'submitted_revision':result['decision']['current_revision'] if result else None,
            'line_count':result['line_count'] if result else None,
            'reservation_status':'initial_allocation_recorded' if result else None,
            'next_actor':result['next_actor'] if result else None,
            'notification_status':'normal_stock_warning_processing',
            'domain_operation_id':op['domain_key'] if result else None,
            'web_url':origin+'/supplies/requests/'+str(op['request_id']),
            'confirmation_url':origin+'/account/integrations/mcp/supply-approvals/'+op['operation_id'],
            'instruction':('The submitted supply request was approved at its exact requested quantities and initial reservations recorded. This is the original decision; inspect Supplies for current reservations/fulfillment. Physical on-hand was not changed and nothing was issued. Custodian action is separate; normal stock-warning processing applies.'
                           if result else 'Review every submitted line, full approved quantities, exact initial reservation/shortage effects and decision reason in Office Connect and confirm. Nothing has been approved or reserved yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,request_id):
    if type(request_id) is not int or not 1<=request_id<=2147483647:raise ValueError('Use a positive integer supply request ID.')
    with transaction(conn):
        _enabled(conn);user,_=actions.token_actor(conn,token,resource,SCOPE)
        _,request,header,info=_source(conn,user,request_id)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_supply_approvals',target_id=request_id,summary='MCP scoped supply approval context',commit=False)
        return {'request_id':str(request_id),'revision':request['revision'],'expected_revision':info['expected_revision'],
                'submitted_revision':header['revision'],'line_count':len(info['lines']),
                'web_url':origin+'/supplies/requests/'+str(request_id)}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=normalize(fields)
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled(conn);user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_supply_approvals WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different supply approval or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(op,origin)
        snapshot=context(conn,user,values)
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_supply_approvals WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The supply-approval preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_supply_approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS,values['request_id']))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_supply_approvals',target_id=operation_id,summary='MCP full-quantity supply approval preview',commit=False)
        return _result(_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Supply approval operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_supply_approvals',target_id=operation_id,summary='MCP own supply-approval receipt read',commit=False)
        return _result(op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this supply approval.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this supply approval.')
            if not op['completed_at']:
                values=json.loads(op['payload_json'])
                try:result=approval.approve_in_transaction(conn,user,**values,operation_key=op['domain_key'])
                except (permissions.Denied,domain.Denied):raise
                except ValueError:
                    raise actions.ActionError('revision_conflict','The request or allocation effects changed. Read fresh context and prepare a new preview.') from None
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_supply_approvals SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_supply_approvals',target_id=operation_id,summary='MCP submitted supply request approved',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
