"""Visible approved shortages, immutable remainder cancellations and allocation recovery."""
import supplies as s
import supplies_permissions as permissions
import supplies_requests as requests
import supplies_stock as stock
from supplies_allocations import allocate_outstanding
from supplies_storage import Conflict, Denied, Invalid, operation, record, rows, transaction
import tzutil as tz


def cancel_remainder(conn, user, request_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_actor(conn,user)
        s.require_enabled(conn)
        request = requests._visible(conn,user,request_id)
        if request['requester_id']!=user['id'] and not permissions.has_role(conn,user,'custodian'):
            raise Denied('Only the requester or a current supply custodian can cancel remaining demand.')
        raw = fields.get('lines')
        if not isinstance(raw,list) or not 1 <= len(raw) <= requests.MAX_LINES:
            raise Invalid('Select 1–20 lines whose full remaining quantity should be cancelled.')
        lines = []
        for line in raw:
            if not isinstance(line,dict) or set(line)!={'line_id','version'}:
                raise Invalid('Select a line and its current version; only full remainder cancellation is supported.')
            lines.append({'line_id':s.integer(line['line_id'],'Request line',1),
                          'version':s.integer(line['version'],'Reservation version',1)})
        lines.sort(key=lambda line:line['line_id'])
        if len({line['line_id'] for line in lines})!=len(lines):
            raise Invalid('Select each request line only once.')
        payload = {'id':request['id'],'revision':s.integer(expected_revision,'Request revision',1),
                   'reason':s.text(fields.get('reason'),'Cancellation reason',2000),'lines':lines}
        key,digest,prior = operation(conn,user,operation_key,'request_cancel_remainder',payload)
        if prior is not None:
            return prior
        requests._check_revision(request,expected_revision)
        if request['approval_status']!='approved':
            raise Conflict('Only an approved request can have its remaining demand cancelled.')
        selected = []
        for line in lines:
            found = rows(conn,'''SELECT r.*,d.approved_quantity FROM supply_reservation r
              JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
              JOIN supply_request_revision_line l ON l.id=r.revision_line_id
              JOIN supply_request_revision v ON v.id=l.revision_id
              WHERE r.request_id=? AND r.line_id=? AND v.revision=?''', (request['id'],line['line_id'],request['current_revision']))
            if not found:
                raise Invalid('A selected line does not belong to this approved request.')
            reservation = found[0]
            if reservation['version']!=line['version']:
                raise Conflict('Reservations changed. Reload and review the current remaining quantities.')
            remaining = reservation['approved_quantity']-reservation['effective_issued_quantity']-reservation['cancelled_quantity']
            if remaining<=0:
                raise Conflict('A selected line has no remaining demand to cancel.')
            if reservation['reserved_quantity']>remaining:
                raise Conflict('The selected reservation needs reconciliation before cancellation.')
            selected.append((reservation,remaining))
        now = tz.now_iso()
        cancellation_id = conn.execute('''INSERT INTO supply_request_cancellation
          (request_id,submitted_revision,reason,cancelled_by,actor_snapshot,cancelled_at,operation_key)
          VALUES (?,?,?,?,?,?,?)''',(request['id'],request['current_revision'],payload['reason'],user['id'],stock._actor_name(conn,user),now,key)).lastrowid
        detail_lines=[]
        for reservation,remaining in selected:
            conn.execute('''INSERT INTO supply_request_cancellation_line
              (cancellation_id,reservation_id,cancelled_quantity,issued_quantity_snapshot,previous_reserved_quantity)
              VALUES (?,?,?,?,?)''',(cancellation_id,reservation['id'],remaining,reservation['effective_issued_quantity'],reservation['reserved_quantity']))
            conn.execute('UPDATE supply_reservation SET cancelled_quantity=cancelled_quantity+?,version=version+1 WHERE id=?',(remaining,reservation['id']))
            detail_lines.append({'line_id':reservation['line_id'],'item_id':reservation['item_id'],'cancelled_quantity':remaining})
        conn.execute('UPDATE supply_request SET revision=revision+1,updated_at=? WHERE id=?',(now,request['id']))
        result={'id':request['id'],'cancellation_id':cancellation_id,'revision':request['revision']+1,'approval_status':'approved'}
        record(conn,user,key,digest,'request_cancel_remainder','request',result,
               {**payload,'cancelled_lines':detail_lines,'cancellation_id':cancellation_id})
        allocate_outstanding(conn,user,[r['item_id'] for r,_ in selected],key)
        return result


def awaiting_stock(conn, user, *, page=1):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn,user)
        page = s.integer(page,'Page',1)
        global_read = permissions.has_role(conn,user,'custodian') or permissions.has_role(conn,user,'auditor')
        found = rows(conn,'''SELECT q.id AS request_id,q.control_number,q.requester_snapshot,q.unit_snapshot AS request_unit_snapshot,
          l.code_snapshot,l.description_snapshot,l.unit_snapshot,l.requested_quantity,d.approved_quantity,
          r.reserved_quantity,r.effective_issued_quantity,r.cancelled_quantity,r.approved_at,
          d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity-r.reserved_quantity AS awaiting_stock_quantity
          FROM supply_reservation r JOIN supply_request q ON q.id=r.request_id
          JOIN supply_request_revision_line l ON l.id=r.revision_line_id
          JOIN supply_request_decision_line d ON d.revision_line_id=l.id
          JOIN org_unit o ON o.id=q.unit_id
          WHERE q.approval_status='approved'
            AND d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity>r.reserved_quantity
            AND (? OR q.requester_id=? OR EXISTS (
              SELECT 1 FROM supply_role_grant g JOIN org_unit scope ON scope.id=g.unit_id
              WHERE g.user_id=? AND g.role='request_approver' AND g.revoked_at IS NULL
                AND (o.path=scope.path OR substr(o.path,1,length(scope.path)+1)=scope.path||'/')))
          ORDER BY r.approved_at,r.request_id,r.line_id LIMIT 26 OFFSET ?''',
          (int(global_read),user['id'],user['id'],(page-1)*25))
        return {'shortages':found[:25],'page':page,'has_next':len(found)>25}


def refresh_reservations(conn, user, *, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn,user)
        s.require_enabled(conn)
        key,digest,prior=operation(conn,user,operation_key,'allocation_refresh',{})
        if prior is not None:
            return prior
        item_ids=[r[0] for r in conn.execute('SELECT DISTINCT item_id FROM supply_reservation')]
        result={'id':0,'item_count':len(item_ids)}
        record(conn,user,key,digest,'allocation_refresh','allocation',result,result)
        allocate_outstanding(conn,user,item_ids,key)
        return result
