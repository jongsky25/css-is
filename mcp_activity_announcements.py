"""M3.11 exact browser-confirmed first activity pinned-update publication."""
import hashlib
import json
import os
import re
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import activity_announcements as publication
import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE='activities:announcement:publish'
FLAG='CSS_MCP_ACTIVITY_ANNOUNCEMENTS_ENABLED'


class PublicationFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    event_id: StrictInt = Field(ge=1,le=2**63-1)
    expected_revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    announcement: StrictStr = Field(min_length=1,max_length=1000)


def normalize(fields):
    values=PublicationFields.model_validate(fields).model_dump()
    values['announcement']=publication.normalize_text(values['announcement'])
    return values


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    publication.install(conn)
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_activity_announcements (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      event_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_activity_announcements_expiry ON mcp_activity_announcements(expires_at) WHERE payload_json IS NOT NULL;''')


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1':
        raise actions.ActionError('not_available','Pinned-update publication through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_activity_announcements SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_activity_announcements WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def _source(conn,user,event_id,*,for_write=True):
    try:return publication.source(conn,user,event_id,for_write=for_write)
    except permissions.Denied:raise
    except ValueError:
        raise actions.ActionError('publication_unavailable','Use a current or upcoming bureau activity with 1–25 forms, at least one active form, and no existing or previously MCP-published pinned update. Review ordinary Manage for changes.') from None


def context(conn,user,values):
    user,ev,info=_source(conn,user,values['event_id'])
    if info['expected_revision']!=values['expected_revision']:
        raise actions.ActionError('revision_conflict','The activity, audience or current management authority changed. Read fresh context and prepare a new preview.')
    return {'event_id':ev['id'],'title':ev['title'],'event_date':ev['event_date'],
            'event_token':ev['event_token'],'created_at':ev['created_at'],
            'expected_revision':info['expected_revision'],'announcement':values['announcement'],
            'registered_count':info['registered_count'],'timezone':'Asia/Manila'}


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_activity_announcements WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Pinned-publication operation not found or unavailable to you.')
    return found[0]


def _check(conn,user,op,resource):
    _enabled();actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Pinned-publication operation not found or unavailable to you.')
    if op['completed_at']:
        result=json.loads(op['result_json']);_,ev,_=_source(conn,user,op['event_id'],for_write=False)
        if ev['event_token']!=result['event_token'] or ev['created_at']!=result['created_at']:
            raise permissions.Denied('The original activity source is unavailable.')
        mapped=conn.execute('SELECT operation_key FROM activity_announcement_publication WHERE event_token=? AND event_id=? AND event_created_at IS ?',(result['event_token'],op['event_id'],result['created_at'])).fetchone()
        if not mapped or mapped[0]!=op['domain_key']:
            raise permissions.Denied('Original publication identity unavailable.')
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This pinned-publication preview expired. Prepare a new operation.')
    try:
        values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if normalize(values)!=values or _digest(values)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored pinned-publication preview changed. Prepare a new operation.') from None
    if context(conn,user,values)!=snapshot:
        raise actions.ActionError('revision_conflict','The activity changed. Read fresh context and prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','event_id')])


def _result(op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    source_token=result['event_token'] if result else json.loads(op['snapshot_json'])['event_token']
    return {'operation_id':op['operation_id'],'action':'prepare_activity_announcement',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'event_id':str(op['event_id']),'publication_status':'published' if result else None,
            'published_at':result['published_at'] if result else None,
            'registered_count_at_publication':result['registered_count'] if result else None,
            'next_actor':{'role':'organizer_manage_activity'} if result else None,
            'notification_status':'none_created',
            'web_url':origin+'/activities/'+source_token+'/manage#announcement',
            'participant_url':origin+'/e/'+source_token if result else None,
            'confirmation_url':origin+'/account/integrations/mcp/activity-announcements/'+op['operation_id'],
            'instruction':('The pinned update was published on registered participants’ activity pages under normal access rules. This is the original publication; inspect Manage for current text. No email, invitation, approval or new activity was created.'
                           if result else 'Review the exact activity, text and participant-page visibility in Office Connect and confirm. Nothing has been published yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,event_token):
    if not isinstance(event_token,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',event_token) or not 3<=len(event_token)<=40:
        raise ValueError('Use the activity token or slug from its Monitor/Manage link.')
    with transaction(conn):
        _enabled();user,_=actions.token_actor(conn,token,resource,SCOPE)
        event=st.get_event(conn,event_token)
        if not event:raise permissions.Denied('Activity not found or unavailable to you.')
        event_id=event['id']
        _,ev,info=_source(conn,user,event_id)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_announcements',target_id=event_id,summary='MCP permitted pinned update context',commit=False)
        return {'event_id':str(event_id),'expected_revision':info['expected_revision'],'event_date':ev['event_date'],
                'timezone':'Asia/Manila','registered_count':info['registered_count'],'max_text_characters':st.ANNOUNCEMENT_MAX,
                'web_url':origin+'/activities/'+ev['event_token']+'/manage#announcement'}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=normalize(fields)
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled();user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_activity_announcements WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different pinned publication or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(op,origin)
        snapshot=context(conn,user,values)
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_activity_announcements WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The pinned-publication preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_activity_announcements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS,values['event_id']))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_activity_announcements',target_id=operation_id,summary='MCP pinned update preview',commit=False)
        return _result(_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Pinned-publication operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_announcements',target_id=operation_id,summary='MCP own pinned-publication receipt read',commit=False)
        return _result(op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this pinned-update publication.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this pinned-update publication.')
            if not op['completed_at']:
                values=json.loads(op['payload_json'])
                try:result=publication.publish_in_transaction(conn,user,**values,operation_key=op['domain_key'])
                except permissions.Denied:raise
                except ValueError:
                    raise actions.ActionError('revision_conflict','The activity or publication context changed. Read fresh context and prepare a new preview.') from None
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_activity_announcements SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_activity_announcements',target_id=operation_id,summary='MCP first activity pinned update published',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
