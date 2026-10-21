"""Immutable, numbered stock handovers against current reserved approved demand."""
import json

import storage as st
import supplies as s
import supplies_permissions as permissions
import supplies_requests as requests
import supplies_stock as stock
from supplies_allocations import allocate_outstanding, availability
from supplies_storage import Conflict, Denied, Invalid, Missing, operation, record, rows, transaction
import tzutil as tz


def recipient(conn, recipient_id):
    user=st.get_admin_user_by_id(conn,s.integer(recipient_id,'Recipient',1))
    if not user or not user['active']:
        raise Invalid('Choose an active internal staff recipient with a directory unit.')
    try:
        _,identity=requests.requester(conn,user)
    except Denied as exc:
        raise Invalid('Choose an active internal staff recipient with a directory unit.') from exc
    return user,identity


def prepare_issue(conn,user,request_id):
    with stock._snapshot(conn):
        permissions.require_custodian(conn,user)
        request=requests.get_request(conn,user,request_id)
        if request['approval_status']!='approved':
            raise Conflict('Only an approved request can be issued.')
        recipients=rows(conn,'''SELECT u.id,rp.name,o.name AS unit_name FROM admin_user u
          JOIN resource_person rp ON rp.id=u.rp_id JOIN org_unit o ON o.id=rp.org_unit_id
          WHERE u.active=1 AND rp.is_internal=1 AND rp.archived_at IS NULL ORDER BY rp.name,u.id''')
        return {'supply_request':request,'recipients':recipients,'today':tz.today_local().isoformat()}


def issuance_queue(conn,user,*,page=1):
    with stock._snapshot(conn):
        permissions.require_custodian(conn,user)
        page=s.integer(page,'Page',1)
        found=rows(conn,'''SELECT q.id,q.control_number,q.requester_snapshot,q.unit_snapshot FROM supply_request q
          WHERE q.approval_status='approved' AND EXISTS (
            SELECT 1 FROM supply_reservation r WHERE r.request_id=q.id AND r.reserved_quantity>0)
          ORDER BY (SELECT MIN(r.approved_at) FROM supply_reservation r WHERE r.request_id=q.id),q.id
          LIMIT 26 OFFSET ?''',((page-1)*25,))
        return {'requests':found[:25],'page':page,'has_next':len(found)>25}


def _number(conn):
    year=tz.today_local().year
    conn.execute("INSERT INTO supply_sequence VALUES ('ISS',?,0) ON CONFLICT(kind,year) DO NOTHING",(year,))
    last=conn.execute("SELECT last_value FROM supply_sequence WHERE kind='ISS' AND year=?",(year,)).fetchone()[0]
    if last>=99999:
        raise Conflict('The annual release number limit has been reached. No stock was issued.')
    conn.execute("UPDATE supply_sequence SET last_value=last_value+1 WHERE kind='ISS' AND year=?",(year,))
    return f'ISS-{year}-{last+1:05d}'


