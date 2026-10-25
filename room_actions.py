"""Actor-aware linking of one plain room request, inside a caller transaction."""
import hashlib
import json

import calendar_actions
import office_calendar as calendar
import rooms
import storage as st
import tzutil as tz


def meeting(conn,user,entry_id,*,for_write=True):
    user=calendar_actions.actor(conn,user)
    entry=calendar.viewable_entry(conn,user,entry_id)
    if (not entry or not (entry['created_by']==user['username'] or any(p['user_id']==user['id'] for p in entry['people']))
            or (for_write and (entry['kind']!='meeting' or entry.get('event_id') or entry.get('rrule')
                or entry['status']=='cancelled' or entry.get('cancelled_at')
                or (entry.get('end_date') and entry['end_date']!=entry['start_date'])))):
        raise ValueError('Meeting unavailable for a linked room request. Choose a one-day meeting you created or participate in.')
    return user,entry


def revision(entry):
    return hashlib.sha256(json.dumps({**entry,'people':[{k:p[k] for k in ('user_id','role')} for p in entry['people']]},sort_keys=True,default=str).encode()).hexdigest()


def validate(conn,user,entry_id,slots,expected):
    user,entry=meeting(conn,user,entry_id)
    if revision(entry)!=expected:
        raise ValueError('The meeting changed. Prepare a new room preview.')
    if any(r['status'] in ('requested','approved') for r in rooms.reservations_for_entry(conn,entry_id)):
        raise ValueError('This meeting already has a live room request. Review it in Office Connect.')
    rooms.precheck(conn,entry['start_date'],slots,today=tz.today_local())
    return user,entry


def request_in_transaction(conn,user,entry_id,slots,expected):
    if not conn.in_transaction:
        raise RuntimeError('Linked requests require a caller-owned writer transaction.')
    user,entry=validate(conn,user,entry_id,slots,expected)
    record=rooms.request(conn,title=entry['title'],day=entry['start_date'],slot_ids=slots,
                         requester_user_id=user['id'],actor=user['username'],today=tz.today_local(),
                         modality='f2f',purpose='Requested for linked calendar meeting.',commit=False)
    return rooms.link_entry(conn,record['id'],entry_id,user,commit=False)
