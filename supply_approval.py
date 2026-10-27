"""Bounded full-quantity approval with exact, non-displacing allocation effects."""
import hashlib
import json

import storage as st
import supplies as supplies
import supplies_allocations as allocations
import supplies_approvals as approvals
import supplies_requests as requests
import supplies_stock as stock
from supplies_storage import Conflict,Denied,rows
import tzutil as tz


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def source(conn,user,request_id,*,for_write=True):
    found=rows(conn,'SELECT * FROM supply_request WHERE id=?',(request_id,))
    if not found:raise Denied('Supply request not found or unavailable to you.')
    request=found[0];user=approvals.require_approver(conn,user,request)
    header=rows(conn,'SELECT * FROM supply_request_revision WHERE request_id=? AND revision=?',(request_id,request['current_revision']))
    if not header:raise Denied('Submitted supply source unavailable.')
    header=header[0]
    if not for_write:return user,request,header,None
    supplies.require_enabled(conn)
    if request['approval_status']!='submitted':raise Conflict('Review a currently submitted request.')
    if conn.execute('SELECT 1 FROM supply_reservation WHERE request_id=? LIMIT 1',(request_id,)).fetchone():
        raise Conflict('Use ordinary Supplies for requests with an earlier reservation cycle.')
    requester=st.get_admin_user_by_id(conn,request['requester_id'])
    if not requester or not requester['active'] or header['submitted_by']!=requester['id']:
        raise Conflict('Review the active requester and original submission in the ordinary screen.')
    lines=rows(conn,'SELECT * FROM supply_request_revision_line WHERE revision_id=? ORDER BY id LIMIT 21',(header['id'],))
    if not 1<=len(lines)<=20:raise Conflict('Use a request with 1–20 submitted lines.')
    items=[];proposed=[];now=tz.now_iso()
    for line in lines:
        item=supplies._item(conn,line['item_id'])
        if not item['active'] or any(item[k]!=line[k+'_snapshot'] for k in ('code','description','unit')):
            raise Conflict('Return the request in ordinary Supplies to correct a changed catalog item.')
        items.append(item)
        proposed.append({'request_id':request_id,'line_id':line['line_id'],'item_id':line['item_id'],
                         'approved_at':now,'approved_quantity':line['requested_quantity'],
                         'reserved_quantity':0,'effective_issued_quantity':0,'cancelled_quantity':0})
    projection=allocations.allocation_projection(conn,[l['item_id'] for l in lines],proposed=proposed,max_existing=25)
    allocation_inputs=[]
    for item in items:
        queue=rows(conn,"""SELECT r.*,d.approved_quantity FROM supply_reservation r
            JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
            JOIN supply_request q ON q.id=r.request_id WHERE r.item_id=? AND q.approval_status='approved'
            ORDER BY r.approved_at,r.request_id,r.line_id LIMIT 26""",(item['id'],))
        allocation_inputs.append([stock._totals(conn,item['id']),queue])
    own={}
    for item in projection:
        for line in item['lines']:
            if line['request_id']==request_id:own[line['line_id']]=line['projected_reserved_quantity']
            elif line['reserved_quantity']!=line['projected_reserved_quantity']:
                raise Conflict('Use ordinary Supplies when approval would change another request’s reservation.')
    grant_scope=rows(conn,"""SELECT g.id,g.revision,g.unit_id,ou.path FROM supply_role_grant g
        JOIN org_unit ou ON ou.id=g.unit_id WHERE g.user_id=? AND g.role='request_approver'
        AND g.revoked_at IS NULL ORDER BY g.id""",(user['id'],))
    unit=rows(conn,'SELECT id,name,path FROM org_unit WHERE id=?',(header['unit_id'],))
    approver={'id':user['id'],'name':st._account_display_name(conn,user['id']) or user['username'],'role':user['role']}
    # Private stock/queue metadata is bound by a digest, never shown to the model
    # or copied into the browser snapshot. Only this request's effects are shown.
    revision=digest([request,header,lines,items,projection,allocation_inputs,grant_scope,unit,approver,requester['id']])
    visible=[{'revision_line_id':l['id'],'line_id':l['line_id'],'item_id':l['item_id'],
              **{k:l[k] for k in ('code_snapshot','description_snapshot','unit_snapshot','requested_quantity')},
              'approved_quantity':l['requested_quantity'],'reserved_quantity':own[l['line_id']],
              'awaiting_stock_quantity':l['requested_quantity']-own[l['line_id']]} for l in lines]
    return user,request,header,{'expected_revision':revision,'approver':approver,'lines':visible,'projection':projection}


def approve_in_transaction(conn,user,request_id,revision,expected_revision,reason,*,operation_key):
    if not conn.in_transaction:raise RuntimeError('Supply approval requires a caller-owned transaction.')
    user,request,header,info=source(conn,user,request_id)
    if request['revision']!=revision or info['expected_revision']!=expected_revision:
        raise Conflict('The request, authority, catalog or allocation effects changed.')
    result=approvals.decide_request_in_transaction(conn,user,request_id,
        {'decision':'approved','reason':reason,'lines':[{'revision_line_id':l['revision_line_id'],
         'approved_quantity':l['approved_quantity'],'reason':''} for l in info['lines']]},
        expected_revision=revision,submitted_revision=request['current_revision'],operation_key=operation_key,
        expected_allocation=info['projection'])
    return {'decision':result,'submitted_revision_id':header['id'],'submission_operation_key':header['operation_key'],
            'request_created_at':request['created_at'],
            'line_count':len(info['lines']),
            'next_actor':{'role':'supply_custodian_issue_or_await_stock'}}
