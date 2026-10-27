"""Owner-scoped supply drafts, immutable submissions and preapproval withdrawal."""
import json

import supplies as s
import supplies_permissions as permissions
import supplies_stock as stock
import tzutil as tz
from supplies_storage import Conflict, Denied, Invalid, Missing, operation, record, rows, transaction


MAX_LINES = 20


def requester(conn, user):
    user = permissions.require_actor(conn, user)
    found = rows(conn, '''SELECT rp.id AS requester_rp_id,rp.name AS requester_snapshot,
      ou.id AS unit_id,ou.name AS unit_snapshot FROM resource_person rp
      JOIN org_unit ou ON ou.id=rp.org_unit_id
      WHERE rp.id=? AND rp.is_internal=1 AND rp.archived_at IS NULL''', (user.get('rp_id'),))
    if not found:
        raise Denied('Supply requests require an account linked to current internal staff with an organizational unit. Ask an administrator to update your directory linkage.')
    return user, found[0]


def _owned(conn, user, request_id):
    found = rows(conn, 'SELECT * FROM supply_request WHERE id=? AND requester_id=?',
                 (s.integer(request_id, 'Request', 1), user['id']))
    if not found:
        raise Missing('Supply request not found or unavailable to you.')
    return found[0]


def _fields(fields):
    purpose = s.text(fields.get('purpose'), 'Purpose', 2000)
    needed = stock._date(fields.get('date_needed'), 'Date needed', optional=True)
    raw = fields.get('lines')
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LINES:
        raise Invalid('A request needs 1–20 item lines.')
    combined = {}
    for line in raw:
        if not isinstance(line, dict):
            raise Invalid('Each request line needs an item and quantity.')
        item = s.integer(line.get('item_id'), 'Request item', 1)
        quantity = s.integer(line.get('requested_quantity'), 'Requested quantity', 1)
        combined[item] = s.integer(combined.get(item, 0) + quantity, 'Combined requested quantity', 1)
    return {'purpose': purpose, 'date_needed': needed,
            'lines': [{'item_id': k, 'requested_quantity': v} for k,v in sorted(combined.items())]}


def _active_items(conn, lines):
    for line in lines:
        if not s._item(conn, line['item_id'])['active']:
            raise Conflict('A requested item is inactive. Choose an active catalog item before saving or submitting.')


def _check_revision(request, revision):
    if request['revision'] != s.integer(revision, 'Request revision', 1):
        raise Conflict('This request changed. Reload and review the latest version.')


def _write_lines(conn, request_id, lines):
    # Keep identifiers for retained draft lines; submission snapshots never change.
    ids = [line['item_id'] for line in lines]
    placeholders = ','.join('?' for _ in ids)
    conn.execute('UPDATE supply_request_draft_line SET active=0 WHERE request_id=? AND item_id NOT IN (' + placeholders + ')', (request_id,*ids))
    for line in lines:
        item = s._item(conn,line['item_id'])
        conn.execute('''INSERT INTO supply_request_draft_line
          (request_id,item_id,requested_quantity,code_snapshot,description_snapshot,unit_snapshot) VALUES (?,?,?,?,?,?)
          ON CONFLICT(request_id,item_id) DO UPDATE SET active=1,requested_quantity=excluded.requested_quantity,
          code_snapshot=excluded.code_snapshot,description_snapshot=excluded.description_snapshot,unit_snapshot=excluded.unit_snapshot''',
          (request_id,line['item_id'],line['requested_quantity'],item['code'],item['description'],item['unit']))


def save_draft(conn, user, fields, *, operation_key, request_id=None, expected_revision=None):
    with transaction(conn):
        return save_draft_in_transaction(conn, user, fields, operation_key=operation_key,
                                         request_id=request_id, expected_revision=expected_revision)


