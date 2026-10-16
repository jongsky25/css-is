"""Read-only configuration inventory, never a certification of operational readiness."""
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import json
import os
import storage as st
import documents_permissions as p
import documents_rules as rules
from documents_storage import rows


def relay_configured(prefix):
    endpoint = os.environ.get(prefix + '_URL', '')
    if not endpoint or not os.environ.get(prefix + '_SECRET'):
        return False
    try:
        parsed = urlparse(endpoint)
        return (parsed.scheme == 'https' and parsed.hostname == 'script.google.com'
                and not parsed.username and parsed.port in (None, 443)
                and parsed.path.endswith('/exec'))
    except ValueError:
        return False


def report(conn, user, year=None):
    user = p.actor(conn, user)
    if user['role'] != 'admin' and not any(p.has_role(conn, user, r) for r in ('grant_admin', 'workflow_admin')):
        raise p.Denied('A system administrator or designated administrator for all units is required.')
    year = year or datetime.now(ZoneInfo('Asia/Manila')).year
    items = []

    def add(key, title, status, detail, blocks, action, href=None):
        items.append(dict(key=key, title=title, status=status, detail=detail,
                          blocks=blocks, action=action, href=href))

    grants = rows(conn, '''SELECT g.* FROM document_role_grant g JOIN admin_user u ON u.id=g.user_id
                          WHERE g.revoked_at IS NULL AND u.active=1''')
    for role, label in [('grant_admin', 'Permissions administrators'), ('workflow_admin', 'Workflow administrators'),
                        ('records', 'Records officers'), ('signatory', 'Signing authority')]:
        matching = [g for g in grants if g['role'] == role]
        global_grant = any(g['unit_id'] is None for g in matching)
        add(role, label, 'Configured — review scope' if global_grant else 'Review required' if matching else 'Missing',
            f'{len(matching)} active grants; ' + ('an all-unit grant is present.' if global_grant else 'no all-unit grant is present. Scoped grants may be sufficient for the intended rollout.'),
            {'grant_admin': 'Maintaining document permissions.', 'workflow_admin': 'Maintaining routing and policy rules.',
             'records': 'Officer verification and ownership confirmation where directory authority is absent.',
             'signatory': 'Signing documents where a signature is required.'}[role],
            'Ask the permissions administrator to confirm authorized people and unit coverage in Rules and policies. Initial appointments use Documents setup. A technical administrator role does not confer this authority.',
            '/documents/rules')

    users = rows(conn, 'SELECT * FROM admin_user WHERE active=1')
    officers = sum(bool(p.seats(conn, u) or p.director(conn, u)) for u in users)
    add('directory', 'Directory review authority', 'Review required',
        f'{officers} active accounts have chief, OIC or Director authority. This count does not prove coverage of every division.',
        'Routing reviews to the authorized chief or Director.',
        'Ask the directory owner to confirm staff account links, chiefs and OIC appointments for each participating unit; check a sample review route.', '/admin/users')

    active = rows(conn, "SELECT body_json FROM document_rule_version WHERE state='active'")
    complete = 0
    required = rules.POLICY_KEYS
    for rule in active:
        try:
            body = rules.validate(json.loads(rule['body_json']))
            complete += required <= body.get('policy', {}).keys()
        except (ValueError, TypeError):
            pass
    add('policies', 'Document policies and deadlines', 'Review required' if active else 'Missing',
        f'{len(active)} active rule versions; {complete} include all policy fields. Multiple rules may combine or conflict, so this is not a coverage check.',
        'Predictable due dates, reminders, approval, release and closure requirements.',
        'Have the workflow administrator review each document type and test matching and conflicting rules. Confirm working days, Manila cutoff and reminder times, escalation, signature, acknowledgment and evidence requirements.', '/documents/rules')
    for y in (year, year + 1):
        confirmed = st.get_setting(conn, f'documents.holidays_confirmed.{y}', '0') == '1'
        add(f'holidays_{y}', f'Holiday coverage: {y}', 'Recorded — review dates' if confirmed else 'Missing confirmation',
            'Year confirmation is recorded.' if confirmed else 'Year confirmation is absent.',
            f'Confidence in working-day deadlines crossing {y}.',
            f'Have the calendar owner review national and local holidays and suspensions in Holidays. After review, the deployment maintainer records documents.holidays_confirmed.{y}=1 using the setup runbook. Review other years used by long-running work.', '/admin/holidays')

    docs_relay = relay_configured('CSS_DOCS_RELAY')
    for key, title, action in [
        ('drive', 'Google Drive access', 'Have the deployment maintainer configure CSS_DOCS_RELAY_URL and CSS_DOCS_RELAY_SECRET and DOCUMENTS_ROOT_FOLDER_ID in the existing Apps Script project. Inspect a synthetic file and confirm private folder permissions.'),
        ('extraction', 'Document extraction', 'Have the relay maintainer deploy document extraction support. Test a synthetic text document and scan, ambiguous dates, unsupported formats and manual-entry fallback.'),
        ('signing', 'Stored-signature integration', 'Have each authorized signatory save their own signature in My profile. With the relay maintainer, preview and sign an approved synthetic version; check marker placement, PDF layout and receipt. Grants alone do not prove signature availability.'),
    ]:
        add(key, title, 'Configured — not verified' if docs_relay else 'Missing or invalid configuration',
            'Relay endpoint and secret presence checked locally; remote deployment, permissions and receipts have not been verified.',
            {'drive': 'Inspecting linked files.', 'extraction': 'Extracted suggestions; manual registration remains available.', 'signing': 'Applying a stored signature to an approved version.'}[key], action)
    mail = relay_configured('CSS_MAIL_RELAY')
    sender = bool(st.get_setting(conn, 'documents.official_sender', '').strip())
    add('email', 'Official email integration', 'Configured — not verified' if mail and sender else 'Missing or invalid configuration',
        f'Mail relay configuration: {"present" if mail else "missing or invalid"}; official sender: {"present" if sender else "missing"}. No email was sent.',
        'Direct official dispatch.',
        'Have the deployment maintainer configure CSS_MAIL_RELAY_URL, CSS_MAIL_RELAY_SECRET and documents.official_sender. Deploy document dispatch support with Gmail API, confirm the mailbox or authorized alias, then use an explicitly authorized synthetic recipient to verify delivery and reconciliation receipts.')
    flags = {key: st.get_setting(conn, key, '0') == '1' for key in
             ('documents.enabled', 'work.enabled', 'documents.sending_enabled')}
    return {'items': items, 'flags': flags}
