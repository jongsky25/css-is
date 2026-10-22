"""S5.3 replenishment deliveries and accepted stock posting."""
import json

import supplies as s
import supplies_permissions as permissions
import supplies_replenishment as rep
import supplies_stock as stock
import tzutil as tz
from supplies_allocations import allocate_outstanding
from supplies_storage import Conflict, Invalid, Missing, operation, record, rows, transaction


def _fields(fields):
    if not isinstance(fields, dict):
        raise Invalid('Delivery details are required.')
    header = {'supplier': s.text(fields.get('supplier'), 'Supplier', 240),
              'dr_number': s.text(fields.get('dr_number'), 'DR number', 120),
              'apr_number': stock._optional_text(fields.get('apr_number'), 'APR number', 120),
              'procurement_mode': stock._optional_text(fields.get('procurement_mode'), 'Procurement mode', 120),
              'note': stock._optional_text(fields.get('note'), 'Delivery note', 2000),
              'effective_date': stock._effective_date(fields.get('effective_date'))}
    raw = fields.get('lines')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        raise Invalid('A delivery needs 1–20 item lines.')
    lines, seen = [], set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise Invalid('Each delivery line needs quantities and a replenishment line.')
        line_id = s.integer(entry.get('replenishment_line_id'), 'Replenishment line', 1)
        if line_id in seen:
            raise Invalid('Each replenishment line may appear only once per delivery.')
        seen.add(line_id)
        delivered = s.integer(entry.get('delivered_quantity'), 'Delivered quantity', 1)
        accepted = s.integer(entry.get('accepted_quantity'), 'Accepted quantity')
        rejected = s.integer(entry.get('rejected_quantity'), 'Rejected quantity')
        if delivered != accepted + rejected:
            raise Invalid('Delivered quantity must equal accepted plus rejected quantities.')
        reason = stock._optional_text(entry.get('rejection_reason'), 'Rejection reason', 2000)
        if bool(rejected) != bool(reason):
            raise Invalid('Explain rejected units and leave the rejection reason empty when none are rejected.')
        lines.append({'replenishment_line_id': line_id, 'delivered_quantity': delivered,
                      'accepted_quantity': accepted, 'rejected_quantity': rejected,
                      'rejection_reason': reason,
                      'expected_item_revision': s.integer(entry.get('expected_item_revision'), 'Item revision', 1),
                      'unit_cost': stock.unit_cost(entry.get('unit_cost')),
                      'expiry_date': stock._date(entry.get('expiry_date'), 'Expiry date', optional=True)})
    return header, sorted(lines, key=lambda line: line['replenishment_line_id'])


def sync_status(conn, replenishment_id, *, now=None):
    """Caller owns the write transaction and updates the parent revision once."""
    totals = conn.execute('''SELECT COALESCE(SUM(c.approved_quantity-c.received_quantity-c.cancelled_quantity),0),
      COALESCE(SUM(c.received_quantity),0) FROM supply_replenishment_commitment c
      JOIN supply_replenishment_line l ON l.id=c.line_id WHERE l.replenishment_id=?''',
      (replenishment_id,)).fetchone()
    remaining, received = totals
    if remaining == 0:
        status = 'received' if received else 'cancelled'
    elif received:
        status = 'partially_received'
    else:
        status = ('ordered' if conn.execute('SELECT 1 FROM supply_replenishment_order WHERE replenishment_id=?',
                                          (replenishment_id,)).fetchone() else 'approved')
    conn.execute('''UPDATE supply_replenishment SET status=?,revision=revision+1,updated_at=? WHERE id=?''',
                 (status, now or tz.now_iso(), replenishment_id))
    return status, remaining


