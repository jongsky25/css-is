"""Focused intake screens, authenticated with the existing Documents session."""
import asyncio
import json
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
import documents as d
import documents_permissions as p
import documents_intake as intake
import documents_gmail_settings as gmail_settings
from documents_routes import csrf
from documents_storage import rows
import tzutil as tz


def make_router(templates,get_conn):
    router=APIRouter()

    def context(request,conn,**values):
        user=p.actor(conn,request.state.user)
        return {'nav_active':'documents','enabled':d.enabled(conn),'csrf':csrf(request),'error':'',
                'submitted':{},'intake_access':intake.can_review(conn,user),'is_director':p.director(conn,user),
                'workflow_admin':p.has_role(conn,user,'workflow_admin'),'archive_admin':p.has_role(conn,user,'workflow_admin'),**values}

    def render(request,conn,template_name,status=200,**values):
        response=templates.TemplateResponse(request,'documents/'+template_name+'.html',context(request,conn,**values),status_code=status)
        response.headers['Cache-Control']='no-store'
        return response

    def queue_page(request,conn,error='',status=200):
        user=intake.reviewer(conn,request.state.user)
        page=max(1,int(request.query_params.get('page','1')))
        state=request.query_params.get('state','waiting')
        if state not in ('waiting','attention','registered','dismissed'): state='waiting'
        items,more,counts=intake.list_page(conn,user,state,page)
        return render(request,conn,'intake_queue',status,items=items,more=more,page=page,state=state,
                      counts=counts,config=intake.settings(conn),now=tz.now_iso(),error=error)

    def review_page(request,conn,item_id,error='',status=200,values=None):
        item=intake.get(conn,request.state.user,item_id)
        if item['email_id'] and not item['email_primary']:
            return RedirectResponse('/documents/intake/'+str(item['email']['primary_intake_id']),status_code=303)
        if item['document_id']:
            d.get(conn,request.state.user,item['document_id'])
            return RedirectResponse('/documents/'+str(item['document_id']),status_code=303)
        editable=item['state'] in ('waiting','attention') and item['claimed_by']==request.state.user['id'] and (item['claim_until'] or '')>tz.now_iso()
        candidates=rows(conn,"""SELECT id,original_name,revision FROM document_intake WHERE id<>? AND state='waiting' AND email_id IS NULL
            AND (claimed_by IS NULL OR claimed_by=? OR claim_until<=?) ORDER BY id LIMIT 30""",
                        (item_id,request.state.user['id'],tz.now_iso()))
        possible_duplicates=[doc for doc in rows(conn,'''SELECT DISTINCT d.* FROM document d JOIN document_intake i
            ON i.document_id=d.id WHERE i.content_key=? AND i.id<>? LIMIT 30''',(item['content_key'],item_id))
            if p.can_view(conn,request.state.user,doc)]
        return render(request,conn,'intake_review',status,item=item,values=item['draft'] if values is None else values,
                      editable=editable,candidates=candidates,error=error,possible_duplicates=possible_duplicates,
                      claimant=conn.execute('SELECT username FROM admin_user WHERE id=?',(item['claimed_by'],)).fetchone(),now=tz.now_iso())

    async def posted(request):
        import hmac
        import auth
        from urllib.parse import parse_qs
        raw=await request.body()
        if len(raw)>65536: raise ValueError('Review form is too large.')
        data={k:v[-1] for k,v in parse_qs(raw.decode(),keep_blank_values=True).items()}
        if not request.cookies.get(auth.COOKIE_NAME) or not hmac.compare_digest(data.pop('csrf',''),csrf(request)):
            raise p.Denied('The form expired. Reload and try again.')
        return data

    @router.get('/documents/intake',response_class=HTMLResponse)
    def queue(request:Request):
        conn=get_conn()
        try: return queue_page(request,conn)
        except (ValueError,p.Denied) as exc: return HTMLResponse(str(exc),status_code=403 if isinstance(exc,p.Denied) else 400)
        finally: conn.close()

    @router.get('/documents/intake/settings',response_class=HTMLResponse)
    def settings_page(request:Request):
        conn=get_conn()
        try:
            user=intake.reviewer(conn,request.state.user)
            d.require(p.has_role(conn,user,'workflow_admin'))
            return render(request,conn,'intake_settings',config=intake.settings(conn),
                          gmail=gmail_settings.settings(conn),records_accounts=gmail_settings.records_accounts(conn))
        except p.Denied as exc: return HTMLResponse(str(exc),status_code=403)
        finally: conn.close()

    @router.post('/documents/intake/settings')
    async def configure(request:Request):
        conn=get_conn()
        try:
            data=await posted(request)
            intake.configure(conn,request.state.user,data)
            return RedirectResponse('/documents/intake',status_code=303)
        except (ValueError,p.Denied) as exc:
            return HTMLResponse(str(exc),status_code=403 if isinstance(exc,p.Denied) else 400)
        finally: conn.close()

    @router.post('/documents/intake/settings/gmail')
    async def configure_gmail(request:Request):
        conn=get_conn()
        data={}
        try:
            gmail_settings.administrator(conn,request.state.user)
            data=await posted(request)
            gmail_settings.configure(conn,request.state.user,data)
            return RedirectResponse('/documents/intake/settings?gmail_saved=1#gmail',status_code=303)
        except p.Denied as exc:
            return HTMLResponse(str(exc),status_code=403)
        except ValueError as exc:
            # Preserve harmless form values; credentials are never accepted here.
            values={key:data.get(key,'') for key in ('mailbox','actor_id','enabled')}
            return render(request,conn,'intake_settings',400,config=intake.settings(conn),
                          gmail=gmail_settings.settings(conn),records_accounts=gmail_settings.records_accounts(conn),
                          gmail_values=values,error=str(exc))
        finally: conn.close()

    def sync_background():
        conn=get_conn()
        try: intake.sync(conn)
        finally: conn.close()

    @router.post('/documents/intake/sync')
    async def sync(request:Request,background_tasks:BackgroundTasks):
        conn=get_conn()
        try:
            await posted(request)
            intake.reviewer(conn,request.state.user);intake._active(conn)
            background_tasks.add_task(sync_background)
            return RedirectResponse('/documents/intake?checking=1',status_code=303)
        except (ValueError,p.Denied) as exc:
            return HTMLResponse(str(exc),status_code=403 if isinstance(exc,p.Denied) else 400)
        finally: conn.close()

    @router.get('/documents/intake/{item_id:int}',response_class=HTMLResponse)
    def review(request:Request,item_id:int):
        conn=get_conn()
        try: return review_page(request,conn,item_id)
        except p.Denied as exc: return HTMLResponse(str(exc),status_code=403)
        finally: conn.close()

    def handle(request,item_id,data):
        conn=get_conn()
        try:
            action=data.get('action','save');rev=int(data['revision']);user=request.state.user
            if action=='requeue': intake.requeue(conn,user,item_id,rev)
            elif action=='claim': intake.claim(conn,user,item_id,rev)
            elif action in ('register','register_next'):
                attachments=[(key.split(':')[1],value) for key,value in data.items() if key.startswith('attach:')]
                doc=intake.register(conn,user,item_id,rev,data,attachments)
                if action=='register_next':
                    following=rows(conn,'''SELECT id,revision FROM document_intake WHERE state='waiting' AND email_primary=1
                        AND (claimed_by IS NULL OR claimed_by=? OR claim_until<=?) ORDER BY id LIMIT 1''',
                        (user['id'],tz.now_iso()))
                    if following:
                        try:
                            intake.claim(conn,user,following[0]['id'],following[0]['revision'])
                            return RedirectResponse('/documents/intake/'+str(following[0]['id'])+'?registered=1',status_code=303)
                        except d.Conflict: pass
                    return RedirectResponse('/documents/intake?registered=1',status_code=303)
                return RedirectResponse('/documents/'+str(doc['id']),status_code=303)
            elif action in ('save','release','attention','dismiss','extract','reread','apply'):
                saved=intake.save(conn,user,item_id,rev,data,action if action in ('release','attention','dismiss') else 'save')
                if action in ('extract','reread'): intake.extract(conn,user,item_id,saved['revision'],force=action=='reread')
                if action=='apply':
                    # Apply to empty inputs only; never overwrite a reviewer's corrections.
                    values=saved['draft']
                    for key,value in saved['suggestions'].get('suggestions',{}).items():
                        if key in intake.FIELDS and not values.get(key): values[key]=value
                    intake.save(conn,user,item_id,saved['revision'],values)
                if action in ('release','attention','dismiss'):
                    return RedirectResponse('/documents/intake',status_code=303)
            else: raise ValueError('Choose a supported review action.')
            return RedirectResponse('/documents/intake/'+str(item_id),status_code=303)
        except (ValueError,KeyError) as exc:
            if conn.in_transaction: conn.rollback()
            if isinstance(exc,p.Denied): return HTMLResponse(str(exc),status_code=403)
            # Reload current permissions before displaying submitted content.
            return review_page(request,conn,item_id,error=str(exc),status=409 if isinstance(exc,d.Conflict) else 400,
                               values={k:v for k,v in data.items() if k in intake.FIELDS})
        except Exception:
            if conn.in_transaction: conn.rollback()
            return review_page(request,conn,item_id,error='Drive could not complete this action. Your saved review is retained; retry or enter details manually.',status=400)
        finally: conn.close()

    @router.post('/documents/intake/{item_id:int}')
    async def review_action(request:Request,item_id:int):
        try: data=await posted(request)
        except (ValueError,p.Denied) as exc: return HTMLResponse(str(exc),status_code=403 if isinstance(exc,p.Denied) else 400)
        # OCR and Drive checks execute off the event loop, with a connection owned
        # by that worker thread. No SQLite transaction spans external I/O.
        return await asyncio.to_thread(handle,request,item_id,data)

    return router
