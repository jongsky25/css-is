"""Transaction-neutral oldest-first reservation allocator shared by future stock flows."""
import json

import supplies_stock as stock
import tzutil as tz
from supplies_storage import Conflict, rows


def availability(conn, item_id):
    on_hand = stock._totals(conn, item_id)['on_hand']
    reserved = sum(r[0] for r in conn.execute('SELECT reserved_quantity FROM supply_reservation WHERE item_id=?', (item_id,)))
    if not 0 <= reserved <= on_hand:
        raise Conflict('Stock reservations need reconciliation before continuing.')
    return {'on_hand': on_hand, 'reserved_quantity': reserved, 'available': on_hand-reserved}


def allocate_outstanding(conn, user, item_ids, operation_key):
    """Caller owns the write transaction and its recorded operation; no hidden commit."""
    if not conn.in_transaction:
        raise RuntimeError('Allocation requires the caller write transaction.')
    for item_id in sorted(set(item_ids)):
        remaining = stock._totals(conn, item_id)['on_hand']
        lines = rows(conn, '''SELECT r.*,d.approved_quantity FROM supply_reservation r
          JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
          JOIN supply_request q ON q.id=r.request_id WHERE r.item_id=? AND q.approval_status='approved'
          ORDER BY r.approved_at,r.request_id,r.line_id''', (item_id,))
        for line in lines:
            outstanding = line['approved_quantity']-line['effective_issued_quantity']-line['cancelled_quantity']
            if not 0 <= outstanding <= line['approved_quantity']:
                raise Conflict('Approved demand needs reconciliation before allocation.')
            quantity = min(outstanding, remaining)
            remaining -= quantity
            if quantity == line['reserved_quantity']:
                continue
            conn.execute('UPDATE supply_reservation SET reserved_quantity=?,version=version+1 WHERE id=?', (quantity,line['id']))
            detail = {'line_id':line['line_id'],'item_id':item_id,
                      'previous_reserved_quantity':line['reserved_quantity'],'reserved_quantity':quantity}
            conn.execute('''INSERT INTO supply_event
              (entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
              VALUES ('request',?,'reservation_allocate',?,?,?,?)''',
              (line['request_id'],user['id'],json.dumps(detail,sort_keys=True),tz.now_iso(),operation_key))
        availability(conn,item_id)
        from supplies_notify import enqueue
        enqueue(conn,[item_id],operation_key)


def fulfillment(lines):
    approved = sum(line['approved_quantity'] for line in lines)
    issued = sum(line['effective_issued_quantity'] for line in lines)
    cancelled = sum(line['cancelled_quantity'] for line in lines)
    reserved = sum(line['reserved_quantity'] for line in lines)
    outstanding = approved-issued-cancelled
    if not approved:
        return 'No approved quantity'
    if outstanding==0:
        if issued==approved:
            return 'Fully issued'
        return 'Cancelled before issue' if issued==0 else 'Closed with remainder cancelled'
    if issued:
        return 'Partially issued'
    return 'Ready to issue' if reserved else 'Awaiting stock'
