"""A20 delegated read credentials. Secrets are shown once and stored only hashed."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time

import auth
import storage as st
from documents_storage import rows, transaction
from request_security import _origin

SCOPES = {'documents:read': 'Document metadata', 'work:read': 'Work and task metadata'}
TOKEN_PATTERN = r'oc_read_[0-9a-f]{32}\.[0-9a-f]{64}'
DAYS = (7, 30, 90)
MAX_ACTIVE = 20


class InvalidCredential(ValueError):
    pass


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS integration_credential (
      id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES admin_user(id),
      name TEXT NOT NULL, secret_hash TEXT NOT NULL, scopes_json TEXT NOT NULL,
      audience TEXT NOT NULL, issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
      revoked_at INTEGER, last_used_at INTEGER,
      CHECK(expires_at > issued_at));
    CREATE INDEX IF NOT EXISTS integration_credential_owner ON integration_credential(owner_id,issued_at);
    CREATE TRIGGER IF NOT EXISTS integration_credential_fixed_grant
    BEFORE UPDATE OF id,owner_id,name,secret_hash,scopes_json,audience,issued_at,expires_at ON integration_credential
    BEGIN SELECT RAISE(ABORT,'Integration grants are immutable; issue a new credential'); END;
    CREATE TRIGGER IF NOT EXISTS integration_credential_no_restore
    BEFORE UPDATE OF revoked_at ON integration_credential
    WHEN OLD.revoked_at IS NOT NULL AND OLD.revoked_at IS NOT NEW.revoked_at
    BEGIN SELECT RAISE(ABORT,'Revoked integration credentials cannot be restored'); END;
    CREATE TRIGGER IF NOT EXISTS revoke_integrations_on_account_change
    AFTER UPDATE OF username,pw_hash,salt,role,active,must_change,rp_id,bureau_access ON admin_user
    WHEN OLD.username IS NOT NEW.username OR OLD.pw_hash IS NOT NEW.pw_hash
      OR OLD.salt IS NOT NEW.salt OR OLD.role IS NOT NEW.role
      OR OLD.active IS NOT NEW.active OR OLD.must_change IS NOT NEW.must_change
      OR OLD.rp_id IS NOT NEW.rp_id OR OLD.bureau_access IS NOT NEW.bureau_access
    BEGIN
      UPDATE integration_credential SET revoked_at=COALESCE(revoked_at,CAST(strftime('%s','now') AS INTEGER))
      WHERE owner_id=OLD.id;
    END;
    ''')


def audience(request):
    canonical = os.environ.get('CSS_BASE_URL')
    if not canonical and os.environ.get('SPACE_HOST'):
        canonical = 'https://' + os.environ['SPACE_HOST']
    origin = _origin(canonical or str(request.base_url.replace(path='/',query='')))
    if origin is None:
        raise InvalidCredential('The deployment origin is unavailable.')
    return json.dumps([*origin, '/api/v1'], separators=(',', ':'))


def _session(conn, payload):
    user = st.session_actor(conn, payload) if payload else None
    if not user or not auth.valid_role(user['role']):
        raise InvalidCredential('Sign in again to manage connected tools.')
    return user


def issue(conn, payload, verified_hash, name, scopes, days, target_audience):
    if (not isinstance(name, str) or not name.strip() or len(name.strip()) > 80
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError('Give the tool a name of 1 to 80 characters.')
    name.encode('utf-8')
    if not scopes or len(scopes) != len(set(scopes)) or set(scopes) - SCOPES.keys():
        raise ValueError('Choose document metadata, work metadata, or both.')
    if type(days) is not int or days not in DAYS or not target_audience:
        raise ValueError('Choose an expiry of 7, 30 or 90 days.')
    now = int(time.time())
    key = secrets.token_hex(16)
    token = 'oc_read_' + key + '.' + secrets.token_hex(32)
    with transaction(conn):
        user = _session(conn, payload)
        account = st.get_admin_user_by_id(conn, user['id'])
        if not hmac.compare_digest(account['pw_hash'], verified_hash):
            raise InvalidCredential('Your account changed. Sign in again.')
        count = conn.execute('''SELECT COUNT(*) FROM integration_credential
            WHERE owner_id=? AND revoked_at IS NULL AND expires_at>?''', (user['id'], now)).fetchone()[0]
        if count >= MAX_ACTIVE:
            raise ValueError('You have 20 active credentials. Revoke an unused one first.')
        conn.execute('''INSERT INTO integration_credential
            (id,owner_id,name,secret_hash,scopes_json,audience,issued_at,expires_at)
            VALUES(?,?,?,?,?,?,?,?)''', (key,user['id'],name.strip(),hashlib.sha256(token.encode()).hexdigest(),
                json.dumps(sorted(scopes)),target_audience,now,now+days*86400))
        st.audit(conn,user['username'],'integration_issue',target_type='integration_credential',target_id=key,
                 after=json.dumps({'name':name.strip(),'scopes':sorted(scopes),'expires_at':now+days*86400}),commit=False)
    return token


def authenticate(conn, request):
    values = request.headers.getlist('authorization')
    # Never choose an identity/scope by falling back to an ambient browser cookie.
    if len(values) != 1 or request.cookies.get(auth.COOKIE_NAME):
        raise InvalidCredential('A valid integration credential is required.')
    match = re.fullmatch(r'(?i:Bearer) (' + TOKEN_PATTERN + ')', values[0])
    if not match:
        raise InvalidCredential('A valid integration credential is required.')
    token = match[1]
    found = rows(conn, 'SELECT * FROM integration_credential WHERE id=?', (token[8:40],))
    row = found[0] if found else None
    if (not row or not hmac.compare_digest(row['secret_hash'], hashlib.sha256(token.encode()).hexdigest())
            or row['revoked_at'] is not None or row['expires_at'] <= int(time.time())
            or row['audience'] != audience(request)):
        raise InvalidCredential('A valid integration credential is required.')
    user = st.get_admin_user_by_id(conn,row['owner_id'])
    try:
        scopes = json.loads(row['scopes_json'])
    except (ValueError,TypeError):
        raise InvalidCredential('A valid integration credential is required.') from None
    if (not user or not user['active'] or user['must_change'] or not auth.valid_role(user['role'])
            or not isinstance(scopes,list) or not scopes or any(not isinstance(s,str) or s not in SCOPES for s in scopes)):
        raise InvalidCredential('A valid integration credential is required.')
    return {'id':user['id'],'username':user['username'],'role':user['role']}, {'id':row['id'],'scopes':scopes}


def resource(path):
    if path in ('/', '/openapi.json'):
        return 'contract', None
    if re.fullmatch(r'/documents(?:/[1-9][0-9]{0,18})?', path):
        return 'documents', 'documents:read'
    if re.fullmatch(r'/work-items(?:/[1-9][0-9]{0,18}(?:/tasks(?:/[1-9][0-9]{0,18})?)?)?', path):
        return 'work', 'work:read'
    return 'unsupported', None


def record_use(conn, user, credential_id, path, method, status):
    # No raw URL/query, submitted text, secret, cookie or record title in audit.
    with transaction(conn):
        conn.execute('UPDATE integration_credential SET last_used_at=? WHERE id=?',
                     (int(time.time()),credential_id))
        st.audit(conn,user['username'],'integration_read',target_type='integration_credential',target_id=credential_id,
                 summary=json.dumps({'resource':resource(path)[0], 'method':method if method in ('GET','POST','HEAD','OPTIONS','PUT','PATCH','DELETE') else 'other',
                                     'status':status}),commit=False)


def listing(conn, payload, admin=False, before=''):
    user = _session(conn,payload)
    if admin and not auth.can(user['role'],'manage_users'):
        raise InvalidCredential('Account administration access is required.')
    cursor = None
    if before:
        if not re.fullmatch(r'[0-9a-f]{32}',before):
            raise InvalidCredential('Invalid credential page.')
        cursor = conn.execute('SELECT issued_at FROM integration_credential WHERE id=? AND (? OR owner_id=?)',
                              (before,int(admin),user['id'])).fetchone()
        if not cursor:
            raise InvalidCredential('Credential page not found.')
    entries = rows(conn, '''SELECT c.id,c.owner_id,c.name,c.scopes_json,c.issued_at,c.expires_at,c.revoked_at,c.last_used_at,
                        u.username AS owner FROM integration_credential c JOIN admin_user u ON u.id=c.owner_id
                        WHERE (? OR c.owner_id=?)
                        AND (?=0 OR c.issued_at<? OR (c.issued_at=? AND c.id<?))
                        ORDER BY c.issued_at DESC,c.id DESC LIMIT 101''',
                (int(admin),user['id'],int(bool(cursor)),cursor[0] if cursor else 0,cursor[0] if cursor else 0,before))
    return entries[:100], entries[99]['id'] if len(entries)>100 else None


def revoke(conn,payload,key,admin=False):
    with transaction(conn):
        user = _session(conn,payload)
        if admin and not auth.can(user['role'],'manage_users'):
            raise InvalidCredential('Account administration access is required.')
        found = rows(conn,'SELECT * FROM integration_credential WHERE id=? AND (? OR owner_id=?)',
                     (key,int(admin),user['id']))
        if not found:
            raise InvalidCredential('Credential not found or unavailable to you.')
        if found[0]['revoked_at'] is None:
            conn.execute('UPDATE integration_credential SET revoked_at=? WHERE id=?',(int(time.time()),key))
            st.audit(conn,user['username'],'integration_revoke',target_type='integration_credential',target_id=key,
                     summary='Revoked delegated read access',commit=False)
