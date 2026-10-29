"""Read-only role-aware Supplies dashboard and shared count/list query predicates."""
from urllib.parse import urlencode

import supplies as s
import supplies_permissions as permissions
import supplies_stock as stock
from supplies_status import requester_stage
from supplies_storage import Denied, Invalid, rows


REQUEST_STATES = ('draft','returned','submitted','approved','rejected','cancelled')
QUEUE_META = {
    'requests':('requests',('control_number','purpose','requester_snapshot','unit_snapshot'),'id DESC'),
    'approvals':('requests',('control_number','purpose','requester_snapshot','unit_snapshot'),'submitted_at,id'),
    'issuance':('requests',('control_number','purpose','requester_snapshot','unit_snapshot'),'priority,id'),
    'shortages':('shortages',('control_number','requester_snapshot','request_unit_snapshot','code_snapshot','description_snapshot'),'approved_at,request_id,line_id'),
    'releases':('releases',('release_number','control_number','recipient_snapshot','recipient_unit_snapshot'),'id DESC'),
    'warnings':('warnings',('code','description','unit'),'severity_order,code,id'),
    'activity':('activities',('code_snapshot','description_snapshot','actor_snapshot'),'id DESC'),
}


FILTER_OPTIONS = {
    'requests':[('', 'All my requests'),('action','Drafts and returned'),('submitted','Awaiting approval'),
                ('outstanding','Approved and outstanding'),('draft','Draft'),('returned','Returned'),
                ('approved','All approved'),('rejected','Rejected'),('cancelled','Cancelled')],
    'releases':[('', 'All acknowledgments'),('pending','Pending acknowledgment'),('disputed','Disputed'),('acknowledged','Acknowledged')],
    'warnings':[('', 'All warnings'),('out_of_stock','Out of stock'),('fully_reserved','Fully reserved'),('low_available','Low available')],
    'activity':[('', 'All movements'),('opening','Opening stock'),('receipt','Receipts'),('issue','Issues'),
                ('return','Usable returns'),('adjustment','Physical-count adjustments'),('reversal','Reversals')],
}


