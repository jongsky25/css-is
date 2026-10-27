"""M3.7 standalone own meal requests, confirmed in the signed-in browser."""
from datetime import date, timedelta
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
import meals
import rooms
import rooms_meals
import rooms_notify
import storage as st
import tzutil as tz

SCOPE = 'meals:request'
FLAG = 'CSS_MCP_MEAL_REQUESTS_ENABLED'


class MealLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    meal: Literal['breakfast', 'am_snack', 'lunch', 'pm_snack']
    deliver_at: StrictStr = Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')


class RequestFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: StrictStr = Field(min_length=1, max_length=240)
    day: StrictStr = Field(min_length=10, max_length=10)
    venue: StrictStr = Field(min_length=1, max_length=240)
    pax: StrictInt = Field(ge=1, le=1000)
    special_request: StrictStr = Field(default='', max_length=800)
    meals: list[MealLine] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def exact(self):
        self.title, self.venue, self.special_request = self.title.strip(), self.venue.strip(), self.special_request.strip()
        if not self.title or not self.venue or any(ord(c) < 32 or ord(c) == 127 for c in self.title+self.venue):
            raise ValueError('Use an activity title and delivery location on one line.')
        if any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 for c in self.special_request):
            raise ValueError('Remove control characters from the special request.')
        if date.fromisoformat(self.day).isoformat() != self.day:
            raise ValueError('Use a YYYY-MM-DD activity date.')
        if len({m.meal for m in self.meals}) != len(self.meals):
            raise ValueError('Choose each meal only once.')
        for line in self.meals:
            try:
                rooms_meals._clean_time(line.deliver_at, rooms_meals.LABEL[line.meal])
            except rooms_meals.MealError:
                raise ValueError('Use delivery times between 06:00 and 19:00.') from None
        self.meals.sort(key=lambda line: line.meal)
        return self


