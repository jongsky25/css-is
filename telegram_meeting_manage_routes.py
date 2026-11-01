"""Signed-in, script-free preparation of private meeting management previews."""
import hmac
import json
import re
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
from documents_storage import rows
import ratelimit
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meeting_manage as manage
import telegram_meetings as meetings
from telegram_link_routes import PRIVATE, csrf


def make_router(templates,get_conn, *, manager=manage, template="telegram_meeting_manage.html",
                target="entry_id", dated_mode="reschedule", date_fields=("day","start_time","end_time"), resource="Meeting",
                field_sets=None, form_context=None, max_body=4096, max_fields=8):
    router=APIRouter()
    def fields_for(mode):return field_sets[mode] if field_sets else ((target,*date_fields) if mode==dated_mode else (target,))
    def screen(request,mode,error='',status=200,values=None):
        if mode not in manager.MODES:return HTMLResponse('Action unavailable.',status_code=404,headers=PRIVATE)
        action=manager.MODES[mode];conn=get_conn()
        try:
            user=links.current(conn,auth.parse_token(request.cookies.get(auth.COOKIE_NAME)))
            identifier=(values or {}).get('origin') or request.query_params.get('origin','')
            if identifier:meetings.origin(conn,user,identifier,bot.now_utc(),action)
            origins=[]
            for item in rows(conn,'SELECT id FROM telegram_meeting_origin WHERE account_id=? AND action=? AND expires_at>? ORDER BY created_at DESC LIMIT 20',
                             (user['id'],action,links.stamp(bot.now_utc()))):
                try:
                    meetings.origin(conn,user,item['id'],bot.now_utc(),action)
                    origins.append(item['id'])
                except ValueError:pass
            operation=request.query_params.get('operation','');prepared=None
            if re.fullmatch('[a-f0-9]{32}',operation):
                found=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=? AND actor_id=? AND action=?',
                           (operation,user['id'],action))
                if found and found[0]['context_json']:
                    ctx=json.loads(found[0]['context_json'])
                    current,_,_=actions.authority(conn,ctx,action)
                    if current['id']==user['id']:prepared=found[0]
            return templates.TemplateResponse(request,template,
                {'show_scope':False,'mode':mode,'action_path':manager.PATH+mode,'origins':origins,'selected':identifier,
                 'values':values or {},'key':secrets.token_hex(16),'csrf':csrf(request),'prepared':prepared,'error':error,
                 **(form_context(conn,user,mode) if form_context and origins else {})},
                status_code=status,headers=PRIVATE)
        except ValueError:
            return HTMLResponse(resource+' action unavailable. Sign in again and start the action in your private Telegram chat.',status_code=403,headers=PRIVATE)
        finally:conn.close()

    @router.get(manager.PATH+'{mode}')
    def page(request:Request,mode:str):return screen(request,mode)

    @router.post(manager.PATH+'{mode}')
    async def prepare(request:Request,mode:str):
        if mode not in manager.MODES:return HTMLResponse('Action unavailable.',status_code=404,headers=PRIVATE)
        form=None
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>max_body:raise ValueError('The form is too large.')
            request._body=bytes(body);form=await request.form(max_fields=max_fields,max_files=0)
            fields=fields_for(mode)
            if (set(form)!={'csrf','origin','key',*fields} or any(len(form.getlist(k))!=1 for k in form)
                    or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
                raise ValueError('The form expired or is invalid. Reload and try again.')
            if not ratelimit.allow('integration_issue',str(request.state.user['id'])):
                return screen(request,mode,'Too many previews. Try again later.',429)
            conn=get_conn()
            try:
                user=links.current(conn,auth.parse_token(request.cookies.get(auth.COOKIE_NAME)))
                ctx=meetings.origin(conn,user,str(form['origin']),bot.now_utc(),manager.MODES[mode])
                result=actions.issue(conn,ctx,manager.MODES[mode],str(form['key']),{k:str(form[k]) for k in fields},bot.now_utc())
            finally:conn.close()
        except ValueError as error:
            values={k:str(form.get(k,'')) for k in ('origin',*fields_for(mode))} if form else None
            return screen(request,mode,str(error),400,values)
        return RedirectResponse(manager.PATH+mode+'?operation='+result['operation_id'],status_code=303,headers=PRIVATE)
    return router