def _base(conn, user, kind, mine):
    clause, args = permissions.request_read_clause(conn,user)
    if kind in ('requests','approvals','issuance'):
        where = 'q.requester_id=?' if kind=='requests' else clause
        values = [user['id']] if kind=='requests' else args
        if kind=='approvals':
            if not conn.execute("SELECT 1 FROM supply_role_grant WHERE user_id=? AND role='request_approver' AND revoked_at IS NULL",(user['id'],)).fetchone():
                raise Denied('A current supply request approver grant is required.')
            where = "q.approval_status='submitted' AND q.requester_id<>? AND "+permissions.request_scope_clause()
            values = [user['id'],user['id']]
        if kind=='issuance':
            permissions.require_custodian(conn,user)
            where += " AND q.approval_status='approved' AND EXISTS (SELECT 1 FROM supply_reservation r WHERE r.request_id=q.id AND r.reserved_quantity>0)"
        return '''SELECT q.*,
          (SELECT MIN(r.approved_at) FROM supply_reservation r WHERE r.request_id=q.id) AS priority,
          COALESCE((SELECT SUM(r.reserved_quantity) FROM supply_reservation r WHERE r.request_id=q.id),0) AS reserved_quantity,
          COALESCE((SELECT SUM(d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity) FROM supply_reservation r
            JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id WHERE r.request_id=q.id),0) AS outstanding_quantity
          ,(SELECT COUNT(*) FROM supply_issue i WHERE i.request_id=q.id) AS issue_count,
          (SELECT COUNT(*) FROM supply_issue i WHERE i.request_id=q.id AND COALESCE((SELECT a.status FROM supply_issue_acknowledgment a
            WHERE a.issue_id=i.id ORDER BY a.revision DESC LIMIT 1),'pending')='pending') AS ack_pending,
          (SELECT COUNT(*) FROM supply_issue i WHERE i.request_id=q.id AND COALESCE((SELECT a.status FROM supply_issue_acknowledgment a
            WHERE a.issue_id=i.id ORDER BY a.revision DESC LIMIT 1),'pending')='disputed') AS ack_disputed
          FROM supply_request q WHERE '''+where, values
    if kind=='shortages':
        return '''SELECT q.id AS request_id,q.control_number,q.requester_snapshot,q.unit_snapshot AS request_unit_snapshot,
          r.line_id,l.code_snapshot,l.description_snapshot,l.unit_snapshot,l.requested_quantity,d.approved_quantity,
          r.reserved_quantity,r.effective_issued_quantity,r.cancelled_quantity,r.approved_at,
          d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity-r.reserved_quantity AS awaiting_stock_quantity
          FROM supply_reservation r JOIN supply_request q ON q.id=r.request_id
          JOIN supply_request_revision_line l ON l.id=r.revision_line_id
          JOIN supply_request_decision_line d ON d.revision_line_id=l.id
          WHERE q.approval_status='approved'
            AND d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity>r.reserved_quantity AND '''+clause,args
    if kind=='releases':
        clause,args = permissions.issue_read_clause(conn,user)
        if mine:
            clause += ' AND i.recipient_id=?'
            args.append(user['id'])
        return '''SELECT i.id,i.request_id,i.recipient_id,i.release_number,i.effective_date,i.recipient_snapshot,i.recipient_unit_snapshot,
          q.control_number,COALESCE((SELECT a.status FROM supply_issue_acknowledgment a WHERE a.issue_id=i.id ORDER BY a.revision DESC LIMIT 1),'pending') AS acknowledgment_status
          FROM supply_issue i JOIN supply_request q ON q.id=i.request_id WHERE '''+clause,args
    permissions.require_stock_reader(conn,user)
    if kind=='warnings':
        return '''SELECT x.*,t.on_hand,COALESCE(r.reserved,0) AS reserved,
          CASE WHEN t.on_hand=0 THEN 'out_of_stock' WHEN t.on_hand=COALESCE(r.reserved,0) THEN 'fully_reserved' ELSE 'low_available' END AS availability_state,
          CASE WHEN t.on_hand=0 THEN 0 WHEN t.on_hand=COALESCE(r.reserved,0) THEN 1 ELSE 2 END AS severity_order
          FROM supply_item x JOIN (SELECT item_id,SUM(quantity_delta) AS on_hand FROM supply_stock_movement GROUP BY item_id) t ON t.item_id=x.id
          LEFT JOIN (SELECT item_id,SUM(reserved_quantity) AS reserved FROM supply_reservation GROUP BY item_id) r ON r.item_id=x.id
          WHERE x.active=1 AND (t.on_hand=0 OR t.on_hand-COALESCE(r.reserved,0)=0 OR t.on_hand-COALESCE(r.reserved,0)<x.critical_level)''',[]
    return '''SELECT id,item_id,kind,quantity_delta,effective_date,posted_at,actor_snapshot,code_snapshot,description_snapshot,unit_snapshot
      FROM supply_stock_movement''',[]


def _filter(kind, state):
    if not state:
        return '1',[]
    if kind=='requests':
        if state=='action':return "approval_status IN ('draft','returned')",[]
        if state=='outstanding':return "approval_status='approved' AND outstanding_quantity>0",[]
        # Supplies 3.1: the requester's three views. Needs action is what only the requester can move forward.
        if state=='needs_action':return "(approval_status IN ('draft','returned') OR (approval_status='approved' AND ack_pending>0))",[]
        if state=='active':return "(approval_status='submitted' OR (approval_status='approved' AND (outstanding_quantity>0 OR ack_pending>0)))",[]
        if state=='completed':return "(approval_status IN ('rejected','cancelled') OR (approval_status='approved' AND outstanding_quantity<=0 AND ack_pending=0))",[]
        if state in REQUEST_STATES:return 'approval_status=?',[state]
    if kind=='releases' and state in ('pending','acknowledged','disputed'):
        return 'acknowledgment_status=?',[state]
    if kind=='warnings' and state in ('out_of_stock','fully_reserved','low_available'):
        return 'availability_state=?',[state]
    if kind=='activity' and state in ('opening','receipt','issue','return','adjustment','reversal'):
        return 'kind=?',[state]
    raise Invalid('Choose a supported queue status.')


