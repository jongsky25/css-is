"""Signed-in Telegram consent/status/disconnect. No credentials in URL parameters."""
import hashlib
import hmac

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import ratelimit
import telegram_bot as bot
import telegram_links as links

PRIVATE = {'Cache-Control': 'private, no-store', 'Referrer-Policy': 'same-origin'}


def csrf(request):
    return hmac.new(auth._secret(), ('telegram-link:'+request.cookies.get(auth.COOKIE_NAME,'')).encode(), hashlib.sha256).hexdigest()


def make_router(templates, get_conn):
    router = APIRouter()

    def payload(request):
        return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))

    def screen(request, error='', status=200):
        conn = get_conn()
        try:
            user, connection, grants, pending = links.status(conn, payload(request), bot.now_utc())
            return templates.TemplateResponse(request, 'telegram_link.html',
                {'show_scope': False, 'account': user, 'connection': connection, 'grants': grants,
                 'pending': pending, 'ready': bool(links.available()), 'csrf': csrf(request),
                 'scopes': links.SCOPES, 'error': error,
                 'rooms_ready': bool(links.authorized(conn,user['id'],'rooms.read') and links.origin() and len(links.origin())<=200 and bot.storage.enabled('inbound') and bot.storage.enabled('delivery')),
                 'calendar_ready': bool(links.authorized(conn,user['id'],'calendar.read') and links.origin() and len(links.origin())<=200 and bot.storage.enabled('inbound') and bot.storage.enabled('delivery'))}, status_code=status, headers=PRIVATE)
        except ValueError:
            return HTMLResponse('Sign in again to manage your private Telegram connection.', status_code=403, headers=PRIVATE)
        finally:
            conn.close()

    @router.get('/account/telegram')
    def page(request: Request):
        return screen(request)

    async def posted(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise ValueError('The form is too large.')
        request._body = bytes(body)
        form = await request.form(max_fields=8, max_files=0)
        if (set(form)-{'csrf','code','scopes','consent'} or
                any(len(form.getlist(k)) != 1 for k in form if k != 'scopes') or
                not hmac.compare_digest(str(form.get('csrf','')).encode(), csrf(request).encode())):
            raise ValueError('The form expired or is invalid. Reload and try again.')
        return form

    @router.post('/account/telegram/link')
    async def link(request: Request):
        try:
            form = await posted(request)
            if not ratelimit.allow('integration_issue', str(request.state.user['id'])):
                return screen(request, 'Too many attempts. Try again in 15 minutes.', 429)
            if form.get('consent') != 'yes':
                raise ValueError('Confirm that you want to link your own private Telegram account.')
            conn = get_conn()
            try:
                links.claim(conn, payload(request), str(form.get('code','')), form.getlist('scopes'), bot.now_utc())
            finally:
                conn.close()
        except ValueError as error:
            return screen(request, str(error), 400)
        return RedirectResponse('/account/telegram', status_code=303, headers=PRIVATE)

    @router.post('/account/telegram/disconnect')
    async def disconnect(request: Request):
        try:
            await posted(request)
            conn = get_conn()
            try:
                links.disconnect(conn, payload(request), bot.now_utc())
            finally:
                conn.close()
        except ValueError:
            return screen(request, 'The form expired or is invalid. Reload and try again.', 400)
        return RedirectResponse('/account/telegram', status_code=303, headers=PRIVATE)

    return router