def normalize(fields):
    return RequestFields.model_validate(fields).model_dump()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS mcp_meal_request (
      owner_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
      grant_id TEXT NOT NULL, resource TEXT NOT NULL, request_digest TEXT NOT NULL,
      snapshot_digest TEXT NOT NULL, payload_json TEXT, snapshot_json TEXT,
      domain_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      completed_at TEXT, result_json TEXT, PRIMARY KEY(owner_id,operation_id));
    CREATE INDEX IF NOT EXISTS mcp_meal_request_expiry ON mcp_meal_request(expires_at) WHERE payload_json IS NOT NULL;
    CREATE TABLE IF NOT EXISTS mcp_meal_identity (
      request_id INTEGER PRIMARY KEY REFERENCES meal_request(id) ON DELETE CASCADE,
      operation_key TEXT NOT NULL UNIQUE REFERENCES mcp_meal_request(domain_key));''')


def _json(value): return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _digest(value): return hashlib.sha256(_json(value).encode()).hexdigest()


def _enabled():
    if os.environ.get('CSS_MCP_ENABLED') != '1' or os.environ.get(FLAG) != '1':
        raise actions.ActionError('not_available', 'Meal requests through ChatGPT are disabled.')


def prune(conn):
    conn.execute('''UPDATE mcp_meal_request SET payload_json=NULL,snapshot_json=NULL WHERE rowid IN
      (SELECT rowid FROM mcp_meal_request WHERE payload_json IS NOT NULL AND expires_at<=?
       ORDER BY expires_at LIMIT 100)''', (int(time.time()),))


def _domain_fields(values):
    return {k: values[k] for k in ('title','day','venue','pax','special_request')} | {
        'wanted': [m['meal'] for m in values['meals']], 'times': {m['meal']:m['deliver_at'] for m in values['meals']}}


def _staff(conn):
    # Same active Administrative Section membership as the ordinary meal queue.
    return sorted(({'id':a['id'], 'name':a['name']} for a in rooms_notify.approver_accounts(conn)), key=lambda a:a['id'])


def context(conn, user, values):
    user = permissions.actor(conn, user)
    try:
        meals.validate(**_domain_fields(values), today=tz.today_local())
    except meals.MealError:
        raise actions.ActionError('meal_unavailable', 'Review the meal fields and the current two-calendar-day deadline in Office Connect.') from None
    rp = st.get_rp(conn, user['rp_id']) if user.get('rp_id') else None
    return {'requester': {'id':user['id'], 'name':st._account_display_name(conn,user['id']) or user['username'],
                         'identity_digest':_digest([user['username'],user.get('rp_id'),rp])},
            'queue_staff':_staff(conn), 'lead_days':rooms.MEAL_LEAD_DAYS,
            'delivery_earliest':rooms_meals.EARLIEST, 'delivery_latest':rooms_meals.LATEST}


def _op(conn, owner_id, key):
    found = rows(conn,'SELECT * FROM mcp_meal_request WHERE owner_id=? AND operation_id=?',(owner_id,actions._key(key)))
    if not found: raise permissions.Denied('Meal operation not found or unavailable to you.')
    return found[0]


def _check(conn, user, op, resource):
    _enabled()
    actions._grant(conn,op['grant_id'],user['id'],resource,SCOPE)
    user = permissions.actor(conn,user)
    if op['resource'] != resource: raise permissions.Denied('Meal operation not found or unavailable to you.')
    if op['completed_at']:
        result = json.loads(op['result_json'])
        record = meals.get(conn,result['id'])
        if (not record or record['requester_user_id'] != user['id'] or record['ref_code'] != result['reference']
                or record['created_at'] != result['created_at'] or not conn.execute(
                    'SELECT 1 FROM mcp_meal_identity WHERE request_id=? AND operation_key=?',(result['id'],op['domain_key'])).fetchone()):
            raise permissions.Denied('The original meal request source is unavailable.')
        return
    if op['expires_at'] <= int(time.time()) or not op['payload_json']:
        raise actions.ActionError('preview_expired','This meal preview expired. Prepare and review a new operation.')
    try:
        values, snapshot = json.loads(op['payload_json']), json.loads(op['snapshot_json'])
        if normalize(values) != values or _digest(values) != op['request_digest'] or _digest(snapshot) != op['snapshot_digest']:
            raise ValueError
    except (ValueError,TypeError):
        raise actions.ActionError('preview_mismatch','The stored meal preview changed. Prepare and review a new operation.') from None
    if context(conn,user,values) != snapshot:
        raise actions.ActionError('revision_conflict','The requester, queue staff or meal policy changed. Prepare and review a new preview.')


def _preview_digest(op):
    return _digest([op[k] for k in ('owner_id','operation_id','grant_id','resource','request_digest','snapshot_digest','domain_key','created_at','expires_at')])


def _result(op, origin):
    result = json.loads(op['result_json']) if op['completed_at'] else None
    return {'operation_id':op['operation_id'], 'action':'prepare_meal_request',
            'status':'completed' if result else 'awaiting_confirmation', 'completed_at':op['completed_at'], 'expires_at':op['expires_at'],
            'meal_request_id':str(result['id']) if result else None, 'reference':result['reference'] if result else None,
            'submitted_status':'submitted' if result else None, 'meal_status':'pending' if result else None,
            'next_actor':{'role':'administrative_section_meal_ordering','queue_staff_count':result['queue_staff_count']} if result else None,
            'notification_status':'none_created',
            'web_url':origin+('/meals/'+str(result['id']) if result else '/meals/mine'),
            'confirmation_url':origin+'/account/integrations/mcp/meal-requests/'+op['operation_id'],
            'instruction':('Meal request submitted to the Administrative Section queue; meals were awaiting order at creation. No supplier order, delivery or email was performed. This is the original result; inspect the source for current status.'
                           if result else 'Review the exact activity, delivery location, headcount, meals, delivery times, special request and queue visibility in Office Connect before confirming. No meal request has been created yet. Keep this key for recovery.')}


def read_context(conn, token, resource, origin):
    with transaction(conn):
        _enabled(); user,_ = actions.token_actor(conn,token,resource,SCOPE)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_meal_request',summary='MCP own meal preparation context',commit=False)
        return {'earliest_day':(tz.today_local()+timedelta(days=rooms.MEAL_LEAD_DAYS)).isoformat(),
                'timezone':'Asia/Manila','lead_calendar_days':rooms.MEAL_LEAD_DAYS,'maximum_pax':1000,
                'meal_types':[{'meal':m,'label':label} for m,label in rooms_meals.MEALS],
                'earliest_delivery':rooms_meals.EARLIEST,'latest_delivery':rooms_meals.LATEST,
                'queue_staff_count':len(_staff(conn)), 'web_url':origin+'/meals/new'}


def prepare(conn, token, resource, origin, operation_id, fields):
    actions._key(operation_id); values = normalize(fields)
    with transaction(conn): prune(conn)
    with transaction(conn):
        _enabled(); user,grant_id = actions.token_actor(conn,token,resource,SCOPE); digest = _digest(values)
        if conn.execute('SELECT 1 FROM mcp_meal_request WHERE owner_id=? AND operation_id=?',(user['id'],operation_id)).fetchone():
            op = _op(conn,user['id'],operation_id)
            if op['grant_id'] != grant_id or op['request_digest'] != digest:
                raise actions.ActionError('idempotency_conflict','This key belongs to a different meal request or connection. Recover the original operation.')
            _check(conn,user,op,resource); return _result(op,origin)
        snapshot = context(conn,user,values)
        count,pending = conn.execute('SELECT COUNT(*),COALESCE(SUM(completed_at IS NULL AND expires_at>?),0) FROM mcp_meal_request WHERE owner_id=?',(int(time.time()),user['id'])).fetchone()
        if count >= 10000 or pending >= 50: raise actions.ActionError('operation_capacity','The meal preview limit has been reached.')
        now = int(time.time())
        conn.execute('INSERT INTO mcp_meal_request VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                     (user['id'],operation_id,grant_id,resource,digest,_digest(snapshot),_json(values),_json(snapshot),str(uuid4()),now,now+actions.PREVIEW_SECONDS))
        st.audit(conn,user['username'],'integration_action_prepare',target_type='mcp_meal_request',target_id=operation_id,summary='MCP own meal request preview',commit=False)
        return _result(_op(conn,user['id'],operation_id),origin)


def recover(conn, token, resource, origin, operation_id):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user,grant_id = actions.token_actor(conn,token,resource,SCOPE); op = _op(conn,user['id'],operation_id)
        if op['grant_id'] != grant_id: raise permissions.Denied('Meal operation not found or unavailable to you.')
        _check(conn,user,op,resource)
        st.audit(conn,user['username'],'integration_read',target_type='mcp_meal_request',target_id=operation_id,summary='MCP own meal receipt read',commit=False)
        return _result(op,origin)


def browser(conn, payload, resource, origin, operation_id, *, confirm_digest=None):
    with transaction(conn): prune(conn)
    with transaction(conn):
        user = st.session_actor(conn,payload) if payload else None
        if not user: raise permissions.Denied('Sign in again to review this meal request.')
        op = _op(conn,user['id'],operation_id); _check(conn,user,op,resource)
        if confirm_digest is not None:
            if confirm_digest != _preview_digest(op): raise actions.ActionError('preview_mismatch','The confirmation does not match this meal request.')
            if not op['completed_at']:
                values,snapshot = json.loads(op['payload_json']),json.loads(op['snapshot_json'])
                try:
                    record = meals.create(conn,user,**_domain_fields(values),today=tz.today_local(),commit=False)
                except meals.MealError:
                    raise actions.ActionError('meal_unavailable','The meal fields or deadline changed. Prepare a new preview.') from None
                result = {'id':record['id'],'reference':record['ref_code'],'created_at':record['created_at'],'queue_staff_count':len(snapshot['queue_staff'])}
                conn.execute('INSERT INTO mcp_meal_identity VALUES (?,?)',(record['id'],op['domain_key']))
                completed = tz.now_iso()
                conn.execute('UPDATE mcp_meal_request SET completed_at=?,result_json=?,payload_json=NULL,snapshot_json=NULL WHERE owner_id=? AND operation_id=?',
                             (completed,_json(result),user['id'],operation_id))
                st.audit(conn,user['username'],'integration_action_complete',target_type='mcp_meal_request',target_id=operation_id,summary='MCP own meal request submitted',commit=False)
                op.update(completed_at=completed,result_json=_json(result),payload_json=None,snapshot_json=None)
        return dict(_result(op,origin),preview_digest=_preview_digest(op),fields=json.loads(op['payload_json']) if op['payload_json'] else None,
                    snapshot=json.loads(op['snapshot_json']) if op['snapshot_json'] else None)
