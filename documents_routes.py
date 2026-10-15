"""Authenticated document screens and form/JSON actions with session-bound CSRF."""
import csv
import hashlib
import hmac
import io
import json
import sqlite3
import uuid
from urllib.parse import quote
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
import auth
import documents as d
import documents_permissions as p
import documents_operations as ops
import documents_rules as rules
import documents_calendar as cal
from documents_storage import rows


def csrf(request):
    return hmac.new(auth._secret(),('documents:'+request.cookies.get(auth.COOKIE_NAME,'')).encode(),hashlib.sha256).hexdigest()


def make_router(templates,get_conn):
    router=APIRouter()

    def context(request,conn,**values):
        user=p.actor(conn,getattr(request.state,'user',None))
        return {'nav_active':'documents','enabled':d.enabled(conn),'csrf':csrf(request),'error':'',
                'workflow_admin':p.has_role(conn,user,'workflow_admin'),
                'people':rows(conn,'SELECT id,username FROM admin_user WHERE active=1 ORDER BY username'),
                'units':rows(conn,'SELECT id,name FROM org_unit ORDER BY path'),**values}

    def render(request,conn,page,**values):
        return templates.TemplateResponse(request,'documents/'+page+'.html',context(request,conn,**values))

    def detail_context(conn,user,doc_id):
        doc=d.get(conn,user,doc_id)
        if doc['canonical_id']:
            return {'redirect':doc['canonical_id']}
        details={name:rows(conn,'SELECT * FROM '+table+' WHERE document_id=? ORDER BY id', (doc_id,)) for name,table in
                 [('assignments','document_assignment'),('versions','document_file_version'),('history','document_event'),
                  ('dispatches','document_dispatch'),('jobs','document_job'),('references','document_reference'),('receipts','document_receipt'),('directives','document_directive')]}
        for e in details['history']:
            e['detail']=json.loads(e['detail_json'])
        policy=json.loads(doc['policy_json'])
        warnings=rules.coverage(conn,doc['created_at'],doc['due_date'])
        if any(a['due_date'] and a['due_date']<doc['created_at'][:10] for a in details['assignments']):
            warnings.append('The proposed contributor buffer cannot fit before the deadline. The lead must adjust milestones explicitly.')
        return {'doc':doc,**details,'policy':policy,'duplicates':d.duplicate_candidates(conn,user,doc_id),
                'warnings':warnings,
                'evaluation':rules.evaluate(conn,doc),'operation_id':str(uuid.uuid4()),
                'officer':p.officer(conn,p.actor(conn,user),doc),'can_work':p.can_work(conn,p.actor(conn,user),doc),
                'signatory':p.has_role(conn,p.actor(conn,user),'signatory',doc['unit_id']),
                'can_release':p.can_release(conn,p.actor(conn,user),doc),
                'merged_sources':rows(conn,'SELECT id,number,subject FROM document WHERE canonical_id=?',(doc_id,)),
                'notice_rows':rows(conn,"SELECT * FROM document_notice WHERE document_id=? AND user_id=? ORDER BY id DESC",(doc_id,user['id'])),
                'recipient_outcomes':rows(conn,'SELECT r.* FROM document_dispatch_recipient r JOIN document_dispatch x ON x.id=r.dispatch_id WHERE x.document_id=?',(doc_id,)),
                'related': [x for x in d.list_visible(conn,user) if x['id'] in {r[0] for r in conn.execute('SELECT target_id FROM document_relation WHERE source_id=? UNION SELECT source_id FROM document_relation WHERE target_id=?',(doc_id,doc_id))}]}

    @router.get('/documents',response_class=HTMLResponse)
    def index(request:Request):
        conn=get_conn()
        try:
            docs=d.list_visible(conn,request.state.user,request.query_params.get('q',''),request.query_params.get('queue','all'))
            return render(request,conn,'index',documents=docs,queue=request.query_params.get('queue','all'),
                          missing_dates=sum(not x['due_date'] for x in docs),metrics=d.metrics(conn,docs))
        except p.Denied as e:
            return HTMLResponse(str(e),status_code=403)
        finally:
            conn.close()

    @router.get('/documents/export.csv')
    def export(request:Request):
        conn=get_conn()
        try:
            docs=d.list_visible(conn,request.state.user,request.query_params.get('q',''),request.query_params.get('queue','all'))
            month=request.query_params.get('month','')
            if month:
                docs=[x for x in docs if x['created_at'].startswith(month)]
            stream=io.StringIO(); writer=csv.writer(stream)
            keys=['number','direction','subject','type','verification','status','due_date','created_at','updated_at']
            writer.writerow(keys)
            # Neutralize spreadsheet formulas in user-controlled metadata.
            for doc in docs:
                writer.writerow([("'"+str(doc[k]) if str(doc[k] or '').lstrip().startswith(('=','+','-','@')) else doc[k]) for k in keys])
            return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="documents.csv"'})
        finally:
            conn.close()

    @router.get('/documents/new',response_class=HTMLResponse)
    def new(request:Request):
        conn=get_conn()
        try:
            return render(request,conn,'new',values={})
        finally:
            conn.close()

    @router.get('/documents/rules',response_class=HTMLResponse)
    def rule_page(request:Request):
        conn=get_conn()
        try:
            user=p.actor(conn,request.state.user)
            d.require(p.has_role(conn,user,'workflow_admin') or p.has_role(conn,user,'grant_admin'))
            items=rows(conn,'SELECT * FROM document_rule_version ORDER BY id DESC')
            for r in items:
                r['body']=json.loads(r['body_json'])
            return render(request,conn,'rules',rules=items,can_grant=p.has_role(conn,user,'grant_admin'),grants=rows(conn,'SELECT * FROM document_role_grant WHERE revoked_at IS NULL'))
        except p.Denied as e:
            return HTMLResponse(str(e),status_code=403)
        finally:
            conn.close()

    @router.get('/documents/{doc_id}',response_class=HTMLResponse)
    def detail(request:Request,doc_id:int):
        conn=get_conn()
        try:
            values=detail_context(conn,request.state.user,doc_id)
            if 'redirect' in values:
                return RedirectResponse('/documents/'+str(values['redirect']),status_code=303)
            return render(request,conn,'detail',**values)
        except p.Denied as e:
            return HTMLResponse(str(e),status_code=404)
        finally:
            conn.close()

    async def posted(request):
        raw=await request.body()
        if len(raw)>65536:
            raise ValueError('This form is too large.')
        if request.headers.get('content-type','').startswith('application/json'):
            data=json.loads(raw)
            if not isinstance(data,dict):
                raise ValueError('Expected a form object.')
        else:
            from urllib.parse import parse_qs
            data={k:v[-1] for k,v in parse_qs(raw.decode(),keep_blank_values=True).items()}
        supplied=str(data.pop('csrf',request.headers.get('x-csrf-token','')))
        if not supplied or not hmac.compare_digest(supplied,csrf(request)) or not request.cookies.get(auth.COOKIE_NAME):
            raise p.Denied('The form expired or came from another session. Reload and try again.')
        for key in ('viewers','recipients','assignees','unit_ids'):
            if key in data and isinstance(data[key],str):
                data[key]=[v.strip() for v in data[key].replace(',','\n').splitlines() if v.strip()]
        for key in ('preview','body','checklist','evidence'):
            if key in data and isinstance(data[key],str) and data[key].lstrip().startswith('{'):
                data[key]=json.loads(data[key])
        for prefix in ('checklist','closure'):
            fields={k.split(':',1)[1]:v for k,v in data.items() if k.startswith(prefix+':')}
            if fields:
                data['checklist' if prefix=='checklist' else 'evidence']=fields
        return data

    @router.post('/documents/new')
    async def create(request:Request):
        conn=get_conn(); data={}
        try:
            data=await posted(request)
            doc=d.register(conn,request.state.user,data)
            return RedirectResponse('/documents/'+str(doc['id']),status_code=303)
        except (ValueError,sqlite3.IntegrityError) as e:
            return templates.TemplateResponse(request,'documents/new.html',context(request,conn,error=str(e),values=data),status_code=403 if isinstance(e,p.Denied) else 400)
        finally:
            conn.close()

    @router.post('/documents/rules')
    async def save_rule(request:Request):
        conn=get_conn()
        try:
            data=await posted(request)
            if data.get('action')=='grant':
                d.grant(conn,request.state.user,int(data['target_id']),data['role'],int(data['unit_id']) if data.get('unit_id') else None,int(data['revoke_id']) if data.get('revoke_id') else None)
                return RedirectResponse('/documents/rules',status_code=303)
            body=data.get('body')
            if body is None:
                policy={}
                for k in rules.POLICY_KEYS:
                    value=data.get(k)
                    if value not in ('',None):
                        if k in ('default_days','buffer_days','escalate_chief_days','escalate_director_days'):
                            value=int(value)
                        elif k in ('signature_required','ack_required'):
                            value=value=='true'
                        elif k in ('closure','release'):
                            value=[v.strip() for v in value.splitlines() if v.strip()]
                        policy[k]=value
                body={'type':data.get('type',''),'field':data.get('field','subject'),'mode':data.get('mode','any'),
                      'keywords':[v.strip() for v in data.get('keywords','').splitlines() if v.strip()],
                      'priority':int(data.get('priority') or 0),'assignees':[int(v) for v in data.get('assignees',[])],'policy':policy}
                body['unit_ids']=[int(v) for v in data.get('unit_ids',[])]
                if data.get('lead_unit_id'):
                    body['lead_unit_id']=int(data['lead_unit_id'])
                if data.get('lead_id'):
                    body['lead_id']=int(data['lead_id'])
            if data.get('action')=='preview':
                rules.validate(body)
                return JSONResponse({'rule':body,'notice':'Saving an active version affects future submissions; existing records require explicit reevaluation.'})
            d.rule_save(conn,request.state.user,data['name'],body,int(data['rule_id']) if data.get('rule_id') else None,data.get('revision'),data.get('state','draft'))
            return RedirectResponse('/documents/rules',status_code=303)
        except (ValueError,KeyError,sqlite3.IntegrityError) as e:
            return JSONResponse({'error':str(e)},status_code=403 if isinstance(e,p.Denied) else 409 if isinstance(e,d.Conflict) else 400)
        finally:
            conn.close()

    @router.post('/documents/{doc_id}/{action}')
    async def action_route(request:Request,doc_id:int,action:str):
        conn=get_conn();data={}
        try:
            data=await posted(request); user=request.state.user
            revision=int(data['revision'])
            if action=='attach':
                ops.attach(conn,user,doc_id,revision,data['url'],data['classification'],data['reason'])
            elif action=='external_signature':
                ops.external_signature(conn,user,doc_id,revision,data['url'],data['source_fingerprint'],data['evidence'])
            elif action in ('extract','sign','dispatch'):
                operation=ops.queue(conn,user,doc_id,revision,action,data)
                # An explicit submit requests this effect; process it now, with intent
                # durably persisted before I/O. Interrupted operations remain visible.
                result=ops.execute(conn,operation)
                if action=='extract':
                    return render(request,conn,'extraction',doc=d.get(conn,user,doc_id),result=result)
            elif action=='record_dispatch':
                ops.record_dispatch(conn,user,doc_id,revision,data)
            elif action=='operation_status':
                job=rows(conn,'SELECT * FROM document_job WHERE id=? AND document_id=?',(data['operation_id'],doc_id))
                doc=d.get(conn,user,doc_id)
                d.require(job and (job[0]['actor_id']==user['id'] or p.officer(conn,p.actor(conn,user),doc)))
                ops.execute(conn,data['operation_id'],reconcile=True)
            elif action=='reverse_merge':
                source=d.raw(conn,int(data['source_id']))
                d.require(source and source['canonical_id']==doc_id)
                d.reverse_merge(conn,user,source['id'],data['reason'])
            elif action=='notice_retry':
                import documents_notify
                documents_notify.retry(conn,user,doc_id,int(data['notice_id']),data['reason'])
            elif action=='operation_reconcile':
                job=rows(conn,'SELECT * FROM document_job WHERE id=? AND document_id=?',(data['operation_id'],doc_id))
                if not job:
                    raise ValueError('Operation not found.')
                ops.reconcile(conn,user,data['operation_id'],data['outcome'],data['evidence'])
            elif action=='acknowledge':
                ops.acknowledge(conn,user,doc_id,revision,int(data['dispatch_id']),data['recipient'],data['evidence'])
            elif action=='calendar':
                cal.confirm(conn,user,doc_id,revision,data['day'],int(data['entry_id']) if data.get('entry_id') else None)
            elif action=='calendar_preview':
                return render(request,conn,'calendar',doc=d.get(conn,user,doc_id),day=data['day'],candidates=cal.candidates(conn,user,doc_id,data['day']))
            elif action=='history':
                source=d.get(conn,user,int(data['source_id']))
                d.require(source['canonical_id']==doc_id)
                return render(request,conn,'history',source=source,history=rows(conn,'SELECT * FROM document_event WHERE document_id=? ORDER BY id',(source['id'],)),
                              versions=rows(conn,'SELECT * FROM document_file_version WHERE document_id=?',(source['id'],)))
            elif action=='merge_preview':
                return render(request,conn,'merge',doc=d.get(conn,user,doc_id),preview=d.merge_preview(conn,user,doc_id,int(data['target_id'])))
            elif action=='merge':
                if data['preview']['source_id']!=doc_id:
                    raise ValueError('Merge source mismatch.')
                d.merge(conn,user,data['preview'],data['reason'])
            else:
                d.mutate(conn,user,doc_id,revision,action,data)
            return RedirectResponse('/documents/'+str(doc_id),status_code=303)
        except (ValueError,KeyError,sqlite3.IntegrityError,http_error(),TimeoutError) as e:
            status=403 if isinstance(e,p.Denied) else 409 if isinstance(e,d.Conflict) else 400
            if request.headers.get('content-type','').startswith('application/json'):
                return JSONResponse({'error':str(e)},status_code=status)
            # Keep submitted text on errors without exposing it to another viewer.
            try:
                values=detail_context(conn,request.state.user,doc_id)
                return templates.TemplateResponse(request,'documents/detail.html',context(request,conn,**values,error=str(e),submitted=data),status_code=status)
            except p.Denied:
                return HTMLResponse('Document not found or unavailable to you.',status_code=404)
        finally:
            conn.close()
    return router


def http_error():
    import httpx
    return httpx.HTTPError
