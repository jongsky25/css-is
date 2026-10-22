"""S5.1 stock suggestions and custodian-owned replenishment drafts."""
import supplies as s
import supplies_permissions as permissions
import supplies_stock as stock
import tzutil as tz
from supplies_storage import Conflict, Denied, Invalid, Missing, operation, record, rows, transaction

MAX_LINES = 20


def _summary(conn, item):
    item_id = item['id']
    on_hand = conn.execute('SELECT COALESCE(SUM(quantity_delta),0) FROM supply_stock_movement WHERE item_id=?', (item_id,)).fetchone()[0]
    reserved = conn.execute('SELECT COALESCE(SUM(reserved_quantity),0) FROM supply_reservation WHERE item_id=?', (item_id,)).fetchone()[0]
    outstanding = conn.execute('''SELECT COALESCE(SUM(d.approved_quantity-r.effective_issued_quantity-r.cancelled_quantity),0)
      FROM supply_reservation r JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
      WHERE r.item_id=?''', (item_id,)).fetchone()[0]
    incoming = conn.execute('''SELECT COALESCE(SUM(c.approved_quantity-c.received_quantity-c.cancelled_quantity),0)
      FROM supply_replenishment_commitment c JOIN supply_replenishment_line l ON l.id=c.line_id
      JOIN supply_replenishment p ON p.id=l.replenishment_id
      WHERE l.item_id=? AND p.status IN ('approved','ordered','partially_received')''', (item_id,)).fetchone()[0]
    open_records = rows(conn, '''SELECT p.id,p.control_number,p.status,l.requested_quantity
      FROM supply_replenishment_line l JOIN supply_replenishment p ON p.id=l.replenishment_id
      WHERE l.item_id=? AND p.status IN ('draft','submitted','returned','approved','ordered','partially_received')
      ORDER BY p.id''', (item_id,))
    available = on_hand-reserved
    target = item['target_level']
    suggested = None if target is None else max(0, target+outstanding-on_hand-incoming)
    attention = on_hand == 0 or available < item['critical_level'] or outstanding > reserved
    explanation = ('Set target or enter quantity' if target is None else
                   'Approved incoming already covers the target and outstanding demand.' if suggested == 0 and incoming else
                   'Target and outstanding demand are already covered.' if suggested == 0 else '')
    return {**item, 'on_hand': on_hand, 'reserved': reserved, 'available': available,
            'outstanding': outstanding, 'incoming': incoming, 'suggested': suggested,
            'attention': attention, 'explanation': explanation, 'open_records': open_records}


def suggest_replenishment(conn, user, item_id=None):
    with stock._snapshot(conn):
        permissions.require_stock_reader(conn, user)
        if item_id is None:
            items = rows(conn, 'SELECT * FROM supply_item WHERE active=1 ORDER BY code,id')
            return [_summary(conn, item) for item in items]
        item = s._item(conn, s.integer(item_id, 'Item', 1))
        if not item['active']:
            raise Missing('Active item not found.')
        return _summary(conn, item)


def _draft(conn, user, replenishment_id):
    found = rows(conn, 'SELECT * FROM supply_replenishment WHERE id=? AND prepared_by=?',
                 (s.integer(replenishment_id, 'Replenishment', 1), user['id']))
    if not found:
        raise Missing('Replenishment draft not found or unavailable to you.')
    return found[0]


