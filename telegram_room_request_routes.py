"""Signed-in deterministic fields; final approval stays in the linked private bot."""
import hmac
import secrets

from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse,RedirectResponse

import auth
from documents_storage import rows
import rooms
import ratelimit
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_room_requests as room_requests
from telegram_link_routes import PRIVATE,csrf


def make_router(templates,get_conn):
    router=APIRouter()
    def payload(request):return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))

    def screen(request,error='',status=200,values=None):
        conn=get_conn()
        try:
            user=links.current(conn,payload(request));identifier=(values or {}).get('origin') or request.query_params.get('origin','')
            origins=rows(conn,"SELECT * FROM telegram_meeting_origin WHERE account_id=? AND action='rooms.request' AND expires_at>? ORDER BY created_at DESC LIMIT 20",
                         (user['id'],links.stamp(bot.now_utc())))
            selected=None
            if identifier:
                ctx=meetings.origin(conn,user,identifier,bot.now_utc(),room_requests.ACTION);selected=identifier
            ready=[]
            for item in origins:
                try:
                    ctx=meetings.origin(conn,user,item['id'],bot.now_utc(),room_requests.ACTION)
                    ready.append({'id':item['id'],'label':'Private chat' if ctx['chat_id']>0 else 'Group '+str(ctx['chat_id'])+' · topic '+str(ctx['topic_id'] or 0)})
                except ValueError:pass
            return templates.TemplateResponse(request,'telegram_room_request.html',{'show_scope':False,'csrf':csrf(request),
                'origins':ready,'selected':selected,'values':values or {},'key':secrets.token_hex(16),'slots':rooms.list_slots(conn) if ready else [],'error':error,'queued':bool(request.query_params.get('queued')),'already':bool(request.query_params.get('already'))},status_code=status,headers=PRIVATE)
        except ValueError:
            return HTMLResponse('Room request unavailable. Sign in again or send /room_request in the intended conversation.',status_code=403,headers=PRIVATE)
        finally:conn.close()

    @router.get(room_requests.PATH)
    def page(request:Request):return screen(request)

    @router.post(room_requests.PATH)
    async def prepare(request:Request):
        form=None
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>8192:raise ValueError('The form is too large.')
            request._body=bytes(body)
            form=await request.form(max_fields=30,max_files=0)
            if (set(form)-{'csrf','origin','key','entry_id','from_time','to_time'}
                    or any(len(form.getlist(k))!=1 for k in form )
                    or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
                raise ValueError('The form expired or is invalid. Reload and try again.')
            if not ratelimit.allow('integration_issue',str(request.state.user['id'])):
                return screen(request,'Too many previews. Try again in 15 minutes.',429)
            conn=get_conn()
            try:
                user=links.current(conn,payload(request))
                ctx=meetings.origin(conn,user,str(form.get('origin','')),bot.now_utc(),room_requests.ACTION)
                fields={k:str(form.get(k,'')) for k in ('entry_id','from_time','to_time')}
                result=actions.issue(conn,ctx,room_requests.ACTION,str(form.get('key','')),fields,bot.now_utc())
            finally:conn.close()
        except ValueError as error:
            values={k:str(form.get(k,'')) for k in ('origin','entry_id','from_time','to_time')} if form else None
            return screen(request,str(error),400,values)
        return RedirectResponse(room_requests.PATH+('?already=1' if result.get('receipt') else '?queued=1'),status_code=303,headers=PRIVATE)
    return router
