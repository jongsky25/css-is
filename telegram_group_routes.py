"""Signed-in group registration, explicit audience consent and emergency pause."""
import asyncio
import hmac

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
from documents_storage import rows
import ratelimit
import telegram_bot as bot
import telegram_groups as groups
import telegram_links as links
from telegram_link_routes import PRIVATE, csrf

PATH='/account/telegram/groups'


def make_router(templates,get_conn):
    router=APIRouter()
    def payload(request):
        return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))

    def screen(request,error='',status=200):
        conn=get_conn()
        try:
            user=links.current(conn,payload(request))
            own=rows(conn,'SELECT * FROM telegram_group WHERE owner_account_id=? OR ?=\'admin\' ORDER BY id DESC LIMIT 50',(user['id'],user['role']))
            pending=rows(conn,"SELECT * FROM telegram_group_request WHERE account_id=? AND state='observed' AND expires_at>? ORDER BY created_at DESC LIMIT 20",(user['id'],links.stamp(bot.now_utc()))) if user['role']=='admin' else []
            return templates.TemplateResponse(request,'telegram_groups.html',{'show_scope':False,'groups':own,
                'requests':pending,'is_admin':user['role']=='admin','ready':bool(bot.storage.enabled('groups') and links.available()),'csrf':csrf(request),'error':error},status_code=status,headers=PRIVATE)
        except ValueError:
            return HTMLResponse('Sign in again to manage Telegram groups.',status_code=403,headers=PRIVATE)
        finally:
            conn.close()

    @router.get(PATH)
    def page(request:Request):
        return screen(request)

    async def posted(request):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>4096:
                raise ValueError('Form too large.')
        request._body=bytes(body)
        form=await request.form(max_fields=8,max_files=0)
        if (set(form)-{'csrf','request_id','purpose','consent','group_id','generation','action'}
                or any(len(form.getlist(k))!=1 for k in form)
                or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
            raise ValueError('The form expired or is invalid. Reload and try again.')
        return form

    def mutate(request,form,register):
        conn=get_conn()
        try:
            if register:
                groups.register(conn,payload(request),str(form.get('request_id','')),str(form.get('purpose','')),form.get('consent'),bot.now_utc())
            else:
                raw=str(form.get('group_id',''))
                if not raw.isascii() or not raw.isdecimal() or len(raw)>18:
                    raise ValueError('Invalid registration.')
                groups.manage(conn,payload(request),int(raw),str(form.get('generation','')),str(form.get('action','')))
        finally:
            conn.close()

    async def change(request,register):
        try:
            form=await posted(request)
            if register and not ratelimit.allow('integration_issue',str(request.state.user['id'])):
                return await asyncio.to_thread(screen,request,'Too many attempts. Try again in 15 minutes.',429)
            await asyncio.to_thread(mutate,request,form,register)
        except ValueError as error:
            return await asyncio.to_thread(screen,request,str(error),400)
        return RedirectResponse(PATH,status_code=303,headers=PRIVATE)

    @router.post(PATH+'/register')
    async def register(request:Request):
        return await change(request,True)

    @router.post(PATH+'/manage')
    async def manage(request:Request):
        return await change(request,False)

    return router
