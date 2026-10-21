"""Append-only recipient acknowledgment/dispute and attributed paper evidence."""
import supplies as s
import supplies_issues as issues
import supplies_permissions as permissions
import supplies_stock as stock
from supplies_storage import Conflict, Denied, Invalid, operation, record, rows, transaction
import tzutil as tz


def _state(conn,issue_id):
    history=rows(conn,'SELECT * FROM supply_issue_acknowledgment WHERE issue_id=? ORDER BY revision',(issue_id,))
    return {'revision':history[-1]['revision'] if history else 0,
            'status':history[-1]['status'] if history else 'pending',
            'method':history[-1]['method'] if history else None,'history':history}


def _post(conn,user,issue_id,fields,*,expected_revision,operation_key,paper):
    with transaction(conn):
        user=permissions.require_actor(conn,user)
        s.require_enabled(conn)
        if paper:
            user=permissions.require_custodian(conn,user)
        issue=issues.get_issue(conn,user,issue_id)
        if not paper and issue['recipient_id']!=user['id']:
            raise Denied('Only the recorded recipient can acknowledge or dispute this release.')
        status='acknowledged' if paper else fields.get('status')
        if status not in ('acknowledged','disputed'):
            raise Invalid('Choose acknowledge receipt or report a dispute.')
        note=stock._optional_text(fields.get('note'),'Acknowledgment note or dispute reason',2000)
        if status=='disputed' and not note:
            raise Invalid('A dispute requires a reason.')
        reference=s.text(fields.get('paper_reference'),'Paper receipt reference',120) if paper else None
        received=stock._effective_date(fields.get('paper_received_date')) if paper else None
        if paper and (not note or received<issue['effective_date']):
            raise Invalid('Paper acknowledgment needs an evidence note and a date on or after handover.')
        payload={'id':issue['id'],'revision':s.integer(expected_revision,'Acknowledgment revision'),
                 'status':status,'method':'paper_recorded' if paper else 'recipient','note':note,
                 'paper_reference':reference,'paper_received_date':received}
        action='issue_paper_acknowledgment' if paper else 'issue_acknowledgment'
        key,digest,prior=operation(conn,user,operation_key,action,payload)
        if prior is not None:
            return prior
        current=issue['acknowledgment']
        if current['revision']!=payload['revision']:
            raise Conflict('Acknowledgment changed. Reload and review the latest evidence.')
        if current['status']==status:
            raise Conflict('This release already has this acknowledgment status. Review its history.')
        if current['status']=='disputed' and status=='acknowledged' and not note:
            raise Invalid('Resolving a dispute requires an explanation or supporting evidence.')
        revision=current['revision']+1
        conn.execute('''INSERT INTO supply_issue_acknowledgment
          (issue_id,revision,status,method,actor_id,actor_snapshot,created_at,note,paper_reference,paper_received_date,operation_key)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(issue['id'],revision,status,payload['method'],user['id'],
          stock._actor_name(conn,user),tz.now_iso(),note,reference,received,key))
        result={'id':issue['id'],'revision':revision,'status':status,'method':payload['method']}
        return record(conn,user,key,digest,action,'issue',result,{**payload,'previous_status':current['status']})


def acknowledge_issue(conn,user,issue_id,fields,*,expected_revision,operation_key):
    return _post(conn,user,issue_id,fields,expected_revision=expected_revision,operation_key=operation_key,paper=False)


def record_paper_acknowledgment(conn,user,issue_id,fields,*,expected_revision,operation_key):
    return _post(conn,user,issue_id,fields,expected_revision=expected_revision,operation_key=operation_key,paper=True)
