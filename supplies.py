"""Supplies catalog and configuration; stock posting lives in supplies_stock."""
import re
import sqlite3

import storage as st
import tzutil as tz
import supplies_permissions as permissions
from supplies_storage import (Conflict, Denied, Disabled, Invalid, Missing,
                             operation, record, rows, transaction)


def enabled(conn):
    return st.get_setting(conn, 'supplies.enabled', '0') == '1'


def require_enabled(conn):
    if not enabled(conn):
        raise Disabled('Supplies changes are disabled. Existing catalog records remain readable.')


def integer(value, label, minimum=0):
    if type(value) not in (str, int) or not re.fullmatch(r'[0-9]+', str(value)):
        raise Invalid(f'{label} must be a whole number.')
    if len(str(value)) > 10 or not minimum <= int(value) <= 2147483647:
        raise Invalid(f'{label} must be between {minimum} and 2,147,483,647.')
    return int(value)


def text(value, label, limit):
    if not isinstance(value, str):
        raise Invalid(f'{label} is required.')
    value = value.strip()
    if not 1 <= len(value) <= limit or any(ord(c) < 32 for c in value):
        raise Invalid(f'{label} must contain 1–{limit} characters without control characters.')
    return value


def item_fields(fields):
    code = text(fields.get('code'), 'Item code', 40).upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]*', code):
        raise Invalid('Item code must use letters, numbers, dots, slashes, hyphens or underscores.')
    critical = integer(fields.get('critical_level', '0'), 'Critical level')
    raw_target = fields.get('target_level')
    target = None if raw_target in ('', None) else integer(raw_target, 'Target level')
    if target is not None and target < critical:
        raise Invalid('Target level must be at least the critical level.')
    return {'code': code, 'description': text(fields.get('description'), 'Description', 240),
            'unit': text(fields.get('unit'), 'Unit', 40), 'critical_level': critical, 'target_level': target}


def _item(conn, item_id):
    found = rows(conn, 'SELECT * FROM supply_item WHERE id=?', (item_id,))
    if not found:
        raise Missing('Item not found or unavailable to you.')
    return found[0]


def get_item(conn, user, item_id):
    user = permissions.require_actor(conn, user)
    item = _item(conn, item_id)
    if not item['active'] and not (permissions.has_role(conn, user, 'custodian') or
                                    permissions.has_role(conn, user, 'auditor')):
        raise Missing('Item not found or unavailable to you.')
    return item


def catalog(conn, user, *, query='', include_inactive=False, page=1):
    user = permissions.require_actor(conn, user)
    page = integer(page, 'Page', 1)
    if not isinstance(query, str) or len(query) > 200:
        raise Invalid('Search must contain at most 200 characters.')
    include_inactive = bool(include_inactive and
        (permissions.has_role(conn, user, 'custodian') or permissions.has_role(conn, user, 'auditor')))
    where, args = [], []
    if not include_inactive:
        where.append('active=1')
    if query.strip():
        # Literal substring matching, not SQL LIKE wildcards from input.
        where.append('(instr(lower(code),lower(?))>0 OR instr(lower(description),lower(?))>0)')
        args.extend([query.strip(), query.strip()])
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''
    count = conn.execute('SELECT COUNT(*) FROM supply_item' + clause, args).fetchone()[0]
    items = rows(conn, '''SELECT supply_item.*,COALESCE(stock.on_hand,0) AS on_hand,
      COALESCE(stock.movement_count,0) AS movement_count FROM supply_item LEFT JOIN (
        SELECT item_id,SUM(quantity_delta) AS on_hand,COUNT(*) AS movement_count
        FROM supply_stock_movement GROUP BY item_id) stock ON stock.item_id=supply_item.id'''
        + clause + ' ORDER BY code,supply_item.id LIMIT 50 OFFSET ?',
                 (*args, (page - 1) * 50))
    return {'items': items, 'count': count, 'page': page, 'has_next': page * 50 < count,
            'query': query, 'include_inactive': include_inactive}


