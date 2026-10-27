"""M3.8 new pending work-arrangement filings with explicit browser confirmation."""
from datetime import date
import hashlib
import json
import os
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE = 'work_arrangements:request'
FLAG = 'CSS_MCP_WORK_ARRANGEMENTS_ENABLED'


def period(value):
    if not isinstance(value,str) or len(value)!=10:
        raise ValueError('Use an exact half-month YYYY-MM-01 or YYYY-MM-16 period.')
    d=date.fromisoformat(value)
    if d.isoformat()!=value or d.day not in (1,16):
        raise ValueError('Use an exact half-month YYYY-MM-01 or YYYY-MM-16 period.')
    return value


class RequestFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    period_start: StrictStr = Field(min_length=10,max_length=10)
    arrangement: Literal['REG','CWW','WFH']
    weekday: StrictInt | None = Field(default=None,ge=0,le=4)
    note: StrictStr = Field(default='',max_length=1000)

    @model_validator(mode='after')
    def exact(self):
        period(self.period_start)
        if (self.arrangement=='REG') != (self.weekday is None):
            raise ValueError('REG has no weekday; CWW and WFH require a Monday–Friday index (0–4).')
        self.note=self.note.strip()
        if any((ord(c)<32 and c not in '\n\t') or ord(c)==127 for c in self.note):
            raise ValueError('Remove control characters from the note.')
        return self