def receive_delivery(conn, user, replenishment_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        replenishment_id = s.integer(replenishment_id, 'Replenishment', 1)
        revision = s.integer(expected_revision, 'Replenishment revision', 1)
        header, lines = _fields(fields)
        payload = {'replenishment_id': replenishment_id, 'revision': revision,
                   'header': header, 'lines': lines}
        key, digest, prior = operation(conn, user, operation_key, 'delivery_receive', payload)
        if prior is not None:
            return prior
        found = rows(conn, 'SELECT * FROM supply_replenishment WHERE id=?', (replenishment_id,))
        if not found:
            raise Missing('Replenishment not found.')
        parent = found[0]
        if parent['revision'] != revision or parent['status'] not in ('approved', 'ordered', 'partially_received'):
            raise Conflict('The replenishment changed or has no open approved delivery. Reload it.')
        accepted_items = []
        checked = []
        for line in lines:
            matches = rows(conn, '''SELECT l.*,c.approved_quantity,c.received_quantity,c.cancelled_quantity
              FROM supply_replenishment_line l JOIN supply_replenishment_commitment c ON c.line_id=l.id
              WHERE l.id=? AND l.replenishment_id=?''',
              (line['replenishment_line_id'], replenishment_id))
            if not matches:
                raise Invalid('A delivery line is not approved on this replenishment.')
            source = matches[0]
            remaining = source['approved_quantity']-source['received_quantity']-source['cancelled_quantity']
            if line['delivered_quantity'] > remaining:
                raise Conflict('Delivered quantity exceeds the unreceived approved remainder.')
            item = stock._posting_item(conn, source['item_id'], line['expected_item_revision'])
            if item['unit'] != source['unit_snapshot']:
                raise Conflict('The item unit changed. Reconcile the approved replenishment before delivery.')
            checked.append((line, source, item))
            if line['accepted_quantity']:
                accepted_items.append(item['id'])
        now = tz.now_iso()
        delivery_id = conn.execute('''INSERT INTO supply_delivery
          (replenishment_id,supplier,dr_number,apr_number,procurement_mode,note,effective_date,
           received_by,received_at,operation_key) VALUES (?,?,?,?,?,?,?,?,?,?)''',
          (replenishment_id, *header.values(), user['id'], now, key)).lastrowid
        receipt_id = None
        if accepted_items:
            receipt_id = conn.execute('''INSERT INTO supply_receipt
              (supplier,dr_number,apr_number,procurement_mode,note,effective_date,
               received_by,recipient_snapshot,posted_at,operation_key,delivery_id)
              VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
              (*header.values(), user['id'], stock._actor_name(conn, user), now, key, delivery_id)).lastrowid
        for line, source, item in checked:
            receipt_line_id = None
            if line['accepted_quantity']:
                receipt_line_id = conn.execute('''INSERT INTO supply_receipt_line
                  (receipt_id,item_id,accepted_quantity,unit_cost,expiry_date,code_snapshot,
                   description_snapshot,unit_snapshot,replenishment_line_id)
                  VALUES (?,?,?,?,?,?,?,?,?)''',
                  (receipt_id,item['id'],line['accepted_quantity'],line['unit_cost'],line['expiry_date'],
                   item['code'],item['description'],item['unit'],source['id'])).lastrowid
                stock._add_movement(conn,user,item,kind='receipt',quantity=line['accepted_quantity'],
                                    effective_date=header['effective_date'],key=key,
                                    source_id=receipt_id,source_line_id=receipt_line_id,reason=header['note'])
                conn.execute('''UPDATE supply_replenishment_commitment
                  SET received_quantity=received_quantity+? WHERE line_id=?''',
                  (line['accepted_quantity'],source['id']))
            conn.execute('''INSERT INTO supply_delivery_line
              (delivery_id,replenishment_line_id,item_id,delivered_quantity,accepted_quantity,
               rejected_quantity,rejection_reason,unit_cost,expiry_date,receipt_line_id)
              VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (delivery_id,source['id'],item['id'],line['delivered_quantity'],line['accepted_quantity'],
               line['rejected_quantity'],line['rejection_reason'],line['unit_cost'],line['expiry_date'],receipt_line_id))
        status, remaining = sync_status(conn, replenishment_id, now=now)
        result = {'id': delivery_id, 'replenishment_id': replenishment_id, 'receipt_id': receipt_id,
                  'status': status, 'remaining_incoming': remaining,
                  'accepted_quantity': sum(line['accepted_quantity'] for line in lines),
                  'rejected_quantity': sum(line['rejected_quantity'] for line in lines)}
        record(conn,user,key,digest,'delivery_receive','delivery',result,payload)
        conn.execute('''INSERT INTO supply_event(entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
          VALUES ('replenishment',?,'delivery_receive',?,?,?,?)''',
          (replenishment_id,user['id'],json.dumps(result,sort_keys=True),now,key))
        if accepted_items:
            allocate_outstanding(conn,user,accepted_items,key)
        return result


def get_delivery(conn, user, replenishment_id, delivery_id):
    with stock._snapshot(conn):
        rep.get_replenishment(conn,user,replenishment_id)
        found = rows(conn, '''SELECT d.*,r.id AS receipt_id FROM supply_delivery d
          LEFT JOIN supply_receipt r ON r.delivery_id=d.id WHERE d.id=? AND d.replenishment_id=?''',
          (s.integer(delivery_id,'Delivery',1),s.integer(replenishment_id,'Replenishment',1)))
        if not found:
            raise Missing('Delivery not found or unavailable to you.')
        result=found[0]
        result['lines']=rows(conn, '''SELECT l.*,i.code_snapshot,i.unit_snapshot FROM supply_delivery_line l
          JOIN supply_replenishment_line i ON i.id=l.replenishment_line_id
          WHERE l.delivery_id=? ORDER BY l.id''',(delivery_id,))
        return result
