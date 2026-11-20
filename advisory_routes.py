"""Authenticated advisory drafts/register. All writes stay inside Office Connect."""
import json
import uuid
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import activity_advisory as aa
import activity_advisory_routes as legacy_routes
import activity_permissions
import advisory
import advisory_workflow as workflow
import documents
import documents_permissions as permissions
import storage as st


def make_router(templates, get_conn, base_url):
    router = APIRouter()

    def failure(error):
        status = 404 if isinstance(error,permissions.Denied) else 409 if isinstance(error,documents.Conflict) else 422
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
            'available':workflow.available(conn),'can_edit':not record or record['initiator_id']==user['id'],
            'source_changed':bool(record and workflow.digest(workflow.encoded(record['snapshot']))!=current_source),
            'adopt_source':adopt,'source_defaults':aa.defaults(conn,ev,qr),
            'history':workflow.history(conn,user,record['id'])[:10] if record else []},status_code=status)

    @router.get('/advisories',response_class=HTMLResponse)
    def register(request:Request,before:int=0,division:int=0):
        conn=get_conn()
        try:
            user=actor(request,conn)
            listing=workflow.list_visible(conn,user,before=max(0,before),unit_id=max(0,division))
            return templates.TemplateResponse(request,'advisory_register.html',{
                **listing,'divisions':workflow.divisions(conn),'division':division,'available':workflow.available(conn)})
        except ValueError as error:
            return failure(error)
        finally: conn.close()

    @router.get('/activities/{event_token}/advisory/draft',response_class=HTMLResponse)
    def prepare(request:Request,event_token:str):
        conn=get_conn()
        try:
            user=actor(request,conn); ev=st.get_event(conn,event_token)
            if not ev: raise permissions.Denied('Activity not found or unavailable to you.')
            return show(request,conn,user,ev)
        except ValueError as error: return failure(error)
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
        except ValueError as error: return failure(error)
        finally: conn.close()

    @router.get('/advisories/existing',response_class=HTMLResponse)
    def existing(request:Request,before:int=0):
        conn=get_conn()
        try:
            user=actor(request,conn)
            return templates.TemplateResponse(request,'advisory_existing.html',workflow.list_existing(conn,user,max(0,before)))
        except ValueError as error: return failure(error)
        finally: conn.close()

    @router.get('/advisories/{advisory_id}',response_class=HTMLResponse)
    def detail(request:Request,advisory_id:int):
        conn=get_conn()
        try:
            user=actor(request,conn); record=workflow.get_visible(conn,user,advisory_id)
            ev=st.get_event(conn,record['event_token'])
            return show(request,conn,user,ev)
        except ValueError as error: return failure(error)
        finally: conn.close()

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
        except ValueError as error: return failure(error)
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
        except ValueError as error: return failure(error)
        finally: conn.close()

    return router