def save_draft_in_transaction(conn, user, fields, *, operation_key, request_id=None, expected_revision=None):
    """Shared UI/MCP service; caller commits the draft and its outer receipt."""
    if not conn.in_transaction:
        raise RuntimeError('An active transaction is required.')
    user = permissions.require_actor(conn, user)
    s.require_enabled(conn)
    values = _fields(fields)
    payload = {'request_id': request_id, 'revision': expected_revision, **values}
    key,digest,prior = operation(conn,user,operation_key,'request_save',payload)
    if prior is not None:
        return prior
    user, identity = requester(conn,user)
    _active_items(conn,values['lines'])
    now = tz.now_iso()
    if request_id is None:
        request_id = conn.execute('''INSERT INTO supply_request
          (requester_id,requester_rp_id,requester_snapshot,unit_id,unit_snapshot,purpose,date_needed,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?)''', (user['id'], *[identity[k] for k in ('requester_rp_id','requester_snapshot','unit_id','unit_snapshot')],
                   values['purpose'],values['date_needed'],now,now)).lastrowid
    else:
        request = _owned(conn,user,request_id)
        _check_revision(request,expected_revision)
        if request['approval_status'] not in ('draft','returned'):
            raise Conflict('Only a draft or returned request can be edited.')
        conn.execute('''UPDATE supply_request SET purpose=?,date_needed=?,requester_rp_id=?,requester_snapshot=?,
          unit_id=?,unit_snapshot=?,revision=revision+1,updated_at=? WHERE id=?''',
          (values['purpose'],values['date_needed'],*[identity[k] for k in ('requester_rp_id','requester_snapshot','unit_id','unit_snapshot')],now,request_id))
    _write_lines(conn,request_id,values['lines'])
    result = {'id': request_id, 'revision': _owned(conn,user,request_id)['revision']}
    return record(conn,user,key,digest,'request_save','request',result,values)


def eligible_approvers(conn, owner_id, unit_id):
    users = rows(conn, '''SELECT DISTINCT u.* FROM admin_user u JOIN supply_role_grant g ON g.user_id=u.id
      WHERE u.active=1 AND u.id<>? AND g.role='request_approver' AND g.revoked_at IS NULL''', (owner_id,))
    return [u for u in users if permissions.has_role(conn,u,'request_approver',unit_id)]


def _number(conn):
    year = tz.today_local().year
    conn.execute("INSERT INTO supply_sequence(kind,year,last_value) VALUES ('SUP',?,0) ON CONFLICT(kind,year) DO NOTHING", (year,))
    last = conn.execute("SELECT last_value FROM supply_sequence WHERE kind='SUP' AND year=?", (year,)).fetchone()[0]
    if last >= 99999:
        raise Conflict('The annual supply request number limit has been reached. No request was submitted.')
    conn.execute("UPDATE supply_sequence SET last_value=last_value+1 WHERE kind='SUP' AND year=?", (year,))
    return f'SUP-{year}-{last+1:05d}'


def submit(conn, user, request_id, *, expected_revision, operation_key):
    with transaction(conn):
        return submit_in_transaction(conn, user, request_id, expected_revision=expected_revision,
                                     operation_key=operation_key)


