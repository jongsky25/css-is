"""Supplies authority uses current accounts and independent module grants."""
import storage as st
from supplies_storage import Denied, rows


ROLES = {
    'custodian': 'Supply custodian',
    'request_approver': 'Supply request approver',
    'replenishment_approver': 'Replenishment approver',
    'auditor': 'Supplies auditor',
}


def require_actor(conn, user):
    uid = user.get('id') if isinstance(user, dict) else None
    found = st.get_admin_user_by_id(conn, uid) if type(uid) is int and uid > 0 else None
    if not found or not found['active']:
        raise Denied('An active staff account is required.')
    return found


def require_admin(conn, user):
    user = require_actor(conn, user)
    if user['role'] != 'admin':
        raise Denied('Only administrators can configure Supplies roles and access.')
    return user


def scope_contains(conn, parent, child):
    if parent is None or child is None:
        return False
    units = {r['id']: r['path'] for r in rows(conn,
             'SELECT id,path FROM org_unit WHERE id IN (?,?)', (parent, child))}
    return (parent in units and child in units and
            (units[child] == units[parent] or units[child].startswith(units[parent] + '/')))


def has_role(conn, user, role, unit_id=None):
    user = require_actor(conn, user)
    grants = rows(conn, '''SELECT unit_id FROM supply_role_grant
      WHERE user_id=? AND role=? AND revoked_at IS NULL''', (user['id'], role))
    if role == 'request_approver':
        return any(scope_contains(conn, g['unit_id'], unit_id) for g in grants)
    return role in ROLES and bool(grants)


def require_custodian(conn, user):
    user = require_actor(conn, user)
    if not has_role(conn, user, 'custodian'):
        raise Denied('A current supply custodian grant is required.')
    return user


def require_stock_reader(conn, user):
    user = require_actor(conn, user)
    if not (has_role(conn, user, 'custodian') or has_role(conn, user, 'auditor')):
        raise Denied('A current custodian or auditor grant is required to view stock history and receipts.')
    return user