def approver_names(conn, request_id):
    return [p['name'] for p in rows(conn,'''SELECT COALESCE(rp.name,u.username) AS name FROM supply_request q
      JOIN admin_user u ON u.active=1 LEFT JOIN resource_person rp ON rp.id=u.rp_id
      WHERE q.id=? AND u.id<>q.requester_id AND '''+permissions.request_scope_clause('u.id')+' ORDER BY name,u.id LIMIT 6',(request_id,))]


def _next_action(conn, entry, kind):
    if kind=='releases':
        entry['next_action'] = ('Recipient: '+entry['recipient_snapshot']+(' — resolve the dispute' if entry['acknowledgment_status']=='disputed' else ' — acknowledge receipt')) if entry['acknowledgment_status']!='acknowledged' else 'Acknowledged; no receipt response pending'
        return
    if kind not in ('requests','approvals','issuance'):
        return
    state = entry['approval_status']
    action = {'draft':'You: review and submit','returned':'You: correct and resubmit',
              'rejected':'Decision complete; review the reason','cancelled':'Request cancelled; no further action'}.get(state)
    if state=='submitted':
        names = approver_names(conn,entry['id'])
        action = ('Approver: '+', '.join(names[:5])+(' and others' if len(names)>5 else '')) if names else 'Administrator: assign a supply request approver'
    elif state=='approved':
        action = ('Custodian: arrange handover of reserved supplies' if entry['reserved_quantity'] else
                  'Custodian: receive stock for outstanding demand') if entry['outstanding_quantity'] else 'Fulfillment complete; review releases and acknowledgments'
    entry['next_action'] = action
    if kind=='requests':
        entry['approver_names'] = approver_names(conn,entry['id']) if state=='submitted' else []
        entry['stage'] = requester_stage(entry)


def queue(conn, user, kind, *, page=1, query='', state='', mine=False, count_only=False, limit=25):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn,user)
        if kind not in QUEUE_META:
            raise Invalid('Choose a supported supply queue.')
        page = s.integer(page,'Page',1)
        limit = s.integer(limit,'Page size',1)
        if limit>25:
            raise Invalid('Use at most 25 entries per page.')
        if not isinstance(query,str) or len(query)>200 or any(ord(c)<32 for c in query):
            raise Invalid('Search must contain at most 200 characters without control characters.')
        query = query.strip()
        if not isinstance(state,str):
            raise Invalid('Choose a supported queue status.')
        base,args = _base(conn,user,kind,mine)
        predicate,values = _filter(kind,state)
        key,search_columns,order = QUEUE_META[kind]
        if query:
            predicate += ' AND ('+' OR '.join('instr(lower(COALESCE('+column+",'')),lower(?))>0" for column in search_columns)+')'
            values += [query]*len(search_columns)
        sql = 'WITH queue AS ('+base+') '
        total = conn.execute(sql+'SELECT COUNT(*) FROM queue WHERE '+predicate,(*args,*values)).fetchone()[0]
        found = [] if count_only else rows(conn,sql+'SELECT * FROM queue WHERE '+predicate+' ORDER BY '+order+' LIMIT ? OFFSET ?',
                                         (*args,*values,limit,(page-1)*limit))
        if kind=='warnings':
            from supplies_notify import classify
            for item in found:item['warning'] = classify(item['on_hand'],item['reserved'],item['critical_level'])
        for entry in found:_next_action(conn,entry,kind)
        params = {'q':query,'status':state}
        if kind=='releases' and mine:params['mine']='1'
        return {key:found,'total':total,'page':page,'has_next':page*limit<total,'query':query,
                'status_filter':state,'mine':bool(mine),'queue_kind':kind,'filter_options':FILTER_OPTIONS.get(kind,[]),
                'previous_url':'?'+urlencode({**params,'page':page-1}),
                'next_url':'?'+urlencode({**params,'page':page+1})}