def submit_in_transaction(conn, user, request_id, *, expected_revision, operation_key):
    """Submit through the normal domain contract in the caller's writer transaction."""
    if not conn.in_transaction:
        raise RuntimeError('A caller-owned supply submission transaction is required.')
    user = permissions.require_actor(conn,user)
    s.require_enabled(conn)
    request = _owned(conn,user,request_id)
    revision = s.integer(expected_revision,'Request revision',1)
    key,digest,prior = operation(conn,user,operation_key,'request_submit',{'id':request['id'],'revision':revision})
    if prior is not None:
        return prior
    _check_revision(request,revision)
    if request['approval_status'] not in ('draft','returned'):
        raise Conflict('Only a draft or returned request can be submitted. Reload the request to check its status.')
    user,identity = requester(conn,user)
    lines = rows(conn,'SELECT * FROM supply_request_draft_line WHERE request_id=? AND active=1 ORDER BY id',(request['id'],))
    _fields({**request,'lines':lines})
    _active_items(conn,lines)
    for line in lines:
        item = s._item(conn,line['item_id'])
        if any(line[k+'_snapshot'] != item[k] for k in ('code','description','unit')):
            raise Conflict('A catalog description or unit changed. Edit and save the draft to confirm the current item before submitting.')
    now = tz.now_iso()
    current_revision = request['current_revision'] + 1
    control = request['control_number'] or _number(conn)
    revision_id = conn.execute('''INSERT INTO supply_request_revision
      (request_id,revision,purpose,date_needed,requester_rp_id,requester_snapshot,unit_id,unit_snapshot,submitted_at,submitted_by,operation_key)
      VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (request['id'],current_revision,request['purpose'],request['date_needed'],
      *[identity[k] for k in ('requester_rp_id','requester_snapshot','unit_id','unit_snapshot')],now,user['id'],key)).lastrowid
    for line in lines:
        item = s._item(conn,line['item_id'])
        conn.execute('''INSERT INTO supply_request_revision_line
          (revision_id,line_id,item_id,code_snapshot,description_snapshot,unit_snapshot,item_revision,requested_quantity)
          VALUES (?,?,?,?,?,?,?,?)''', (revision_id,line['id'],item['id'],item['code'],item['description'],item['unit'],item['revision'],line['requested_quantity']))
    conn.execute('''UPDATE supply_request SET control_number=?,approval_status='submitted',current_revision=?,
      revision=revision+1,requester_rp_id=?,requester_snapshot=?,unit_id=?,unit_snapshot=?,submitted_at=?,updated_at=? WHERE id=?''',
      (control,current_revision,*[identity[k] for k in ('requester_rp_id','requester_snapshot','unit_id','unit_snapshot')],now,now,request['id']))
    approvers = eligible_approvers(conn,user['id'],identity['unit_id'])
    result = {'id':request['id'],'control_number':control,'revision':revision+1,'current_revision':current_revision,'approval_status':'submitted'}
    return record(conn,user,key,digest,'request_submit','request',result,
                  {**result, **identity,'eligible_approver_count':len(approvers)})


def withdraw(conn, user, request_id, *, reason, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_actor(conn,user)
        s.require_enabled(conn)
        request = _owned(conn,user,request_id)
        payload = {'id':request['id'],'revision':s.integer(expected_revision,'Request revision',1),
                   'reason':s.text(reason,'Withdrawal reason',2000)}
        key,digest,prior = operation(conn,user,operation_key,'request_withdraw',payload)
        if prior is not None:
            return prior
        _check_revision(request,expected_revision)
        if request['approval_status'] not in ('draft','submitted','returned'):
            raise Conflict('This request can no longer be withdrawn before approval.')
        conn.execute("UPDATE supply_request SET approval_status='cancelled',revision=revision+1,updated_at=? WHERE id=?",(tz.now_iso(),request['id']))
        return record(conn,user,key,digest,'request_withdraw','request',
                      {'id':request['id'],'revision':request['revision']+1,'approval_status':'cancelled'},payload)


def submitted_unit(conn, request):
    if request['current_revision']:
        return conn.execute('SELECT unit_id FROM supply_request_revision WHERE request_id=? AND revision=?',
                            (request['id'],request['current_revision'])).fetchone()[0]
    return request['unit_id']


def _visible(conn, user, request_id):
    clause,args = permissions.request_read_clause(conn,user)
    found = rows(conn,'SELECT q.* FROM supply_request q WHERE q.id=? AND '+clause,
                 (s.integer(request_id,'Request',1),*args))
    if not found:
        raise Missing('Supply request not found or unavailable to you.')
    return found[0]


def get_request(conn, user, request_id):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn,user)
        request = _visible(conn,user,request_id)
        owner = request['requester_id']==user['id']
        request['is_owner'] = owner
        request['can_decide'] = (not owner and request['approval_status']=='submitted' and
            permissions.has_role(conn,user,'request_approver',submitted_unit(conn,request)))
        if request['current_revision'] and (not owner or request['approval_status'] not in ('draft','returned')):
            header = rows(conn,'SELECT * FROM supply_request_revision WHERE request_id=? AND revision=?',(request['id'],request['current_revision']))[0]
            for field in ('purpose','date_needed','unit_id','unit_snapshot','requester_snapshot','requester_rp_id'):
                request[field] = header[field]
            request['lines'] = rows(conn,"""SELECT l.*,d.approved_quantity,d.reason AS reduction_reason,
              r.reserved_quantity,r.effective_issued_quantity,r.cancelled_quantity,r.version AS reservation_version,
              d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity AS outstanding_quantity,
              d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity-r.reserved_quantity AS awaiting_stock_quantity
              FROM supply_request_revision_line l LEFT JOIN supply_request_decision_line d ON d.revision_line_id=l.id
              LEFT JOIN supply_reservation r ON r.revision_line_id=l.id WHERE l.revision_id=? ORDER BY l.line_id""",(header['id'],))
        else:
            request['lines'] = rows(conn,"""SELECT l.*,i.active FROM supply_request_draft_line l
              JOIN supply_item i ON i.id=l.item_id WHERE request_id=? AND l.active=1 ORDER BY l.id""",(request['id'],))
        request['events'] = rows(conn,"SELECT action,created_at,detail_json FROM supply_event WHERE entity_type='request' AND entity_id=? ORDER BY id",(request['id'],))
        if not owner:
            request['events'] = [event for event in request['events'] if event['action']!='request_save']
        for event in request['events']:
            detail = json.loads(event['detail_json'])
            event['reason'] = detail.get('reason','') if event['action'] in ('request_withdraw','request_decide','request_cancel_remainder','correction_return','correction_issue_reversal','stocktake_reservation_release') else ''
            event['decision'] = detail.get('decision','')
            event['correction_id'] = detail.get('correction_id')
        request['history'] = rows(conn,"""SELECT v.*,d.decision,d.actor_snapshot,d.decided_at,d.reason AS decision_reason
          FROM supply_request_revision v LEFT JOIN supply_request_decision d ON d.revision_id=v.id
          WHERE v.request_id=? ORDER BY v.revision""",(request['id'],))
        for version in request['history']:
            version['lines'] = rows(conn,"""SELECT l.*,d.approved_quantity,d.reason AS reduction_reason
              FROM supply_request_revision_line l LEFT JOIN supply_request_decision_line d ON d.revision_line_id=l.id
              WHERE l.revision_id=? ORDER BY l.line_id""",(version['id'],))
        request['routing_warning'] = request['approval_status']=='submitted' and not eligible_approvers(conn,request['requester_id'],request['unit_id'])
        if request['approval_status']=='approved':
            from supplies_allocations import fulfillment
            request['fulfillment'] = fulfillment(request['lines'])
            request['can_cancel_remainder'] = owner or permissions.has_role(conn,user,'custodian')
            request['cancellations'] = rows(conn,"""SELECT c.*,r.line_id,l.code_snapshot,l.unit_snapshot,
              cl.cancelled_quantity FROM supply_request_cancellation c
              JOIN supply_request_cancellation_line cl ON cl.cancellation_id=c.id
              JOIN supply_reservation r ON r.id=cl.reservation_id
              JOIN supply_request_revision_line l ON l.id=r.revision_line_id
              WHERE c.request_id=? ORDER BY c.id,cl.id""",(request['id'],))

        request['releases'] = rows(conn,'''SELECT i.id,i.release_number,i.effective_date,i.recipient_snapshot,
          COALESCE((SELECT a.status FROM supply_issue_acknowledgment a WHERE a.issue_id=i.id ORDER BY a.revision DESC LIMIT 1),'pending') AS acknowledgment_status
          FROM supply_issue i WHERE request_id=? ORDER BY i.id''',(request['id'],))
        return request


def my_requests(conn, user, *, page=1, query='', state='', mine=False):
    from supplies_dashboard import queue
    return queue(conn,user,'requests',page=page,query=query,state=state,mine=mine)
