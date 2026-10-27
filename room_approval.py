"""Current Administrative Section approval of one plain internal room request."""
import hashlib
import json

import documents_permissions as permissions
from documents_storage import rows
import room_actions
import rooms
import storage as st
import telegram_preferences as preferences
import tzutil as tz


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def actor(conn,user):
    user=permissions.actor(conn,user)
    if not rooms.is_room_admin(conn,user):raise permissions.Denied('Current Administrative Section membership is required.')
    return user


def source(conn,user,room_request_id,*,for_write=True):
    user=actor(conn,user);res=rooms.get_reservation(conn,room_request_id)
    if not res or res['requester_user_id']==user['id']:
        raise permissions.Denied('Room request not found or unavailable for this decision.')
    if not for_write:return user,res,None
    if (res['status']!='requested' or not res['requester_user_id'] or res['source']!='internal'
            or res['standby'] or res['series_id'] or res['moves_reservation_id'] or res['event_id']
            or res['meals_requested'] or res.get('on_behalf_of')
            or conn.execute('SELECT 1 FROM room_meal WHERE reservation_id=?',(res['id'],)).fetchone()):
        raise ValueError('Use a plain internal pending request without meals, series, moves, standby or activity links.')
    if (not res['created_at'] or not res['title'].strip() or len(res['title'])>250 or len(res['purpose'] or '')>2000
            or res['modality'] not in rooms.MODALITIES or res['decided_at'] or res['decided_by']
            or conn.execute("SELECT 1 FROM room_notice WHERE reservation_id=? AND kind='approved' LIMIT 1",(res['id'],)).fetchone()
            or conn.execute('SELECT 1 FROM mcp_room_approval_identity WHERE room_id=? AND reference=? AND created_at=?',
                            (res['id'],res['ref_code'],res['created_at'])).fetchone()):
        raise ValueError('Use ordinary Rooms for earlier decisions or unsupported request metadata.')
    requester=permissions.actor(conn,{'id':res['requester_user_id']})
    if res['created_by']==user['username']:
        raise permissions.Denied('The filing actor cannot approve their own room request through this pilot.')
    slots=rooms.precheck(conn,res['day'],res['slot_ids'],today=tz.today_local())
    configured={s['id']:s for s in rooms.list_slots(conn)}
    selected=[configured[s] for s in slots]
    if len(selected)>12 or any(a['end_time']!=b['start_time'] for a,b in zip(selected,selected[1:])):
        raise ValueError('Use one continuous configured room block.')
    if res['day']==tz.today_local().isoformat() and selected[0]['start_time']<=tz.now_local().strftime('%H:%M'):
        raise ValueError('Use a room block whose start has not passed.')
    slot_rows=rows(conn,'SELECT * FROM room_reservation_slot WHERE reservation_id=? ORDER BY slot_id',(res['id'],))
    if any(r['day']!=res['day'] or r['is_approved'] for r in slot_rows):raise ValueError('Room-slot state needs review.')
    entry=None
    if res['calendar_entry_id']:
        _,entry=room_actions.meeting(conn,requester,res['calendar_entry_id'])
        if (entry['start_date']!=res['day'] or entry['title']!=res['title']
                or not entry.get('start_time') or not entry.get('end_time')
                or selected[0]['start_time']<entry['start_time'] or selected[-1]['end_time']>entry['end_time']):
            raise ValueError('Review the current linked meeting and requested hours in ordinary Rooms.')
    rivals=rows(conn,'''SELECT DISTINCT r.id,r.updated_at,r.created_at FROM room_reservation r
        JOIN room_reservation_slot rs ON rs.reservation_id=r.id WHERE r.id<>? AND r.status='requested'
        AND EXISTS(SELECT 1 FROM room_reservation_slot mine WHERE mine.reservation_id=?
          AND mine.day=rs.day AND mine.slot_id=rs.slot_id) ORDER BY r.id LIMIT 26''',(res['id'],res['id']))
    if len(rivals)>25:raise ValueError('Use ordinary Rooms for this competing-request count.')
    recipient={'id':requester['id'],'name':st._account_display_name(conn,requester['id']) or requester['username'],'email':requester['username']}
    rp=st.get_rp(conn,user['rp_id']) if user.get('rp_id') else None
    unit=rows(conn,'SELECT * FROM org_unit WHERE id=?',(rp['org_unit_id'],)) if rp else []
    approver={'id':user['id'],'name':st._account_display_name(conn,user['id']) or user['username'],'role':user['role']}
    pref=preferences.get(conn,requester['id'])
    policy={'feature_enabled':st.email_feature_enabled(conn,'room_decided'),'room_email':bool(pref['room_email']),
            'room_ics':st.email_option_enabled(conn,'room_ics'),'quiet_start':pref['quiet_start'],'quiet_end':pref['quiet_end']}
    revision=digest([res,slot_rows,selected,entry,rivals,rp,unit,approver,recipient,policy])
    return user,res,{'expected_revision':revision,'slots':selected,'recipient':recipient,'approver':approver,
                    'policy':policy,'competing_request_count':len(rivals),'linked_meeting_digest':digest(entry)}


def live_digest(conn,res):
    slots=rows(conn,'SELECT * FROM room_reservation_slot WHERE reservation_id=? ORDER BY slot_id',(res['id'],))
    configured=rows(conn,'''SELECT s.* FROM room_slot s JOIN room_reservation_slot rs ON rs.slot_id=s.id
        WHERE rs.reservation_id=? ORDER BY s.id''',(res['id'],))
    return digest([res,slots,configured])


def approve_in_transaction(conn,user,room_request_id,expected_revision,reason):
    if not conn.in_transaction:raise RuntimeError('Room approval requires a caller-owned transaction.')
    user,res,info=source(conn,user,room_request_id)
    if info['expected_revision']!=expected_revision:raise ValueError('The request, authority, hours or notice routing changed.')
    approved,_,rivals=rooms.approve_in_transaction(conn,res['id'],user['username'],reason,today=tz.today_local(),decline_rivals=False)
    if rivals:raise RuntimeError('This pilot must never decline another request.')
    return approved,info
