"""Browser-only consent, one-time disclosure and revocation of read credentials."""
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import integration_access as access
import ratelimit as rl
import storage as st
import tzutil as tz


def csrf(request):
    return hmac.new(auth._secret(), ('integration-access:' + request.cookies.get(auth.COOKIE_NAME,'')).encode(),
                    hashlib.sha256).hexdigest()


def make_router(templates, get_conn):
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
            return templates.TemplateResponse(request,'integration_access.html',
                {'show_scope':False,'entries':entries,'admin':admin,'error':error,'secret':secret,
                 'csrf':csrf(request),'scopes':access.SCOPES,'next_cursor':next_cursor}, status_code=status,headers=private)
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

    @router.get('/admin/integrations',response_class=HTMLResponse)
    def admin_list(request: Request):
        return screen(request,admin=True)

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

    return router
