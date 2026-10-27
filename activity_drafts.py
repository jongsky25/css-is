"""Owner-private activity preparation; saving never creates an event or survey."""
import hashlib
import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

import activity_scheduling as scheduling
import auth
import documents_permissions as permissions
from documents_storage import rows
import storage as st
import tzutil as tz


class Conflict(ValueError):pass


class DraftFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    activity_name: StrictStr = Field(min_length=1,max_length=200)
    event_date: StrictStr = Field(min_length=10,max_length=10)
    section_id: StrictInt = Field(ge=1,le=2**63-1)
    venue: StrictStr = Field(default='',max_length=240)

    @model_validator(mode='after')
    def exact(self):
        self.activity_name,self.venue=self.activity_name.strip(),self.venue.strip()
        if not self.activity_name or any(ord(c)<32 or ord(c)==127 for c in self.activity_name+self.venue):
            raise ValueError('Use a one-line activity title and venue.')
        scheduling.exact_date(self.event_date)
        return self


def normalize(fields):return DraftFields.model_validate(fields).model_dump()


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def install(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS activity_draft (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      fields_json TEXT NOT NULL, section_json TEXT NOT NULL,
      operation_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS activity_draft_owner ON activity_draft(owner_id,id);''')
    conn.executescript('''CREATE TABLE IF NOT EXISTS activity_draft_save (
      operation_key TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      request_digest TEXT NOT NULL, draft_id INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS activity_draft_save_owner ON activity_draft_save(owner_id);''')


def actor(conn,user):
    user=permissions.actor(conn,user)
    if not auth.can(user['role'],'create_activity'):
        raise permissions.Denied('Activity preparation is unavailable to this account.')
    return user


def key(value):
    try:
        parsed=UUID(value)
        if parsed.version!=4 or str(parsed)!=value:raise ValueError
    except (ValueError,TypeError,AttributeError):
        raise ValueError('Use the original private draft key.') from None
    return value


def context(conn,user,fields):
    user=actor(conn,user);values=normalize(fields)
    lo,hi=scheduling.date_bounds()
    if not lo<=values['event_date']<=hi:
        raise ValueError('Choose an activity date within the ordinary Create date range.')
    section=rows(conn,"SELECT id,name,path FROM org_unit WHERE id=? AND level='section'",(values['section_id'],))
    if not section:raise ValueError('Choose a current organizing section.')
    rp=st.get_rp(conn,user['rp_id']) if user.get('rp_id') else None
    return {'section':section[0], 'requester':{'id':user['id'],'name':st._account_display_name(conn,user['id']) or user['username'],
            'identity_digest':_digest([user['username'],user['role'],user.get('rp_id'),rp])},
            'event_type':'bureau','modality':'f2f','qr_mode':'combined'}


def get(conn,user,draft_key):
    user=actor(conn,user)
    found=rows(conn,'''SELECT d.* FROM activity_draft d JOIN activity_draft_save s
        ON s.operation_key=d.operation_key AND s.draft_id=d.id AND s.owner_id=d.owner_id
        WHERE d.operation_key=? AND d.owner_id=?''',(key(draft_key),user['id']))
    if not found:raise permissions.Denied('Private activity draft not found or unavailable to you.')
    draft=found[0]
    return dict(draft,fields=json.loads(draft['fields_json']),section=json.loads(draft['section_json']))


def listing(conn,user,*,before=None,limit=20):
    user=actor(conn,user)
    if type(limit) is not int or not 1<=limit<=25 or (before is not None and (type(before) is not int or not 1<=before<=2**63-1)):
        raise ValueError('Use a valid private draft page.')
    where='owner_id=?';args=[user['id']]
    if before is not None:where+=' AND id<?';args.append(before)
    found=rows(conn,'SELECT id,fields_json,section_json,operation_key,created_at FROM activity_draft WHERE '+where+' ORDER BY id DESC LIMIT ?',(*args,limit+1))
    return {'data':[dict(r,fields=json.loads(r['fields_json']),section=json.loads(r['section_json'])) for r in found[:limit]],
            'next_before':found[limit-1]['id'] if len(found)>limit else None}


def save_in_transaction(conn,user,fields,*,operation_key,expected_context=None):
    if not conn.in_transaction:raise RuntimeError('Private activity drafts require a caller-owned transaction.')
    user=actor(conn,user);values=normalize(fields);operation_key=key(operation_key)
    prior=conn.execute('SELECT owner_id,request_digest FROM activity_draft_save WHERE operation_key=?',(operation_key,)).fetchone()
    if prior:
        if prior[0]!=user['id']:raise permissions.Denied('Private activity draft unavailable.')
        if prior[1]!=_digest(values):raise Conflict('This key belongs to a different private draft.')
        saved=get(conn,user,operation_key)
        if saved['fields']!=values:raise Conflict('This key belongs to a different private draft.')
        return saved
    current=context(conn,user,values)
    if expected_context is not None and current!=expected_context:
        raise Conflict('The requester or organizing section changed. Review a new preview.')
    if conn.execute('SELECT COUNT(*) FROM activity_draft WHERE owner_id=?',(user['id'],)).fetchone()[0]>=1000:
        raise Conflict('The private activity draft limit has been reached. Use the ordinary Create screen.')
    if conn.execute('SELECT COUNT(*) FROM activity_draft_save WHERE owner_id=?',(user['id'],)).fetchone()[0]>=10000:
        raise Conflict('The private activity draft key limit has been reached. Use the ordinary Create screen.')
    draft_id=conn.execute('INSERT INTO activity_draft(owner_id,fields_json,section_json,operation_key,created_at) VALUES (?,?,?,?,?)',
        (user['id'],_json(values),_json(current['section']),operation_key,tz.now_iso())).lastrowid
    conn.execute('INSERT INTO activity_draft_save VALUES (?,?,?,?)',(operation_key,user['id'],_digest(values),draft_id))
    st.audit(conn,user['username'],'activity_draft_save',target_type='activity_draft',target_id=draft_id,
             summary='Saved own private activity preparation draft',commit=False)
    return get(conn,user,operation_key)


def prefill(conn,user,draft_key):
    draft=get(conn,user,draft_key)
    context(conn,user,draft['fields'])
    # This GET prefill never consumes the draft or calls the live creation service.
    return {**draft['fields'],'section_id':str(draft['fields']['section_id']),
            'event_type':'bureau','modality':'f2f','qr_mode':'combined'}
