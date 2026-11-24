"""Authenticated advisory drafts/register. All writes stay inside Office Connect."""
import json
import uuid
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import activity_advisory as aa
import activity_advisory_routes as legacy_routes
import activity_permissions
import advisory
import advisory_workflow as workflow
import advisory_review
import advisory_distribution
import advisory_new as new_flow
import documents
import documents_permissions as permissions
import storage as st


def make_router(templates, get_conn, base_url):
    router = APIRouter()

    def failure(error,request=None):
        status = 404 if isinstance(error,permissions.Denied) else 409 if isinstance(error,documents.Conflict) else 422
        # A person opening a page gets a readable page with a way back; scripts and tests keep the plain text.
        if request is not None and 'text/html' in request.headers.get('accept',''):
            return templates.TemplateResponse(request,'advisory_error.html',{
                'error':str(error),'denied':isinstance(error,permissions.Denied)},status_code=status)
        return Response(str(error),status_code=status,media_type='text/plain')

    def actor(request,conn):
        return permissions.actor(conn,getattr(request.state,'user',None))

    def show(request,conn,user,ev,*,posted=None,error='',status=200):
        raw = workflow.for_event(conn,ev['id'])
        record = workflow.get_visible(conn,user,raw['id']) if raw else None
        if not record and not activity_permissions.can_manage(user,ev,conn):
            raise permissions.Denied('Activity not found or unavailable to you.')
        stored = aa.get(conn,ev['id'])
        qr = (stored or {}).get('qr_url') or f"{base_url(request)}/e/{ev['event_token']}"
        current_source = workflow.source_hash(conn,ev)
        if record:
            values = record['payload']['content']
            unit = record['unit_id']; audience=record['payload']['audience']; external='\n'.join(record['payload']['external'])
        else:
            values = stored or aa.defaults(conn,ev,qr)
            unit = ''; audience='internal'; external=''
        expected_revision = record['revision'] if record else 0
        expected_source = current_source
        legacy_revision = (stored or {}).get('revision',0)
        operation = str(uuid.uuid4())
        summary=''
        adopt = False
        if posted is not None:
            values = {**legacy_routes._form_fields(posted),'qr_url':qr}
            unit=posted.get('unit_id',''); audience=posted.get('audience',''); external=posted.get('external','')
            summary=posted.get('summary',''); operation=posted.get('operation_key','')
            # Do not silently rebase a stale form onto a newer version.
            expected_revision=posted.get('expected_revision','')
            expected_source=posted.get('expected_source','')
            legacy_revision=posted.get('expected_legacy_revision','')
            adopt=posted.get('adopt_source')=='1'
        form_rows=list(values.get('rows') or [])
        form_rows += [('', '')]*(advisory.MAX_ROWS-len(form_rows))
        return templates.TemplateResponse(request,'advisory_draft.html',{
            'ev':ev,'record':record,'legacy':stored,'v':values,'rows':form_rows,'unit_id':str(unit),
            'audience':audience,'external':external,'summary':summary,'operation_key':operation,
            'expected_revision':expected_revision,'expected_source':expected_source,'legacy_revision':legacy_revision,
            'divisions':workflow.divisions(conn),'limits':advisory.LIMITS,'error':error,
            'available':workflow.available(conn),'can_edit':not record or (record['initiator_id']==user['id'] and record['status'] in ('draft','changes_requested')),
            'distribution':advisory_distribution.screen(conn,user,record) if record else None,
            'review':advisory_review.screen(conn,user,record,int(request.query_params.get('comments_before',0)),int(request.query_params.get('actions_before',0))) if record else None,'action_key':str(uuid.uuid4()),
            'source_changed':bool(record and workflow.digest(workflow.encoded(record['snapshot']))!=current_source),
            'adopt_source':adopt,'source_defaults':aa.defaults(conn,ev,qr),
            'history':workflow.history(conn,user,record['id'])[:10] if record else []},status_code=status)

    @router.get('/advisories',response_class=HTMLResponse)
    def register(request:Request,before:int=0,division:int=0,status:str="all",month:str="",audience:str="all"):
        conn=get_conn()
        try:
            user=actor(request,conn)
            listing=workflow.list_visible(conn,user,before=max(0,before),unit_id=max(0,division),status=status,month=month,audience=audience)
            filters={'division':division,'status':status,'month':month,'audience':audience}
            links={key:'/advisories?'+urlencode({**filters,'status':key}) for key in workflow.QUEUE_LABELS}
            return templates.TemplateResponse(request,'advisory_register.html',{
                **listing,'divisions':workflow.divisions(conn),**filters,'filter_query':urlencode(filters),'queue_links':links,'available':workflow.available(conn)})
        except ValueError as error:
            return failure(error,request)
        finally: conn.close()

    # ---- New advisory flow (Google Slides) ----

    def details_page(request,conn,user,kind,ev,*,posted=None,error='',status=200,refresh=False,field=''):
        off=new_flow.switched_on(conn)
        designs,designs_error=([],'') if off else new_flow.designs(conn,refresh=refresh)
        values=new_flow.defaults(conn,user,kind,ev)
        if posted is not None:
            values.update({k:posted.get(k,'') for k in ('title','dates','venue','message','attention','contact','link',
                'audience','external','variant','unit_id','activity_date','section_id')})
        sections=[] if kind!='new_activity' else rows_sections(conn)
        return templates.TemplateResponse(request,'advisory_new_details.html',{
            'kind':kind,'ev':ev,'v':values,'designs':designs,'designs_error':designs_error,'error':error,'off':off,'field':field,
            'divisions':workflow.divisions(conn),'sections':sections,
            'operation_key':(posted or {}).get('operation_key') or str(uuid.uuid4())},status_code=status)

    def rows_sections(conn):
        return [dict(id=r[0],name=r[1]) for r in conn.execute("SELECT id,name FROM org_unit WHERE level='section' ORDER BY name,id")
                if st.unit_is_active(conn,r[0],'section')]

    def home_page(request,conn,user,advisory_id,*,error='',reason='',status=200):
        q=request.query_params
        page=new_flow.home(conn,user,advisory_id)
        record=workflow.get_visible(conn,user,advisory_id)
        notice=''
        if q.get('made')=='1' and page['slides']: notice='Advisory created. Open it in Google Slides to write and design it.'
        if q.get('sent')=='1': notice='Sent to the Division Chief. Your section can still read and comment on it, but not edit it until it comes back.'
        if q.get('access')=='0' and not error:
            error='The advisory moved on, but who can edit the Google Slides file could not be updated. Press "Update access" to try again.'
        review=advisory_review.screen(conn,user,record,int(q.get('comments_before',0)),int(q.get('actions_before',0))) if record.get('current_revision') else None
        if review: review['actions']=[a for a in review['actions'] if a[0]!='submit']
        page['share']=new_flow.share_info(conn,user,advisory_id,base_url(request))
        return templates.TemplateResponse(request,'advisory_home.html',{**page,'notice':notice,'error':error,'reason':reason,
            'review':review,'review_record':record,'action_key':str(uuid.uuid4()),'available':workflow.available(conn),
            'distribution':advisory_distribution.screen(conn,user,record) if record.get('current_revision') else None},status_code=status)

    @router.post('/advisories/{advisory_id}/access')
    def new_access(request:Request,advisory_id:int):
        conn=get_conn()
        try:
            user=actor(request,conn); record=workflow.get_visible(conn,user,advisory_id)
            if not record.get('kind') or not new_flow.can_edit(conn,user,new_flow._record(conn,advisory_id)):
                raise permissions.Denied('Advisory not found or unavailable to you.')
            warning=new_flow.sync_access(conn,user,advisory_id)
            return RedirectResponse(f'/advisories/{advisory_id}'+('?access=0' if warning else ''),status_code=303)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/new',response_class=HTMLResponse)
    def new_choose(request:Request,pick:str='',q:str=''):
        conn=get_conn()
        try:
            user=actor(request,conn)
            activities=new_flow.activities_for(conn,user,q) if pick=='activity' else []
            return templates.TemplateResponse(request,'advisory_new.html',{
                'pick':pick,'q':q[:100],'activities':activities,'off':new_flow.switched_on(conn)})
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/new/details',response_class=HTMLResponse)
    def new_details(request:Request,kind:str='',event:str='',refresh:int=0):
        conn=get_conn()
        try:
            user=actor(request,conn)
            if kind not in new_flow.KINDS: return RedirectResponse('/advisories/new',status_code=303)
            ev=None
            if kind=='activity':
                ev=st.get_event(conn,event)
                if not ev or not activity_permissions.can_manage(user,ev,conn):
                    raise permissions.Denied('Activity not found or unavailable to you.')
                existing=workflow.for_event(conn,ev['id'])
                if existing: return RedirectResponse(f"/advisories/{existing['id']}",status_code=303)
            return details_page(request,conn,user,kind,ev,refresh=bool(refresh))
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.post('/advisories/new')
    async def new_create(request:Request):
        body=await request.body()
        if len(body)>128000: return Response('The form is too large.',status_code=413)
        posted=dict(parse_qsl(body.decode('utf-8',errors='replace'),keep_blank_values=True))
        conn=get_conn()
        try:
            user=actor(request,conn)
            kind=posted.get('kind','')
            if kind not in new_flow.KINDS: return RedirectResponse('/advisories/new',status_code=303)
            ev=st.get_event(conn,posted.get('event_token','')) if kind=='activity' else None
            off=new_flow.switched_on(conn)
            if off: return details_page(request,conn,user,kind,ev,posted=posted,error=off,status=422)
            designs,_=new_flow.designs(conn)
            try:
                aid=new_flow.start(conn,user,posted,variants=designs)
            except new_flow.AlreadyHasAdvisory as found:
                return RedirectResponse(f'/advisories/{found.advisory_id}',status_code=303)
            except permissions.Denied: raise
            except ValueError as error:
                return details_page(request,conn,user,kind,ev,posted=posted,error=str(error),field=getattr(error,'field',''),
                                    status=409 if isinstance(error,documents.Conflict) else 422)
            try:
                new_flow.make_file(conn,user,aid,base_url=base_url(request))
                return RedirectResponse(f'/advisories/{aid}?made=1',status_code=303)
            except ValueError:
                return RedirectResponse(f'/advisories/{aid}?made=0',status_code=303)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.post('/advisories/{advisory_id}/slides')
    def new_make_file(request:Request,advisory_id:int):
        conn=get_conn()
        try:
            user=actor(request,conn)
            try:
                new_flow.make_file(conn,user,advisory_id,base_url=base_url(request))
            except permissions.Denied: raise
            except ValueError:
                return RedirectResponse(f'/advisories/{advisory_id}?made=0',status_code=303)
            return RedirectResponse(f'/advisories/{advisory_id}?made=1',status_code=303)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.post('/advisories/{advisory_id}/send')
    async def new_send(request:Request,advisory_id:int):
        raw=await request.body()
        if len(raw)>16000: return Response('This form is too large.',status_code=413)
        data=dict(parse_qsl(raw.decode('utf-8',errors='replace'),keep_blank_values=True))
        conn=get_conn()
        try:
            user=actor(request,conn)
            try:
                warning=new_flow.send_for_review(conn,user,advisory_id,reason=data.get('reason',''),
                                                 operation_key=data.get('operation_key',''))
            except permissions.Denied: raise
            except ValueError as error:
                return home_page(request,conn,user,advisory_id,error=str(error),reason=data.get('reason',''),
                                 status=409 if isinstance(error,documents.Conflict) else 422)
            return RedirectResponse(f'/advisories/{advisory_id}?sent=1'+('&access=0' if warning else ''),status_code=303)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/designs/{variant}.png')
    def design_image(request:Request,variant:int):
        conn=get_conn()
        try:
            actor(request,conn)
            data=new_flow.design_png(conn,variant)
            if not data: return Response('Not found.',status_code=404)
            return Response(data,media_type='image/png',headers={'Cache-Control':'private, max-age=3600'})
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/activities/{event_token}/advisory/draft',response_class=HTMLResponse)
    def prepare(request:Request,event_token:str):
        conn=get_conn()
        try:
            user=actor(request,conn); ev=st.get_event(conn,event_token)
            if not ev: raise permissions.Denied('Activity not found or unavailable to you.')
            existing=workflow.for_event(conn,ev['id'])
            if existing and existing.get('kind'):
                return RedirectResponse(f"/advisories/{existing['id']}",status_code=303)
            if not existing and not new_flow.switched_on(conn):
                return RedirectResponse(f"/advisories/new/details?kind=activity&event={ev['event_token']}",status_code=303)
            return show(request,conn,user,ev)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.post('/activities/{event_token}/advisory/draft')
    async def save(request:Request,event_token:str):
        body=await request.body()
        if len(body)>128000: return Response('The form is too large.',status_code=413)
        posted=dict(parse_qsl(body.decode('utf-8',errors='replace'),keep_blank_values=True))
        conn=get_conn()
        try:
            user=actor(request,conn); ev=st.get_event(conn,event_token)
            if not ev: raise permissions.Denied('Activity not found or unavailable to you.')
            record=workflow.for_event(conn,ev['id'])
            if record: workflow.get_visible(conn,user,record['id'])
            elif not activity_permissions.can_manage(user,ev,conn):
                raise permissions.Denied('Activity not found or unavailable to you.')
            stored=aa.get(conn,ev['id'])
            fields=legacy_routes._form_fields(posted)
            fields['qr_url']=(stored or {}).get('qr_url') or f"{base_url(request)}/e/{ev['event_token']}"
            try:
                saved=workflow.save_draft(conn,user,event_token,fields,unit_id=posted.get('unit_id'),
                    audience=posted.get('audience'),external=posted.get('external',''),
                    expected_revision=posted.get('expected_revision'),expected_source=posted.get('expected_source'),
                    expected_legacy_revision=posted.get('expected_legacy_revision',0),operation_key=posted.get('operation_key'),
                    summary=posted.get('summary',''),adopt_source=posted.get('adopt_source')=='1')
            except permissions.Denied: raise
            except (ValueError,advisory.AdvisoryTooLong) as error:
                return show(request,conn,user,ev,posted=posted,error=str(error),status=409 if isinstance(error,documents.Conflict) else 422)
            return RedirectResponse(f"/advisories/{saved['id']}",status_code=303)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/existing',response_class=HTMLResponse)
    def existing(request:Request,before:int=0):
        conn=get_conn()
        try:
            user=actor(request,conn)
            return templates.TemplateResponse(request,'advisory_existing.html',workflow.list_existing(conn,user,max(0,before)))
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/issued',response_class=HTMLResponse)
    def issued_list(request:Request,before:int=0):
        conn=get_conn()
        try:
            user=actor(request,conn)
            found=advisory_distribution.issued_for_user(conn,user,before)
            return templates.TemplateResponse(request,'advisory_issued.html',{'items':found[:30],'older':found[29]['id'] if len(found)>30 else None})
        except ValueError as error:return failure(error,request)
        finally:conn.close()

    @router.get('/advisories/issued/{issue_id}/file.{fmt}')
    def issued_file(request:Request,issue_id:int,fmt:str):
        conn=get_conn()
        try:
            user=actor(request,conn)
            return Response(advisory_distribution.issued_artifact(conn,user,issue_id,fmt),
                media_type='application/pdf' if fmt=='pdf' else 'image/png',headers={'Cache-Control':'private, no-store'})
        except ValueError as error:return failure(error,request)
        finally:conn.close()

    @router.get('/advisories/{advisory_id}',response_class=HTMLResponse)
    def detail(request:Request,advisory_id:int):
        conn=get_conn()
        try:
            user=actor(request,conn); record=workflow.get_visible(conn,user,advisory_id)
            if record.get('kind'):
                return home_page(request,conn,user,advisory_id)
            ev=st.get_event(conn,record['event_token'])
            return show(request,conn,user,ev)
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/{advisory_id}/issue',response_class=HTMLResponse)
    def issue_preview(request:Request,advisory_id:int):
        conn=get_conn()
        try:
            user=actor(request,conn)
            record=workflow.get_visible(conn,user,advisory_id)
            if record.get('kind'):
                changed=new_flow.unchanged_since_approval(conn,user,advisory_id)
                if changed:
                    return templates.TemplateResponse(request,'advisory_action_error.html',{'record':record,'error':changed,'reason':''},status_code=409)
            return templates.TemplateResponse(request,'advisory_issue.html',{
                **advisory_distribution.preview(conn,user,advisory_id),'action_key':str(uuid.uuid4()),
                'available':workflow.available(conn)})
        except ValueError as error:return failure(error,request)
        finally:conn.close()

    @router.post('/advisories/{advisory_id}/actions')
    async def action(request:Request,advisory_id:int):
        raw=await request.body()
        if len(raw)>16000:return Response('This action is too large.',status_code=413)
        data=dict(parse_qsl(raw.decode('utf-8',errors='replace'),keep_blank_values=True))
        conn=get_conn()
        try:
            user=actor(request,conn); record=workflow.get_visible(conn,user,advisory_id)
            slides_kind=bool(record.get('kind'))
            def refuse(message,status=409):
                return templates.TemplateResponse(request,'advisory_action_error.html',{'record':record,
                    'error':message,'reason':data.get('reason','')},status_code=status)
            if slides_kind and data.get('action')=='submit':
                return refuse('Use "Send to Division Chief" on the advisory page; it takes a fresh copy from Google Slides first.')
            if record.get('current_revision') is None:
                return refuse('Send the advisory for review first.')
            if slides_kind and data.get('action')=='issue':
                changed=new_flow.unchanged_since_approval(conn,user,advisory_id)
                if changed: return refuse(changed)
            try:
                documents.mutate(conn,user,record['document_id'],data.get('expected_revision'),
                                 'advisory_'+data.get('action',''),data)
            except permissions.Denied:raise
            except ValueError as error:
                return refuse(str(error),409 if isinstance(error,documents.Conflict) else 422)
            if slides_kind:
                warning=new_flow.sync_access(conn,user,advisory_id)
                if warning: return RedirectResponse(f'/advisories/{advisory_id}?access=0',status_code=303)
            return RedirectResponse(f'/advisories/{advisory_id}',status_code=303)
        except ValueError as error:return failure(error,request)
        finally:conn.close()

    @router.get('/advisories/{advisory_id}/history',response_class=HTMLResponse)
    def history(request:Request,advisory_id:int,before:int=0):
        conn=get_conn()
        try:
            user=actor(request,conn); record=workflow.get_visible(conn,user,advisory_id)
            found=workflow.history(conn,user,advisory_id,max(0,before))
            for entry in found:
                entry['payload']=json.loads(entry['payload_json'])
                previous=json.loads(entry['previous_payload']) if entry['previous_payload'] else None
                entry['changes']=[]
                if previous:
                    before={**previous['content'],**{k:previous[k] for k in ('unit_id','audience','external')}}
                    after={**entry['payload']['content'],**{k:entry['payload'][k] for k in ('unit_id','audience','external')}}
                    entry['changes']=[{'field':key.replace('_',' '),'before':before[key],'after':after[key]}
                                      for key in after if before[key]!=after[key]]
            return templates.TemplateResponse(request,'advisory_history.html',{
                'record':record,'entries':found[:30],'older':found[29]['id'] if len(found)>30 else None})
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    @router.get('/advisories/{advisory_id}/revisions/{revision_id}/file.{fmt}')
    def file(request:Request,advisory_id:int,revision_id:int,fmt:str):
        conn=get_conn()
        try:
            user=actor(request,conn); record=workflow.get_visible(conn,user,advisory_id)
            if fmt not in ('pdf','png'): return Response('Not found.',status_code=404)
            data=workflow.artifact(conn,user,advisory_id,revision_id,fmt)
            return Response(data,media_type='application/pdf' if fmt=='pdf' else 'image/png',headers={
                'Cache-Control':'private, no-store','Content-Disposition':f'inline; filename="{advisory.filename(record["number"],fmt)}"'})
        except ValueError as error: return failure(error,request)
        finally: conn.close()

    return router
