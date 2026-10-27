"""Single-attempt delivery of approval notices for MCP work-arrangement filings."""
import json
import os
import time
from uuid import uuid4

from documents_storage import rows, transaction
import mcp_actions as actions
import mcp_work_arrangements as pilot
import mailer
import storage as st
import tzutil as tz


def _finish(conn,key,recipient_id,state,*,attempt=None,recipient=None,subject=None):
    clause="operation_key=? AND recipient_id=? AND state='queued'" if attempt is None else "operation_key=? AND recipient_id=? AND state='attempting' AND attempt_id=?"
    args=(state,tz.now_iso(),key,recipient_id) if attempt is None else (state,tz.now_iso(),key,recipient_id,attempt)
    changed=conn.execute('UPDATE mcp_work_arrangement_mail SET state=?,finished_at=?,payload_json=NULL WHERE '+clause,args).rowcount
    if changed and recipient:
        status='sent' if state=='sent' else 'skipped_off' if state=='skipped_off' else 'not_configured' if state=='not_configured' else 'failed'
        conn.execute('INSERT INTO email_log(created_at,feature,recipient,subject,status,detail) VALUES (?,?,?,?,?,?)',
                     (tz.now_iso(),'awa_approval',recipient,subject,status,'MCP durable filing notice: '+state+'; no automatic retry'))


def _transport(to,subject,body,html=None):
    # run gates feature/pause, commits the attempt claim and logs each outcome.
    return mailer.send(to,subject,body,html=html)


def run(conn,*,send=None,limit=5):
    if type(limit) is not int or not 1<=limit<=20:raise ValueError('Use a batch of 1–20.')
    with transaction(conn):
        pilot.prune(conn)
        for row in rows(conn,"SELECT operation_key,recipient_id,attempt_id FROM mcp_work_arrangement_mail WHERE state='attempting' AND attempted_at<=? LIMIT 20",(int(time.time())-600,)):
            _finish(conn,row['operation_key'],row['recipient_id'],'uncertain',attempt=row['attempt_id'])
        for row in rows(conn,"SELECT operation_key,recipient_id FROM mcp_work_arrangement_mail WHERE state='queued' AND created_at<=? LIMIT 20",(int(time.time())-86400,)):
            _finish(conn,row['operation_key'],row['recipient_id'],'cancelled')
    if os.environ.get('CSS_MCP_ENABLED')!='1' or os.environ.get(pilot.FLAG)!='1':return 0
    send=send or _transport;attempted=0
    pending=rows(conn,"SELECT operation_key,recipient_id FROM mcp_work_arrangement_mail WHERE state='queued' ORDER BY rowid LIMIT ?",(limit,))
    for row in pending:
        key,rid=row['operation_key'],row['recipient_id']
        with transaction(conn):
            found=rows(conn,"SELECT * FROM mcp_work_arrangement_mail WHERE operation_key=? AND recipient_id=? AND state='queued'",(key,rid))
            if not found:continue
            op=rows(conn,'SELECT * FROM mcp_work_arrangement WHERE domain_key=?',(key,))
            try:
                if not op:raise ValueError
                op=op[0];owner=st.get_admin_user_by_id(conn,op['owner_id'])
                if not owner:raise ValueError
                pilot._check(conn,owner,op,op['resource'])
                result=json.loads(op['result_json']);payload=json.loads(found[0]['payload_json'])
                record=pilot.owned(conn,owner,result['id'])
                recipient=next((r for r in pilot.recipients(conn,owner['id']) if r['id']==rid),None)
                if (not recipient or record['status']!='pending' or pilot.record_digest(record)!=result['record_digest']
                        or payload['to']!=recipient['email'] or payload['recipient_name']!=recipient['name']
                        or payload['requester_name']!=(st._account_display_name(conn,owner['id']) or owner['username'])
                        or pilot._digest(payload)!=result['mail_digests'].get(str(rid))):raise ValueError
            except (ValueError,TypeError,KeyError,actions.ActionError):
                _finish(conn,key,rid,'cancelled');continue
            subject,body,html=mailer.awa_pending_message(payload['recipient_name'],payload['requester_name'],payload['period_label'],payload['arrangement_label'],payload['link'])
            if not st.email_feature_enabled(conn,'awa_approval'):
                _finish(conn,key,rid,'skipped_off',recipient=payload['to'],subject=subject);continue
            if not mailer.email_configured():
                _finish(conn,key,rid,'not_configured',recipient=payload['to'],subject=subject);continue
            attempt=str(uuid4())
            conn.execute("UPDATE mcp_work_arrangement_mail SET state='attempting',attempt_id=?,attempted_at=? WHERE operation_key=? AND recipient_id=? AND state='queued'",(attempt,int(time.time()),key,rid))
        attempted+=1;state='uncertain'
        try:
            answer=send(payload['to'],subject,body,html=html)
            if isinstance(answer,dict) and answer.get('sent') is True:state='sent'
        except Exception:pass
        with transaction(conn):_finish(conn,key,rid,state,attempt=attempt,recipient=payload['to'],subject=subject)
    return attempted
