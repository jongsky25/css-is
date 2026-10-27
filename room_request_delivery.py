"""Single-attempt notification delivery for MCP-created room requests only."""
import json
import os
import time
from uuid import uuid4

from documents_storage import rows, transaction
import mcp_actions as actions
import mcp_room_requests as pilot
import mailer
import rooms
import rooms_notify
import storage as st
import tzutil as tz


def _finish(conn, notice_id, state, *, attempt=None, recipient=None, subject=None):
    where = "notice_id=? AND state='queued'" if attempt is None else "notice_id=? AND state='attempting' AND attempt_id=?"
    args = (state,tz.now_iso(),notice_id) if attempt is None else (state,tz.now_iso(),notice_id,attempt)
    if not conn.execute('UPDATE mcp_room_notice SET state=?,finished_at=? WHERE '+where,args).rowcount:return
    status = 'sent' if state=='sent' else 'failed' if state=='uncertain' else 'skipped_off' if state=='skipped_off' else 'not_configured' if state=='not_configured' else 'skipped_none'
    conn.execute('UPDATE room_notice SET email_status=?,emailed_at=? WHERE id=?',(status,tz.now_iso(),notice_id))
    if recipient:
        conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
            (tz.now_iso(),'room_new_request',recipient,subject,status,'MCP durable room notice: '+state+'; no automatic retry'))


def _transport(to,subject,body,html=None):
    # run owns the feature/pause gates, durable claim and atomic result logging.
    return mailer.send(to,subject,body,html=html)


def run(conn, *, send=None, limit=5):
    if type(limit) is not int or not 1<=limit<=20:raise ValueError('Use a batch of 1–20.')
    with transaction(conn):
        pilot.prune(conn)
        for row in rows(conn,"SELECT notice_id,attempt_id FROM mcp_room_notice WHERE state='attempting' AND attempted_at<=? LIMIT 20",(int(time.time())-600,)):
            _finish(conn,row['notice_id'],'uncertain',attempt=row['attempt_id'])
        for row in rows(conn,"SELECT notice_id FROM mcp_room_notice WHERE state='queued' AND created_at<=? LIMIT 20",(int(time.time())-86400,)):
            _finish(conn,row['notice_id'],'cancelled')
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(pilot.FLAG)!='1':return 0
    send = send or _transport
    ids = [r[0] for r in conn.execute("SELECT notice_id FROM mcp_room_notice WHERE state='queued' ORDER BY notice_id LIMIT ?",(limit,))]
    attempted=0
    for notice_id in ids:
        with transaction(conn):
            mapped=rows(conn,"SELECT * FROM mcp_room_notice WHERE notice_id=? AND state='queued'",(notice_id,))
            if not mapped:continue
            op=rows(conn,'SELECT * FROM mcp_room_request WHERE domain_key=?',(mapped[0]['operation_key'],))
            notice=rows(conn,'SELECT * FROM room_notice WHERE id=?',(notice_id,))
            try:
                if not op or not notice:raise ValueError
                op,notice=op[0],notice[0]
                owner=st.get_admin_user_by_id(conn,op['owner_id'])
                if not owner:raise ValueError
                pilot._check(conn,owner,op,op['resource'])
                result=json.loads(op['result_json']);room=rooms.get_reservation(conn,result['room_id'])
                recipient=next((a for a in rooms_notify.approver_accounts(conn) if a['id']==notice['user_id'] and a['id']!=owner['id']),None)
                if (not recipient or result['recipient_digests'].get(str(recipient['id']))!=pilot._digest(recipient['username'])
                        or notice['kind']!='new_request' or notice['reservation_id']!=room['id'] or room['status']!='requested'
                        or room['day']<tz.today_local().isoformat() or pilot.room_digest(room)!=result['room_digest']):raise ValueError
            except (ValueError,TypeError,KeyError,actions.ActionError):
                _finish(conn,notice_id,'cancelled');continue
            origin=op['resource'].removesuffix('/mcp')
            built=rooms_notify._build(conn,notice,origin,recipient['name'],True)
            if not built:_finish(conn,notice_id,'cancelled');continue
            feature,subject,body,html,_attachments=built
            if not st.email_feature_enabled(conn,feature):
                _finish(conn,notice_id,'skipped_off',recipient=recipient['username'],subject=subject);continue
            if not mailer.email_configured():
                _finish(conn,notice_id,'not_configured',recipient=recipient['username'],subject=subject);continue
            attempt=str(uuid4())
            conn.execute("UPDATE mcp_room_notice SET state='attempting',attempt_id=?,attempted_at=? WHERE notice_id=? AND state='queued'",(attempt,int(time.time()),notice_id))
            conn.execute('UPDATE room_notice SET attempts=attempts+1 WHERE id=?',(notice_id,))
        attempted+=1;state='uncertain'
        try:
            answer=send(recipient['username'],subject,body,html=html)
            if isinstance(answer,dict) and answer.get('sent') is True:state='sent'
        except Exception:pass
        with transaction(conn):_finish(conn,notice_id,state,attempt=attempt,recipient=recipient['username'],subject=subject)
    return attempted
