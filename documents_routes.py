"""Authenticated document screens and form/JSON actions with session-bound CSRF."""
import csv
import hashlib
import hmac
import io
import json
import sqlite3
import uuid
from urllib.parse import quote, urlencode
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
import auth
import storage as st
import documents as d
import documents_permissions as p
import documents_operations as ops
import documents_rules as rules
import documents_calendar as cal
import documents_actions as actions
import documents_memo as memo
import documents_annotations as annotations
import documents_file_text as file_text
import documents_registration as registration
import work
import work_intake
import work_readiness
import work_review
from documents_storage import rows


def csrf(request):
    return hmac.new(auth._secret(),('documents:'+request.cookies.get(auth.COOKIE_NAME,'')).encode(),hashlib.sha256).hexdigest()


def make_router(templates,get_conn):
    router=APIRouter()

    def context(request,conn,**values):
        user=p.actor(conn,getattr(request.state,'user',None))
        return {'nav_active':'documents','enabled':d.enabled(conn),'csrf':csrf(request),'error':'',
                'submitted':{},'intake_access':p.has_role(conn,user,'records'),'is_director':p.director(conn,user),'workflow_admin':p.has_role(conn,user,'workflow_admin'),
                'archive_admin':bool(conn.execute("SELECT 1 FROM document_role_grant WHERE user_id=? AND role='workflow_admin' AND revoked_at IS NULL",(user['id'],)).fetchone()),
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
                  ('reviews','document_review'),('dispatches','document_dispatch'),('jobs','document_job'),('references','document_reference'),('receipts','document_receipt'),('directives','document_directive')]}
        migration = conn.execute('SELECT case_id FROM work_legacy_document WHERE document_id=?',(doc_id,)).fetchone()
        if migration:
            try:
                work.get(conn, user, migration[0])
            except p.Denied:
                details['assignments'] = []
                migration = None
        imports=rows(conn,'SELECT mailbox,message_id,received_at,created_at,attachments_json FROM document_email_import WHERE document_id=?',(doc_id,))
        details['gmail_source']=imports[0] if imports else None
        imported_files={a['file_id'] for a in json.loads(imports[0]['attachments_json'])} if imports else set()
        details['gmail_attachments']=[v for v in details['versions'] if v['file_id'] in imported_files and v['role']=='reference']
        import documents_instruction_tags as instruction_tags
        details['mention_people'],details['mention_sections']=instruction_tags.choices(
            conn,doc,initial=bool(p.director(conn,user) and doc['instruction_state']=='pending'))
        details['instruction_tags']=rows(conn,'''SELECT t.directive_id,t.target_type,t.target_id,
            CASE WHEN t.target_type='person' THEN COALESCE(NULLIF(r.name,''),u.username)
                 ELSE o.name END AS name
            FROM document_instruction_tag t JOIN document_directive x ON x.id=t.directive_id
            LEFT JOIN admin_user u ON t.target_type='person' AND u.id=t.target_id
            LEFT JOIN resource_person r ON r.id=u.rp_id
            LEFT JOIN org_unit o ON t.target_type='section' AND o.id=t.target_id
            WHERE x.document_id=? ORDER BY t.directive_id,t.target_type,t.target_id''',(doc_id,))
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
                'file_indexes':{row['version_id']:row for row in rows(conn,
                    'SELECT version_id,indexed_at,chars FROM document_file_index WHERE document_id=?',(doc_id,))},
                'email_bodies':rows(conn,"SELECT body_text FROM document_intake_email WHERE document_id=? AND body_text<>''",(doc_id,)),
                'filing_rows':rows(conn,"SELECT original_name,filing_state,error FROM document_intake WHERE document_id=? AND filing_state<>'none'",(doc_id,)),
                'instruction_recipients':rows(conn,'SELECT r.directive_id,r.user_id FROM document_instruction_recipient r JOIN document_directive d ON d.id=r.directive_id WHERE d.document_id=?',(doc_id,)),
                'unread_instructions':{r['id'] for r in rows(conn,'''SELECT x.id FROM document_directive x
                    JOIN document_instruction_recipient r ON r.directive_id=x.id
                    LEFT JOIN document_instruction_read seen ON seen.directive_id=x.id AND seen.user_id=r.user_id
                    WHERE x.document_id=? AND r.user_id=? AND seen.directive_id IS NULL
                      AND EXISTS(SELECT 1 FROM document_instruction_tag t WHERE t.directive_id=x.id)''',(doc_id,user['id']))},
                'work_migration':migration,'consolidation':work_review.summaries(conn,user,[doc]).get(doc_id),
                'assignments_migrated':bool(conn.execute('SELECT 1 FROM work_legacy_document WHERE document_id=?',(doc_id,)).fetchone()),
                'work_enabled':work.enabled(conn),'work_cases':work.cases_for_document(conn,user,doc_id),
                'warnings':warnings,
                'evaluation':rules.evaluate(conn,doc),'operation_id':str(uuid.uuid4()),
                'officer':p.officer(conn,p.actor(conn,user),doc),'can_work':p.can_work(conn,p.actor(conn,user),doc),
                'signatory':p.has_role(conn,p.actor(conn,user),'signatory',doc['unit_id']),
                'can_release':p.can_release(conn,p.actor(conn,user),doc),
                'can_archive':p.has_role(conn,user,'workflow_admin',doc['unit_id']),
                'merged_sources':rows(conn,'SELECT id,number,subject FROM document WHERE canonical_id=?',(doc_id,)),
                'notice_rows':rows(conn,"SELECT * FROM document_notice WHERE document_id=? AND user_id=? ORDER BY id DESC",(doc_id,user['id'])),
                'recipient_outcomes':rows(conn,'SELECT r.* FROM document_dispatch_recipient r JOIN document_dispatch x ON x.id=r.dispatch_id WHERE x.document_id=?',(doc_id,)),
                'related': [x for x in rows(conn,'SELECT * FROM document WHERE id IN (SELECT target_id FROM document_relation WHERE source_id=? UNION SELECT source_id FROM document_relation WHERE target_id=?)',(doc_id,doc_id)) if p.can_view(conn,user,x)]}

    @router.get('/documents',response_class=HTMLResponse)
    def index(request:Request):
        conn=get_conn()
        try:
            queue=request.query_params.get('queue','all')
            query=request.query_params.get('q','') if queue!='instruction' else ''
            page=d.list_page(conn,request.state.user,query,queue,
                             before=request.query_params.get('before','0'))
            filters={'queue':queue,'q':query}
            page['newest_url']='/documents?'+urlencode(filters)
            page['older_url']=('/documents?'+urlencode({**filters,'before':page['next_before']})
                               if page['more'] else '')
            return render(request,conn,'index',queue=queue,**page)
        except (p.Denied,ValueError) as e:
            return HTMLResponse(str(e),status_code=403 if isinstance(e,p.Denied) else 400)
        finally:
            conn.close()

    @router.get('/documents/actions',response_class=HTMLResponse)
    def action_screen(request:Request):
        conn=get_conn()
        try:
            user=p.actor(conn,request.state.user)
            view=request.query_params.get('view','mine')
            if view not in ('mine','division'):
                return HTMLResponse('Unknown action view.',status_code=400)
            units=actions.division_units(conn,user)
            if view=='division' and not units:
                return HTMLResponse('Division follow-up is for division chiefs or OICs.',status_code=403)
            cards=actions.team(conn,user) if view=='division' else actions.personal(conn,user)
            return render(request,conn,'actions',cards=cards,view=view,division_access=bool(units))
        except p.Denied as e:
            return HTMLResponse(str(e),status_code=403)
        finally:
            conn.close()

    @router.get('/documents/export.csv')
    def export(request:Request):
        conn=get_conn()
        try:
            docs=d.list_visible(conn,request.state.user,request.query_params.get('q',''),request.query_params.get('queue','all'),snippets=False)
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
            submission_id=data.get('submission_id') or registration.issue(p.actor(conn,request.state.user)),
            preview=preview,error=error),status_code=status_code)

    async def transient_page_body(request, limit):
        conn = get_conn()
        try:
            p.actor(conn, getattr(request.state, 'user', None))
            d.writable(conn)
            supplied = request.headers.get('x-csrf-token', '')
            if not supplied or not hmac.compare_digest(supplied, csrf(request)) or not request.cookies.get(auth.COOKIE_NAME):
                raise p.Denied('The form expired. Reload and try again.')
        finally:
            conn.close()
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > limit:
                raise ValueError('The page request is too large. Select fewer pages or retry at a lower resolution.')
            raw.extend(chunk)
        return bytes(raw)

    @router.post('/documents/intake/page')
    @router.post('/documents/intake/pages-result')
    async def page_reading(request: Request):
        import documents_page_reader as page_reader
        from pdf_reader_process import PDFBusy
        headers = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
        try:
            aggregate = request.url.path.endswith('/pages-result')
            expected = ('application/json',) if aggregate else ('image/jpeg', 'image/png')
            if request.headers.get('content-type', '').split(';')[0] not in expected:
                raise ValueError('Unsupported page request format.')
            raw = await transient_page_body(request, page_reader.MAX_RESULT_BYTES if aggregate else page_reader.MAX_IMAGE_BYTES)
            result = (page_reader.summarize(json.loads(raw)) if aggregate else
                      await page_reader.read_image_async(raw, disconnected=request.is_disconnected))
            return JSONResponse(result, headers=headers)
        except p.Denied:
            return JSONResponse({'error': 'Your session expired or this account is unavailable. Sign in again.'}, status_code=403, headers=headers)
        except PDFBusy as exc:
            return JSONResponse({'error': str(exc)}, status_code=429, headers={**headers, 'Retry-After': '3'})
        except ValueError as exc:
            return JSONResponse({'error': str(exc)}, status_code=400, headers=headers)
        except Exception:
            return JSONResponse({'error': 'The page could not be read. Retry it or continue manually.'}, status_code=400, headers=headers)

    @router.post('/documents/intake/read')
    async def intake_read(request: Request):
        import asyncio
        import documents_reader as reader
        conn = get_conn()
        headers = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
        try:
            p.actor(conn, getattr(request.state, 'user', None))
            d.writable(conn)
            supplied = request.headers.get('x-csrf-token', '')
            if not supplied or not hmac.compare_digest(supplied, csrf(request)) or not request.cookies.get(auth.COOKIE_NAME):
                raise p.Denied('The form expired. Reload and try again.')
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > reader.MAX_BYTES:
                    raise ValueError('Choose a PDF no larger than 20 MiB.')
                raw.extend(chunk)
            content_type = request.headers.get('content-type', '').split(';')[0]
            if content_type == 'application/pdf':
                result = await reader.read_pdf_async(bytes(raw), disconnected=request.is_disconnected)
            elif content_type == 'application/json' and len(raw) <= 4096:
                payload = json.loads(raw)
                url = payload.get('url') if isinstance(payload, dict) else None
                if not isinstance(url, str) or not url.strip():
                    raise ValueError('Enter a public PDF link or select a PDF.')
                pdf = await asyncio.to_thread(reader.fetch_pdf, url.strip())
                result = await reader.read_pdf_async(pdf, first_page=True, disconnected=request.is_disconnected)
            else:
                raise ValueError('Select a PDF or enter a public PDF link.')
            return JSONResponse(result, headers=headers)
        except p.Denied:
            return JSONResponse({'error': 'The form expired or the account is unavailable.'}, status_code=403, headers=headers)
        except reader.PDFBusy as exc:
            return JSONResponse({'error': str(exc)}, status_code=429, headers={**headers, 'Retry-After': '3'})
        except ValueError as exc:
            return JSONResponse({'error': str(exc)}, status_code=400, headers=headers)
        except Exception:
            return JSONResponse({'error': 'The PDF could not be read. Select the file or continue manually.'}, status_code=400, headers=headers)
        finally:
            conn.close()

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
            selected=request.query_params.get('file','')
            values['preview_file']=next((v for v in values['versions'] if str(v['id'])==selected),
                                        next((v for v in values['versions'] if v['id']==values['doc']['current_version']),
                                             values['versions'][0] if values['versions'] else None))
            response=render(request,conn,'detail',**values)
            response.headers['Cache-Control']='no-store'
            return response
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

    @router.post('/documents/{doc_id}/memo.docx')
    async def memo_draft(request: Request, doc_id: int):
        conn = get_conn()
        try:
            data = await posted(request)
            user = p.actor(conn, request.state.user)
            doc = d.get(conn, user, doc_id)
            d.writable(conn)
            d.require(p.can_work(conn, user, doc) and doc['direction'] == 'OUT'
                      and doc['status'] not in ('closed', 'cancelled', 'released', 'awaiting_acknowledgment')
                      and not doc['archived_at'])
            content = memo.build(doc, data)
            return Response(content, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            headers={'Content-Disposition': f'attachment; filename="{doc["number"]}-memo-draft.docx"',
                                     'Cache-Control': 'no-store'})
        except p.Denied as exc:
            return HTMLResponse(str(exc), status_code=403)
        except ValueError as exc:
            return HTMLResponse(str(exc), status_code=400)
        finally:
            conn.close()

    @router.get('/documents/{doc_id}/annotate/{version_id}', response_class=HTMLResponse)
    def annotation_page(request: Request, doc_id: int, version_id: int):
        conn = get_conn()
        try:
            user = p.actor(conn, request.state.user)
            doc, file_version = annotations.source(conn, user, doc_id, version_id)
            items = annotations.list_for_version(conn, user, doc_id, version_id)
            for item in items:
                item['strokes'] = json.loads(item['strokes_json'])
            can_annotate = (d.enabled(conn) and not doc['archived_at'] and
                doc['status'] not in ('closed', 'cancelled', 'released', 'awaiting_acknowledgment') and
                (p.can_work(conn, user, doc) or (doc['reviewer_id'] == user['id'] and doc['status'] == 'in_review')))
            response = render(request, conn, 'annotate', doc=doc, file_version=file_version,
                              annotations=items, can_annotate=can_annotate)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except p.Denied as exc:
            return HTMLResponse(str(exc), status_code=404)
        finally:
            conn.close()

    @router.post('/documents/{doc_id}/annotate/{version_id}')
    async def annotation_save(request: Request, doc_id: int, version_id: int):
        try:
            import asyncio
            data = await posted(request)
            ink = data.get('kind') == 'ink'
            strokes = json.loads(data.get('strokes', '[]')) if ink and isinstance(data.get('strokes'), str) else data.get('strokes') if ink else None
            def save():
                conn = get_conn()
                try:
                    return annotations.save(conn, request.state.user, doc_id, version_id,
                                            data.get('revision'), data.get('page_number'),
                                            body=data.get('body', ''), strokes=strokes,
                                            source_sha256=data.get('source_sha256', ''))
                finally:
                    conn.close()
            await asyncio.to_thread(save)
            return RedirectResponse(f'/documents/{doc_id}/annotate/{version_id}', status_code=303)
        except p.Denied as exc:
            return HTMLResponse(str(exc), status_code=403)
        except (ValueError, TypeError) as exc:
            return HTMLResponse(str(exc), status_code=409 if isinstance(exc, d.Conflict) else 400)

    @router.post('/documents/{doc_id}/index-file')
    async def index_file(request: Request, doc_id: int):
        try:
            import asyncio
            data = await posted(request)
            version_id = int(data.get('version_id'))
            def index():
                conn = get_conn()
                try:
                    return file_text.index(conn, request.state.user, doc_id, version_id,
                                           data.get('revision'))
                finally:
                    conn.close()
            await asyncio.to_thread(index)
            return RedirectResponse(f'/documents/{doc_id}?file={version_id}', status_code=303)
        except p.Denied as exc:
            return HTMLResponse(str(exc), status_code=403)
        except (ValueError, TypeError) as exc:
            return HTMLResponse(str(exc), status_code=409 if isinstance(exc, d.Conflict) else 400)

    @router.post('/documents/{doc_id}/unindex-file')
    async def unindex_file(request: Request, doc_id: int):
        conn = get_conn()
        try:
            data = await posted(request)
            version_id = int(data.get('version_id'))
            file_text.remove(conn, request.state.user, doc_id, version_id, data.get('revision'))
            return RedirectResponse(f'/documents/{doc_id}', status_code=303)
        except p.Denied as exc:
            return HTMLResponse(str(exc), status_code=403)
        except (ValueError, TypeError) as exc:
            return HTMLResponse(str(exc), status_code=409 if isinstance(exc, d.Conflict) else 400)
        finally:
            conn.close()

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

    @router.get('/admin/documents/readiness', response_class=HTMLResponse)
    def admin_readiness(request: Request):
        conn = get_conn()
        try:
            readiness = work_readiness.report(conn, getattr(request.state, 'user', None))
            return templates.TemplateResponse(request, 'documents/readiness.html', {
                'nav_active': 'documents_setup', 'readiness': readiness,
            })
        except p.Denied as e:
            return HTMLResponse(str(e), status_code=403)
        finally:
            conn.close()

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

    @router.get('/documents/registrations/{submission_id}')
    def registration_status(request:Request,submission_id:str):
        conn=get_conn()
        headers={'Cache-Control':'no-store','Pragma':'no-cache'}
        try:
            return JSONResponse(registration.status(conn,request.state.user,submission_id),headers=headers)
        except p.Denied:
            return JSONResponse({'state':'unavailable','error':'The registration result is unavailable to this account. Sign in again if needed.'},status_code=404,headers=headers)
        finally:
            conn.close()

    def save_registration(user,data):
        # Own this connection in the worker thread; SQLite connections cannot
        # cross threads. Waiting for another writer must not block navigation.
        conn=get_conn()
        try:
            return registration.register(conn,user,data)
        finally:
            conn.close()

    @router.post('/documents/new')
    async def create(request:Request):
        import asyncio
        data={}
        json_reply='application/json' in request.headers.get('accept','')
        headers={'Cache-Control':'no-store','Pragma':'no-cache'}
        try:
            data=await posted(request)
            result=await asyncio.to_thread(save_registration,request.state.user,data)
            return JSONResponse(result,headers=headers) if json_reply else RedirectResponse(result['url'],status_code=303)
        except (ValueError,sqlite3.IntegrityError) as exc:
            code=403 if isinstance(exc,p.Denied) else 409 if isinstance(exc,d.Conflict) else 400
            if json_reply:
                return JSONResponse({'state':'unavailable' if code==403 else 'conflict' if code==409 else 'invalid',
                    'error':str(exc)},status_code=code,headers=headers)
            conn=get_conn()
            try:
                return intake_page(request,conn,data,error=str(exc),status_code=code)
            finally:
                conn.close()
        except Exception as exc:
            busy=isinstance(exc,sqlite3.OperationalError) and (getattr(exc,'sqlite_errorcode',0) & 255) in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)
            message='The save is not confirmed. Check the saved result or retry this same submission; do not start another registration yet.'
            if busy:
                headers['Retry-After']='3'
            if json_reply:
                return JSONResponse({'state':'unconfirmed','error':message},status_code=503 if busy else 500,headers=headers)
            conn=get_conn()
            try:
                return intake_page(request,conn,data,error=message,status_code=503 if busy else 500)
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
            if action not in ('restore','instruction_read') and d.get(conn,user,doc_id)['archived_at']:
                raise ValueError('Restore this document before changing it.')
            if action=='instruction_read':
                d.mark_instruction_read(conn,user,doc_id,int(data['directive_id']))
            elif action in ('archive','restore'):
                d.set_archived(conn,user,doc_id,revision,action=='archive',data['reason'])
            elif action=='attach':
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
                extraction_doc=d.get(conn,user,doc_id) if action=='extract' else None
                try:
                    result=ops.execute(conn,operation)
                except Exception:
                    if action!='extract':
                        raise
                    raise ValueError('The source could not be read. Your document is unchanged. Correct fields manually or retry extraction.') from None
                if action=='extract':
                    # Reload permission after external I/O, but retain the revision
                    # captured before extraction so concurrent corrections cannot be overwritten.
                    d.get(conn,user,doc_id)
                    source=json.loads(rows(conn,'SELECT payload_json FROM document_job WHERE id=?',(operation,))[0]['payload_json'])
                    response=render(request,conn,'extraction',doc=extraction_doc,result=result,source_url=source['url'])
                    response.headers['Cache-Control']='no-store'
                    return response
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
