"""Reviewed, append-only returns, physical counts and linked issue/receipt reversals."""
import hashlib
import json

import supplies as s
import supplies_permissions as permissions
import supplies_stock as stock
from supplies_allocations import allocate_outstanding, availability
from supplies_storage import Conflict, Invalid, Missing, operation, record, rows, transaction
import tzutil as tz


KINDS = {'return', 'stocktake', 'issue_reversal', 'receipt_reversal'}
LABELS = {'return': 'Record returned supplies', 'stocktake': 'Record a physical stock count',
          'issue_reversal': 'Reverse a mistaken issue', 'receipt_reversal': 'Reverse a mistaken receipt'}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _sources(conn, kind, parent_id):
    if kind not in KINDS:
        raise Invalid('Choose a supported correction action.')
    parent_id = s.integer(parent_id, 'Original record', 1)
    if kind == 'stocktake':
        return [s._item(conn, parent_id)]
    if kind in ('return', 'issue_reversal'):
        source = rows(conn, '''SELECT l.*,m.effective_date FROM supply_issue_line l
          JOIN supply_stock_movement m ON m.id=l.movement_id WHERE l.issue_id=? ORDER BY l.id''', (parent_id,))
        for line in source:
            totals = conn.execute('''SELECT COALESCE(SUM(quantity),0) FROM supply_correction
              WHERE issue_line_id=?''', (line['id'],)).fetchone()[0]
            line['remaining_quantity'] = line['issued_quantity'] - totals
    else:
        source = rows(conn, '''SELECT l.*,m.id AS movement_id,m.effective_date FROM supply_receipt_line l
          JOIN supply_stock_movement m ON m.receipt_line_id=l.id WHERE l.receipt_id=? ORDER BY l.id''', (parent_id,))
        for line in source:
            totals = conn.execute('''SELECT COALESCE(SUM(quantity),0) FROM supply_correction
              WHERE receipt_line_id=?''', (line['id'],)).fetchone()[0]
            line['remaining_quantity'] = line['accepted_quantity'] - totals
    if not source:
        raise Missing('Original stock record not found or unavailable to you.')
    return source


def form_context(conn, user, kind, parent_id):
    with stock._snapshot(conn):
        permissions.require_custodian(conn, user)
        source = _sources(conn, kind, parent_id)
        reference = (source[0]['code'] if kind == 'stocktake' else
                     f'RCV-{int(parent_id):06d}' if kind == 'receipt_reversal' else
                     conn.execute('SELECT release_number FROM supply_issue WHERE id=?',(parent_id,)).fetchone()[0])
        return {'original_reference': reference, 'kind': kind, 'title': LABELS[kind], 'parent_id': parent_id, 'source_lines': source,
                'linked_delivery': kind == 'receipt_reversal' and any(line.get('replenishment_line_id') is not None for line in source),
                'today': tz.today_local().isoformat()}


def _fields(kind, parent_id, fields):
    payload = {'kind': kind, 'parent_id': s.integer(parent_id, 'Original record', 1),
               'quantity': s.integer(fields.get('quantity'), 'Physical count' if kind == 'stocktake' else 'Quantity',
                                     0 if kind == 'stocktake' else 1),
               'effective_date': stock._effective_date(fields.get('effective_date')),
               'reason': s.text(fields.get('reason'), 'Reason and evidence', 2000)}
    if kind != 'stocktake':
        payload['source_line_id'] = s.integer(fields.get('source_line_id'), 'Original item line', 1)
    if kind == 'return':
        if fields.get('condition') not in ('usable', 'unusable'):
            raise Invalid('Choose whether the returned supplies are usable or damaged/unusable.')
        payload['condition'] = fields['condition']
    if kind == 'issue_reversal':
        if fields.get('reopen_demand') not in ('yes', 'no'):
            raise Invalid('Choose explicitly whether to reopen the corrected demand or cancel it.')
        payload['reopen_demand'] = fields['reopen_demand']
    if kind == 'receipt_reversal' and fields.get('reopen_incoming') not in ('', None):
        if fields['reopen_incoming'] not in ('yes', 'no'):
            raise Invalid('Choose whether the corrected accepted quantity returns to incoming or is cancelled.')
        payload['reopen_incoming'] = fields['reopen_incoming']
    return payload


