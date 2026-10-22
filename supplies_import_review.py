"""Explicit reconciliation and atomic adoption of staged workbook evidence."""
import hashlib
import json
import sqlite3

import supplies as s
import supplies_permissions as permissions
import supplies_stock as stock
import tzutil as tz
from supplies_storage import Conflict, Invalid, Missing, operation, record, rows, transaction


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _batch(conn, batch_id):
    found = rows(conn, 'SELECT * FROM supply_import_batch WHERE id=?', (s.integer(batch_id, 'Batch', 1),))
    if not found:
        raise Missing('Workbook preview not found.')
    return found[0]


def _editable(batch, revision):
    if batch['status'] == 'applied':
        raise Conflict('This batch has already been applied.')
    if batch['revision'] != s.integer(revision, 'Review revision', 1):
        raise Conflict('The review changed. Reload and check the current decisions.')


def decisions(conn, batch_id):
    found = rows(conn, """SELECT r.row_id,r.detail_json FROM supply_import_review r
      WHERE r.batch_id=? AND r.kind='decision' AND r.id=(SELECT MAX(x.id)
        FROM supply_import_review x WHERE x.batch_id=r.batch_id AND x.row_id=r.row_id AND x.kind='decision')""", (batch_id,))
    return {r['row_id']: json.loads(r['detail_json']) for r in found}


def review_state(conn, user, batch_id):
    permissions.require_stock_reader(conn, user)
    batch = _batch(conn, batch_id)
    latest = rows(conn, "SELECT detail_json FROM supply_import_review WHERE batch_id=? AND kind=? ORDER BY id DESC LIMIT 1",
                  (batch_id, 'apply' if batch['status'] == 'applied' else 'finalize'))
    return {'decisions': decisions(conn, batch_id),
            'selection': json.loads(latest[0]['detail_json']) if latest and batch['status'] != 'preview' else None,
            'items': rows(conn, 'SELECT id,code,description,unit,revision FROM supply_item WHERE active=1 ORDER BY code')}


def _save(conn, user, batch, kind, detail, key, digest, row_id=None):
    revision = batch['revision'] + 1
    status = {'decision': 'preview', 'finalize': 'reviewed', 'apply': 'applied'}[kind]
    conn.execute('UPDATE supply_import_batch SET status=?,revision=? WHERE id=?', (status, revision, batch['id']))
    conn.execute('''INSERT INTO supply_import_review
      (batch_id,row_id,revision,kind,detail_json,actor_id,created_at,operation_key) VALUES (?,?,?,?,?,?,?,?)''',
      (batch['id'], row_id, revision, kind, _json(detail), user['id'], tz.now_iso(), key))
    result = {'id': batch['id'], 'revision': revision, 'status': status}
    return record(conn, user, key, digest, 'import_' + kind, 'import', result, detail)


def _validate_target(conn, decision):
    if decision['decision'] == 'exclude':
        return
    values = decision['item']
    if decision['item_id'] is not None:
        item = stock._posting_item(conn, decision['item_id'], decision['item_revision'])
        if any(item[k] != values[k] for k in ('code', 'description', 'unit')):
            raise Conflict('The mapped catalog identity changed. Review its canonical unit again.')
        if stock._totals(conn, item['id'])['recorded']:
            raise Conflict('An included item already has stock history; the entire batch was rejected.')
    elif conn.execute('SELECT 1 FROM supply_item WHERE code=? COLLATE NOCASE', (values['code'],)).fetchone():
        raise Conflict('A new item code already exists. Map the row to the catalog item explicitly.')