def dashboard(conn, user):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn,user)
        custodian = permissions.has_role(conn,user,'custodian')
        stock_reader = custodian or permissions.has_role(conn,user,'auditor')
        approver = bool(conn.execute("SELECT 1 FROM supply_role_grant WHERE user_id=? AND role='request_approver' AND revoked_at IS NULL",(user['id'],)).fetchone())
        from supplies_requests import requester
        try:requester(conn,user);can_request=True
        except Denied:can_request=False
        cards=[]
        def card(kind,title,url,*,state='',mine=False,responsible):
            count=queue(conn,user,kind,state=state,mine=mine,count_only=True)['total']
            params={}
            if state:params['status']=state
            if mine:params['mine']='1'
            operational = kind in ('approvals','issuance','warnings') or (kind=='shortages' and (stock_reader or approver)) or (kind=='releases' and not mine)
            cards.append({'title':title,'count':count,'url':url+('?' + urlencode(params) if params else ''),
                          'responsible':responsible,'operational':operational})
        card('requests','My drafts and returned requests','/supplies/requests',state='action',responsible='You: review, correct and submit')
        card('requests','My requests awaiting approval','/supplies/requests',state='submitted',responsible='Current approver for your submitted unit')
        card('requests','My approved requests still outstanding','/supplies/requests',state='outstanding',responsible='Supply custodian: stock and handover')
        card('releases','My releases awaiting acknowledgment','/supplies/issues',state='pending',mine=True,responsible='You: acknowledge receipt or report a dispute')
        card('releases','My disputed releases','/supplies/issues',state='disputed',mine=True,responsible='You and the custodian: resolve the discrepancy')
        card('shortages','Awaiting-stock lines I can view','/supplies/awaiting-stock',responsible='Supply custodian: receive and allocate stock')
        if approver:
            card('approvals','Pending approvals in my scope','/supplies/approvals',responsible='You: review the submitted request')
        if custodian:
            card('issuance','Requests ready to issue','/supplies/issuance',responsible='You: arrange the reserved handover')
            card('releases','All unacknowledged releases','/supplies/issues',state='pending',responsible='Recorded recipients; custodian follows up')
            card('releases','All disputed releases','/supplies/issues',state='disputed',responsible='Recorded recipients and custodian')
            from supplies_notify import list_notices
            cards.append({'title':'My unread active stock notices','count':list_notices(conn,user,unread=True)['unread_count'],
                          'url':'/supplies/notices?unread=1','responsible':'You: review current stock and warning evidence','operational':True})
        if stock_reader:
            card('warnings','Items with stock warnings','/supplies/warnings',responsible='Custodian: review physical stock and availability')
        operational = [card for card in cards if card['operational']]
        operational.sort(key=lambda card: (0 if card['url']=='/supplies/approvals' else
                                          1 if card['url']=='/supplies/issuance' else 2))
        groups = []
        if operational:
            groups.append({'title':'Stockroom work' if custodian else 'Stock overview' if stock_reader else 'Approvals and scope work',
                           'cards':operational})
        groups.append({'title':'My requests and releases','cards':[card for card in cards if not card['operational']]})
        return {'cards':cards,'card_groups':groups,'recent_requests':queue(conn,user,'requests',limit=5)['requests'],
                'activities':queue(conn,user,'activity',limit=5)['activities'] if stock_reader else [],
                'can_request':can_request,'show_stock_activity':stock_reader,
                'pending_warning_updates':conn.execute('SELECT COUNT(*) FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0] if stock_reader else 0}