def post_issue(conn,user,request_id,fields,*,expected_revision,operation_key):
    with transaction(conn):
        user=permissions.require_custodian(conn,user)
        s.require_enabled(conn)
        request=requests._visible(conn,user,request_id)
        recipient_id=s.integer(fields.get('recipient_id',request['requester_id']),'Recipient',1)
        if fields.get('confirmed')!='yes':
            raise Invalid('Confirm the quantities were handed to the selected recipient.')
        raw=fields.get('lines')
        if not isinstance(raw,list) or not 1<=len(raw)<=requests.MAX_LINES:
            raise Invalid('Enter issued quantities for 1–20 reserved lines.')
        lines=[]
        for line in raw:
            if not isinstance(line,dict):
                raise Invalid('Each issue line needs its quantity and reservation version.')
            lines.append({'line_id':s.integer(line.get('line_id'),'Request line',1),
                          'version':s.integer(line.get('version'),'Reservation version',1),
                          'issued_quantity':s.integer(line.get('issued_quantity'),'Issued quantity',1)})
        lines.sort(key=lambda line:line['line_id'])
        if len({line['line_id'] for line in lines})!=len(lines):
            raise Invalid('Select each request line only once.')
        payload={'request_id':request['id'],'revision':s.integer(expected_revision,'Request revision',1),
                 'recipient_id':recipient_id,'effective_date':stock._effective_date(fields.get('effective_date')),
                 'alternate_reason':stock._optional_text(fields.get('alternate_reason'),'Alternate recipient reason',2000),
                 'note':stock._optional_text(fields.get('note'),'Handover note',2000),'lines':lines}
        key,digest,prior=operation(conn,user,operation_key,'issue_post',payload)
        if prior is not None:
            return prior
        requests._check_revision(request,expected_revision)
        if request['approval_status']!='approved':
            raise Conflict('Only an approved request can be issued.')
        _,identity=recipient(conn,recipient_id)
        if recipient_id!=request['requester_id'] and not payload['alternate_reason']:
            raise Invalid('Record why an alternate recipient is receiving these supplies.')
        selected=[]
        for line in lines:
            found=rows(conn,'''SELECT r.*,d.approved_quantity,l.code_snapshot,l.description_snapshot,l.unit_snapshot
              FROM supply_reservation r JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
              JOIN supply_request_revision_line l ON l.id=r.revision_line_id
              JOIN supply_request_revision v ON v.id=l.revision_id
              WHERE r.request_id=? AND r.line_id=? AND v.revision=?''',(request['id'],line['line_id'],request['current_revision']))
            if not found:
                raise Invalid('An issue line does not belong to this approved request.')
            reservation=found[0]
            if reservation['version']!=line['version']:
                raise Conflict('Reservations changed. Reload the handover form before issuing stock.')
            remaining=reservation['approved_quantity']-reservation['effective_issued_quantity']-reservation['cancelled_quantity']
            if line['issued_quantity']>min(reservation['reserved_quantity'],remaining):
                raise Conflict('Issued quantity exceeds the currently reserved or outstanding quantity.')
            item=s._item(conn,reservation['item_id'])
            if not item['active'] or item['unit']!=reservation['unit_snapshot']:
                raise Conflict('The issue item is inactive or its canonical unit changed.')
            availability(conn,item['id'])
            selected.append((line,reservation,item))
        number=_number(conn)
        now=tz.now_iso()
        issue_id=conn.execute('''INSERT INTO supply_issue
          (release_number,request_id,submitted_revision,recipient_id,recipient_rp_id,recipient_snapshot,recipient_unit_snapshot,
           alternate_reason,issued_by,issuer_snapshot,effective_date,posted_at,note,operation_key)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(number,request['id'],request['current_revision'],recipient_id,
          identity['requester_rp_id'],identity['requester_snapshot'],identity['unit_snapshot'],payload['alternate_reason'],
          user['id'],stock._actor_name(conn,user),payload['effective_date'],now,payload['note'],key)).lastrowid
        for line,reservation,item in selected:
            line_id=conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM supply_issue_line').fetchone()[0]
            snapshot={**item,**{k:reservation[k+'_snapshot'] for k in ('code','description','unit')}}
            movement_id=stock._add_movement(conn,user,snapshot,kind='issue',quantity=-line['issued_quantity'],
                effective_date=payload['effective_date'],key=key,source_id=issue_id,source_line_id=line_id,reason=payload['note'])
            conn.execute('''INSERT INTO supply_issue_line
              (id,issue_id,line_id,revision_line_id,reservation_id,item_id,issued_quantity,code_snapshot,description_snapshot,unit_snapshot,movement_id)
              VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(line_id,issue_id,line['line_id'],reservation['revision_line_id'],reservation['id'],
              item['id'],line['issued_quantity'],snapshot['code'],snapshot['description'],snapshot['unit'],movement_id))
            conn.execute('''UPDATE supply_reservation SET effective_issued_quantity=effective_issued_quantity+?,
              reserved_quantity=reserved_quantity-?,version=version+1 WHERE id=?''',(line['issued_quantity'],line['issued_quantity'],reservation['id']))
        conn.execute('UPDATE supply_request SET revision=revision+1,updated_at=? WHERE id=?',(now,request['id']))
        result={'id':issue_id,'request_id':request['id'],'release_number':number,'revision':request['revision']+1}
        record(conn,user,key,digest,'issue_post','issue',result,payload)
        conn.execute('''INSERT INTO supply_event(entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
          VALUES ('request',?,'issue_post',?,?,?,?)''',(request['id'],user['id'],
          json.dumps({'issue_id':issue_id,'release_number':number}),now,key))
        allocate_outstanding(conn,user,[item['id'] for _,_,item in selected],key)
        return result


def get_issue(conn,user,issue_id):
    with stock._snapshot(conn):
        user=permissions.require_actor(conn,user)
        found=rows(conn,'SELECT * FROM supply_issue WHERE id=?',(s.integer(issue_id,'Release',1),))
        if not found:
            raise Missing('Supply release not found or unavailable to you.')
        issue=found[0]
        if issue['recipient_id']!=user['id']:
            requests._visible(conn,user,issue['request_id'])
        header=rows(conn,'''SELECT q.control_number,v.requester_snapshot,v.unit_snapshot,v.purpose
          FROM supply_request q JOIN supply_request_revision v ON v.request_id=q.id
          WHERE q.id=? AND v.revision=?''',(issue['request_id'],issue['submitted_revision']))[0]
        issue['request']=header
        issue['lines']=rows(conn,'SELECT * FROM supply_issue_line WHERE issue_id=? ORDER BY id',(issue['id'],))
        from supplies_acknowledgments import _state
        issue['acknowledgment']=_state(conn,issue['id'])
        issue['can_acknowledge']=issue['recipient_id']==user['id']
        issue['can_record_paper']=permissions.has_role(conn,user,'custodian')
        return issue


def list_issues(conn,user,*,page=1):
    with stock._snapshot(conn):
        user=permissions.require_actor(conn,user)
        page=s.integer(page,'Page',1)
        global_read=permissions.has_role(conn,user,'custodian') or permissions.has_role(conn,user,'auditor')
        found=rows(conn,"""SELECT i.id,i.release_number,i.effective_date,i.recipient_snapshot,q.control_number,
          COALESCE((SELECT a.status FROM supply_issue_acknowledgment a WHERE a.issue_id=i.id ORDER BY a.revision DESC LIMIT 1),'pending') AS acknowledgment_status
          FROM supply_issue i JOIN supply_request q ON q.id=i.request_id JOIN org_unit o ON o.id=q.unit_id
          WHERE (? OR i.recipient_id=? OR q.requester_id=? OR EXISTS (
            SELECT 1 FROM supply_role_grant g JOIN org_unit scope ON scope.id=g.unit_id
            WHERE g.user_id=? AND g.role='request_approver' AND g.revoked_at IS NULL
              AND (o.path=scope.path OR substr(o.path,1,length(scope.path)+1)=scope.path||'/')))
          ORDER BY i.id DESC LIMIT 26 OFFSET ?""",(int(global_read),user['id'],user['id'],user['id'],(page-1)*25))
        return {'releases':found[:25],'page':page,'has_next':len(found)>25}