def save_decision(conn, user, batch_id, row_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        batch = _batch(conn, batch_id)
        row_id = s.integer(row_id, 'Source row', 1)
        # Key the submitted intent before looking up mutable catalog state.
        payload = {'batch_id': batch['id'], 'row_id': row_id,
                   'revision': s.integer(expected_revision, 'Review revision', 1),
                   'fields': {k: fields.get(k) for k in ('decision', 'reason', 'quantity', 'item_choice',
                       'code', 'description', 'unit', 'critical_level', 'target_level')}}
        key, digest, prior = operation(conn, user, operation_key, 'import_decision', payload)
        if prior is not None:
            return prior
        _editable(batch, expected_revision)
        choice = fields.get('decision')
        if choice not in ('include', 'exclude'):
            raise Invalid('Explicitly include or exclude this row.')
        detail = {'row_id': row_id, 'decision': choice,
                  'reason': s.text(fields.get('reason'), 'Count, unit reconciliation or exclusion reason', 2000)}
        if choice == 'include':
            detail['quantity'] = s.integer(fields.get('quantity'), 'Physical count')
            target = fields.get('item_choice', 'new')
            if target == 'new':
                detail.update(item_id=None, item_revision=None, item=s.item_fields(fields))
            else:
                parts = str(target).split(':')
                if len(parts) != 2:
                    raise Invalid('Choose a current catalog item or create a new item.')
                item = stock._posting_item(conn, parts[0], parts[1])
                values = s.item_fields({**item, 'critical_level': fields.get('critical_level'),
                                       'target_level': fields.get('target_level')})
                detail.update(item_id=item['id'], item_revision=item['revision'], item=values)
        if not conn.execute('SELECT 1 FROM supply_import_row WHERE id=? AND batch_id=?', (row_id, batch['id'])).fetchone():
            raise Missing('Source row does not belong to this batch.')
        _validate_target(conn, detail)
        return _save(conn, user, batch, 'decision', detail, key, digest, row_id)


def finalize(conn, user, batch_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        s.require_enabled(conn)
        batch = _batch(conn, batch_id)
        payload = {'batch_id': batch['id'], 'revision': s.integer(expected_revision, 'Review revision', 1),
                   'count_date': stock._effective_date(fields.get('count_date')),
                   'basis': s.text(fields.get('basis'), 'Physical count and cutover basis', 2000)}
        if fields.get('confirmed') != 'yes':
            raise Invalid('Confirm that counts use the canonical units at the stated cutover date.')
        key, digest, prior = operation(conn, user, operation_key, 'import_finalize', payload)
        if prior is not None:
            return prior
        _editable(batch, expected_revision)
        selected = decisions(conn, batch['id'])
        source = rows(conn, 'SELECT id,source_sheet,source_row FROM supply_import_row WHERE batch_id=? ORDER BY id', (batch['id'],))
        if not source or set(selected) != {r['id'] for r in source}:
            raise Invalid('Every source row needs an explicit include or exclude decision.')
        codes, targets, accepted = set(), set(), []
        for row in source:
            decision = selected[row['id']]
            _validate_target(conn, decision)
            if decision['decision'] == 'include':
                code = decision['item']['code'].upper()
                target = decision['item_id']
                if code in codes or (target is not None and target in targets):
                    raise Invalid('Included rows must map to distinct catalog items and item codes.')
                codes.add(code); targets.add(target)
                accepted.append(decision)
        if not accepted:
            raise Invalid('Include at least one reconciled item before finalizing.')
        detail = {**payload, 'source_sha256': batch['source_sha256'],
                  'rows': [{**selected[r['id']], 'source_sheet': r['source_sheet'], 'source_row': r['source_row']} for r in source],
                  'included_count': len(accepted), 'excluded_count': len(source)-len(accepted)}
        detail['selection_sha256'] = hashlib.sha256(_json(detail).encode()).hexdigest()
        return _save(conn, user, batch, 'finalize', detail, key, digest)


def apply(conn, user, batch_id, *, expected_revision, selection_sha256, operation_key):
    try:
        with transaction(conn):
            user = permissions.require_custodian(conn, user)
            s.require_enabled(conn)
            batch = _batch(conn, batch_id)
            payload = {'batch_id': batch['id'], 'revision': s.integer(expected_revision, 'Review revision', 1),
                       'selection_sha256': s.text(selection_sha256, 'Final review identifier', 64)}
            key, digest, prior = operation(conn, user, operation_key, 'import_apply', payload)
            if prior is not None:
                return prior
            _editable(batch, expected_revision)
            if batch['status'] != 'reviewed':
                raise Conflict('Finalize all row decisions before applying this batch.')
            review = rows(conn, "SELECT detail_json FROM supply_import_review WHERE batch_id=? AND revision=? AND kind='finalize'",
                          (batch['id'], batch['revision']))
            if not review:
                raise Conflict('The finalized selection is unavailable. Review the batch again.')
            detail = json.loads(review[0]['detail_json'])
            if detail['selection_sha256'] != selection_sha256:
                raise Conflict('The finalized selection changed. Reload the review.')
            if conn.execute("SELECT 1 FROM supply_import_batch WHERE source_sha256=? AND status='applied'", (batch['source_sha256'],)).fetchone():
                raise Conflict('This source workbook has already been applied in another batch.')
            for decision in detail['rows']:
                _validate_target(conn, decision)
            now = tz.now_iso()
            posted = []
            for decision in detail['rows']:
                if decision['decision'] == 'exclude':
                    continue
                values = decision['item']
                item_id = decision['item_id']
                if item_id is None:
                    item_id = conn.execute('''INSERT INTO supply_item
                      (code,description,unit,critical_level,target_level,created_by,created_at,updated_at)
                      VALUES (?,?,?,?,?,?,?,?)''', (*[values[k] for k in ('code','description','unit','critical_level','target_level')], user['id'], now, now)).lastrowid
                else:
                    conn.execute('UPDATE supply_item SET critical_level=?,target_level=?,revision=revision+1,updated_at=? WHERE id=?',
                                 (values['critical_level'], values['target_level'], now, item_id))
                item = s._item(conn, item_id)
                movement_id = stock._post_opening(conn, user, item, quantity=decision['quantity'],
                    effective_date=detail['count_date'], key=key, source_id=batch['id'], source_line_id=decision['row_id'],
                    reason=decision['reason'])
                posted.append({'row_id': decision['row_id'], 'item_id': item_id, 'movement_id': movement_id, 'quantity': decision['quantity']})
            result = _save(conn, user, batch, 'apply', {**detail, 'posted': posted}, key, digest)
            from supplies_allocations import allocate_outstanding
            allocate_outstanding(conn, user, [posting['item_id'] for posting in posted], key)
            for posting in posted:
                conn.execute('''INSERT INTO supply_event
                  (entity_type,entity_id,action,actor_id,detail_json,created_at,operation_key)
                  VALUES ('item',?,'import_opening',?,?,?,?)''',
                  (posting['item_id'], user['id'], _json({**posting, 'batch_id': batch['id'],
                   'source_sha256': batch['source_sha256'], 'selection_sha256': selection_sha256}), now, key))
            return result
    except sqlite3.IntegrityError as exc:
        raise Conflict('An import target changed. The entire batch was rolled back; reload and review.') from exc
