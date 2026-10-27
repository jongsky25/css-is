"""Shared activity date policy and constrained, caller-owned date changes."""
from datetime import date
import hashlib
import json

import activity_permissions
import documents_permissions as permissions
from documents_storage import rows
import storage as st
import tzutil as tz


def date_bounds(today=None,years_back=5,years_ahead=2):
    today=today or tz.today_local()
    try:
        lo=today.replace(year=today.year-years_back);hi=today.replace(year=today.year+years_ahead)
    except ValueError:
        lo=today.replace(year=today.year-years_back,day=28);hi=today.replace(year=today.year+years_ahead,day=28)
    return lo.isoformat(),hi.isoformat()


def exact_date(value):
    if not isinstance(value,str) or len(value)!=10 or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('Use an exact YYYY-MM-DD date.')
    return value


def owned_context(conn,user,event_id,*,for_write=True):
    user=permissions.actor(conn,user)
    found=rows(conn,'SELECT * FROM event WHERE id=?',(event_id,))
    if not found or not activity_permissions.can_manage(user,found[0],conn):
        raise permissions.Denied('Activity not found or unavailable to you.')
    ev=found[0]
    if not for_write:return user,ev,None
    forms=rows(conn,'SELECT f.* FROM event_form ef JOIN form_instance f ON f.id=ef.form_instance_id WHERE ef.event_id=? ORDER BY ef.ordinal,f.id LIMIT 2',(event_id,))
    if (ev.get('event_kind','bureau')!='bureau' or ev.get('end_date') or len(forms)!=1
            or ev['event_date']<=tz.today_local().isoformat()):
        raise ValueError('Use a future single-day bureau activity with one event-review form.')
    form=forms[0]
    if (form['survey_type']!=2 or form['form']!='F2' or form.get('archived') or form.get('pooled')
            or form.get('encoding_locked') or form.get('end_date') or form['event_date']!=ev['event_date']
            or form.get('open_at') or form.get('close_at') or form.get('attendance') is not None):
        raise ValueError('The event-review form or its entry window is outside this pilot.')
    guards=(('SELECT 1 FROM attendee WHERE event_id=? LIMIT 1',event_id),
            ('SELECT 1 FROM activity_demographics WHERE event_id=? LIMIT 1',event_id),
            ('SELECT 1 FROM response WHERE form_instance_id=? LIMIT 1',form['id']),
            ('SELECT 1 FROM event_form WHERE form_instance_id=? AND event_id<>? LIMIT 1',(form['id'],event_id)),
            ('SELECT 1 FROM calendar_entry WHERE event_id=? LIMIT 1',event_id),
            ('SELECT 1 FROM room_reservation WHERE event_id=? LIMIT 1',event_id),
            ('SELECT 1 FROM travel_filing WHERE event_id=? LIMIT 1',event_id))
    for sql,values in guards:
        if conn.execute(sql,values if isinstance(values,tuple) else (values,)).fetchone():
            raise ValueError('Use the ordinary activity screen for registrations, responses, shared forms or linked work.')
    rp=st.get_rp(conn,user['rp_id']) if user.get('rp_id') else None
    authority=[user['id'],user['username'],user['role'],rp,st.team_scope_for_user(conn,user),st.event_scope_paths(conn,event_id)]
    # Bind all stored metadata without copying private messages or location into MCP results.
    revision=hashlib.sha256(json.dumps([ev,form,authority],sort_keys=True,default=str).encode()).hexdigest()
    return user,ev,{'expected_revision':revision,'form_id':form['id'],'form_count':1}


def check_new_date(event_date):
    value=exact_date(event_date)
    if not tz.today_local().isoformat()<value<=date_bounds()[1]:
        raise ValueError('Choose a future activity date within the ordinary two-year horizon.')
    return value


def change_in_transaction(conn,user,event_id,expected_revision,event_date):
    if not conn.in_transaction:raise RuntimeError('Activity dates require a caller-owned transaction.')
    user,ev,info=owned_context(conn,user,event_id)
    check_new_date(event_date)
    if info['expected_revision']!=expected_revision:raise ValueError('The activity changed. Prepare a new preview.')
    if ev['event_date']==event_date:raise ValueError('Choose a different future date.')
    changed=st.set_event_dates(conn,event_id,event_date,None,commit=False)
    if changed!=1:raise RuntimeError('The activity form changed during scheduling.')
    st.audit(conn,user['username'],'event_dates_set',target_type='event',target_id=event_id,
             summary='Updated upcoming unused activity date on one event-review form',commit=False)
    return {'event_id':event_id,'event_token':ev['event_token'],'created_at':ev['created_at'],
            'old_event_date':ev['event_date'],'event_date':event_date,'updated_forms':changed}
