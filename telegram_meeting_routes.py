"""Signed-in deterministic fields; final approval stays in the linked private bot."""
import hmac
import secrets
import re
import json

from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse,RedirectResponse

import auth
from documents_storage import rows
import office_calendar as oc
import rooms
import ratelimit
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
from telegram_link_routes import PRIVATE,csrf


def make_router(templates,get_conn):
    router=APIRouter()
    def payload(request):return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))

    def screen(request,error='',status=200,values=None):
        conn=get_conn()
        try:
            user=links.current(conn,payload(request));identifier=(values or {}).get('origin') or request.query_params.get('origin','')
            origins=rows(conn,"SELECT * FROM telegram_meeting_origin WHERE account_id=? AND action='calendar.create' AND expires_at>? ORDER BY created_at DESC LIMIT 20",
                         (user['id'],links.stamp(bot.now_utc())))
            selected=None
            if identifier:
                ctx=meetings.origin(conn,user,identifier,bot.now_utc());selected=identifier
            ready=[]
            for item in origins:
                try:
                    ctx=meetings.origin(conn,user,item['id'],bot.now_utc())
                    ready.append({'id':item['id'],'label':'Private chat' if ctx['chat_id']>0 else 'Group '+str(ctx['chat_id'])+' · topic '+str(ctx['topic_id'] or 0)})
                except ValueError:pass
            prepared_operation=request.query_params.get('operation','')
            operation_row=rows(conn,'SELECT context_json FROM telegram_operation WHERE operation_id=? AND actor_id=? AND action=?',
                                (prepared_operation,user['id'],'calendar.create'))
            if not re.fullmatch('[a-f0-9]{32}',prepared_operation) or not operation_row or not operation_row[0]['context_json']:
                prepared_operation=None
            return templates.TemplateResponse(request,'telegram_meeting.html',{'show_scope':False,'csrf':csrf(request),'webhook_pull':bot.reply_transport()=='webhook' and (not prepared_operation or json.loads(operation_row[0]['context_json'])['chat_id']>0),
                'prepared_operation':prepared_operation,
                'origins':ready,'selected':selected,'values':values or {},'key':secrets.token_hex(16),'people':oc.people_choices(conn) if ready else [],
                'units':oc.unit_choices(conn) if ready else [],
                'room_ready':bool(ready) and all(links.authorized(conn,user['id'],scope) for scope in ('rooms.read','rooms.request')),
                'slots':rooms.list_slots(conn) if ready and links.authorized(conn,user['id'],'rooms.request') else [],'error':error,'queued':bool(request.query_params.get('queued')),'already':bool(request.query_params.get('already'))},status_code=status,headers=PRIVATE)
        except ValueError:
            return HTMLResponse('Meeting request unavailable. Sign in again or send /meeting in the intended conversation.',status_code=403,headers=PRIVATE)
        finally:conn.close()

    @router.get(meetings.PATH)
    def page(request:Request):return screen(request)

    @router.post(meetings.PATH)
    async def prepare(request:Request):
        form=None
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>8192:raise ValueError('The form is too large.')
            request._body=bytes(body)
            form=await request.form(max_fields=30,max_files=0)
            if (set(form)-{'csrf','origin','key','title','day','start_time','end_time','venue','audience','owner_org_id','people','room_request','room_from','room_to'}
                    or any(len(form.getlist(k))!=1 for k in form if k!='people')
                    or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
                raise ValueError('The form expired or is invalid. Reload and try again.')
            if not ratelimit.allow('integration_issue',str(request.state.user['id'])):
                return screen(request,'Too many previews. Try again in 15 minutes.',429)
            conn=get_conn()
            try:
                user=links.current(conn,payload(request))
                ctx=meetings.origin(conn,user,str(form.get('origin','')),bot.now_utc())
                fields={k:str(form.get(k,'')) for k in ('title','day','start_time','end_time','venue','audience','owner_org_id')}
                fields['people']=[str(v) for v in form.getlist('people')]
                if form.get('room_request'):
                    if form['room_request']!='1':raise ValueError('Choose the optional room request explicitly.')
                    fields['room']={'from_time':str(form.get('room_from','')),'to_time':str(form.get('room_to',''))}
                result=actions.issue(conn,ctx,meetings.ACTION,str(form.get('key','')),fields,bot.now_utc())
            finally:conn.close()
        except ValueError as error:
            values={k:str(form.get(k,'')) for k in ('origin','title','day','start_time','end_time','venue','audience','owner_org_id','room_request','room_from','room_to')} if form else None
            if values is not None:values['people']=form.getlist('people')
            return screen(request,str(error),400,values)
        return RedirectResponse(meetings.PATH+('?already=1' if result.get('receipt') else '?queued=1')+'&operation='+result['operation_id'],status_code=303,headers=PRIVATE)
    return router