def get_replenishment(conn, user, replenishment_id):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn, user)
        found = rows(conn, 'SELECT * FROM supply_replenishment WHERE id=?',
                     (s.integer(replenishment_id, 'Replenishment', 1),))
        if not found:
            raise Missing('Replenishment not found or unavailable to you.')
        result = found[0]
        if (result['prepared_by'] != user['id'] and
            not permissions.has_role(conn, user, 'auditor') and
            not (result['status'] not in ('draft','returned') and permissions.has_role(conn, user, 'custodian')) and
            not (result['status'] != 'draft' and permissions.has_role(conn, user, 'replenishment_approver'))):
            raise Missing('Replenishment not found or unavailable to you.')
        historical_return = (result['status']=='returned' and result['prepared_by']!=user['id'] and
                             not permissions.has_role(conn,user,'auditor'))
        if historical_return:
            historical=rows(conn,'''SELECT * FROM supply_replenishment_revision
              WHERE replenishment_id=? ORDER BY revision DESC LIMIT 1''',(result['id'],))[0]
            result['purpose']=historical['purpose']
            result['procurement_reference']=historical['procurement_reference']
            result['expected_need_date']=historical['expected_need_date']
            result['lines']=rows(conn,'''SELECT l.*,NULL AS approved_quantity,NULL AS received_quantity,
              NULL AS cancelled_quantity,NULL AS ordered_quantity FROM supply_replenishment_revision_line l
              WHERE l.revision_id=? ORDER BY l.id''',(historical['id'],))
        else:
            result['lines'] = rows(conn, '''SELECT l.*,c.approved_quantity,c.received_quantity,c.cancelled_quantity,
              ol.ordered_quantity FROM supply_replenishment_line l
              LEFT JOIN supply_replenishment_commitment c ON c.line_id=l.id
              LEFT JOIN supply_replenishment_order_line ol ON ol.line_id=l.id
              WHERE l.replenishment_id=? ORDER BY l.id''', (result['id'],))
        for line in result['lines']:
            line['incoming_quantity'] = ((line['approved_quantity'] or 0) - (line['received_quantity'] or 0) -
                                         (line['cancelled_quantity'] or 0))
        result['submissions'] = rows(conn, '''SELECT * FROM supply_replenishment_revision
          WHERE replenishment_id=? ORDER BY revision DESC''', (result['id'],))
        result['decisions'] = rows(conn, '''SELECT d.*,u.username AS actor_name FROM supply_replenishment_decision d
          JOIN admin_user u ON u.id=d.decided_by WHERE d.replenishment_id=? ORDER BY d.id DESC''', (result['id'],))
        result['order'] = next(iter(rows(conn, 'SELECT * FROM supply_replenishment_order WHERE replenishment_id=?', (result['id'],))), None)
        result['cancellations'] = rows(conn, '''SELECT * FROM supply_replenishment_cancellation
          WHERE replenishment_id=? ORDER BY id DESC''', (result['id'],))
        result['deliveries'] = rows(conn, '''SELECT d.id,d.supplier,d.dr_number,d.effective_date,d.received_at,
          r.id AS receipt_id,COALESCE(SUM(l.accepted_quantity),0) AS accepted_quantity,
          COALESCE(SUM(l.rejected_quantity),0) AS rejected_quantity
          FROM supply_delivery d JOIN supply_delivery_line l ON l.delivery_id=d.id
          LEFT JOIN supply_receipt r ON r.delivery_id=d.id
          WHERE d.replenishment_id=? GROUP BY d.id ORDER BY d.id DESC''', (result['id'],))
        latest = result['submissions'][0] if result['submissions'] else None
        result['submitted_lines'] = rows(conn, '''SELECT * FROM supply_replenishment_revision_line
          WHERE revision_id=? ORDER BY id''', (latest['id'],)) if latest else []
        return result


def list_replenishments(conn, user):
    with stock._snapshot(conn):
        user = permissions.require_actor(conn, user)
        if permissions.has_role(conn, user, 'auditor'):
            where, args = '1=1', ()
        elif permissions.has_role(conn, user, 'custodian'):
            where, args = "(prepared_by=? OR status NOT IN ('draft','returned'))", (user['id'],)
        elif permissions.has_role(conn, user, 'replenishment_approver'):
            where, args = "status<>'draft'", ()
        else:
            raise Denied('A replenishment grant is required.')
        return rows(conn, '''SELECT p.id,p.control_number,p.prepared_by,p.status,p.revision,p.current_revision,
          CASE WHEN p.status='returned' AND p.prepared_by<>? THEN
            (SELECT v.purpose FROM supply_replenishment_revision v WHERE v.replenishment_id=p.id
              ORDER BY v.revision DESC LIMIT 1) ELSE p.purpose END AS purpose
          FROM supply_replenishment p WHERE '''+where+' ORDER BY p.id DESC LIMIT 100', (user['id'],*args))


