"""Atomic receipts for retries of the correspondence registration form."""
import hashlib
import hmac
import json
import re
import uuid

import auth
import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work
import work_intake


def _signature(user, key):
    return hmac.new(auth._secret(), f'document-registration:{user["id"]}:{key}'.encode(), hashlib.sha256).hexdigest()


def issue(user):
    key = uuid.uuid4().hex
    return key + '.' + _signature(user, key)


def _key(user, value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}\.[a-f0-9]{64}', value):
        raise permissions.Denied('This registration form cannot be verified. Check your document register before opening a new form.')
    key, signature = value.split('.')
    if not hmac.compare_digest(signature, _signature(user, key)):
        raise permissions.Denied('This registration form cannot be verified. Check your document register before opening a new form.')
    return key


def _result(conn, user, receipt):
    # A receipt is not an access grant. Recheck current record/case visibility.
    doc = docs.get(conn, user, receipt['document_id'])
    url = '/documents/' + str(doc['id'])
    if receipt['case_id']:
        try:
            case = work.get(conn, user, receipt['case_id'])
            url = '/work/' + str(case['id'])
        except permissions.Denied:
            pass  # The document can still be readable after case access changes.
    return {'state': 'saved', 'document_id': doc['id'], 'number': doc['number'], 'url': url}


def status(conn, user, submission_id):
    user = permissions.actor(conn, user)
    key = _key(user, submission_id)
    found = rows(conn, 'SELECT * FROM document_registration WHERE actor_id=? AND submission_id=?', (user['id'], key))
    # No committed receipt can mean an in-flight transaction or a rolled-back
    # attempt. Never tell the browser that it is safe to use a different key.
    return _result(conn, user, found[0]) if found else {'state': 'unconfirmed'}


def register(conn, user, fields):
    with transaction(conn):
        user = permissions.actor(conn, user)
        key = _key(user, fields.get('submission_id'))
        body = {k: v for k, v in fields.items() if k not in ('submission_id', 'csrf')}
        canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        fingerprint = hmac.new(auth._secret(), b'document-registration-payload:' + canonical, hashlib.sha256).hexdigest()
        found = rows(conn, 'SELECT * FROM document_registration WHERE actor_id=? AND submission_id=?', (user['id'], key))
        if found:
            result = _result(conn, user, found[0])
            if not hmac.compare_digest(found[0]['payload_hash'], fingerprint):
                raise docs.Conflict('This submission was already saved with different details. Check the saved result; these changes have not been applied.')
            return {**result, 'replayed': True}
        if fields.get('intake') == 'guided':
            doc, case = work_intake.register_in_transaction(conn, user, fields)
        else:
            doc, case = docs.register_in_transaction(conn, user, fields), None
        receipt = {'document_id': doc['id'], 'case_id': case['id'] if case else None}
        conn.execute('''INSERT INTO document_registration
            (actor_id,submission_id,payload_hash,document_id,case_id,created_at) VALUES (?,?,?,?,?,?)''',
            (user['id'], key, fingerprint, doc['id'], receipt['case_id'], tz.now_iso()))
        return {**_result(conn, user, receipt), 'replayed': False}
