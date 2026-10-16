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
import storage as st
import documents as d
import documents_permissions as p
import documents_operations as ops
import documents_rules as rules
import documents_calendar as cal
import work
import work_intake
from documents_storage import rows


def csrf(request):
    return hmac.new(auth._secret(),('documents:'+request.cookies.get(auth.COOKIE_NAME,'')).encode(),hashlib.sha256).hexdigest()


def make_router(templates,get_conn):
    router=APIRouter()

    def context(request,conn,**values):
        user=p.actor(conn,getattr(request.state,'user',None))
        return {'nav_active':'documents','enabled':d.enabled(conn),'csrf':csrf(request),'error':'',
                'workflow_admin':p.has_role(conn,user,'workflow_admin'),
                'people':rows(conn,"SELECT u.id,u.username,COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.active=1 ORDER BY name"),
                'names':{r['id']:r['name'] for r in rows(conn,"SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id")},
                'units':rows(conn,'SELECT id,name FROM org_unit ORDER BY path'),**values}

    def render(request,conn,page,**values):
        return templates.TemplateResponse(request,'documents/'+page+'.html',context(request,conn,**values))

    def detail_context(conn,user,doc_id):
        user=p.actor(conn,user)
        doc=d.get(conn,user,doc_id)
        if doc['canonical_id']:
            return {'redirect':doc['canonical_id']}
        details={name:rows(conn,'SELECT * FROM '+table+' WHERE document_id=? ORDER BY id', (doc_id,)) for name,table in
                 [('assignments','document_assignment_effective'),('versions','document_file_version'),('history','document_event'),
                  ('dispatches','document_dispatch'),('jobs','document_job'),('references','document_reference'),('receipts','document_receipt'),('directives','document_directive')]}
        migration = conn.execute('SELECT case_id FROM work_legacy_document WHERE document_id=?',(doc_id,)).fetchone()
        if migration:
            try:
                work.get(conn, user, migration[0])
            except p.Denied:
                details['assignments'] = []
                migration = None
        is_officer=p.officer(conn,user,doc)
        coordinator=is_officer or doc['lead_id']==user['id']
        for assignment in details['assignments']:
            assignment['progress_choices']=[]
            assignment['milestone_allowed']=False
            if not migration and doc['status'] not in ('closed','cancelled') and assignment['status'] not in ('completed','superseded'):
                if assignment['user_id']==user['id'] or is_officer:
                    assignment['progress_choices']={'assigned':[('acknowledged','Acknowledge')],
                        'acknowledged':[('in_progress','Start contribution'),('submitted','Submit for consolidation')],
                        'in_progress':[('submitted','Submit for consolidation')]}.get(assignment['status'],[])
                if coordinator:
                    if assignment['status']=='submitted':
                        assignment['progress_choices'].append(('completed','Confirm contribution complete'))
                    assignment['milestone_allowed']=True
        for e in details['history']:
            e['detail']=json.loads(e['detail_json'])
            e['note']=e['detail'].get('reason') or e['detail'].get('outcome') or ''
        policy=json.loads(doc['policy_json'])
        warnings=rules.coverage(conn,doc['created_at'],doc['due_date'])
        if any(a['due_date'] and a['due_date']<doc['created_at'][:10] for a in details['assignments']):
            warnings.append('The proposed contributor buffer cannot fit before the deadline. The lead must adjust milestones explicitly.')
        return {'doc':doc,**details,'policy':policy,'duplicates':d.duplicate_candidates(conn,user,doc_id),
                'work_migration':migration,
                'assignments_migrated':bool(conn.execute('SELECT 1 FROM work_legacy_document WHERE document_id=?',(doc_id,)).fetchone()),
                'work_enabled':work.enabled(conn),'work_cases':work.cases_for_document(conn,user,doc_id),
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

    def intake_page(request,conn,data=None,status_code=200,error='',preview=None):
        data=data or {}
        cases=work_intake.choices(conn,request.state.user) if work.enabled(conn) else []
        if data.get('case_selection'):
            try:
                chosen=work.get(conn,request.state.user,int(str(data['case_selection']).split(':')[0]))
                if work.can_link(conn,request.state.user,chosen) and chosen['id'] not in [c['id'] for c in cases]:
                    cases.append(chosen)
            except (ValueError,TypeError):
                pass
        return templates.TemplateResponse(request,'documents/new.html',context(request,conn,
            values=data,work_enabled=work.enabled(conn),cases=cases,scenarios=work_intake.SCENARIOS,
            preview=preview,error=error),status_code=status_code)

    @router.post('/documents/intake/preview')
    async def intake_preview(request:Request):
        conn=get_conn();data={}
        try:
            data=await posted(request)
            result=work_intake.preview(conn,request.state.user,data.get('drive_url',''))
            data.pop('confirmed',None)
            return intake_page(request,conn,data,preview=result)
        except p.Denied:
            return HTMLResponse('The form expired or the account is unavailable.',status_code=403)
        except Exception:
            data.pop('confirmed',None)
            return intake_page(request,conn,data,error='The source could not be read. Your entered fields are retained; continue manually or retry extraction.')
        finally:
            conn.close()

    @router.get('/documents/new',response_class=HTMLResponse)
    def new(request:Request,case_id:int|None=None):
        conn=get_conn()
        try:
            data={}
            if case_id:
                chosen=work.get(conn,request.state.user,case_id)
                if not work.can_link(conn,request.state.user,chosen):
                    raise p.Denied('Work item unavailable for linking.')
                data={'case_selection':str(chosen['id'])+':'+str(chosen['revision']),'work_mode':'existing','scenario':'response'}
            return intake_page(request,conn,data)
        except p.Denied:
            return HTMLResponse('Work item unavailable for linking.',status_code=404)
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

    def setup_signature(request, preview):
        payload = json.dumps(preview, sort_keys=True, separators=(',', ':'))
        return hmac.new(auth._secret(), (csrf(request) + ':' + payload).encode(), hashlib.sha256).hexdigest()

    def setup_page(request, conn, status_code=200, **values):
        operator = d.setup_operator(conn, request.state.user)
        grants = rows(conn, '''SELECT u.username,u.active,g.role,g.revoked_at FROM document_role_grant g
                              JOIN admin_user u ON u.id=g.user_id
                              WHERE g.role IN ('grant_admin','workflow_admin') AND g.unit_id IS NULL
                              ORDER BY u.username,g.role''')
        return templates.TemplateResponse(request, 'documents/setup.html', {
            'nav_active': 'documents_setup', 'csrf': csrf(request), 'error': '',
            'blocker': d.setup_blocker(conn), 'grants': grants,
            'module_enabled': d.enabled(conn),
            'sending_enabled': st.get_setting(conn, 'documents.sending_enabled', '0') == '1',
            'can_enable': p.has_role(conn, operator, 'grant_admin'),
            'settings_revision': st.get_setting(conn, 'documents.settings_revision', '0'),
            'usernames': '', 'authorization': '', 'preview': None, **values,
        }, status_code=status_code)

    @router.get('/admin/documents/setup', response_class=HTMLResponse)
    def admin_setup(request: Request):
        conn = get_conn()
        try:
            return setup_page(request, conn)
        except p.Denied as e:
            return HTMLResponse(str(e), status_code=403)
        finally:
            conn.close()

    @router.post('/admin/documents/setup', response_class=HTMLResponse)
    async def save_admin_setup(request: Request):
        conn = get_conn()
        data = {}
        try:
            d.setup_operator(conn, request.state.user)
            data = await posted(request)
            if data.get('action') in ('enable_module', 'disable_module'):
                if data.get('confirmed') != 'yes':
                    raise ValueError('Confirm the Documents setting change before saving.')
                d.set_module_enabled(conn, request.state.user, data['action'] == 'enable_module',
                                     data.get('settings_revision', ''), data.get('authorization', ''))
                return RedirectResponse('/admin/documents/setup', status_code=303)
            if data.get('action') == 'preview':
                preview = d.preview_admin_setup(conn, request.state.user, data.get('usernames', ''), data.get('authorization', ''))
                return setup_page(request, conn, preview=preview, preview_signature=setup_signature(request, preview))
            if data.get('action') != 'confirm' or data.get('confirmed') != 'yes':
                raise ValueError('Review the accounts and confirm their appointment before saving.')
            preview = data.get('preview')
            supplied = str(data.get('preview_signature', ''))
            if not isinstance(preview, dict) or not hmac.compare_digest(supplied, setup_signature(request, preview)):
                raise p.Denied('The preview changed or expired. Review the accounts again.')
            d.bootstrap_admins(conn, request.state.user, preview)
            return RedirectResponse('/admin/documents/setup', status_code=303)
        except p.Denied as e:
            return HTMLResponse(str(e), status_code=403)
        except ValueError as e:
            return setup_page(request, conn, status_code=409 if isinstance(e, d.Conflict) else 400,
                              error=str(e), usernames=data.get('usernames', ''), authorization=data.get('authorization', ''))
        finally:
            conn.close()

    @router.post('/documents/new')
    async def create(request:Request):
        conn=get_conn(); data={}
        try:
            data=await posted(request)
            if data.get('intake')=='guided':
                doc,case=work_intake.register(conn,request.state.user,data)
                return RedirectResponse('/work/'+str(case['id']) if case else '/documents/'+str(doc['id']),status_code=303)
            doc=d.register(conn,request.state.user,data)
            return RedirectResponse('/documents/'+str(doc['id']),status_code=303)
        except (ValueError,sqlite3.IntegrityError) as e:
            return intake_page(request,conn,data,error=str(e),status_code=403 if isinstance(e,p.Denied) else (409 if isinstance(e,d.Conflict) else 400))
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
            elif action=='sign_preview':
                preview=ops.signature_preview(conn,user,doc_id)
                return render(request,conn,'sign_preview',doc=d.get(conn,user,doc_id),preview=preview)
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