def _fields(fields):
    if not isinstance(fields, dict):
        raise Invalid('Replenishment fields are required.')
    purpose = s.text(fields.get('purpose'), 'Purpose', 2000)
    reference = stock._optional_text(fields.get('procurement_reference'), 'Procurement reference', 120)
    needed = stock._date(fields.get('expected_need_date'), 'Expected need date', optional=True)
    raw = fields.get('lines')
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LINES:
        raise Invalid('A replenishment draft needs 1–20 item lines.')
    lines = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise Invalid('Each replenishment line needs an item and quantity.')
        item_id = s.integer(entry.get('item_id'), 'Item', 1)
        if item_id in seen:
            raise Invalid('Each item may appear only once in a replenishment draft.')
        seen.add(item_id)
        lines.append({'item_id': item_id,
                      'requested_quantity': s.integer(entry.get('requested_quantity'), 'Requested quantity', 1),
                      'intended_target': s.integer(entry.get('intended_target'), 'Intended stock target'),
                      'estimated_unit_cost': stock.unit_cost(entry.get('estimated_unit_cost')),
                      'override_reason': stock._optional_text(entry.get('override_reason'), 'Quantity reason', 2000)})
    return {'purpose': purpose, 'procurement_reference': reference, 'expected_need_date': needed,
            'lines': sorted(lines, key=lambda line: line['item_id'])}


def save_replenishment(conn, user, fields, *, operation_key, replenishment_id=None, expected_revision=None):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        values = _fields(fields)
        revision = None if replenishment_id is None else s.integer(expected_revision, 'Replenishment revision', 1)
        payload = {'id': replenishment_id, 'revision': revision, **values}
        key, digest, prior = operation(conn, user, operation_key, 'replenishment_save', payload)
        if prior is not None:
            return prior
        lines = []
        for line in values['lines']:
            item = s._item(conn, line['item_id'])
            if not item['active']:
                raise Conflict('An item is inactive. Choose an active catalog item.')
            if line['intended_target'] < item['critical_level']:
                raise Invalid('Intended stock target must be at least the critical level.')
            summary = _summary(conn, item)
            # The configured target drives the catalog suggestion. A different
            # planning target or quantity is an explicit, justified override.
            basis = max(0, line['intended_target']+summary['outstanding']-summary['on_hand']-summary['incoming'])
            if ((summary['target_level'] is not None and line['intended_target'] != summary['target_level']) or
                line['requested_quantity'] != basis) and not line['override_reason']:
                raise Invalid('Explain a changed stock target or requested quantity.')
            lines.append((line, item, summary))
        now = tz.now_iso()
        if replenishment_id is None:
            replenishment_id = conn.execute('''INSERT INTO supply_replenishment
              (prepared_by,purpose,procurement_reference,expected_need_date,created_at,updated_at)
              VALUES (?,?,?,?,?,?)''', (user['id'],values['purpose'],values['procurement_reference'],
                                      values['expected_need_date'],now,now)).lastrowid
        else:
            draft = _draft(conn, user, replenishment_id)
            if draft['status'] not in ('draft','returned') or draft['revision'] != revision:
                raise Conflict('This replenishment changed. Reload the draft before saving.')
            conn.execute('''UPDATE supply_replenishment SET purpose=?,procurement_reference=?,expected_need_date=?,
              revision=revision+1,updated_at=? WHERE id=?''',
              (values['purpose'],values['procurement_reference'],values['expected_need_date'],now,replenishment_id))
            conn.execute('DELETE FROM supply_replenishment_line WHERE replenishment_id=?', (replenishment_id,))
        for line,item,summary in lines:
            conn.execute('''INSERT INTO supply_replenishment_line
              (replenishment_id,item_id,code_snapshot,description_snapshot,unit_snapshot,requested_quantity,
               estimated_unit_cost,override_reason,intended_target,suggested_quantity,on_hand_snapshot,
               reserved_snapshot,outstanding_snapshot,incoming_snapshot)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (replenishment_id,item['id'],item['code'],item['description'],item['unit'],line['requested_quantity'],
               line['estimated_unit_cost'],line['override_reason'],line['intended_target'],summary['suggested'],
               summary['on_hand'],summary['reserved'],summary['outstanding'],summary['incoming']))
        current = conn.execute('SELECT revision,status FROM supply_replenishment WHERE id=?', (replenishment_id,)).fetchone()
        result = {'id': replenishment_id, 'revision': current[0], 'status': current[1]}
        return record(conn,user,key,digest,'replenishment_save','replenishment',result,
                      {'purpose': values['purpose'], 'procurement_reference': values['procurement_reference'],
                       'expected_need_date': values['expected_need_date'],
                       'lines': [{**line, 'suggested_quantity': summary['suggested'],
                                  'on_hand': summary['on_hand'], 'reserved': summary['reserved'],
                                  'outstanding': summary['outstanding'], 'incoming': summary['incoming']}
                                 for line, _item, summary in lines]})
