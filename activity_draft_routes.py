"""Ordinary owner-only activity draft screens, sharing the MCP save service."""
import hmac
import os
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import activity_creation
import activity_drafts as drafts
import auth
import documents_permissions as permissions
from documents_storage import transaction
import integration_access_routes as integration_routes
from request_security import same_origin_write
import ratelimit as rl
import storage as st


def make_router(templates,get_conn):
    router=APIRouter()
    private={'Cache-Control':'private, no-store','Referrer-Policy':'same-origin'}

    def actor(conn,request):
        payload=auth.parse_token(request.cookies.get(auth.COOKIE_NAME))
        user=st.session_actor(conn,payload) if payload else None
        if not user:raise permissions.Denied('Sign in again.')
        return drafts.actor(conn,user)

    def new_page(request,conn,*,f=None,key=None,error='',status=200):
        lo,hi=drafts.scheduling.date_bounds()
        return templates.TemplateResponse(request,'activity_draft_new.html',
            {'show_scope':False,'f':f or {},'draft_key':key or str(uuid4()),'csrf':integration_routes.csrf(request),
             'sections':st.list_org_units(conn,level='section'),'date_min':lo,'date_max':hi,'error':error},
            status_code=status,headers=private)

    @router.get('/activity-drafts',response_class=HTMLResponse)
    def collection(request:Request,before:int|None=None):
        conn=get_conn()
        try:
            user=actor(conn,request);page=drafts.listing(conn,user,before=before)
            return templates.TemplateResponse(request,'activity_draft_list.html',{'show_scope':False,'page':page},headers=private)
        except (permissions.Denied,ValueError):return HTMLResponse('Private activity drafts unavailable.',status_code=404,headers=private)
        finally:conn.close()

    @router.get('/activity-drafts/new',response_class=HTMLResponse)
    def new(request:Request):
        conn=get_conn()
        try:actor(conn,request);return new_page(request,conn)
        except permissions.Denied:return HTMLResponse('Private activity drafts unavailable.',status_code=404,headers=private)
        finally:conn.close()

    @router.post('/activity-drafts',response_class=HTMLResponse)
    async def save(request:Request):
        canonical=os.environ.get('CSS_BASE_URL') or ('https://'+os.environ['SPACE_HOST'] if os.environ.get('SPACE_HOST') else None)
        if not same_origin_write(request,canonical):return HTMLResponse('Request verification failed.',status_code=403,headers=private)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>8192:return HTMLResponse('Draft form too large.',status_code=413,headers=private)
        request._body=bytes(raw)
        form=await request.form(max_fields=6,max_files=0)
        if (set(form)!={'csrf','operation_key','activity_name','event_date','section_id','venue'}
                or any(len(form.getlist(k))!=1 for k in form)
                or not hmac.compare_digest(str(form.get('csrf','')).encode(),integration_routes.csrf(request).encode())):
            return HTMLResponse('Draft form verification failed.',status_code=403,headers=private)
        conn=get_conn()
        try:
            user=actor(conn,request)
            if not rl.allow('mcp_action',str(user['id'])):return HTMLResponse('Too many saves. Retry with the same draft key.',status_code=429,headers=private)
            f={k:str(form[k]) for k in ('activity_name','event_date','section_id','venue')}
            try:
                if not f['section_id'].isascii() or not f['section_id'].isdigit():raise ValueError
                values={**f,'section_id':int(f['section_id'])}
                with transaction(conn):saved=drafts.save_in_transaction(conn,user,values,operation_key=str(form['operation_key']))
            except permissions.Denied:raise
            except ValueError as exc:
                error=(str(exc) if isinstance(exc,drafts.Conflict) else
                    'Review the title, activity date, current section and venue. Saving creates only a private draft.')
                if isinstance(exc,drafts.Conflict) and 'different private draft' in error:
                    error='This form already saved a draft. Start a new private draft to save different fields.'
                return new_page(request,conn,f=f,key=str(form['operation_key']),
                    error=error,status=409 if isinstance(exc,drafts.Conflict) else 400)
            return RedirectResponse('/activity-drafts/'+saved['operation_key'],status_code=303,headers=private)
        except permissions.Denied:return HTMLResponse('Private activity draft unavailable.',status_code=404,headers=private)
        finally:conn.close()

    @router.get('/activity-drafts/{draft_key}',response_class=HTMLResponse)
    def source(request:Request,draft_key:str):
        conn=get_conn()
        try:
            saved=drafts.get(conn,actor(conn,request),draft_key)
            try:current=drafts.context(conn,actor(conn,request),saved['fields']);loadable=True
            except ValueError:current=None;loadable=False
            created=activity_creation.lookup(conn,actor(conn,request),draft_key)
            created_url=None
            if created:
                try:
                    activity_creation.live_source(conn,actor(conn,request),created)
                    created_url='/activities/'+created['event_token']+'/manage'
                except ValueError:
                    pass
            return templates.TemplateResponse(request,'activity_draft_source.html',
                {'show_scope':False,'draft':saved,'loadable':loadable,'created':created,'created_url':created_url,
                 'section_changed':bool(current and current['section']!=saved['section'])},headers=private)
        except (permissions.Denied,ValueError):return HTMLResponse('Private activity draft unavailable.',status_code=404,headers=private)
        finally:conn.close()

    return router
