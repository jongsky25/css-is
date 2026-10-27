"""Browser consent, credential management and explicit MCP action confirmation."""
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import integration_access as access
import mcp_auth
import mcp_actions
import documents_permissions as permissions
from request_security import same_origin_write
import ratelimit as rl
import storage as st
import tzutil as tz


def csrf(request):
    return hmac.new(auth._secret(), ('integration-access:' + request.cookies.get(auth.COOKIE_NAME,'')).encode(),
                    hashlib.sha256).hexdigest()


# Explicit allowlist: never expose the hosting environment or credential material.
MCP_PILOTS = (
    ('Mark own work notice read (browser confirmation)', 'NOTIFICATION_WRITES', 'notifications:mark_read', ('mark_my_notification_read', 'get_mcp_operation')),
    ('Monthly CSM summaries', 'CSM', 'surveys:csm:read', ('get_csm_summary',)),
    ('Monthly CSM comparisons', 'CSM_TRENDS', 'surveys:csm_trends:read', ('compare_csm_months',)),
    ('Quarterly activity summaries', 'ACTIVITY_SURVEYS', 'surveys:activities:read', ('get_activity_survey_summary',)),
    ('Individual activity scorecards', 'ACTIVITY_DETAILS', 'surveys:activity_details:read', ('find_survey_activities', 'get_activity_survey_detail')),
    ('Unit activity summaries', 'UNIT_SURVEYS', 'surveys:units:read', ('find_survey_units', 'get_unit_activity_survey_summary')),
    ('Unit quarterly comparisons', 'UNIT_TRENDS', 'surveys:unit_trends:read', ('compare_unit_activity_surveys',)),
    ('Resource-person scores at one activity', 'PERSON_ACTIVITY_SURVEYS', 'surveys:person_activities:read', ('get_resource_person_activity_survey',)),
    ('Annual resource-person summaries', 'RESOURCE_PERSON_SURVEYS', 'surveys:resource_persons:read', ('get_resource_person_survey_summary',)),
    ('Resource-person discovery and comparisons', 'RESOURCE_PERSON_TRENDS', 'surveys:resource_person_trends:read', ('find_survey_resource_persons', 'compare_resource_person_surveys')),
    ('Unread work notices', 'NOTIFICATIONS', 'notifications:read', ('list_my_notifications',)),
    ('Room availability', 'AVAILABILITY', 'calendar:read', ('get_room_availability',)),
)


