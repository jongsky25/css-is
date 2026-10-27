"""M4.3 exact browser-confirmed approval of one plain internal room request."""
import hashlib
import json
import os
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import room_approval as approval
import rooms
import rooms_notify
import telegram_preferences as preferences
import documents_permissions as permissions
from documents_storage import rows, transaction
import mcp_actions as actions
import storage as st
import tzutil as tz

SCOPE='rooms:request:approve'
FLAG='CSS_MCP_ROOM_APPROVALS_ENABLED'


class ApprovalFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    room_request_id: StrictInt = Field(ge=1,le=2**63-1)
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
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_room_approval (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      room_id INTEGER NOT NULL, completed_at TEXT, result_json TEXT,
      PRIMARY KEY(owner_id,operation_id));
    CREATE TABLE IF NOT EXISTS mcp_room_approval_identity (
      operation_key TEXT PRIMARY KEY REFERENCES mcp_room_approval(domain_key),room_id INTEGER NOT NULL,
      reference TEXT NOT NULL,created_at TEXT,requester_id INTEGER NOT NULL,approver_id INTEGER NOT NULL,decided_at TEXT NOT NULL,
      UNIQUE(room_id,reference,created_at));
    CREATE TABLE IF NOT EXISTS mcp_room_approval_notice (
      notice_id INTEGER PRIMARY KEY REFERENCES room_notice(id) ON DELETE CASCADE,
      operation_key TEXT NOT NULL UNIQUE REFERENCES mcp_room_approval(domain_key),
      state TEXT NOT NULL CHECK(state IN ('queued','attempting','sent','uncertain','skipped_off','not_configured','cancelled')),
      created_at INTEGER NOT NULL,attempt_id TEXT,attempted_at INTEGER,finished_at TEXT);
    CREATE INDEX IF NOT EXISTS mcp_room_approval_expiry ON mcp_room_approval(expires_at) WHERE payload_json IS NOT NULL;''')


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(FLAG)!='1':
        raise actions.ActionError('not_available','Room approval through ChatGPT is disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_room_approval SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_room_approval WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''',(int(time.time()),))


def _source(conn,user,room_id,*,for_write=True):
    try:return approval.source(conn,user,room_id,for_write=for_write)
    except permissions.Denied:raise
    except (ValueError,rooms.RoomError):
        raise actions.ActionError('approval_unavailable','Review the plain internal pending request, current Administrative Section access, active requester, meeting, configured hours and room availability in Rooms.') from None


def context(conn,user,values):
    user,res,info=_source(conn,user,values['room_request_id'])
    if info['expected_revision']!=values['expected_revision']:
        raise actions.ActionError('revision_conflict','The request, hours, linked meeting, authority or notification routing changed. Read fresh context and prepare a new preview.')
    return {'room_id':res['id'],'reference':res['ref_code'],'created_at':res['created_at'],
            'title':res['title'],'purpose':res['purpose'],'attendees':res['attendees'],'modality':res['modality'],
            'day':res['day'],'calendar_entry_id':res['calendar_entry_id'],**info}


def _op(conn,owner_id,key):
    found=rows(conn,'SELECT * FROM mcp_room_approval WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found:raise permissions.Denied('Room approval operation not found or unavailable to you.')
    return found[0]


def _check(conn,user,op,resource):
    _enabled();actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    if op['resource']!=resource:raise permissions.Denied('Room approval operation not found or unavailable to you.')
    if op['completed_at']:
        result=json.loads(op['result_json']);_,res,_=_source(conn,user,op['room_id'],for_write=False)
        mapped=rows(conn,'SELECT * FROM mcp_room_approval_identity WHERE operation_key=?',(op['domain_key'],))
        if (not mapped or res['ref_code']!=result['reference'] or res['created_at']!=result['created_at']
                or res['requester_user_id']!=result['requester_id'] or mapped[0]['room_id']!=op['room_id']
                or mapped[0]['approver_id']!=user['id'] or mapped[0]['decided_at']!=result['decided_at']
                or mapped[0]['reference']!=result['reference'] or mapped[0]['created_at']!=result['created_at']):
            raise permissions.Denied('Original room approval source unavailable.')
        return
    if op['expires_at']<=int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This room-approval preview expired. Prepare a new operation.')
    try:
        values,snapshot=json.loads(op['payload_json']),json.loads(op['snapshot_json'])
        if normalize(values)!=values or _digest(values)!=op['request_digest'] or _digest(snapshot)!=op['snapshot_digest']:raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored room-approval preview changed. Prepare a new operation.') from None
    if context(conn,user,values)!=snapshot:
        raise actions.ActionError('revision_conflict','The room approval context changed. Read fresh context and prepare a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at','room_id')])


def _result(conn,op,origin):
    result=json.loads(op['result_json']) if op['completed_at'] else None
    day=result['day'] if result else json.loads(op['snapshot_json'])['day']
    states={r[0]:r[1] for r in conn.execute('SELECT state,COUNT(*) FROM mcp_room_approval_notice WHERE operation_key=? GROUP BY state',(op['domain_key'],))}
    return {'operation_id':op['operation_id'],'action':'prepare_room_request_approval',
            'status':'completed' if result else 'awaiting_confirmation','completed_at':op['completed_at'],'expires_at':op['expires_at'],
            'room_request_id':str(op['room_id']),'reference':result['reference'] if result else None,
            'approval_status':'approved' if result else None,'booking_held_at_approval':True if result else None,
            'day':result['day'] if result else None,'slot_count':result['slot_count'] if result else None,
            'next_actor':{'role':'requester_use_approved_room','initial_notice_recipient_count':1} if result else None,
            'notification_status_counts':states,'web_url':origin+'/rooms?day='+day,
            'confirmation_url':origin+'/account/integrations/mcp/room-approvals/'+op['operation_id'],
            'instruction':('The single room request was approved and its requested hours booked. This is the original decision; inspect Rooms for current booking state. Other pending requests were not declined, and no calendar status, meal, move or series was changed. Requester notice states are current, not proof of delivery.'
                           if result else 'Review the exact room request/hours, decision reason, competing-request count and requester email/ICS policy in Office Connect and confirm. Nothing has been approved yet. Keep this key for recovery.')}


