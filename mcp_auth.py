"""ChatGPT MCP OAuth grants: short-lived access, rotating refresh, current actor."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    OAuthAuthorizationServerProvider, RefreshToken, RegistrationError, TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

import auth
import storage as st


READ_SCOPES = frozenset({'surveys:person_activities:read', 'surveys:resource_person_trends:read', 'surveys:csm_trends:read', 'surveys:unit_trends:read', 'surveys:units:read', 'activities:read', 'calendar:read', 'documents:read',
                    'supplies:read', 'travel:read', 'work:read', 'notifications:read', 'surveys:csm:read', 'surveys:activities:read', 'surveys:resource_persons:read', 'surveys:activity_details:read'})
WRITE_SCOPES = frozenset({'notifications:mark_read', 'supplies:request:draft', 'work:comment:draft', 'reports:view:save', 'calendar:entry:create', 'travel:filing:draft', 'work:task:acknowledge', 'work:task:submit', 'supplies:request:submit', 'travel:review:request', 'travel:filing:submit', 'rooms:request', 'meals:request', 'work_arrangements:request', 'activities:dates:update', 'activities:draft:save', 'activities:draft:create', 'activities:announcement:publish', 'work:task:accept', 'supplies:request:approve', 'rooms:request:approve'})
SCOPES = READ_SCOPES | WRITE_SCOPES
ACCESS_SECONDS = 3600
REFRESH_SECONDS = 30 * 86400
CODE_SECONDS = 120
TICKET_SECONDS = 600


def install(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS mcp_oauth_client (
      id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL, created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS mcp_oauth_pending (
      ticket_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL,
      params_json TEXT NOT NULL, expires_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS mcp_oauth_code (
      code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, owner_id INTEGER NOT NULL,
      params_json TEXT NOT NULL, expires_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS mcp_oauth_grant (
      id TEXT PRIMARY KEY, client_id TEXT NOT NULL, owner_id INTEGER NOT NULL,
      scopes_json TEXT NOT NULL, resource TEXT NOT NULL,
      access_hash TEXT NOT NULL UNIQUE, access_expires INTEGER NOT NULL,
      refresh_hash TEXT NOT NULL UNIQUE, refresh_expires INTEGER NOT NULL,
      revoked_at INTEGER, created_at INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS mcp_oauth_grant_owner ON mcp_oauth_grant(owner_id,created_at);
    CREATE TRIGGER IF NOT EXISTS revoke_mcp_on_account_change
    AFTER UPDATE OF username,pw_hash,salt,role,active,must_change,rp_id,bureau_access ON admin_user
    WHEN OLD.username IS NOT NEW.username OR OLD.pw_hash IS NOT NEW.pw_hash
      OR OLD.salt IS NOT NEW.salt OR OLD.role IS NOT NEW.role
      OR OLD.active IS NOT NEW.active OR OLD.must_change IS NOT NEW.must_change
      OR OLD.rp_id IS NOT NEW.rp_id OR OLD.bureau_access IS NOT NEW.bureau_access
    BEGIN
      UPDATE mcp_oauth_grant SET revoked_at=COALESCE(revoked_at,CAST(strftime('%s','now') AS INTEGER))
      WHERE owner_id=OLD.id;
    END;
    ''')
    import mcp_actions
    mcp_actions.install(conn)
    import mcp_supply_drafts
    mcp_supply_drafts.install(conn)
    import mcp_comment_drafts
    mcp_comment_drafts.install(conn)
    import mcp_report_views
    mcp_report_views.install(conn)
    import mcp_personal_calendar
    mcp_personal_calendar.install(conn)
    import mcp_travel_drafts
    mcp_travel_drafts.install(conn)
    import mcp_task_acknowledgements
    mcp_task_acknowledgements.install(conn)
    import mcp_task_submissions
    mcp_task_submissions.install(conn)
    import mcp_supply_submissions
    mcp_supply_submissions.install(conn)
    import mcp_travel_reviews
    mcp_travel_reviews.install(conn)
    import mcp_travel_submissions
    mcp_travel_submissions.install(conn)
    import mcp_room_requests
    mcp_room_requests.install(conn)
    import mcp_meal_requests
    mcp_meal_requests.install(conn)
    import mcp_work_arrangements
    mcp_work_arrangements.install(conn)
    import mcp_activity_dates
    mcp_activity_dates.install(conn)
    import mcp_activity_drafts
    mcp_activity_drafts.install(conn)
    import mcp_activity_creation
    mcp_activity_creation.install(conn)
    import mcp_activity_announcements
    mcp_activity_announcements.install(conn)
    import mcp_task_acceptances
    mcp_task_acceptances.install(conn)
    import mcp_supply_approvals
    mcp_supply_approvals.install(conn)
    import mcp_room_approvals
    mcp_room_approvals.install(conn)


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _active(conn, owner_id):
    user = st.get_admin_user_by_id(conn, owner_id)
    return user if user and user['active'] and not user['must_change'] and auth.valid_role(user['role']) else None


def current_grant(conn, token, resource, scope):
    """Recheck bearer, audience, scope and account inside the business snapshot."""
    row = conn.execute('SELECT owner_id,scopes_json FROM mcp_oauth_grant '
                       'WHERE access_hash=? AND resource=? AND revoked_at IS NULL AND access_expires>?',
                       (_digest(token), resource, int(time.time()))).fetchone()
    if not row or scope not in json.loads(row[1]):
        return None
    return _active(conn, row[0])


def _callback_allowed(value):
    parsed = urlparse(str(value))
    return (parsed.scheme == 'https' and parsed.netloc == 'chatgpt.com'
            and (parsed.path == '/connector_platform_oauth_redirect'
                 or (parsed.path.startswith('/connector/oauth/')
                     and len(parsed.path.split('/')) == 4
                     and bool(parsed.path.split('/')[-1])))
            and not parsed.query and not parsed.fragment)


class Provider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, get_conn, origin):
        self.get_conn = get_conn
        self.origin = origin.rstrip('/')
        self.resource = self.origin + '/mcp'

    def _run(self, operation):
        conn = self.get_conn()
        try:
            return operation(conn)
        finally:
            conn.close()

    async def get_client(self, client_id):
        def read(conn):
            row = conn.execute('SELECT metadata_json FROM mcp_oauth_client WHERE id=?', (client_id,)).fetchone()
            if not row:
                return None
            client = OAuthClientInformationFull.model_validate_json(row[0])
            # Registration is eligibility, not user consent. Older ChatGPT
            # registrations advertised only work; offer current read choices
            # without modifying any pending request, code, grant or token.
            client.scope = ' '.join(sorted(SCOPES))
            return client
        return await asyncio.to_thread(self._run, read)

    async def register_client(self, client_info):
        if (not client_info.client_id or not client_info.redirect_uris
                or not all(_callback_allowed(uri) for uri in client_info.redirect_uris)
                or client_info.token_endpoint_auth_method not in ('none', 'client_secret_post', 'client_secret_basic')
                or set((client_info.scope or '').split()) - SCOPES):
            raise RegistrationError('invalid_client_metadata', 'Use a supported ChatGPT callback and permission.')
        # Return and persist permission eligibility; it is not a grant.
        # The authorize request and explicit consent still choose actual grants.
        client_info.scope = ' '.join(sorted(SCOPES))
        def save(conn):
            with conn:
                # Expired, unused registrations have no active grant or pending
                # authorization and need not live forever in the SQLite file.
                conn.execute('''DELETE FROM mcp_oauth_client WHERE created_at<?
                    AND NOT EXISTS(SELECT 1 FROM mcp_oauth_grant g WHERE g.client_id=mcp_oauth_client.id
                                   AND g.revoked_at IS NULL AND g.refresh_expires>?)
                    AND NOT EXISTS(SELECT 1 FROM mcp_oauth_pending p WHERE p.client_id=mcp_oauth_client.id
                                   AND p.expires_at>?)''',
                    (int(time.time()) - 86400, int(time.time()), int(time.time())))
                if conn.execute('SELECT COUNT(*) FROM mcp_oauth_client').fetchone()[0] >= 1000:
                    raise RegistrationError('invalid_client_metadata', 'Too many connections are registered.')
                conn.execute('INSERT INTO mcp_oauth_client(id,metadata_json,created_at) VALUES (?,?,?)',
                             (client_info.client_id, client_info.model_dump_json(), int(time.time())))
        await asyncio.to_thread(self._run, save)

    async def authorize(self, client, params: AuthorizationParams):
        scopes = list(params.scopes or sorted(READ_SCOPES))
        if (params.resource != self.resource or not scopes or set(scopes) - SCOPES
                or (client.scope and set(scopes) - set(client.scope.split()))):
            raise AuthorizeError('invalid_scope', 'Choose permitted scopes for this MCP server.')
        ticket = secrets.token_urlsafe(32)
        payload = params.model_dump(mode='json')
        payload['scopes'] = scopes
        def save(conn):
            with conn:
                conn.execute('INSERT INTO mcp_oauth_pending VALUES (?,?,?,?)',
                             (_digest(ticket), client.client_id, json.dumps(payload), int(time.time()) + TICKET_SECONDS))
        await asyncio.to_thread(self._run, save)
        return self.origin + '/mcp-consent?ticket=' + ticket

    def pending(self, ticket):
        if len(ticket) > 100:
            return None
        def read(conn):
            row = conn.execute('SELECT client_id,params_json FROM mcp_oauth_pending '
                               'WHERE ticket_hash=? AND expires_at>?', (_digest(ticket), int(time.time()))).fetchone()
            return (row[0], json.loads(row[1])) if row else None
        return self._run(read)

    def consent_scopes(self, client_id):
        """Offer supported permissions to registered clients, including legacy ones."""
        def read(conn):
            row = conn.execute('SELECT metadata_json FROM mcp_oauth_client WHERE id=?',
                               (client_id,)).fetchone()
            if not row:
                raise ValueError('The connection registration is unavailable.')
            return SCOPES
        return self._run(read)

    def complete(self, ticket, owner_id, approve, additional_scopes=()):
        def save(conn):
            conn.execute('BEGIN IMMEDIATE')
            try:
                row = conn.execute('SELECT client_id,params_json FROM mcp_oauth_pending '
                                   'WHERE ticket_hash=? AND expires_at>?', (_digest(ticket), int(time.time()))).fetchone()
                if not row or not _active(conn, owner_id):
                    raise ValueError('The connection request expired or your session changed.')
                client_id, raw = row
                params = json.loads(raw)
                if approve:
                    # Recheck registration under the writer lock. The server
                    # offers only its explicit permission allowlist, including to legacy clients.
                    row_client = conn.execute('SELECT metadata_json FROM mcp_oauth_client WHERE id=?',
                                              (client_id,)).fetchone()
                    if not row_client:
                        raise ValueError('The connection registration is unavailable.')
                    selected = set(additional_scopes)
                    if selected - SCOPES:
                        raise ValueError('The requested permission is unavailable to this connection.')
                    params['scopes'] = sorted(set(params['scopes']) | selected)
                    raw = json.dumps(params)
                conn.execute('DELETE FROM mcp_oauth_pending WHERE ticket_hash=?', (_digest(ticket),))
                code = secrets.token_urlsafe(32) if approve else None
                if approve:
                    conn.execute('INSERT INTO mcp_oauth_code VALUES (?,?,?,?,?)',
                                 (_digest(code), client_id, owner_id, raw, int(time.time()) + CODE_SECONDS))
                st.audit(conn, _active(conn, owner_id)['username'],
                         'integration_issue' if approve else 'integration_revoke',
                         target_type='mcp_oauth', target_id=client_id,
                         summary='MCP consent approved' if approve else 'MCP consent declined', commit=False)
                conn.commit()
                return params, code
            except Exception:
                conn.rollback()
                raise
        return self._run(save)

    async def load_authorization_code(self, client, authorization_code):
        def read(conn):
            row = conn.execute('SELECT owner_id,params_json,expires_at FROM mcp_oauth_code '
                               'WHERE code_hash=? AND client_id=? AND expires_at>?',
                               (_digest(authorization_code), client.client_id, int(time.time()))).fetchone()
            if not row:
                return None
            owner_id, raw, expires_at = row
            params = json.loads(raw)
            return AuthorizationCode(code=authorization_code, client_id=client.client_id,
                scopes=params['scopes'], expires_at=expires_at,
                code_challenge=params['code_challenge'], redirect_uri=params['redirect_uri'],
                redirect_uri_provided_explicitly=params['redirect_uri_provided_explicitly'],
                resource=params['resource'], subject=str(owner_id))
        return await asyncio.to_thread(self._run, read)

    @staticmethod
    def _tokens(conn, client_id, owner_id, scopes, resource, *, grant_id=None):
        now = int(time.time())
        access = 'oc_mcp_' + secrets.token_urlsafe(32)
        refresh = 'oc_mcp_refresh_' + secrets.token_urlsafe(32)
        if grant_id is None:
            conn.execute('INSERT INTO mcp_oauth_grant VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), client_id, owner_id, json.dumps(scopes), resource,
                          _digest(access), now + ACCESS_SECONDS, _digest(refresh), now + REFRESH_SECONDS,
                          None, now))
        else:
            # The writer-locked refresh exchange already checked this grant.
            # Rotate both secrets atomically while preserving connection identity
            # for browser confirmations, receipts and owner revocation links.
            conn.execute('UPDATE mcp_oauth_grant SET scopes_json=?,access_hash=?,access_expires=?, '
                         'refresh_hash=?,refresh_expires=? WHERE id=?',
                         (json.dumps(scopes), _digest(access), now + ACCESS_SECONDS,
                          _digest(refresh), now + REFRESH_SECONDS, grant_id))
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=ACCESS_SECONDS,
                          refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        def exchange(conn):
            conn.execute('BEGIN IMMEDIATE')
            try:
                row = conn.execute('SELECT owner_id,params_json FROM mcp_oauth_code '
                                   'WHERE code_hash=? AND client_id=? AND expires_at>?',
                                   (_digest(authorization_code.code), client.client_id, int(time.time()))).fetchone()
                if not row or not _active(conn, row[0]):
                    raise TokenError('invalid_grant', 'The authorization code is unavailable.')
                params = json.loads(row[1])
                conn.execute('DELETE FROM mcp_oauth_code WHERE code_hash=?', (_digest(authorization_code.code),))
                result = self._tokens(conn, client.client_id, row[0], params['scopes'], params['resource'])
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
        return await asyncio.to_thread(self._run, exchange)

    async def load_refresh_token(self, client, refresh_token):
        def read(conn):
            row = conn.execute('SELECT owner_id,scopes_json,refresh_expires FROM mcp_oauth_grant '
                               'WHERE refresh_hash=? AND client_id=? AND revoked_at IS NULL AND refresh_expires>?',
                               (_digest(refresh_token), client.client_id, int(time.time()))).fetchone()
            return (RefreshToken(token=refresh_token, client_id=client.client_id,
                    scopes=json.loads(row[1]), expires_at=row[2], subject=str(row[0]))
                    if row and _active(conn, row[0]) else None)
        return await asyncio.to_thread(self._run, read)

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        def exchange(conn):
            conn.execute('BEGIN IMMEDIATE')
            try:
                row = conn.execute('SELECT id,owner_id,scopes_json,resource FROM mcp_oauth_grant '
                                   'WHERE refresh_hash=? AND client_id=? AND revoked_at IS NULL AND refresh_expires>?',
                                   (_digest(refresh_token.token), client.client_id, int(time.time()))).fetchone()
                if not row or not _active(conn, row[1]):
                    raise TokenError('invalid_grant', 'The refresh token is unavailable.')
                granted = json.loads(row[2])
                chosen = scopes or granted
                if set(chosen) - set(granted):
                    raise TokenError('invalid_scope', 'The requested scope exceeds the grant.')
                result = self._tokens(conn, client.client_id, row[1], chosen, row[3], grant_id=row[0])
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
        return await asyncio.to_thread(self._run, exchange)

    async def load_access_token(self, token):
        def read(conn):
            row = conn.execute('SELECT client_id,owner_id,scopes_json,resource,access_expires '
                               'FROM mcp_oauth_grant WHERE access_hash=? AND revoked_at IS NULL AND access_expires>?',
                               (_digest(token), int(time.time()))).fetchone()
            if not row or row[3] != self.resource or not _active(conn, row[1]):
                return None
            return AccessToken(token=token, client_id=row[0], scopes=json.loads(row[2]),
                               expires_at=row[4], resource=row[3], subject=str(row[1]))
        return await asyncio.to_thread(self._run, read)

    async def revoke_token(self, token):
        def revoke(conn):
            with conn:
                conn.execute('UPDATE mcp_oauth_grant SET revoked_at=COALESCE(revoked_at,?) '
                             'WHERE access_hash=? OR refresh_hash=?',
                             (int(time.time()), _digest(token.token), _digest(token.token)))
        await asyncio.to_thread(self._run, revoke)


def owner_grants(conn, owner_id):
    """Metadata only for the owner's Connected tools screen."""
    rows = conn.execute('''SELECT g.id,g.client_id,g.scopes_json,g.created_at,g.refresh_expires,
        g.revoked_at,c.metadata_json FROM mcp_oauth_grant g
        LEFT JOIN mcp_oauth_client c ON c.id=g.client_id
        WHERE g.owner_id=? ORDER BY g.created_at DESC,g.id DESC LIMIT 50''', (owner_id,)).fetchall()
    result = []
    for id_, client_id, scopes, created, expires, revoked, metadata in rows:
        client = json.loads(metadata) if metadata else {}
        result.append({'id': id_, 'name': client.get('client_name') or 'ChatGPT connection',
                       'scopes': json.loads(scopes), 'created_at': created,
                       'expires_at': expires, 'revoked_at': revoked})
    return result


def revoke_owner_grant(conn, owner_id, key):
    if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Connection not found.')
    conn.execute('BEGIN IMMEDIATE')
    try:
        row = conn.execute('SELECT id FROM mcp_oauth_grant WHERE id=? AND owner_id=?',
                           (key, owner_id)).fetchone()
        if not row:
            raise ValueError('Connection not found.')
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=COALESCE(revoked_at,?) WHERE id=?',
                     (int(time.time()), key))
        user = _active(conn, owner_id)
        if user:
            st.audit(conn, user['username'], 'integration_revoke', target_type='mcp_oauth',
                     target_id=key, summary='Revoked MCP read connection', commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
