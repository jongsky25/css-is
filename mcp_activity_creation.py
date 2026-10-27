"""M3.10 browser-confirmed live creation from one owner-private activity draft."""
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel,ConfigDict,Field,StrictStr,model_validator

import activity_creation as creation
import activity_drafts as drafts
import documents_permissions as permissions
from documents_storage import rows,transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE='activities:draft:create'
FLAG='CSS_MCP_ACTIVITY_CREATION_ENABLED'


class CreationFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    draft_key: StrictStr = Field(min_length=36,max_length=36)
    expected_revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def exact(self):drafts.key(self.draft_key);return self


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return creation.digest(value)


def install(conn):
    drafts.install(conn);creation.install(conn)
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_activity_creation (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      draft_key TEXT NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_activity_creation_expiry ON mcp_activity_creation(expires_at) WHERE payload_json IS NOT NULL;
    CREATE TABLE IF NOT EXISTS mcp_activity_creation_mail (
      operation_key TEXT NOT NULL REFERENCES mcp_activity_creation(domain_key),
      feature TEXT NOT NULL CHECK(feature IN ('event_created','event_section_notify')),
      recipient_id INTEGER NOT NULL, created_at INTEGER NOT NULL, payload_json TEXT,
      state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','attempting','sent','uncertain','skipped_off','not_configured','cancelled')),
      attempt_id TEXT, attempted_at INTEGER, finished_at TEXT,
      PRIMARY KEY(operation_key,feature,recipient_id));
    CREATE INDEX IF NOT EXISTS mcp_activity_creation_mail_queue ON mcp_activity_creation_mail(state);''')


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1':
        raise actions.ActionError('not_available','Live activity creation through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_activity_creation SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_activity_creation WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def context(conn,user,draft_key):
    try:return creation.context(conn,user,draft_key)
    except permissions.Denied:raise
    except creation.AlreadyCreated:
        raise actions.ActionError('draft_already_created','This draft already created an activity through confirmed creation. Recover the original key and inspect its draft/source.') from None
    except creation.DuplicateActivity:
        raise actions.ActionError('duplicate_activity','A strong activity duplicate exists. Review ordinary Create/Monitor; this pilot cannot override the warning.') from None
    except ValueError:
        raise actions.ActionError('creation_unavailable','Review the original private draft, current Create access, current section, today/future date and notification routing.') from None


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_activity_creation WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Activity creation operation not found or unavailable to you.')
    return found[0]


def _check(conn,user,op,resource):
    _enabled();actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Activity creation operation not found or unavailable to you.')
    if op['completed_at']:
        mapped=creation.lookup(conn,user,op['draft_key'])
        result=json.loads(op['result_json'])
        if (not mapped or mapped['operation_key']!=op['domain_key'] or mapped['event_id']!=result['event_id']
                or mapped['event_token']!=result['event_token']):
            raise permissions.Denied('Original activity creation source unavailable.')
        creation.live_source(conn,user,mapped)
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This live-creation preview expired. Prepare a new operation.')
    try:
        fields,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if CreationFields.model_validate(fields).model_dump()!=fields or _digest(fields)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored live-creation preview changed. Prepare a new operation.') from None
    current=context(conn,user,fields['draft_key'])
    if creation.revision(current)!=fields['expected_revision'] or current!=snapshot:
        raise actions.ActionError('revision_conflict','The draft, creator, section, duplicate hints or email routing changed. Read fresh context and prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','draft_key')])


def _result(conn,op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    counts={r[0]:r[1] for r in conn.execute('SELECT state,COUNT(*) FROM mcp_activity_creation_mail WHERE operation_key=? GROUP BY state',(op['domain_key'],))}
    return {'operation_id':op['operation_id'],'action':'prepare_activity_from_draft',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'created_status':'live_activity' if result else None,'event_id':str(result['event_id']) if result else None,
            'form_count':1 if result else None,'event_date':result['event_date'] if result else None,
            'next_actor':{'role':'organizer_manage_and_share','initial_notice_recipient_count':result['recipient_count']} if result else None,
            'notification_status_counts':counts,
            'web_url':origin+'/activities/'+result['event_token']+'/manage' if result else origin+'/activity-drafts/'+op['draft_key'],
            'public_url':origin+'/e/'+result['event_token'] if result else None,
            'confirmation_url':origin+'/account/integrations/mcp/activity-creation/'+op['operation_id'],
            'instruction':('Live activity and one event-review form were created with public registration/feedback links and no configured entry window. This is the original result; inspect the source for current settings. Internal notice counts are current, not proof of delivery. No participant invitations, bookings or approval were made.'
                           if result else 'Review the exact draft fields, live public-link effects and internal email recipients in Office Connect before confirming. No event, survey or email queue has been created yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,draft_key):
    drafts.key(draft_key)
    with transaction(conn):
        _enabled();user,_=actions.token_actor(conn,token,resource,SCOPE);snapshot=context(conn,user,draft_key)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_creation',summary='MCP own live-creation context',commit=False)
        return {'draft_id':str(snapshot['draft_id']),'expected_revision':creation.revision(snapshot),
                'event_date':snapshot['fields']['event_date'],'event_type':'bureau','form_count':1,
                'initial_notice_recipient_count':len(snapshot['recipients']),'weak_duplicate_count':snapshot['weak_duplicate_count'],
                'web_url':origin+'/activity-drafts/'+draft_key}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=CreationFields.model_validate(fields).model_dump()
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled();user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_activity_creation WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different creation or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(conn,op,origin)
        snapshot=context(conn,user,values['draft_key'])
        if creation.revision(snapshot)!=values['expected_revision']:
            raise actions.ActionError('revision_conflict','The draft or current creation context changed. Read fresh context.')
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_activity_creation WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The activity-creation preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_activity_creation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS,values['draft_key']))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_activity_creation',target_id=operation_id,summary='MCP live activity creation preview',commit=False)
        return _result(conn,_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Activity creation operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_activity_creation',target_id=operation_id,summary='MCP own activity creation receipt',commit=False)
        return _result(conn,op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this live creation.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this live creation.')
            if not op['completed_at']:
                values=json.loads(op['payload_json'])
                try:snapshot,mapped,live_digest=creation.create_from_draft_in_transaction(conn,user,values['draft_key'],values['expected_revision'],operation_key=op['domain_key'])
                except permissions.Denied:raise
                except ValueError:
                    raise actions.ActionError('creation_unavailable','The draft, duplicate activity or live-creation context changed. Review the draft/source before another key.') from None
                result={'event_id':mapped['event_id'],'event_token':mapped['event_token'],'event_date':snapshot['fields']['event_date'],
                        'live_digest':live_digest,'recipient_count':len(snapshot['recipients']),'mail_digests':{}}
                for recipient in snapshot['recipients']:
                    mail={'to':recipient['email'],'recipient_name':recipient['name'],'creator_name':snapshot['current']['requester']['name'],
                          'title':snapshot['fields']['activity_name'],'event_date':snapshot['fields']['event_date'],
                          'link':origin+'/monitor/'+mapped['event_token']}
                    result['mail_digests'][recipient['feature']+':'+str(recipient['id'])]=_digest(mail)
                    enabled=snapshot['email_enabled'][recipient['feature']]
                    conn.execute('INSERT INTO mcp_activity_creation_mail(operation_key,feature,recipient_id,created_at,payload_json,state,finished_at) VALUES (?,?,?,?,?,?,?)',
                        (op['domain_key'],recipient['feature'],recipient['id'],int(time.time()),_json(mail) if enabled else None,
                         'queued' if enabled else 'skipped_off',None if enabled else tz.now_iso()))
                    if not enabled:
                        subject,_,_=creation.notice_message(recipient['feature'],mail)
                        conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
                            (tz.now_iso(),recipient['feature'],recipient['email'],subject,'skipped_off','MCP creation: disabled at confirmation; no send or retry'))
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_activity_creation SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                    (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_activity_creation',target_id=operation_id,summary='MCP live activity created from private draft',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(conn,op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