def read_context(conn,token,resource,origin,room_request_id):
    if type(room_request_id) is not int or not 1<=room_request_id<=2**63-1:raise ValueError('Use a positive integer room request ID.')
    with transaction(conn):
        _enabled();user,_=actions.token_actor(conn,token,resource,SCOPE)
        _,res,info=_source(conn,user,room_request_id)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_room_approval',target_id=room_request_id,summary='MCP permitted room approval context',commit=False)
        return {'room_request_id':str(room_request_id),'expected_revision':info['expected_revision'],
                'day':res['day'],'slot_count':len(info['slots']),'competing_request_count':info['competing_request_count'],
                'web_url':origin+'/approvals#rooms'}


def prepare(conn,token,resource,origin,operation_id,fields):
    actions._key(operation_id);values=normalize(fields)
    with transaction(conn):prune(conn)
    with transaction(conn):
        _enabled();user,grant_id=actions.token_actor(conn,token,resource,SCOPE);digest=_digest(values)
        if conn.execute('SELECT 1 FROM mcp_room_approval WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op=_op(conn,user['id'],operation_id)
            if op['grant_id']!=grant_id or op['request_digest']!=digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different room approval or connection. Recover the original operation.')
            _check(conn,user,op,resource);return _result(conn,op,origin)
        snapshot=context(conn,user,values)
        count,pending=conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_room_approval WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count>=10000 or pending>=50:raise actions.ActionError('operation_capacity','The room-approval preview limit has been reached.')
        now=int(time.time())
        conn.execute('INSERT INTO mcp_room_approval VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS,values['room_request_id']))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_room_approval',target_id=operation_id,summary='MCP plain room approval preview',commit=False)
        return _result(conn,_op(conn,user['id'],operation_id),origin)


def recover(conn,token,resource,origin,operation_id):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user,grant_id=actions.token_actor(conn,token,resource,SCOPE);op=_op(conn,user['id'],operation_id)
        if op['grant_id']!=grant_id:raise permissions.Denied('Room approval operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_room_approval',target_id=operation_id,summary='MCP own room-approval receipt read',commit=False)
        return _result(conn,op,origin)


def browser(conn,payload,resource,origin,operation_id,*,confirm_digest=None):
    with transaction(conn):prune(conn)
    with transaction(conn):
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again to review this room approval.')
        op=_op(conn,user['id'],operation_id);_check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest!=_preview_digest(op):raise actions.ActionError('preview_mismatch','The confirmation does not match this room approval.')
            if not op['completed_at']:
                values=json.loads(op['payload_json'])
                try:res,info=approval.approve_in_transaction(conn,user,**values)
                except permissions.Denied:raise
                except (ValueError,rooms.RoomError):
                    raise actions.ActionError('revision_conflict','The request or room availability changed. Read fresh context and prepare a new preview.') from None
                rooms_notify.on_decided(conn,res,user['username'],commit=False)
                notices=rows(conn,"SELECT * FROM room_notice WHERE reservation_id=? AND kind='approved' AND user_id=?",(res['id'],res['requester_user_id']))
                if len(notices)!=1:raise RuntimeError('Exactly one requester approval notice is required.')
                notice=notices[0];enabled=info['policy']['feature_enabled'] and info['policy']['room_email']
                conn.execute('INSERT INTO mcp_room_approval_notice(notice_id,operation_key,state,created_at,finished_at) VALUES (?,?,?,?,?)',
                    (notice['id'],op['domain_key'],'queued' if enabled else 'skipped_off',int(time.time()),None if enabled else tz.now_iso()))
                if not enabled:
                    conn.execute("UPDATE room_notice SET email_status='skipped_off',emailed_at=? WHERE id=?",(tz.now_iso(),notice['id']))
                    conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
                        (tz.now_iso(),'room_decided',info['recipient']['email'],'Room request approved','skipped_off','MCP room approval: disabled at confirmation; no send or retry'))
                result={'reference':res['ref_code'],'created_at':res['created_at'],'requester_id':res['requester_user_id'],
                        'decided_at':res['decided_at'],'day':res['day'],'slot_count':len(res['slot_ids']),
                        'live_digest':approval.live_digest(conn,res),'recipient_digest':_digest(info['recipient']),
                        'room_ics':info['policy']['room_ics'],'linked_meeting_digest':info['linked_meeting_digest']}
                conn.execute('INSERT INTO mcp_room_approval_identity VALUES (?,?,?,?,?,?,?)',
                    (op['domain_key'],res['id'],res['ref_code'],res['created_at'],res['requester_user_id'],user['id'],res['decided_at']))
                completed=tz.now_iso()
                conn.execute('UPDATE mcp_room_approval SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_room_approval',target_id=operation_id,summary='MCP room request approved',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(conn,op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