def make_router(templates, get_conn, mcp_readiness=None):
    router = APIRouter()
    private = {'Cache-Control':'private, no-store','Referrer-Policy':'same-origin'}

    def payload(request):
        return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))

    def screen(request, *, admin=False, error='', status=200, secret=''):
        conn = get_conn()
        try:
            entries,next_cursor = access.listing(conn,payload(request),admin,request.query_params.get('before',''))
            now = int(time.time())
            for row in entries:
                row['scope_labels'] = [access.SCOPES[s] for s in json.loads(row['scopes_json'])]
                row['status'] = 'Revoked' if row['revoked_at'] is not None else 'Expired' if row['expires_at']<=now else 'Active'
                for field in ('issued_at','expires_at','last_used_at'):
                    row[field+'_label'] = datetime.fromtimestamp(row[field],timezone.utc).astimezone(tz.LOCAL_TZ).isoformat(timespec='minutes') if row[field] else 'Not used yet'
            mcp_entries = [] if admin else mcp_auth.owner_grants(conn, request.state.user['id'])
            for row in mcp_entries:
                row['status'] = 'Revoked' if row['revoked_at'] is not None else 'Expired' if row['expires_at']<=now else 'Active'
                for field in ('created_at','expires_at'):
                    row[field+'_label'] = datetime.fromtimestamp(row[field],timezone.utc).astimezone(tz.LOCAL_TZ).isoformat(timespec='minutes')
            return templates.TemplateResponse(request,'integration_access.html',
                {'show_scope':False,'entries':entries,'admin':admin,'error':error,'secret':secret,
                 'csrf':csrf(request),'scopes':access.SCOPES,'next_cursor':next_cursor,
                 'mcp_entries':mcp_entries}, status_code=status,headers=private)
        except access.InvalidCredential:
            return HTMLResponse('Sign in with the required access to manage connected tools.',status_code=403,headers=private)
        finally:
            conn.close()

    async def posted(request, create=False):
        # Bound the complete body before parsing; do not reflect any submitted secret.
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>8192:
                raise ValueError('The form is too large. Reload and try again.')
        request._body = bytes(data)
        form = await request.form(max_fields=10,max_files=0)
        allowed = {'csrf','name','scopes','days','password','consent'} if create else {'csrf'}
        if (set(form)-allowed or any(len(form.getlist(k))!=1 for k in form if k!='scopes')
                or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
            raise ValueError('The form expired or is invalid. Reload and try again.')
        return form

    @router.get('/account/integrations',response_class=HTMLResponse)
    def own(request: Request):
        return screen(request)

    @router.get('/account/integrations/mcp', response_class=HTMLResponse)
    async def readiness(request: Request):
        def own_connections():
            conn = get_conn()
            try:
                user = access._session(conn, payload(request))
                return mcp_auth.owner_grants(conn, user['id'])
            finally:
                conn.close()

        try:
            entries = await asyncio.to_thread(own_connections)
        except access.InvalidCredential:
            return HTMLResponse('Sign in again to check your connection.', status_code=403, headers=private)
        state = await mcp_readiness() if mcp_readiness else {'enabled': False, 'tools': [], 'catalog_ok': False, 'build': {}}
        now = int(time.time())
        for row in entries:
            row['status'] = 'Revoked' if row['revoked_at'] is not None else 'Refresh expired' if row['expires_at'] <= now else 'Grant active'
            row['expires_label'] = datetime.fromtimestamp(row['expires_at'], timezone.utc).astimezone(tz.LOCAL_TZ).isoformat(timespec='minutes')
        pilots = []
        for label, flag, scope, names in MCP_PILOTS:
            flag = 'CSS_MCP_' + flag + '_ENABLED'
            pilots.append({'label': label, 'flag': flag, 'scope': scope,
                           'enabled': os.environ.get(flag) == '1',
                           'registered': state['catalog_ok'] and set(names).issubset(state['tools']),
                           'names': names})
        return templates.TemplateResponse(request, 'mcp_readiness.html',
            {'show_scope': False, 'state': state, 'pilots': pilots, 'entries': entries}, headers=private)

    @router.get('/admin/integrations',response_class=HTMLResponse)
    def admin_list(request: Request):
        return screen(request,admin=True)

    def action_origin(request):
        canonical = os.environ.get('CSS_BASE_URL')
        if not canonical and os.environ.get('SPACE_HOST'):
            canonical = 'https://' + os.environ['SPACE_HOST']
        parts = access._origin(canonical or str(request.base_url))
        if parts is None:
            raise mcp_actions.ActionError('invalid_origin', 'The deployment origin is unavailable.')
        scheme, host, port = parts
        host = '[' + host + ']' if ':' in host else host
        return scheme + '://' + host + (':' + str(port) if port != (443 if scheme == 'https' else 80) else '')

    def action_screen(request, operation_id, confirm_digest=None):
        conn = get_conn()
        try:
            origin = action_origin(request)
            result = mcp_actions.browser(conn, payload(request), origin + '/mcp', origin,
                                         operation_id, confirm_digest=confirm_digest)
            return templates.TemplateResponse(request, 'mcp_action.html',
                {'show_scope': False, 'result': result, 'csrf': csrf(request)}, headers=private)
        except permissions.Denied:
            return HTMLResponse('Action not found or unavailable to you. Sign in with the account that prepared it.', status_code=404, headers=private)
        except mcp_actions.ActionError as exc:
            # All action error messages are fixed server-owned text.
            return HTMLResponse(str(exc), status_code=409, headers=private)
        finally:
            conn.close()

    @router.get('/account/integrations/mcp/actions/{operation_id}', response_class=HTMLResponse)
    def action_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id)

    @router.post('/account/integrations/mcp/actions/{operation_id}', response_class=HTMLResponse)
    async def action_confirm(request: Request, operation_id: str):
        canonical = action_origin(request)
        if not same_origin_write(request, canonical):
            return HTMLResponse('Request verification failed.', status_code=403, headers=private)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2048:
                return HTMLResponse('The confirmation form is too large.', status_code=413, headers=private)
        request._body = bytes(raw)
        form = await request.form(max_fields=3, max_files=0)
        if (set(form) != {'csrf', 'preview_digest', 'confirm'}
                or any(len(form.getlist(k)) != 1 for k in form)
                or form.get('confirm') != 'yes'
                or not hmac.compare_digest(str(form.get('csrf', '')).encode(), csrf(request).encode())):
            return HTMLResponse('The confirmation expired or is invalid. Reload the preview.', status_code=403, headers=private)
        if not rl.allow('mcp_action', str(request.state.user['id'])):
            return HTMLResponse('Too many confirmations. Retry later with the same link.', status_code=429, headers=private)
        return await asyncio.to_thread(action_screen, request, operation_id, str(form['preview_digest']))

    def create_credential(request,form):
        if not rl.allow('integration_issue',str(request.state.user['id'])):
            return screen(request,error='Too many attempts. Try again in 15 minutes.',status=429)
        if (form.get('consent')!='yes' or form.get('days') not in ('7','30','90')
                or not isinstance(form.get('password'),str) or not 1<=len(form['password'])<=1024):
            return screen(request,error='Choose access and expiry, confirm consent, and enter your current password.',status=400)
        conn = get_conn()
        try:
            identity = access._session(conn,payload(request))
            account = st.get_admin_user_by_id(conn,identity['id'])
            if not auth.verify_password(form['password'],account['pw_hash'],account['salt']):
                return screen(request,error='The password could not be verified.',status=400)
            token = access.issue(conn,payload(request),account['pw_hash'],form.get('name',''),
                form.getlist('scopes'),int(form['days']),access.audience(request))
        except (ValueError,UnicodeError):
            return screen(request,error='The credential could not be created. Check your access, tool name and selected permissions.',status=400)
        finally:
            conn.close()
        return screen(request,secret=token)

    @router.post('/account/integrations')
    async def create(request: Request):
        try:
            form = await posted(request,create=True)
        except ValueError:
            return await asyncio.to_thread(screen,request,error='The form expired or is invalid. Reload and try again.',status=400)
        # Database, PBKDF2 and rendering stay on one worker, off the event loop.
        return await asyncio.to_thread(create_credential,request,form)

    def revoke_credential(request,key,admin):
        conn = get_conn()
        try:
            access.revoke(conn,payload(request),key,admin)
        except access.InvalidCredential:
            return screen(request,admin=admin,error='Credential not found or unavailable to you.',status=404)
        finally:
            conn.close()
        return RedirectResponse('/admin/integrations' if admin else '/account/integrations',status_code=303,headers=private)

    async def remove(request,key,admin):
        try:
            await posted(request)
        except ValueError:
            return await asyncio.to_thread(screen,request,admin=admin,error='The form expired or is invalid. Reload and try again.',status=400)
        return await asyncio.to_thread(revoke_credential,request,key,admin)

    @router.post('/account/integrations/{key}/revoke')
    async def own_revoke(request: Request,key: str):
        return await remove(request,key,False)

    @router.post('/admin/integrations/{key}/revoke')
    async def admin_revoke(request: Request,key: str):
        return await remove(request,key,True)

    @router.post('/account/mcp/{key}/revoke')
    async def own_mcp_revoke(request: Request,key: str):
        try:
            await posted(request)
            conn = get_conn()
            try:
                mcp_auth.revoke_owner_grant(conn, request.state.user['id'], key)
            finally:
                conn.close()
        except ValueError:
            return await asyncio.to_thread(screen, request,
                error='Connection not found or form expired. Reload and try again.', status=400)
        return RedirectResponse('/account/integrations',status_code=303,headers=private)

    return router