def normalize(fields):return RequestFields.model_validate(fields).model_dump()


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_work_arrangement (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      completed_at TEXT, result_json TEXT, PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_work_arrangement_expiry ON mcp_work_arrangement(expires_at) WHERE payload_json IS NOT NULL;
    CREATE TABLE IF NOT EXISTS mcp_work_arrangement_identity (
      request_id INTEGER PRIMARY KEY REFERENCES work_arrangement(id) ON DELETE CASCADE,
      operation_key TEXT NOT NULL UNIQUE REFERENCES mcp_work_arrangement(domain_key));
    CREATE TABLE IF NOT EXISTS mcp_work_arrangement_mail (
      operation_key TEXT NOT NULL REFERENCES mcp_work_arrangement(domain_key), recipient_id INTEGER NOT NULL,
      created_at INTEGER NOT NULL, payload_json TEXT,
      state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','attempting','sent','uncertain','skipped_off','not_configured','cancelled')),
      attempt_id TEXT, attempted_at INTEGER, finished_at TEXT,
      PRIMARY KEY(operation_key,recipient_id));
    CREATE INDEX IF NOT EXISTS mcp_work_arrangement_mail_queue ON mcp_work_arrangement_mail(state);''')


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1':
        raise actions.ActionError('not_available','Work arrangement requests through ChatGPT are disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_work_arrangement SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_work_arrangement WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def recipients(conn,owner_id):
    out=[]
    for uid in sorted(st.get_approvers_for(conn,owner_id)):
        account=st.get_admin_user_by_id(conn,uid)
        if account and account['active'] and uid!=owner_id:
            out.append({'id':uid,'email':account['username'],'name':st._account_display_name(conn,uid) or account['username']})
    return out


def context(conn,user,values):
    user=permissions.actor(conn,user)
    if st._is_director(conn,user['id']):
        raise actions.ActionError('action_unavailable','Auto-approved Director filings require the ordinary work arrangement screen.')
    try:
        planned=st.work_arrangement_new_fields(conn,user['id'],**values)
    except ValueError:
        raise actions.ActionError('filing_unavailable','Review the open period, existing filings, No AWA tag and boundary-week rules in Office Connect.') from None
    ps=values['period_start'];rp=st.get_rp(conn,user['rp_id']) if user.get('rp_id') else None
    reopen=st.get_work_arrangement_reopen(conn,ps)
    return {'requester':{'id':user['id'],'name':st._account_display_name(conn,user['id']) or user['username'],
                         'identity_digest':_digest([user['username'],user.get('rp_id'),rp])},
            'period_label':st.work_arrangement_period_label(ps),'deadline_label':st.work_arrangement_deadline_label(ps),
            'reopened':bool(reopen),'reopen_digest':_digest(reopen),
            'arrangement_label':st.WORK_ARRANGEMENT_LABELS[values['arrangement']],
            'weekday_name':dict(st.WORK_ARRANGEMENT_WEEKDAYS).get(values['weekday'],''),
            'effective_from':planned['effective_from'],'week_override_note':planned['week_override_note'],
            'proposed_weekdays':[d.isoformat() for d,wd in st.work_arrangement_period_workdays(ps)
                                 if values['weekday']==wd and d.isoformat()>=planned['effective_from']],
            'coverage_advisory':st.work_arrangement_coverage_note(conn,user['id'],ps,values['arrangement'],values['weekday']),
            'recipients':recipients(conn,user['id']),'approver_title':st.approver_title_for(conn,user['id']),
            'email_enabled':st.email_feature_enabled(conn,'awa_approval')}


def record_digest(record):
    return _digest({k:record[k] for k in ('id','user_id','period_start','arrangement','weekday','note','created_at','effective_from','supersedes_id')})


def owned(conn,user,request_id):
    user=permissions.actor(conn,user)
    record=st.get_work_arrangement(conn,request_id)
    if not record or record['user_id']!=user['id']:
        raise permissions.Denied('Work arrangement source not found or unavailable to you.')
    return record


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_work_arrangement WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Work arrangement operation not found or unavailable to you.')
    return found[0]


def source(conn,user,operation_id):
    user=permissions.actor(conn,user)
    op=_op(conn,user['id'],operation_id)
    if not op['completed_at']:raise permissions.Denied('Source unavailable.')
    result=json.loads(op['result_json']);record=owned(conn,user,result['id'])
    if record['created_at']!=result['created_at'] or not conn.execute(
            'SELECT 1 FROM mcp_work_arrangement_identity WHERE request_id=? AND operation_key=?',
            (record['id'],op['domain_key'])).fetchone():
        raise permissions.Denied('The original work arrangement source is unavailable.')
    return record


def _check(conn,user,op,resource):
    _enabled();actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Work arrangement operation not found or unavailable to you.')
    if op['completed_at']:
        result=json.loads(op['result_json']);record=owned(conn,user,result['id'])
        if record['created_at']!=result['created_at'] or not conn.execute(
                'SELECT 1 FROM mcp_work_arrangement_identity WHERE request_id=? AND operation_key=?',(record['id'],op['domain_key'])).fetchone():
            raise permissions.Denied('The original work arrangement source is unavailable.')
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This work arrangement preview expired. Prepare a new operation.')
    try:
        values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if normalize(values)!=values or _digest(values)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored work arrangement preview changed. Prepare a new operation.') from None
    if context(conn,user,values)!=snapshot:
        raise actions.ActionError('revision_conflict','The requester, period, effective dates, advisory, approvers or mail setting changed. Prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at')])


def _result(conn,op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    counts={r[0]:r[1] for r in conn.execute('SELECT state,COUNT(*) FROM mcp_work_arrangement_mail WHERE operation_key=? GROUP BY state',(op['domain_key'],))}
    return {'operation_id':op['operation_id'],'action':'prepare_work_arrangement_request',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'work_arrangement_id':str(result['id']) if result else None,'filed_status':'pending' if result else None,
            'next_actor':{'role':result['next_role'],'initial_notice_recipient_count':result['recipient_count']} if result else None,
            'notification_status_counts':counts,
            'web_url':origin+'/account/integrations/mcp/work-arrangement-requests/saved/'+op['operation_id'] if result else origin+'/work-arrangement',
            'confirmation_url':origin+'/account/integrations/mcp/work-arrangement-requests/'+op['operation_id'],
            'instruction':('Work arrangement filed Pending for a separate approval; it is not an approved schedule. This is the original filing result; inspect the source for current status. Initial notification counts are current; queued is not sent.'
                           if result else 'Review the exact period, arrangement, weekday, effectivity, note, visibility and approver emails in Office Connect before confirming. No filing or email has been created yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,period_start):
    ps=period(period_start)
    with transaction(conn):
        _enabled();user,_=actions.token_actor(conn,token,resource,SCOPE)
        try:st._wa_check_period_open(conn,ps);is_open=True
        except ValueError:is_open=False
        st.audit(conn,user['username'],'integration_read',target_type='mcp_work_arrangement',summary='MCP own filing preparation context',commit=False)
        return {'period_start':ps,'period_label':st.work_arrangement_period_label(ps),'deadline_label':st.work_arrangement_deadline_label(ps),
                'timezone':'Asia/Manila','is_open':is_open,'reopened':bool(st.get_work_arrangement_reopen(conn,ps)),
                'requires_ordinary_auto_approval':st._is_director(conn,user['id']),
                'has_live_filing':bool(st.my_work_arrangement_for(conn,user['id'],ps) or st.my_pending_work_arrangement(conn,user['id'],ps)),
                'has_no_awa_tag':bool(st.get_work_arrangement_noawa(conn,user['id'],ps)),
                'arrangements':[{'code':code,'label':label} for code,label,_ in st.WORK_ARRANGEMENT_TYPES],
                'weekdays':[{'index':idx,'label':label} for idx,label in st.WORK_ARRANGEMENT_WEEKDAYS],
                'initial_notice_recipient_count':len(recipients(conn,user['id'])),'web_url':origin+'/work-arrangement/file?period='+ps}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=normalize(fields)
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled();user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_work_arrangement WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different filing or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(conn,op,origin)
        snapshot=context(conn,user,values)
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_work_arrangement WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The work arrangement preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_work_arrangement VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_work_arrangement',target_id=operation_id,summary='MCP own work arrangement preview',commit=False)
        return _result(conn,_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Work arrangement operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_work_arrangement',target_id=operation_id,summary='MCP own filing receipt read',commit=False)
        return _result(conn,op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this work arrangement.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this filing.')
            if not op['completed_at']:
                values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
                try:wid=st.create_work_arrangement(conn,user['id'],**values,commit=False)
                except ValueError:
                    raise actions.ActionError('filing_unavailable','The period or current filings changed. Prepare a new preview.') from None
                record=st.get_work_arrangement(conn,wid)
                result={'id':wid,'created_at':record['created_at'],'record_digest':record_digest(record),
                        'recipient_count':len(snapshot['recipients']),'next_role':'chain_of_command_approver' if snapshot['recipients'] else 'existing_orphan_approval_fallback',
                        'mail_digests':{}}
                conn.execute('INSERT INTO mcp_work_arrangement_identity VALUES (?,?)',(wid,op['domain_key']))
                now=int(time.time())
                for recipient in snapshot['recipients']:
                    mail={'to':recipient['email'],'recipient_name':recipient['name'],'requester_name':snapshot['requester']['name'],
                          'period_label':snapshot['period_label'],'arrangement_label':snapshot['arrangement_label'],'link':origin+'/approvals#awa'}
                    result['mail_digests'][str(recipient['id'])]=_digest(mail)
                    conn.execute('INSERT INTO mcp_work_arrangement_mail(operation_key,recipient_id,created_at,payload_json) VALUES (?,?,?,?)',
                                 (op['domain_key'],recipient['id'],now,_json(mail)))
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_work_arrangement SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'work_arrangement_file',target_type='work_arrangement',target_id=wid,summary='Filed own work arrangement pending approval',commit=False)
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_work_arrangement',target_id=operation_id,summary='MCP own work arrangement filed',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(conn,op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