def create_item(conn, user, fields, *, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        require_enabled(conn)
        values = item_fields(fields)
        key, digest, prior = operation(conn, user, operation_key, 'item_create', values)
        if prior is not None:
            return prior
        now = tz.now_iso()
        try:
            item_id = conn.execute('''INSERT INTO supply_item
              (code,description,unit,critical_level,target_level,created_by,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?)''', (*values.values(), user['id'], now, now)).lastrowid
        except sqlite3.IntegrityError as exc:
            raise Conflict('That item code already exists. Choose another code.') from exc
        result = _item(conn, item_id)
        return record(conn, user, key, digest, 'item_create', 'item', result, values)


def update_item(conn, user, item_id, fields, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        require_enabled(conn)
        values = item_fields(fields)
        revision = integer(expected_revision, 'Revision', 1)
        key, digest, prior = operation(conn, user, operation_key, 'item_update',
                                       {'id': item_id, 'revision': revision, **values})
        if prior is not None:
            return prior
        before = _item(conn, item_id)
        if revision != before['revision']:
            raise Conflict('This item changed. Reload it before saving.')
        # S1.2 installs this table. Never change units once a movement exists.
        if values['unit'] != before['unit'] and conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='supply_stock_movement'").fetchone():
            if conn.execute('SELECT 1 FROM supply_stock_movement WHERE item_id=? LIMIT 1', (item_id,)).fetchone():
                raise Conflict('The unit is fixed after stock posting. Create a separate item for a different unit.')
            if conn.execute('''SELECT 1 FROM supply_reservation r
              JOIN supply_request_decision_line d ON d.revision_line_id=r.revision_line_id
              WHERE r.item_id=? AND d.approved_quantity>r.effective_issued_quantity+r.cancelled_quantity LIMIT 1''', (item_id,)).fetchone():
                raise Conflict('The unit is fixed while approved demand remains outstanding. Use a separate item for a different unit.')
        try:
            conn.execute('''UPDATE supply_item SET code=?,description=?,unit=?,critical_level=?,target_level=?,
              revision=revision+1,updated_at=? WHERE id=?''', (*values.values(), tz.now_iso(), item_id))
        except sqlite3.IntegrityError as exc:
            raise Conflict('That item code already exists. Choose another code.') from exc
        result = _item(conn, item_id)
        return record(conn, user, key, digest, 'item_update', 'item', result, {'before': before, 'after': values})


def deactivate_item(conn, user, item_id, *, expected_revision, operation_key, reason):
    with transaction(conn):
        user = permissions.require_custodian(conn, user)
        require_enabled(conn)
        reason = text(reason, 'Reason', 2000)
        revision = integer(expected_revision, 'Revision', 1)
        key, digest, prior = operation(conn, user, operation_key, 'item_deactivate',
                                       {'id': item_id, 'revision': revision, 'reason': reason})
        if prior is not None:
            return prior
        before = _item(conn, item_id)
        if before['revision'] != revision or not before['active']:
            raise Conflict('This item changed or is already inactive. Reload it.')
        if conn.execute("""SELECT 1 FROM supply_request r
          JOIN supply_request_revision v ON v.request_id=r.id AND v.revision=r.current_revision
          JOIN supply_request_revision_line l ON l.revision_id=v.id
          LEFT JOIN supply_reservation reservation ON reservation.revision_line_id=l.id
          LEFT JOIN supply_request_decision_line decision ON decision.revision_line_id=l.id
          WHERE l.item_id=? AND (r.approval_status IN ('submitted','returned') OR
            (r.approval_status='approved' AND (decision.id IS NULL OR
              decision.approved_quantity>reservation.effective_issued_quantity+reservation.cancelled_quantity))) LIMIT 1""",
                        (item_id,)).fetchone():
            raise Conflict('This item has an open supply request obligation. Resolve it before deactivation.')
        # S5.1 must also guard open replenishment obligations.

        conn.execute('UPDATE supply_item SET active=0,revision=revision+1,updated_at=? WHERE id=?',
                     (tz.now_iso(), item_id))
        result = _item(conn, item_id)
        return record(conn, user, key, digest, 'item_deactivate', 'item', result,
                      {'reason': reason, 'before': before})


def configuration(conn, user, *, page=1):
    permissions.require_admin(conn, user)
    page = integer(page, 'Page', 1)
    grants = rows(conn, '''SELECT g.*,u.username,COALESCE(NULLIF(r.name,''),u.username) AS name,
      o.path AS unit_path FROM supply_role_grant g JOIN admin_user u ON u.id=g.user_id
      LEFT JOIN resource_person r ON r.id=u.rp_id LEFT JOIN org_unit o ON o.id=g.unit_id
      ORDER BY g.id DESC LIMIT 51 OFFSET ?''', ((page - 1) * 50,))
    return {'enabled': enabled(conn), 'revision': int(st.get_setting(conn, 'supplies.settings_revision', '0')),
            'grants': grants[:50], 'has_next': len(grants) > 50, 'page': page,
            'people': rows(conn, '''SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name
              FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.active=1 ORDER BY name,u.id'''),
            'units': rows(conn, 'SELECT id,path FROM org_unit ORDER BY path'), 'roles': permissions.ROLES}


def set_enabled(conn, user, value, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_admin(conn, user)
        if value not in ('0', '1') or not isinstance(value, str):
            raise Invalid('Choose enabled or disabled.')
        revision = integer(expected_revision, 'Revision')
        key, digest, prior = operation(conn, user, operation_key, 'enabled_set',
                                       {'value': value, 'revision': revision})
        if prior is not None:
            return prior
        if revision != int(st.get_setting(conn, 'supplies.settings_revision', '0')):
            raise Conflict('Supplies settings changed. Reload this page.')
        for name, val in [('supplies.enabled', value), ('supplies.settings_revision', str(revision + 1))]:
            # st.set_setting commits; keep both settings and audit in this transaction instead.
            conn.execute('INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (name, val))
        result = {'id': 0, 'enabled': value == '1', 'revision': revision + 1}
        return record(conn, user, key, digest, 'enabled_set', 'settings', result, result)


def grant_role(conn, user, user_id, role, unit_id=None, *, operation_key):
    with transaction(conn):
        user = permissions.require_admin(conn, user)
        user_id = integer(user_id, 'Account', 1)
        grantee = st.get_admin_user_by_id(conn, user_id)
        if not grantee or not grantee['active']:
            raise Invalid('Choose an active staff account.')
        if role not in permissions.ROLES:
            raise Invalid('Choose a Supplies role.')
        if role == 'request_approver':
            unit_id = integer(unit_id, 'Approval unit', 1)
            if not conn.execute('SELECT 1 FROM org_unit WHERE id=?', (unit_id,)).fetchone():
                raise Invalid('Choose an existing approval unit.')
        elif unit_id not in ('', None):
            raise Invalid('Only request approvers have a unit scope.')
        else:
            unit_id = None
        payload = {'user_id': user_id, 'role': role, 'unit_id': unit_id}
        key, digest, prior = operation(conn, user, operation_key, 'role_grant', payload)
        if prior is not None:
            return prior
        try:
            gid = conn.execute('''INSERT INTO supply_role_grant(user_id,role,unit_id,granted_by,created_at)
              VALUES (?,?,?,?,?)''', (user_id, role, unit_id, user['id'], tz.now_iso())).lastrowid
        except sqlite3.IntegrityError as exc:
            raise Conflict('That active role grant already exists.') from exc
        result = rows(conn, 'SELECT * FROM supply_role_grant WHERE id=?', (gid,))[0]
        return record(conn, user, key, digest, 'role_grant', 'grant', result, payload)


def revoke_role(conn, user, grant_id, *, expected_revision, operation_key):
    with transaction(conn):
        user = permissions.require_admin(conn, user)
        revision = integer(expected_revision, 'Revision', 1)
        key, digest, prior = operation(conn, user, operation_key, 'role_revoke',
                                       {'id': grant_id, 'revision': revision})
        if prior is not None:
            return prior
        found = rows(conn, 'SELECT * FROM supply_role_grant WHERE id=?', (grant_id,))
        if not found:
            raise Missing('Role grant not found.')
        before = found[0]
        if before['revoked_at'] or before['revision'] != revision:
            raise Conflict('This grant changed or was already revoked. Reload this page.')
        conn.execute('UPDATE supply_role_grant SET revoked_by=?,revoked_at=?,revision=revision+1 WHERE id=?',
                     (user['id'], tz.now_iso(), grant_id))
        result = rows(conn, 'SELECT * FROM supply_role_grant WHERE id=?', (grant_id,))[0]
        return record(conn, user, key, digest, 'role_revoke', 'grant', result, {'before': before})
