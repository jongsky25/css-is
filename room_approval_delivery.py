"""Durable single-attempt requester email for MCP-approved rooms only."""
import json
import os
import time
from uuid import uuid4

from documents_storage import rows,transaction
import mcp_actions as actions
import mcp_room_approvals as pilot
import room_approval as approval
import room_actions
import rooms
import rooms_notify
import storage as st
import telegram_preferences as preferences
import mailer
import tzutil as tz


def _finish(conn,notice_id,state,*,attempt=None,recipient=None,subject=None):
    where="notice_id=? AND state='queued'" if attempt is None else "notice_id=? AND state='attempting' AND attempt_id=?"
    args=(state,tz.now_iso(),notice_id) if attempt is None else (state,tz.now_iso(),notice_id,attempt)
    if not conn.execute('UPDATE mcp_room_approval_notice SET state=?,finished_at=? WHERE '+where,args).rowcount:return
    status={'sent':'sent','uncertain':'failed','skipped_off':'skipped_off','not_configured':'not_configured','cancelled':'skipped_none'}[state]
    conn.execute('UPDATE room_notice SET email_status=?,emailed_at=? WHERE id=?',(status,tz.now_iso(),notice_id))
    if recipient:
        conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
            (tz.now_iso(),'room_decided',recipient,subject,status,'MCP durable room approval: '+state+'; no automatic retry'))


def _transport(to,subject,body,html=None,attachments=None):
    return mailer.send(to,subject,body,html=html,attachments=attachments)


def run(conn,*,send=None,limit=5):
    if type(limit) is not int or not 1<=limit<=20:raise ValueError('Use a batch of 1–20.')
    with transaction(conn):
        pilot.prune(conn)
        for row in rows(conn,"SELECT notice_id,attempt_id FROM mcp_room_approval_notice WHERE state='attempting' AND attempted_at<=? LIMIT 20",(int(time.time())-600,)):
            _finish(conn,row['notice_id'],'uncertain',attempt=row['attempt_id'])
        for row in rows(conn,"SELECT notice_id FROM mcp_room_approval_notice WHERE state='queued' AND created_at<=? LIMIT 20",(int(time.time())-86400,)):
            _finish(conn,row['notice_id'],'cancelled')
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(pilot.FLAG)!='1':return 0
    send=send or _transport;attempted=0
    pending=rows(conn,"SELECT notice_id FROM mcp_room_approval_notice WHERE state='queued' ORDER BY notice_id LIMIT ?",(limit,))
    for row in pending:
        notice_id=row['notice_id']
        with transaction(conn):
            mapped=rows(conn,"SELECT * FROM mcp_room_approval_notice WHERE notice_id=? AND state='queued'",(notice_id,))
            if not mapped:continue
            try:
                op=rows(conn,'SELECT * FROM mcp_room_approval WHERE domain_key=?',(mapped[0]['operation_key'],))[0]
                user=st.get_admin_user_by_id(conn,op['owner_id'])
                pilot._check(conn,user,op,op['resource'])
                result=json.loads(op['result_json']);res=rooms.get_reservation(conn,op['room_id'])
                requester=st.get_admin_user_by_id(conn,res['requester_user_id'])
                if not requester or not requester['active']:raise ValueError
                recipient={'id':requester['id'],'name':st._account_display_name(conn,requester['id']) or requester['username'],'email':requester['username']}
                entry=None
                if res['calendar_entry_id']:_,entry=room_actions.meeting(conn,requester,res['calendar_entry_id'])
                if (res['status']!='approved' or res['day']<tz.today_local().isoformat()
                        or approval.live_digest(conn,res)!=result['live_digest']
                        or pilot._digest(recipient)!=result['recipient_digest']
                        or approval.digest(entry)!=result['linked_meeting_digest']
                        or st.email_option_enabled(conn,'room_ics')!=result['room_ics']):raise ValueError
                slots={s['id']:s for s in rooms.list_slots(conn)}
                if res['day']==tz.today_local().isoformat() and slots[res['slot_ids'][0]]['start_time']<=tz.now_local().strftime('%H:%M'):raise ValueError
                notices=rows(conn,"SELECT * FROM room_notice WHERE id=? AND reservation_id=? AND user_id=? AND kind='approved'",(notice_id,res['id'],requester['id']))
                if not notices:raise ValueError
                notice=notices[0]
            except (ValueError,TypeError,KeyError,IndexError,actions.ActionError):
                _finish(conn,notice_id,'cancelled');continue
            built=rooms_notify._build(conn,notice,op['resource'].removesuffix('/mcp'),recipient['name'],True)
            if not built:_finish(conn,notice_id,'cancelled');continue
            feature,subject,body,html,attachments=built
            pref=preferences.get(conn,requester['id'])
            if not st.email_feature_enabled(conn,feature) or not pref['room_email']:
                _finish(conn,notice_id,'skipped_off',recipient=recipient['email'],subject=subject);continue
            if preferences.quiet_until(pref,tz.now_local()):continue
            if not mailer.email_configured():
                _finish(conn,notice_id,'not_configured',recipient=recipient['email'],subject=subject);continue
            attempt=str(uuid4())
            conn.execute("UPDATE mcp_room_approval_notice SET state='attempting',attempt_id=?,attempted_at=? WHERE notice_id=? AND state='queued'",(attempt,int(time.time()),notice_id))
            conn.execute('UPDATE room_notice SET attempts=attempts+1 WHERE id=?',(notice_id,))
        attempted+=1;state='uncertain'
        try:
            answer=send(recipient['email'],subject,body,html=html,attachments=attachments)
            if isinstance(answer,dict) and answer.get('sent') is True:state='sent'
        except Exception:pass
        with transaction(conn):_finish(conn,notice_id,state,attempt=attempt,recipient=recipient['email'],subject=subject)
    return attempted
