"""S1.2 immutable stock ledger, reviewed openings and accepted receipts."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import re

import supplies
import supplies_permissions as permissions
from supplies_storage import Conflict, Invalid, Missing, operation, record, rows, transaction
import tzutil as tz


MAX_TOTAL = 9223372036854775807


@contextmanager
def _snapshot(conn):
    """A multi-query read shares one snapshot without committing caller work."""
    owns = not conn.in_transaction
    if owns:
        conn.execute('BEGIN')
    try:
        yield
    finally:
        if owns:
            conn.rollback()


def _date(value, label, *, optional=False):
    if optional and value in ('', None):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise Invalid(f'{label} must be a valid date (YYYY-MM-DD).')
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise Invalid(f'{label} must be a valid date (YYYY-MM-DD).') from exc
    return value


def _effective_date(value):
    value = _date(value, 'Receipt/count date')
    if value > tz.today_local().isoformat():
        raise Invalid('Receipt/count date cannot be in the future.')
    return value


def _optional_text(value, label, limit):
    return '' if value in ('', None) else supplies.text(value, label, limit)


def unit_cost(value):
    if value in ('', None):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,9}(?:\.\d{1,4})?', value):
        raise Invalid('Unit cost must be a nonnegative decimal with at most four decimal places (maximum 999999999.9999).')
    return format(Decimal(value).quantize(Decimal('0.0001')), 'f')


def _totals(conn, item_id):
    count, total = conn.execute('''SELECT COUNT(*),COALESCE(SUM(quantity_delta),0)
      FROM supply_stock_movement WHERE item_id=?''', (item_id,)).fetchone()
    return {'on_hand': total, 'recorded': bool(count), 'movement_count': count}


def stock_totals(conn, user, item_id):
    with _snapshot(conn):
        supplies.get_item(conn, user, item_id)
        return _totals(conn, item_id)


def _posting_item(conn, item_id, expected_revision):
    item_id = supplies.integer(item_id, 'Item', 1)
    item = supplies._item(conn, item_id)
    if not item['active']:
        raise Conflict('This item is inactive. Choose an active item.')
    if item['revision'] != supplies.integer(expected_revision, 'Item revision', 1):
        raise Conflict('This catalog item changed. Reload the form and confirm its unit before posting.')
    return item


def _actor_name(conn, user):
    found = conn.execute('SELECT name FROM resource_person WHERE id=?', (user.get('rp_id'),)).fetchone()
    return found[0] if found and found[0] else user['username']


def _add_movement(conn, user, item, *, kind, quantity, effective_date, key,
                  source_id, source_line_id=None, reason=''):
    total = _totals(conn, item['id'])['on_hand']
    if not 0 <= total + quantity <= MAX_TOTAL:
        raise Invalid('The resulting stock quantity is outside the supported range.')
    return conn.execute('''INSERT INTO supply_stock_movement
      (item_id,kind,quantity_delta,effective_date,posted_at,posted_by,actor_snapshot,
       source_type,source_id,source_line_id,receipt_line_id,reason,code_snapshot,
       description_snapshot,unit_snapshot,operation_key)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (item['id'], kind, quantity, effective_date, tz.now_iso(), user['id'], _actor_name(conn, user),
       kind, source_id, source_line_id, source_line_id if kind == 'receipt' else None, reason,
       item['code'], item['description'], item['unit'], key)).lastrowid


def _post_opening(conn, user, item, *, quantity, effective_date, key, reason,
                  source_id=None, source_line_id=None):
    """Transaction-neutral posting shared by standalone and atomic batch openings."""
    if _totals(conn, item['id'])['recorded']:
        raise Conflict('Opening stock can only be recorded on an empty item ledger.')
    return _add_movement(conn, user, item, kind='opening', quantity=quantity,
                         effective_date=effective_date, key=key,
                         source_id=item['id'] if source_id is None else source_id,
                         source_line_id=source_line_id, reason=reason)


def post_opening(conn, user, item_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        supplies.require_enabled(conn)
        item_id = supplies.integer(item_id, 'Item', 1)
        quantity = supplies.integer(fields.get('quantity'), 'Opening quantity')
        effective = _effective_date(fields.get('effective_date'))
        reason = supplies.text(fields.get('reason'), 'Physical-count basis', 2000)
        revision = supplies.integer(expected_revision, 'Item revision', 1)
        payload = {'item_id': item_id, 'quantity': quantity, 'effective_date': effective,
                   'reason': reason, 'revision': revision}
        key, digest, prior = operation(conn, user, operation_key, 'opening_post', payload)
        if prior is not None:
            return prior
        item = _posting_item(conn, item_id, revision)
        movement_id = _post_opening(conn, user, item, quantity=quantity,
                                    effective_date=effective, key=key, reason=reason)
        result = {'id': item_id, 'item_id': item_id, 'movement_id': movement_id, 'on_hand': quantity}
        record(conn, user, key, digest, 'opening_post', 'item', result, payload)
        from supplies_allocations import allocate_outstanding
        allocate_outstanding(conn, user, [item_id], key)
        return result


def _receipt_fields(fields):
    header = {'supplier': supplies.text(fields.get('supplier'), 'Supplier', 240),
              'dr_number': _optional_text(fields.get('dr_number'), 'DR number', 120),
              'apr_number': _optional_text(fields.get('apr_number'), 'APR number', 120),
              'procurement_mode': _optional_text(fields.get('procurement_mode'), 'Procurement mode', 120),
              'note': _optional_text(fields.get('note'), 'Receipt note', 2000),
              'effective_date': _effective_date(fields.get('effective_date'))}
    raw_lines = fields.get('lines')
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 20:
        raise Invalid('A receipt needs 1–20 item lines.')
    lines = []
    for line in raw_lines:
        if not isinstance(line, dict):
            raise Invalid('Each receipt line must identify an item and accepted quantity.')
        lines.append({'item_id': supplies.integer(line.get('item_id'), 'Receipt item', 1),
                      'expected_revision': supplies.integer(line.get('expected_revision'), 'Item revision', 1),
                      'accepted_quantity': supplies.integer(line.get('accepted_quantity'), 'Accepted quantity', 1),
                      'unit_cost': unit_cost(line.get('unit_cost')),
                      'expiry_date': _date(line.get('expiry_date'), 'Expiry date', optional=True)})
    return header, lines


def post_receipt(conn, user, fields, *, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        supplies.require_enabled(conn)
        header, lines = _receipt_fields(fields)
        key, digest, prior = operation(conn, user, operation_key, 'receipt_post', {'header': header, 'lines': lines})
        if prior is not None:
            return prior
        items = [_posting_item(conn, line['item_id'], line['expected_revision']) for line in lines]
        # Validate everything before any posting. Same-item lines may have different cost/expiry metadata.
        receipt_id = conn.execute('''INSERT INTO supply_receipt
          (supplier,dr_number,apr_number,procurement_mode,note,effective_date,
           received_by,recipient_snapshot,posted_at,operation_key) VALUES (?,?,?,?,?,?,?,?,?,?)''',
          (*header.values(), user['id'], _actor_name(conn, user), tz.now_iso(), key)).lastrowid
        for line, item in zip(lines, items):
            line_id = conn.execute('''INSERT INTO supply_receipt_line
              (receipt_id,item_id,accepted_quantity,unit_cost,expiry_date,code_snapshot,description_snapshot,unit_snapshot)
              VALUES (?,?,?,?,?,?,?,?)''', (receipt_id, item['id'], line['accepted_quantity'], line['unit_cost'],
                line['expiry_date'], item['code'], item['description'], item['unit'])).lastrowid
            _add_movement(conn, user, item, kind='receipt', quantity=line['accepted_quantity'],
                          effective_date=header['effective_date'], key=key,
                          source_id=receipt_id, source_line_id=line_id, reason=header['note'])
        result = _receipt(conn, receipt_id)
        record(conn, user, key, digest, 'receipt_post', 'receipt', result, {'header': header, 'lines': lines})
        from supplies_allocations import allocate_outstanding
        allocate_outstanding(conn, user, [item['id'] for item in items], key)
        return result


def _receipt(conn, receipt_id):
    found = rows(conn, 'SELECT * FROM supply_receipt WHERE id=?', (receipt_id,))
    if not found:
        raise Missing('Receipt not found or unavailable to you.')
    result = found[0]
    result['receipt_number'] = f"RCV-{result['id']:06d}"
    result['lines'] = rows(conn, 'SELECT * FROM supply_receipt_line WHERE receipt_id=? ORDER BY id', (receipt_id,))
    return result


def get_receipt(conn, user, receipt_id):
    with _snapshot(conn):
        permissions.require_stock_reader(conn, user)
        return _receipt(conn, receipt_id)


def list_receipts(conn, user, *, page=1):
    with _snapshot(conn):
        permissions.require_stock_reader(conn, user)
        page = supplies.integer(page, 'Page', 1)
        items = rows(conn, '''SELECT id,supplier,dr_number,effective_date,posted_at FROM supply_receipt
          ORDER BY id DESC LIMIT 51 OFFSET ?''', ((page - 1) * 50,))
        for receipt in items:
            receipt['receipt_number'] = f"RCV-{receipt['id']:06d}"
        return {'receipts': items[:50], 'has_next': len(items) > 50, 'page': page}


def stock_card(conn, user, item_id, *, page=1):
    with _snapshot(conn):
        permissions.require_stock_reader(conn, user)
        item = supplies.get_item(conn, user, item_id)
        page = supplies.integer(page, 'Page', 1)
        totals = _totals(conn, item_id)
        movements = rows(conn, '''WITH card AS (
          SELECT m.*,SUM(m.quantity_delta) OVER (ORDER BY m.id ROWS UNBOUNDED PRECEDING) AS balance
          FROM supply_stock_movement m WHERE m.item_id=?)
          SELECT card.*,l.unit_cost,l.expiry_date,r.dr_number,r.supplier
          FROM card LEFT JOIN supply_receipt_line l ON l.id=card.receipt_line_id
          LEFT JOIN supply_receipt r ON r.id=l.receipt_id ORDER BY card.id LIMIT 50 OFFSET ?''',
          (item_id, (page - 1) * 50))
        return {'item': item, **totals, 'movements': movements, 'page': page,
                'has_next': page * 50 < totals['movement_count']}
