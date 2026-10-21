"""Current scoped request decisions and atomic initial reservation."""
import supplies as s
import supplies_permissions as permissions
import supplies_requests as requests
import supplies_stock as stock
from supplies_allocations import allocate_outstanding
from supplies_storage import Conflict, Denied, Invalid, Missing, operation, record, rows, transaction
import tzutil as tz


def require_approver(conn, user, request):
    user = permissions.require_actor(conn,user)
    if not request['current_revision']:
        raise Missing('Supply request not found or unavailable to you.')
    unit_id = requests.submitted_unit(conn,request)
    if request['requester_id']==user['id'] or not permissions.has_role(conn,user,'request_approver',unit_id):
        raise Denied('A current request approver grant for this unit is required. You cannot decide your own request.')
    return user


def inbox(conn, user, *, page=1):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn,user)
        page = s.integer(page,'Page',1)
        scopes = rows(conn,"SELECT DISTINCT o.path FROM supply_role_grant g JOIN org_unit o ON o.id=g.unit_id WHERE g.user_id=? AND g.role='request_approver' AND g.revoked_at IS NULL",(user['id'],))
        if not scopes:
            raise Denied('A current supply request approver grant is required.')
        clauses, args = [], [user['id']]
        for scope in scopes:
            clauses.append('(o.path=? OR substr(o.path,1,length(?)+1)=? )')
            args.extend([scope['path'],scope['path'],scope['path']+'/'])
        found = rows(conn,'''SELECT q.id,q.control_number,q.requester_snapshot,q.unit_snapshot,q.purpose,q.submitted_at
          FROM supply_request q JOIN org_unit o ON o.id=q.unit_id
          WHERE q.approval_status='submitted' AND q.requester_id<>? AND ('''+ ' OR '.join(clauses)+''')
          ORDER BY q.submitted_at,q.id LIMIT 26 OFFSET ?''',(*args,(page-1)*25))
        return {'requests':found[:25],'page':page,'has_next':len(found)>25}


def decide_request(conn, user, request_id, fields, *, expected_revision, submitted_revision, operation_key):
    with transaction(conn):
        user = permissions.require_actor(conn,user)
        s.require_enabled(conn)
        found = rows(conn,'SELECT * FROM supply_request WHERE id=?',(s.integer(request_id,'Request',1),))
        if not found:
            raise Missing('Supply request not found or unavailable to you.')
        request = found[0]
        user = require_approver(conn,user,request)
        decision = fields.get('decision')
        if decision not in ('approved','returned','rejected'):
            raise Invalid('Choose approve, return or reject.')
        reason = stock._optional_text(fields.get('reason'),'Decision reason',2000)
        if decision != 'approved' and not reason:
            raise Invalid('Returning or rejecting a request requires a reason.')
        lines = []
        if decision=='approved':
            raw = fields.get('lines')
            if not isinstance(raw,list) or not 1 <= len(raw) <= requests.MAX_LINES:
                raise Invalid('Specify approved quantities for every submitted line.')
            for line in raw:
                if not isinstance(line,dict):
                    raise Invalid('Each approval line must identify a submitted line.')
                lines.append({'revision_line_id':s.integer(line.get('revision_line_id'),'Submitted line',1),
                              'approved_quantity':s.integer(line.get('approved_quantity'),'Approved quantity'),
                              'reason':stock._optional_text(line.get('reason'),'Reduction reason',2000)})
            lines.sort(key=lambda line:line['revision_line_id'])
        payload = {'id':request['id'],'revision':s.integer(expected_revision,'Request revision',1),
                   'submitted_revision':s.integer(submitted_revision,'Submitted revision',1),
                   'decision':decision,'reason':reason,'lines':lines}
        key,digest,prior = operation(conn,user,operation_key,'request_decide',payload)
        if prior is not None:
            return prior
        requests._check_revision(request,expected_revision)
        if request['approval_status']!='submitted' or request['current_revision']!=payload['submitted_revision']:
            raise Conflict('This submitted revision already changed or has been decided. Reload the request.')
        header = rows(conn,'SELECT * FROM supply_request_revision WHERE request_id=? AND revision=?',(request['id'],request['current_revision']))[0]
        original = rows(conn,'SELECT * FROM supply_request_revision_line WHERE revision_id=? ORDER BY id',(header['id'],))
        if decision=='approved':
            by_id = {line['revision_line_id']:line for line in lines}
            if len(by_id)!=len(lines) or set(by_id)!={line['id'] for line in original}:
                raise Invalid('Approve every submitted line exactly once; foreign or missing lines are not allowed.')
            for source in original:
                approved = by_id[source['id']]
                if approved['approved_quantity']>source['requested_quantity']:
                    raise Invalid('Approved quantity cannot exceed the requested quantity.')
                if approved['approved_quantity']<source['requested_quantity'] and not approved['reason']:
                    raise Invalid('Every reduced approved quantity requires a reason.')
                item = s._item(conn,source['item_id'])
                if not item['active'] or any(item[k]!=source[k+'_snapshot'] for k in ('code','description','unit')):
                    raise Conflict('A submitted catalog item changed or is inactive. Return the request for correction.')
        now = tz.now_iso()
        decision_id = conn.execute('''INSERT INTO supply_request_decision
          (request_id,revision_id,submitted_revision,decision,decided_by,actor_snapshot,decided_at,reason,operation_key)
          VALUES (?,?,?,?,?,?,?,?,?)''',(request['id'],header['id'],request['current_revision'],decision,user['id'],stock._actor_name(conn,user),now,reason,key)).lastrowid
        if decision=='approved':
            for source in original:
                approved = by_id[source['id']]
                conn.execute('INSERT INTO supply_request_decision_line(decision_id,revision_line_id,approved_quantity,reason) VALUES (?,?,?,?)',
                             (decision_id,source['id'],approved['approved_quantity'],approved['reason']))
                conn.execute('''INSERT INTO supply_reservation(request_id,line_id,revision_line_id,item_id,approved_at)
                  VALUES (?,?,?,?,?)''',(request['id'],source['line_id'],source['id'],source['item_id'],now))
        conn.execute('UPDATE supply_request SET approval_status=?,revision=revision+1,updated_at=? WHERE id=?',(decision,now,request['id']))
        result = {'id':request['id'],'decision_id':decision_id,'approval_status':decision,'revision':request['revision']+1,
                  'current_revision':request['current_revision']}
        record(conn,user,key,digest,'request_decide','request',result,payload)
        if decision=='approved':
            allocate_outstanding(conn,user,[line['item_id'] for line in original],key)
        return result