def _impact(conn, payload):
    kind, quantity = payload['kind'], payload['quantity']
    sources = _sources(conn, kind, payload['parent_id'])
    if kind == 'stocktake':
        item = sources[0]
        source = None
        if not stock._totals(conn, item['id'])['recorded']:
            raise Conflict('Record reviewed opening stock before a later physical count.')
    else:
        source = next((line for line in sources if line['id'] == payload['source_line_id']), None)
        if source is None:
            raise Invalid('The selected item line does not belong to this original record.')
        if quantity > source['remaining_quantity']:
            raise Conflict('Quantity exceeds the original quantity still eligible for return or reversal.')
        if payload['effective_date'] < source['effective_date']:
            raise Invalid('The correction date cannot precede the original handover or receipt.')
        item = s._item(conn, source['item_id'])
        if item['unit'] != source['unit_snapshot']:
            raise Conflict('The original and current stock units need reconciliation before correction.')
    before = availability(conn, item['id'])
    linked = None
    if kind == 'receipt_reversal':
        linked_rows = rows(conn, '''SELECT dl.replenishment_line_id,d.replenishment_id,
          c.approved_quantity,c.received_quantity,c.cancelled_quantity,p.status,p.revision
          FROM supply_delivery_line dl JOIN supply_delivery d ON d.id=dl.delivery_id
          JOIN supply_replenishment_commitment c ON c.line_id=dl.replenishment_line_id
          JOIN supply_replenishment p ON p.id=d.replenishment_id
          WHERE dl.receipt_line_id=?''', (source['id'],))
        linked = linked_rows[0] if linked_rows else None
        choice = payload.get('reopen_incoming')
        if linked and choice not in ('yes','no'):
            raise Invalid('Choose whether corrected accepted units return to incoming or are cancelled.')
        if not linked and choice is not None:
            raise Invalid('An unrelated receipt has no replenishment incoming to reopen.')
        if linked and linked['received_quantity'] < quantity:
            raise Conflict('Linked delivery totals need reconciliation before reversal.')
        if linked and choice == 'yes' and not item['active']:
            raise Conflict('An inactive item cannot regain incoming stock. Choose cancellation after reconciliation.')
    delta = (quantity - before['on_hand'] if kind == 'stocktake' else
             -quantity if kind == 'receipt_reversal' else
             0 if kind == 'return' and payload['condition'] == 'unusable' else quantity)
    if kind == 'stocktake' and (delta == 0 or abs(delta) > 2147483647):
        raise Invalid('The count must differ from current stock by 1–2147483647 units; unchanged counts need no adjustment.')
    if kind == 'receipt_reversal' and quantity > before['available']:
        raise Conflict(f"Only {before['available']} units are free to reverse. Reconcile issued stock or explicitly cancel reservations first; this reversal never releases reservations automatically.")
    if not 0 <= before['on_hand'] + delta <= stock.MAX_TOTAL:
        raise Invalid('The resulting stock quantity is outside the supported range.')
    reservations = rows(conn, '''SELECT r.*,d.approved_quantity,q.control_number,q.revision AS request_revision
      FROM supply_reservation r JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
      JOIN supply_request q ON q.id=r.request_id WHERE r.item_id=? AND q.approval_status='approved'
      ORDER BY r.approved_at,r.request_id,r.line_id''', (item['id'],))
    # Simulate the allocator, preserving the oldest demand and releasing losses from the newest first.
    remaining, affected = before['on_hand'] + delta, []
    for reservation in reservations:
        issued, cancelled = reservation['effective_issued_quantity'], reservation['cancelled_quantity']
        if kind == 'issue_reversal' and reservation['id'] == source['reservation_id']:
            if issued < quantity:
                raise Conflict('Effective issuance needs reconciliation before reversal.')
            issued -= quantity
            if payload['reopen_demand'] == 'no':
                cancelled += quantity
        outstanding = reservation['approved_quantity'] - issued - cancelled
        if not 0 <= outstanding <= reservation['approved_quantity']:
            raise Conflict('Approved demand needs reconciliation before correction.')
        reserved = min(outstanding, remaining)
        remaining -= reserved
        if reserved != reservation['reserved_quantity']:
            affected.append({'request_id': reservation['request_id'], 'control_number': reservation['control_number'],
                             'line_id': reservation['line_id'], 'previous_reserved': reservation['reserved_quantity'],
                             'reserved': reserved, 'released': max(0, reservation['reserved_quantity'] - reserved)})
    state = {'payload': payload, 'item': item, 'source': source, 'before': before, 'reservations': reservations,
             'linked_commitment': linked,
             'last_movement': conn.execute('SELECT COALESCE(MAX(id),0) FROM supply_stock_movement WHERE item_id=?',
                                          (item['id'],)).fetchone()[0]}
    return {'item': item, 'source': source, 'before': before, 'quantity_delta': delta,
            'linked_commitment': linked,
            'incoming_after': ((linked['approved_quantity']-linked['received_quantity']-linked['cancelled_quantity']+
                               (quantity if payload.get('reopen_incoming')=='yes' else 0)) if linked else None),
            'on_hand_after': before['on_hand'] + delta, 'reserved_after': before['on_hand'] + delta - remaining,
            'available_after': remaining, 'affected_requests': affected,
            'preview_token': hashlib.sha256(_json(state).encode()).hexdigest()}


