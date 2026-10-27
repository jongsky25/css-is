"""M3.9 exact browser-confirmed date changes for upcoming unused activities."""
import hashlib
import json
import os
import re
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import activity_scheduling as scheduling
import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE='activities:dates:update'
FLAG='CSS_MCP_ACTIVITY_DATES_ENABLED'


class DateFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    event_id: StrictInt = Field(ge=1,le=2**63-1)
    expected_revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    event_date: StrictStr = Field(min_length=10,max_length=10)


def normalize(fields):
    values=DateFields.model_validate(fields).model_dump()
    scheduling.exact_date(values['event_date'])
    return values


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_activity_dates (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      event_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_activity_dates_expiry ON mcp_activity_dates(expires_at) WHERE payload_json IS NOT NULL;''')


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1':
        raise actions.ActionError('not_available','Activity date changes through ChatGPT are disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_activity_dates SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_activity_dates WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def _source(conn,user,event_id,*,for_write=True):
    try:return scheduling.owned_context(conn,user,event_id,for_write=for_write)
    except permissions.Denied:raise
    except ValueError:
        raise actions.ActionError('activity_unavailable','Use a future single-day bureau activity with one unused event-review form, no entry window and no linked calendar, room or travel work.') from None


def context(conn,user,values):
    user,ev,info=_source(conn,user,values['event_id'])
    if info['expected_revision']!=values['expected_revision']:
        raise actions.ActionError('revision_conflict','The activity or current management authority changed. Read fresh context and prepare a new preview.')
    try:scheduling.check_new_date(values['event_date'])
    except ValueError:
        raise actions.ActionError('date_unavailable','Choose a different future date within the ordinary two-year activity horizon.') from None
    if ev['event_date']==values['event_date']:
        raise actions.ActionError('date_unavailable','Choose a different future activity date.')
    return {'event_id':ev['id'],'title':ev['title'],'old_event_date':ev['event_date'],
            'event_token':ev['event_token'],'created_at':ev['created_at'],'form_id':info['form_id'],
            'expected_revision':info['expected_revision'],'new_event_date':values['event_date'],
            'updated_forms':1,'timezone':'Asia/Manila'}


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_activity_dates WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Activity date operation not found or unavailable to you.')
    return found[0]


def _check(conn,user,op,resource):
    _enabled();actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Activity date operation not found or unavailable to you.')
    if op['completed_at']:
        result=json.loads(op['result_json']);_,ev,_=_source(conn,user,op['event_id'],for_write=False)
        if ev['event_token']!=result['event_token'] or ev['created_at']!=result['created_at']:
            raise permissions.Denied('The original activity source is unavailable.')
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This activity-date preview expired. Prepare a new operation.')
    try:
        values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if normalize(values)!=values or _digest(values)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored activity-date preview changed. Prepare a new operation.') from None
    if context(conn,user,values)!=snapshot:
        raise actions.ActionError('revision_conflict','The activity changed. Read fresh context and prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','event_id')])


def _period(day):return {'year':int(day[:4]),'quarter':(int(day[5:7])-1)//3+1}


def _result(op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    source_token=result['event_token'] if result else json.loads(op['snapshot_json'])['event_token']
    return {'operation_id':op['operation_id'],'action':'prepare_activity_date_update',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'event_id':str(op['event_id']),'change_status':'date_updated' if result else None,
            'old_event_date':result['old_event_date'] if result else None,'event_date':result['event_date'] if result else None,
            'updated_forms':result['updated_forms'] if result else None,
            'reporting_period_before':_period(result['old_event_date']) if result else None,
            'reporting_period_after':_period(result['event_date']) if result else None,
            'notification_status':'none_created',
            'web_url':origin+'/activities/'+source_token+'/manage#dates',
            'confirmation_url':origin+'/account/integrations/mcp/activity-dates/'+op['operation_id'],
            'instruction':('Activity and its one event-review form were re-dated together. This is the original change; inspect the source for current dates. No rescheduling email, linked-work update, approval or new activity was created.'
                           if result else 'Review the exact activity and old/new dates in Office Connect and confirm. No date has changed yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,event_token):
    if not isinstance(event_token,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',event_token) or not 3<=len(event_token)<=40:
        raise ValueError('Use the activity token or slug from its Monitor/Manage link.')
    with transaction(conn):
        _enabled();user,_=actions.token_actor(conn,token,resource,SCOPE)
        event=st.get_event(conn,event_token)
        if not event:raise permissions.Denied('Activity not found or unavailable to you.')
        event_id=event['id']
        _,ev,info=_source(conn,user,event_id)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_dates',target_id=event_id,summary='MCP permitted activity date context',commit=False)
        return {'event_id':str(event_id),'expected_revision':info['expected_revision'],'event_date':ev['event_date'],
                'timezone':'Asia/Manila','latest_event_date':scheduling.date_bounds()[1],'form_count':1,
                'web_url':origin+'/activities/'+ev['event_token']+'/manage#dates'}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=normalize(fields)
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled();user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_activity_dates WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different date change or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(op,origin)
        snapshot=context(conn,user,values)
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_activity_dates WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The activity-date preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_activity_dates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS,values['event_id']))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_activity_dates',target_id=operation_id,summary='MCP activity date preview',commit=False)
        return _result(_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Activity date operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_dates',target_id=operation_id,summary='MCP own activity-date receipt read',commit=False)
        return _result(op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this activity date change.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this activity date change.')
            if not op['completed_at']:
                values=json.loads(op['payload_json'])
                try:result=scheduling.change_in_transaction(conn,user,**values)
                except permissions.Denied:raise
                except ValueError:
                    raise actions.ActionError('revision_conflict','The activity or date changed. Read fresh context and prepare a new preview.') from None
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_activity_dates SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_activity_dates',target_id=operation_id,summary='MCP upcoming activity date updated',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
