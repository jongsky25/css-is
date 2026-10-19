"""Administrator configuration for the existing signed Gmail intake endpoint."""
import os
import re

import documents as d
import documents_permissions as p
from documents_storage import rows, transaction, event
import storage as st


def administrator(conn, user):
    user = p.actor(conn, user)
    d.require(p.has_role(conn, user, 'records') and p.has_role(conn, user, 'workflow_admin'))
    return user


def settings(conn):
    config = {key: st.get_setting(conn, 'documents.gmail_' + key, '')
              for key in ('intake_enabled', 'mailbox', 'actor_id')}
    # Never expose the credential itself to templates, submitted fields or audit logs.
    config['secret_configured'] = len(os.environ.get('CSS_GMAIL_INTAKE_SECRET', '')) >= 32
    config['review_ready'] = (
        st.get_setting(conn, 'documents.gmail_review_queue_enabled', '0') == '1'
        and bool(st.get_setting(conn, 'documents.drive_last_sync', '')))
    return config


def records_accounts(conn):
    return rows(conn, """SELECT u.id,u.username FROM admin_user u WHERE u.active=1
        AND EXISTS (SELECT 1 FROM document_role_grant g WHERE g.user_id=u.id
                    AND g.role='records' AND g.unit_id IS NULL AND g.revoked_at IS NULL)
        ORDER BY u.username"""
    )


def configure(conn, user, fields):
    with transaction(conn):
        user = administrator(conn, user)
        if fields.get('action') == 'pause':
            # Pausing must remain possible after a secret, grant or account is removed.
            _setting(conn, 'intake_enabled', '0')
            event(conn, None, user, 'gmail_intake_paused', {})
            return
        mailbox = str(fields.get('mailbox', '')).strip().lower()
        if (len(mailbox) > 254 or any(ord(c) < 32 for c in mailbox)
                or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', mailbox)):
            raise ValueError('Enter the primary Gmail mailbox address used by the Apps Script importer.')
        actor_id = str(fields.get('actor_id', ''))
        if not any(str(account['id']) == actor_id for account in records_accounts(conn)):
            raise ValueError('Select an active account with the Records officer grant for All units.')
        enabled = fields.get('enabled') == 'yes'
        if enabled:
            d.writable(conn)
            config = settings(conn)
            if not config['secret_configured']:
                raise ValueError('Add CSS_GMAIL_INTAKE_SECRET with at least 32 characters to the hosting secrets first.')
            if not config['review_ready']:
                raise ValueError('Enable Drive intake and complete a successful Check Drive now before enabling Gmail intake.')
        for key, value in {'mailbox': mailbox, 'actor_id': actor_id,
                           'intake_enabled': '1' if enabled else '0'}.items():
            _setting(conn, key, value)
        event(conn, None, user, 'gmail_intake_configured',
              {'mailbox': mailbox, 'actor_id': int(actor_id), 'enabled': enabled})


def _setting(conn, key, value):
    conn.execute('INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 ('documents.gmail_' + key, value))