def preview(conn, user, kind, parent_id, fields):
    with stock._snapshot(conn):
        permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        return _impact(conn, _fields(kind, parent_id, fields))


def _post(conn, user, kind, parent_id, fields, *, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        payload = _fields(kind, parent_id, fields)
        payload['preview_token'] = s.text(fields.get('preview_token'), 'Reviewed preview', 64)
        if fields.get('confirmed') != 'yes':
            raise Invalid('Confirm the reviewed stock and request impact before posting.')
        key, digest, prior = operation(conn, user, operation_key, 'correction_' + kind, payload)
        if prior is not None:
            return prior
        impact = _impact(conn, {k: v for k, v in payload.items() if k != 'preview_token'})
        if impact['preview_token'] != payload['preview_token']:
            raise Conflict('Stock, reservations or original evidence changed. Review a new preview before posting.')
        item, source, delta = impact['item'], impact['source'], impact['quantity_delta']
        correction_id = conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM supply_correction').fetchone()[0]
        movement_id = None
        if delta:
            movement_id = stock._add_movement(conn, user, item,
                kind='return' if kind == 'return' else 'adjustment' if kind == 'stocktake' else 'reversal',
                quantity=delta, effective_date=payload['effective_date'], key=key,
                source_id=correction_id, source_line_id=payload.get('source_line_id'), reason=payload['reason'],
                reverses_movement_id=source['movement_id'] if kind in ('issue_reversal', 'receipt_reversal') else None)
        now = tz.now_iso()
        issue_line_id = source['id'] if kind in ('return', 'issue_reversal') else None
        receipt_line_id = source['id'] if kind == 'receipt_reversal' else None
        conn.execute('''INSERT INTO supply_correction
          (id,item_id,kind,quantity,quantity_delta,issue_line_id,receipt_line_id,source_movement_id,movement_id,
           condition,reopen_demand,before_on_hand,after_on_hand,effective_date,reason,posted_at,posted_by,
           actor_snapshot,impact_json,operation_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (correction_id,item['id'],kind,payload['quantity'],delta,issue_line_id,receipt_line_id,
           source['movement_id'] if source else None,movement_id,payload.get('condition'),
           (1 if payload['reopen_demand']=='yes' else 0) if kind=='issue_reversal' else None,
           impact['before']['on_hand'],impact['on_hand_after'],payload['effective_date'],payload['reason'],now,
           user['id'],stock._actor_name(conn,user),_json(impact),key))
        if kind == 'receipt_reversal' and impact['linked_commitment']:
            linked = impact['linked_commitment']
            conn.execute('''UPDATE supply_replenishment_commitment SET
              received_quantity=received_quantity-?,cancelled_quantity=cancelled_quantity+?
              WHERE line_id=?''', (payload['quantity'],0 if payload['reopen_incoming']=='yes' else payload['quantity'],
                                  linked['replenishment_line_id']))
            conn.execute('''INSERT INTO supply_replenishment_receipt_reversal
              (correction_id,replenishment_line_id,quantity,reopen_incoming) VALUES (?,?,?,?)''',
              (correction_id,linked['replenishment_line_id'],payload['quantity'],
               1 if payload['reopen_incoming']=='yes' else 0))
            from supplies_deliveries import sync_status
            status,_remaining = sync_status(conn,linked['replenishment_id'],now=now)
        if kind in ('return', 'issue_reversal'):
            request_id = conn.execute('SELECT request_id FROM supply_issue WHERE id=?', (parent_id,)).fetchone()[0]
            if kind == 'issue_reversal':
                conn.execute('''UPDATE supply_reservation SET effective_issued_quantity=effective_issued_quantity-?,
                  cancelled_quantity=cancelled_quantity+?,version=version+1 WHERE id=?''',
                  (payload['quantity'],payload['quantity'] if payload['reopen_demand']=='no' else 0,source['reservation_id']))
            conn.execute('UPDATE supply_request SET revision=revision+1,updated_at=? WHERE id=?', (now,request_id))
        result = {'id': correction_id, 'item_id': item['id'], 'movement_id': movement_id,
                  'quantity_delta': delta, 'on_hand': impact['on_hand_after']}
        record(conn,user,key,digest,'correction_'+kind,'correction',result,{'correction_id':correction_id,**payload,'impact':impact})
        if kind == 'receipt_reversal' and impact['linked_commitment']:
            conn.execute('''INSERT INTO supply_event(entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
              VALUES ('replenishment',?,'receipt_reversal',?,?,?,?)''',
              (linked['replenishment_id'],user['id'],_json({'correction_id':correction_id,
                'quantity':payload['quantity'],'reopen_incoming':payload['reopen_incoming'],'status':status}),now,key))
        if kind in ('return', 'issue_reversal'):
            conn.execute('''INSERT INTO supply_event(entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
              VALUES ('request',?,?,?,?,?,?)''', (request_id,'correction_'+kind,user['id'],
              _json({'correction_id':correction_id,**payload}),now,key))
        if kind == 'stocktake' and delta < 0:
            for affected in reversed(impact['affected_requests']):
                if not affected['released']:
                    continue
                conn.execute('UPDATE supply_reservation SET reserved_quantity=?,version=version+1 WHERE request_id=? AND line_id=?',
                             (affected['reserved'],affected['request_id'],affected['line_id']))
                conn.execute('''INSERT INTO supply_event(entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
                  VALUES ('request',?,'stocktake_reservation_release',?,?,?,?)''',
                  (affected['request_id'],user['id'],_json({'correction_id':correction_id,'reason':payload['reason'],**affected}),now,key))
        allocate_outstanding(conn,user,[item['id']],key)
        return result


def post_return(conn, user, issue_id, fields, *, operation_key):
    return _post(conn,user,'return',issue_id,fields,operation_key=operation_key)


def post_stocktake(conn, user, item_id, fields, *, operation_key):
    return _post(conn,user,'stocktake',item_id,fields,operation_key=operation_key)


def reverse_issue(conn, user, issue_id, fields, *, operation_key):
    return _post(conn,user,'issue_reversal',issue_id,fields,operation_key=operation_key)


def reverse_receipt(conn, user, receipt_id, fields, *, operation_key):
    return _post(conn,user,'receipt_reversal',receipt_id,fields,operation_key=operation_key)


def issue_summary(conn, issue):
    for line in issue['lines']:
        totals = rows(conn, '''SELECT COALESCE(SUM(CASE WHEN kind='issue_reversal' THEN quantity ELSE 0 END),0) AS reversed_quantity,
          COALESCE(SUM(CASE WHEN kind='return' AND condition='usable' THEN quantity ELSE 0 END),0) AS usable_returned,
          COALESCE(SUM(CASE WHEN kind='return' AND condition='unusable' THEN quantity ELSE 0 END),0) AS unusable_returned
          FROM supply_correction WHERE issue_line_id=?''',(line['id'],))[0]
        line.update(totals)
        line['net_issued_quantity'] = line['issued_quantity'] - line['reversed_quantity']
    return issue


def history(conn, user, entity, entity_id, *, page=1):
    with stock._snapshot(conn):
        if entity == 'issues':
            from supplies_issues import get_issue
            get_issue(conn,user,entity_id)
            predicate = 'c.issue_line_id IN (SELECT id FROM supply_issue_line WHERE issue_id=?)'
        elif entity == 'receipts':
            stock.get_receipt(conn,user,entity_id)
            predicate = 'c.receipt_line_id IN (SELECT id FROM supply_receipt_line WHERE receipt_id=?)'
        elif entity == 'items':
            permissions.require_stock_reader(conn,user)
            s.get_item(conn,user,entity_id)
            predicate = 'c.item_id=?'
        else:
            raise Invalid('Choose a supported stock history.')
        page = s.integer(page,'Page',1)
        found = rows(conn, f'''SELECT c.* FROM supply_correction c
          WHERE {predicate} ORDER BY c.id DESC LIMIT 26 OFFSET ?''',(entity_id,(page-1)*25))
        for correction in found:
            correction['impact'] = json.loads(correction.pop('impact_json'))
            correction['code'] = correction['impact']['item']['code']
            correction['unit'] = correction['impact']['item']['unit']
            visible = []
            from supplies_requests import _visible
            for affected in correction['impact']['affected_requests']:
                try:
                    _visible(conn, user, affected['request_id'])
                except Missing:
                    continue
                visible.append(affected)
            correction['impact']['affected_requests'] = visible
        return {'corrections':found[:25],'has_next':len(found)>25,'page':page,'entity':entity,'entity_id':entity_id}


def get_correction(conn, user, correction_id):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn,user)
        found = rows(conn,'SELECT * FROM supply_correction WHERE id=?',(s.integer(correction_id,'Correction',1),))
        if not found:
            raise Missing('Correction not found or unavailable to you.')
        entry = found[0]
        if entry['issue_line_id'] is not None:
            entity = 'issues'
            parent = conn.execute('SELECT issue_id FROM supply_issue_line WHERE id=?',(entry['issue_line_id'],)).fetchone()[0]
        elif entry['receipt_line_id'] is not None:
            entity = 'receipts'
            parent = conn.execute('SELECT receipt_id FROM supply_receipt_line WHERE id=?',(entry['receipt_line_id'],)).fetchone()[0]
        else:
            entity, parent = 'items', entry['item_id']
        # history() applies the source's current read predicate and redacts unrelated requests.
        # Select the containing page, then retain just the requested immutable entry.
        offset = conn.execute('SELECT COUNT(*) FROM supply_correction WHERE id>? AND '+
            ('issue_line_id IN (SELECT id FROM supply_issue_line WHERE issue_id=?)' if entity=='issues' else
             'receipt_line_id IN (SELECT id FROM supply_receipt_line WHERE receipt_id=?)' if entity=='receipts' else
             'item_id=?'),(entry['id'],parent)).fetchone()[0]
        context = history(conn,user,entity,parent,page=offset//25+1)
        context['corrections'] = [c for c in context['corrections'] if c['id']==entry['id']]
        context['single'] = True
        return context
