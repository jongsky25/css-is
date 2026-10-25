"""Current-account notification controls, usable while Telegram pilots are paused."""
import hmac

from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse,RedirectResponse

import auth
import ratelimit
import telegram_bot as bot
import telegram_links as links
import telegram_preferences as preferences
import telegram_reminders as reminders
from telegram_link_routes import PRIVATE,csrf

PATH='/account/telegram/notifications'


def make_router(templates,get_conn):
    router=APIRouter()
    def payload(request):return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))
    def screen(request,error='',status=200):
        conn=get_conn()
        try:
            user=links.current(conn,payload(request));pref=preferences.get(conn,user['id'])
            return templates.TemplateResponse(request,'telegram_preferences.html',{'show_scope':False,'prefs':pref,
                'reminders':reminders.get(conn,user['id']),'reminders_ready':reminders.enabled(),'leads':reminders.LEADS,
                'csrf':csrf(request),'saved':bool(request.query_params.get('saved')),'error':error,
                'calendar_ready':bool(bot.storage.enabled('change_notices') and bot.storage.enabled('inbound') and bot.storage.enabled('delivery') and links.available() and links.authorized(conn,user['id'],'calendar.read')),
                'rooms_ready':bool(bot.storage.enabled('change_notices') and bot.storage.enabled('inbound') and bot.storage.enabled('delivery') and links.available() and links.authorized(conn,user['id'],'rooms.read'))},status_code=status,headers=PRIVATE)
        except ValueError:return HTMLResponse('Sign in again to manage your notification preferences.',status_code=403,headers=PRIVATE)
        finally:conn.close()
    @router.get(PATH)
    def page(request:Request):return screen(request)
    @router.post(PATH)
    async def save(request:Request):
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>4096:raise ValueError('The form is too large.')
            request._body=bytes(body);form=await request.form(max_fields=12,max_files=0)
            if (set(form)-{'csrf','revision','calendar_email_expected','calendar_mode','room_mode','group_calendar','group_room','quiet_start','quiet_end'}
                    or any(len(form.getlist(k))!=1 for k in form)
                    or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())
                    or any(form.get(k) not in (None,'1') for k in ('group_calendar','group_room'))):
                raise ValueError('The form expired or is invalid. Reload and try again.')
            if not ratelimit.allow('integration_issue',str(request.state.user['id'])):return screen(request,'Too many changes. Try again later.',429)
            values={k:str(form.get(k,'')) for k in ('calendar_mode','room_mode','quiet_start','quiet_end')}
            values.update({k:form.get(k)=='1' for k in ('group_calendar','group_room')})
            conn=get_conn()
            try:preferences.save(conn,payload(request),str(form.get('revision','')),str(form.get('calendar_email_expected','')),values,bot.now_utc())
            finally:conn.close()
        except preferences.Conflict as error:return screen(request,str(error),409)
        except ValueError as error:return screen(request,str(error),400)
        return RedirectResponse(PATH+'?saved=1',status_code=303,headers=PRIVATE)
    @router.post(PATH+'/reminders')
    async def save_reminders(request:Request):
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>4096:raise ValueError('The form is too large.')
            request._body=bytes(body);form=await request.form(max_fields=6,max_files=0)
            if (set(form)!={'csrf','revision','calendar_minutes','room_minutes'}
                    or any(len(form.getlist(k))!=1 for k in form)
                    or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
                raise ValueError('The form expired or is invalid. Reload and try again.')
            if not ratelimit.allow('integration_issue',str(request.state.user['id'])):return screen(request,'Too many changes. Try again later.',429)
            conn=get_conn()
            try:reminders.save(conn,payload(request),form['revision'],form['calendar_minutes'],form['room_minutes'],bot.now_utc())
            finally:conn.close()
        except preferences.Conflict as error:return screen(request,str(error),409)
        except ValueError as error:return screen(request,str(error),400)
        return RedirectResponse(PATH+'?saved=1',status_code=303,headers=PRIVATE)
    return router
