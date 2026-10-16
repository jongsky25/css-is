"""Authenticated shared-work screens; session-bound CSRF for every write."""
import hashlib
import hmac
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import documents as docs
import documents_permissions as permissions
from documents_storage import rows
import work
import work_tasks
import work_compat
import work_inbox
import work_discussion
import work_updates
import work_blockers
import work_decisions
import work_handoff
import work_team
import work_review


def csrf(request):
    return hmac.new(auth._secret(), ('work:' + request.cookies.get(auth.COOKIE_NAME, '')).encode(), hashlib.sha256).hexdigest()


def make_router(templates, get_conn):
    router = APIRouter()

    def context(request, conn, **values):
        permissions.actor(conn, getattr(request.state, 'user', None))
        people = rows(conn, '''SELECT u.id,u.username,COALESCE(NULLIF(r.name,''),u.username) AS name
                               FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id
                               WHERE u.active=1 ORDER BY name,u.id''')
        return {'nav_active': 'work', 'enabled': work.enabled(conn), 'csrf': csrf(request),
                'error': '', 'people': people, 'names': {u['id']: u['name'] for u in rows(conn, "SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id")},
                'units': rows(conn, 'SELECT id,name FROM org_unit ORDER BY path'), **values}

    def render(request, conn, template, status_code=200, **values):
        return templates.TemplateResponse(request, 'work/' + template + '.html',
                                          context(request, conn, **values), status_code=status_code)

    async def posted(request):
        form = await request.form()
        fields = dict(form)
        fields['mentions'] = form.getlist('mentions')
        fields['affected_tasks'] = form.getlist('affected_tasks')
        if not hmac.compare_digest(str(fields.get('csrf', '')), csrf(request)):
            raise permissions.Denied('The form expired. Reload this page and try again.')
        return fields

    def detail(request, conn, case_id, status_code=200, error='', submitted=None):
        user = permissions.actor(conn, request.state.user)
        case = work.get(conn, user, case_id)
        events = rows(conn, '''SELECT e.action,e.created_at,e.detail_json,COALESCE(NULLIF(r.name,''),u.username) AS actor
                               FROM work_event e JOIN admin_user u ON u.id=e.actor_id
                               LEFT JOIN resource_person r ON r.id=u.rp_id
                               WHERE e.case_id=? ORDER BY e.id DESC''', (case_id,))
        for event in events:
            payload = json.loads(event['detail_json'])
            event['note'] = payload.get('reason', '')
            event['task_title'] = payload.get('title', '')
            event['submission'] = payload.get('submission', '') if event['action']=='task_submit' else ''
            event['task_id'] = payload.get('task_id')
            event['owner_id'] = payload.get('owner_id')
            event['followup_owner_id'] = payload.get('followup_owner_id')
            event['followup_date'] = payload.get('followup_date')
            event['prerequisite_title'] = payload.get('prerequisite_title')
            event['previous_blocker'] = payload.get('previous_blocker')
            event['decision_id'] = payload.get('decision_id')
            event['status'] = work_tasks.LABELS.get(payload.get('status'), '')
        tasks = work_tasks.list_for_case(conn, user, case_id)
        blocked = ''
        try:
            work_compat.require_open(conn, case_id)
        except ValueError as e:
            blocked = str(e)
        counts = {state:0 for state in work_tasks.LABELS}
        next_steps = []
        for task in tasks:
            counts[task['status']] += 1
            task['pending_decisions'] = work_decisions.pending(conn,task['id'])
            task['source_message'] = work_decisions.task_source(conn,user,case_id,task['id'])
            task['dependencies'] = work_blockers.dependencies(conn,task['id'])
            task['waiting_on'] = [t for t in task['dependencies'] if t['status']!='done']
            task['can_block'],task['can_depend'] = work_blockers.authority(conn,user,case,task)
            if blocked:
                task['can_block']=task['can_depend']=False
            task['followup_available'] = not task['blocker_owner_id'] or work_updates.permitted(conn,task['blocker_owner_id'],case_id)
            task['actions'] = [] if blocked else work_tasks.actions(conn, user, case, task)
            task['attention'] = ''
            if task['owner_id'] and task['status'] != 'cancelled':
                try:
                    work_tasks._owner(conn,case_id,task['owner_id'])
                except ValueError as e:
                    task['attention'] = str(e)
                    task['actions'] = [a for a in task['actions'] if a in ('reassign','cancel','milestone')]
            preferred = {'proposed':'confirm','todo':'acknowledge','in_progress':'submit','for_review':'accept'}.get(task['status'])
            if preferred in ('acknowledge','submit') and task['owner_id']!=user['id']:
                preferred = None  # Officer intervention remains available as another authorized action.
            task['primary'] = preferred if preferred in task['actions'] and work.enabled(conn) else None
            labels = {'confirm':'Confirm assignment','acknowledge':'Acknowledge and start',
                      'submit':'Submit for review','accept':'Review submitted contribution'}
            task['next_label'] = labels.get(task['primary'], {'proposed':'Awaiting officer confirmation',
                'todo':'Waiting for the owner to start','in_progress':'Waiting for the owner’s output',
                'for_review':'Awaiting lead or officer review','done':'Accepted contribution','cancelled':'Cancelled — retained for history'}[task['status']])
            if task['pending_decisions']:
                task['next_label'] = 'Review changed work direction'
            elif task['blocker_reason'] or task['waiting_on']:
                task['next_label'] = 'Review blocker or prerequisite contributions'
            latest = next((event for event in events if event['task_id']==task['id'] and event['action'] in ('task_return','task_submit','task_reassign','task_reopen','task_cancel','task_accept')), None)
            task['return_note'] = latest['note'] if latest and latest['action']=='task_return' else ''
            task['task_history'] = [event for event in events if event['task_id']==task['id']]
            if task['primary']:
                next_steps.append(task)
        unfinished = [task for task in tasks if task['mandatory'] and task['status'] not in ('done','cancelled')]

        return render(request, conn, 'detail', status_code=status_code, error=error, case=case,
                      tasks=tasks, task_labels=work_tasks.LABELS, counts=counts, next_steps=next_steps, unfinished=unfinished, blocked=blocked, can_link=work.can_link(conn, user, case),
                      documents=work.linked_documents(conn, user, case_id), history=events, working_draft=work_handoff.current(conn,case_id),
                      choices=work.document_choices(conn, user, request.query_params.get('q', '')),
                      officer=work.officer(conn, user, case), blocker_people=work_updates.candidates(conn,user,case_id), blocker_viewer_id=user['id'], submitted=submitted or {})

    def discussion_page(request, conn, case_id, status_code=200, error='', submitted=None):
        query = request.query_params
        task_id = int(query['task_id']) if query.get('task_id') else None
        values = work_discussion.page(conn, request.state.user, case_id, task_id,
                    before=int(query['before']) if query.get('before') else None,
                    focus=int(query['focus']) if query.get('focus') else None)
        selected = None
        revisions = []
        if query.get('message'):
            selected, revisions = work_discussion.history(conn, request.state.user, case_id, task_id, int(query['message']),
                before=int(query['history_before']) if query.get('history_before') else None)
        reply = work_discussion.message(conn, case_id, task_id, int(query['reply'])) if query.get('reply') else None
        for message in values['messages']:
            message['mentions'] = work_updates.mentions(conn, message['id'], message['revision'])
            message['unread'] = work_updates.read_revision(conn, values['viewer_id'], message['id']) < message['revision']
        for revision in revisions:
            revision['mentions'] = work_updates.mentions(conn, selected['id'], revision['revision'])
        if selected:
            selected['mentioned_ids'] = [m['user_id'] for m in work_updates.mentions(conn, selected['id'], selected['revision'])]
        return render(request, conn, 'discussion', status_code=status_code, error=error,
                      thread_url='/work/' + str(case_id) + '/discussion' + ('?task_id=' + str(task_id) if task_id else '?'),
                      selected=selected, revisions=revisions[:30], older_history=revisions[29]['revision'] if len(revisions)>30 else None,
                      reply=reply, submitted=submitted or {}, mention_people=work_updates.candidates(conn, request.state.user, case_id),
                      following=work_updates.following(conn, request.state.user, case_id, task_id),
                      following_case=work_updates.following(conn, request.state.user, case_id) if task_id else False,
                      observed=[[m['id'],m['revision']] for m in values['messages']], **values)

    @router.get('/work/{case_id}/discussion', response_class=HTMLResponse)
    def discussion(request: Request, case_id: int):
        conn = get_conn()
        try:
            return discussion_page(request, conn, case_id)
        except permissions.Denied:
            return HTMLResponse('Discussion not found or unavailable to you.', status_code=404)
        except (ValueError, TypeError):
            return HTMLResponse('Invalid discussion link.', status_code=400)
        finally:
            conn.close()

    @router.post('/work/{case_id}/discussion/messages')
    async def discussion_change(request: Request, case_id: int):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            task_id = int(request.query_params['task_id']) if request.query_params.get('task_id') else None
            if fields.get('action') == 'edit':
                cid = int(fields.get('comment_id', ''))
                work_discussion.edit(conn, request.state.user, case_id, task_id, cid,
                                     int(fields.get('revision', '')), fields.get('body'), mentions=fields['mentions'])
            elif fields.get('action') == 'post':
                cid = work_discussion.post(conn, request.state.user, case_id, fields.get('body'), task_id,
                                          int(fields['parent_id']) if fields.get('parent_id') else None, mentions=fields['mentions'])
            else:
                raise ValueError('Choose a discussion action.')
            url = '/work/' + str(case_id) + '/discussion?focus=' + str(cid)
            if task_id:
                url += '&task_id=' + str(task_id)
            return RedirectResponse(url + '#message-' + str(cid), status_code=303)
        except permissions.Denied:
            return HTMLResponse('Discussion or action not available to you. Reload the page.', status_code=403)
        except (ValueError, TypeError) as e:
            try:
                return discussion_page(request, conn, case_id, status_code=409 if isinstance(e, docs.Conflict) else 400,
                                       error=str(e), submitted=fields)
            except permissions.Denied:
                return HTMLResponse('Discussion not found or unavailable to you.', status_code=404)
            except (ValueError, TypeError):
                return HTMLResponse('Invalid discussion link.', status_code=400)
        finally:
            conn.close()

    @router.get('/work/updates', response_class=HTMLResponse)
    def updates(request: Request, before: int | None = None):
        conn = get_conn()
        try:
            notices, cursor = work_updates.inbox(conn, request.state.user, before)
            return render(request, conn, 'updates', notices=notices, next_cursor=cursor, before=before)
        except permissions.Denied:
            return HTMLResponse('Updates unavailable.', status_code=403)
        finally:
            conn.close()

    @router.post('/work/{case_id}/discussion/preferences')
    async def discussion_preferences(request: Request, case_id: int):
        conn = get_conn()
        try:
            fields = await posted(request)
            task_id = int(fields['task_id']) if fields.get('task_id') else None
            if fields.get('action') in ('follow', 'unfollow'):
                work_updates.follow(conn, request.state.user, case_id, task_id, fields['action']=='follow')
            elif fields.get('action') == 'read':
                work_updates.mark_read(conn, request.state.user, case_id, task_id, json.loads(fields.get('observed', '[]')))
            else:
                raise ValueError('Unknown discussion preference.')
            return RedirectResponse('/work/' + str(case_id) + '/discussion' + ('?task_id=' + str(task_id) if task_id else ''), status_code=303)
        except permissions.Denied:
            return HTMLResponse('Discussion unavailable.', status_code=403)
        except (ValueError, TypeError):
            return HTMLResponse('The discussion preference could not be saved. Reload and try again.', status_code=400)
        finally:
            conn.close()

    def source_page(request, conn, case_id, comment_id, status_code=200, error='', fields=None):
        user, case, message = work_decisions.source(conn, request.state.user, case_id, comment_id)
        tasks = work_tasks.list_for_case(conn,user,case_id)
        documents = work.linked_documents(conn,user,case_id)
        linked_task = conn.execute('SELECT task_id FROM work_task_source WHERE comment_id=?',(comment_id,)).fetchone()
        blocked = ''
        try:
            work_compat.require_open(conn,case_id)
        except ValueError as e:
            blocked = str(e)
        return render(request,conn,'message_actions',status_code=status_code,error=error,case=case,message=message,
            tasks=tasks,documents=documents,values=fields or {},task_revisions={str(t['id']):t['revision'] for t in tasks},
            document_revisions={str(d['id']):d['revision'] for d in documents},
            can_decide=work_decisions.can_decide(conn,user,case),linked_task=linked_task[0] if linked_task else None,
            source_url=work_decisions.source_url(case_id,comment_id,message['task_id']),blocked=blocked,
            previous=rows(conn, "SELECT id,body FROM work_decision d WHERE case_id=? AND NOT EXISTS(SELECT 1 FROM work_decision n WHERE n.supersedes_id=d.id) ORDER BY id DESC",(case_id,)))

    @router.get('/work/{case_id}/messages/{comment_id}/actions', response_class=HTMLResponse)
    def message_actions(request: Request, case_id: int, comment_id: int):
        conn=get_conn()
        try:
            return source_page(request,conn,case_id,comment_id)
        except permissions.Denied:
            return HTMLResponse('Message unavailable.',status_code=404)
        finally:
            conn.close()

    @router.post('/work/{case_id}/messages/{comment_id}/actions')
    async def save_message_action(request: Request, case_id: int, comment_id: int):
        conn=get_conn();fields={}
        try:
            fields=await posted(request)
            revision=int(fields.get('source_revision',''))
            if fields.get('action')=='task':
                task=work_decisions.propose(conn,request.state.user,case_id,comment_id,revision,fields)
                url=f"/work/{case_id}#task-{task['id']}"
            elif fields.get('action')=='decision':
                parsed={**fields,'task_revisions':json.loads(fields.get('task_revisions','{}')),
                        'document_revisions':json.loads(fields.get('document_revisions','{}'))}
                did=work_decisions.record(conn,request.state.user,case_id,comment_id,revision,parsed)
                url=f'/work/{case_id}/decisions/{did}'
            else:
                raise ValueError('Choose a message action.')
            return RedirectResponse(url,status_code=303)
        except permissions.Denied:
            return HTMLResponse('Message or action unavailable.',status_code=403)
        except (ValueError,TypeError) as e:
            try:
                return source_page(request,conn,case_id,comment_id,409 if isinstance(e,docs.Conflict) else 400,str(e),fields)
            except permissions.Denied:
                return HTMLResponse('Message unavailable.',status_code=404)
        finally:
            conn.close()

    def decision_page(request,conn,case_id,decision_id,status_code=200,error='',review_submitted=None):
        user=permissions.actor(conn,request.state.user)
        case,decision,affected=work_decisions.detail(conn,user,case_id,decision_id)
        blocked=''
        try:work_compat.require_open(conn,case_id)
        except ValueError as e:blocked=str(e)
        return render(request,conn,'decision',status_code=status_code,error=error,case=case,decision=decision,
                      affected=affected,task_labels=work_tasks.LABELS,can_decide=work_decisions.can_decide(conn,user,case),blocked=blocked,review_submitted=review_submitted or {})

    @router.get('/work/{case_id}/decisions', response_class=HTMLResponse)
    def decisions(request: Request,case_id: int,before: int | None = None):
        conn=get_conn()
        try:
            case=work.get(conn,request.state.user,case_id)
            decisions=rows(conn, "SELECT d.*,(SELECT id FROM work_decision n WHERE n.supersedes_id=d.id) AS successor_id FROM work_decision d WHERE case_id=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT 26",(case_id,before,before))
            return render(request,conn,'decisions',case=case,decisions=decisions[:25],next_cursor=decisions[24]['id'] if len(decisions)>25 else None)
        except permissions.Denied:
            return HTMLResponse('Work decisions unavailable.',status_code=404)
        finally:conn.close()

    @router.get('/work/{case_id}/decisions/{decision_id}', response_class=HTMLResponse)
    def decision(request: Request,case_id: int,decision_id: int):
        conn=get_conn()
        try:return decision_page(request,conn,case_id,decision_id)
        except permissions.Denied:return HTMLResponse('Work decision unavailable.',status_code=404)
        finally:conn.close()

    @router.post('/work/{case_id}/decisions/{decision_id}/resolve')
    async def resolve_decision(request: Request,case_id: int,decision_id: int):
        conn=get_conn();fields={}
        try:
            fields=await posted(request)
            work_decisions.resolve(conn,request.state.user,case_id,decision_id,int(fields.get('task_id','')),
                int(fields.get('revision','')),fields.get('outcome'),fields.get('reason'))
            return RedirectResponse(f'/work/{case_id}/decisions/{decision_id}',status_code=303)
        except permissions.Denied:return HTMLResponse('Decision or action unavailable.',status_code=403)
        except (ValueError,TypeError) as e:
            try:return decision_page(request,conn,case_id,decision_id,409 if isinstance(e,docs.Conflict) else 400,str(e),fields)
            except permissions.Denied:return HTMLResponse('Work decision unavailable.',status_code=404)
        finally:conn.close()

    def handoff_page(request,conn,case_id,status_code=200,error='',submitted=None):
        q=request.query_params
        values=work_handoff.page(conn,request.state.user,case_id,
            task_id=int(q['task_id']) if q.get('task_id') else None,
            before=int(q['before']) if q.get('before') else None,
            draft_before=int(q['draft_before']) if q.get('draft_before') else None,
            file_before=int(q['file_before']) if q.get('file_before') else None)
        blocked=''
        try:work_compat.require_open(conn,case_id)
        except ValueError as e:blocked=str(e)
        return render(request,conn,'draft',status_code=status_code,error=error,submitted=submitted or {},
            blocked=blocked,task_labels=work_tasks.LABELS,
            task_revisions={str(t['id']):t['revision'] for t in values['handoff_tasks']},**values)

    @router.get('/work/{case_id}/draft', response_class=HTMLResponse)
    def draft(request: Request,case_id: int):
        conn=get_conn()
        try:return handoff_page(request,conn,case_id)
        except permissions.Denied:return HTMLResponse('Work draft unavailable.',status_code=404)
        except (ValueError,TypeError):return HTMLResponse('Invalid draft or handoff link.',status_code=400)
        finally:conn.close()

    @router.post('/work/{case_id}/draft')
    async def save_draft(request: Request,case_id: int):
        conn=get_conn();fields={}
        try:
            fields=await posted(request)
            action=fields.get('action');anchor='working-draft'
            if action in ('set_draft','clear_draft'):
                work_handoff.set_draft(conn,request.state.user,case_id,int(fields.get('draft_id','')),fields,clear=action=='clear_draft')
            elif action=='add_file':
                work_handoff.add_file(conn,request.state.user,case_id,fields);anchor='supporting-files'
            elif action=='retire_file':
                work_handoff.retire_file(conn,request.state.user,case_id,int(fields.get('support_id','')),fields.get('reason'));anchor='supporting-files'
            elif action=='handoff':
                revisions=json.loads(fields.get('task_revisions','{}'))
                if not isinstance(revisions,dict):raise ValueError('Reload the contribution choices.')
                tid=int(fields.get('task_id',''))
                hid=work_handoff.post(conn,request.state.user,case_id,tid,int(revisions.get(str(tid),0)),
                    int(fields.get('draft_id','')),fields.get('note'),int(fields['support_id']) if fields.get('support_id') else None)
                anchor='handoff-'+str(hid)
            else:raise ValueError('Choose a draft or handoff action.')
            return RedirectResponse(f'/work/{case_id}/draft#{anchor}',status_code=303)
        except permissions.Denied:return HTMLResponse('Draft or handoff action unavailable.',status_code=403)
        except (ValueError,TypeError) as e:
            try:return handoff_page(request,conn,case_id,409 if isinstance(e,docs.Conflict) else 400,str(e),fields)
            except permissions.Denied:return HTMLResponse('Work draft unavailable.',status_code=404)
            except (ValueError,TypeError):return HTMLResponse('Invalid draft or handoff link.',status_code=400)
        finally:conn.close()

    def consolidation_page(request,conn,case_id,status_code=200,error='',submitted=None):
        return render(request,conn,'consolidation',status_code=status_code,error=error,
            submitted=submitted or {},task_labels=work_tasks.LABELS,**work_review.page(conn,request.state.user,case_id))

    @router.get('/work/{case_id}/consolidation',response_class=HTMLResponse)
    def consolidation(request: Request,case_id: int):
        conn=get_conn()
        try:return consolidation_page(request,conn,case_id)
        except permissions.Denied:return HTMLResponse('Consolidation unavailable.',status_code=404)
        finally:conn.close()

    @router.post('/work/{case_id}/consolidation/{document_id}')
    async def consolidation_change(request: Request,case_id: int,document_id: int):
        conn=get_conn();fields={}
        try:
            fields=await posted(request)
            work.get(conn,request.state.user,case_id)
            work.writable(conn)
            if document_id not in {d['id'] for d in work.linked_documents(conn,request.state.user,case_id)}:
                raise permissions.Denied('Correspondence unavailable.')
            if fields.get('action') not in ('review_route','review'):
                raise ValueError('Choose a review action.')
            docs.mutate(conn,request.state.user,document_id,int(fields.get('revision','')),
                        fields['action'],{**fields,'work_case_id':case_id})
            return RedirectResponse(f'/work/{case_id}/consolidation',status_code=303)
        except permissions.Denied:return HTMLResponse('Review or correspondence unavailable to you.',status_code=403)
        except (ValueError,TypeError) as e:
            try:return consolidation_page(request,conn,case_id,409 if isinstance(e,docs.Conflict) else 400,str(e),{**fields,'document_id':document_id})
            except permissions.Denied:return HTMLResponse('Consolidation unavailable.',status_code=404)
        finally:conn.close()

    @router.get('/work', response_class=HTMLResponse)
    def index(request: Request, before: int | None = None):
        conn = get_conn()
        try:
            cases, next_cursor = work.list_page(conn, request.state.user, before=before)
            return render(request, conn, 'index', cases=cases, next_cursor=next_cursor, before=before)
        except permissions.Denied as e:
            return HTMLResponse(str(e), status_code=403)
        finally:
            conn.close()

    @router.get('/work/new', response_class=HTMLResponse)
    def new(request: Request, source_document_id: int | None = None):
        conn = get_conn()
        try:
            user = permissions.actor(conn, request.state.user)
            source = work.resolved_document(conn, source_document_id) if source_document_id else None
            if source_document_id:
                permissions.require_view(conn, user, source)
            return render(request, conn, 'new', values={'source_document_id': source['id'], 'title': source['subject'],
                                                       'unit_id': source['unit_id']} if source else {}, source=source)
        except permissions.Denied:
            return HTMLResponse('Document not found or unavailable to you.', status_code=404)
        finally:
            conn.close()

    @router.post('/work/new')
    async def create(request: Request):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            case = work.create(conn, request.state.user, fields)
            return RedirectResponse('/work/' + str(case['id']), status_code=303)
        except permissions.Denied as e:
            return HTMLResponse(str(e), status_code=403)
        except (ValueError, TypeError) as e:
            return render(request, conn, 'new', status_code=400, error=str(e), values=fields, source=None)
        finally:
            conn.close()

    @router.get('/work/mine', response_class=HTMLResponse)
    def mine(request: Request, before: int | None = None, view: str = 'action'):
        conn = get_conn()
        try:
            if view not in ('action', 'waiting'):
                return HTMLResponse('Unknown work view.', status_code=400)
            items, cursor = work_inbox.page(conn, request.state.user, before=before, waiting=view=='waiting')
            return render(request, conn, 'mine', items=items, next_cursor=cursor, before=before, view=view)
        except permissions.Denied:
            return HTMLResponse('An active staff account is required.', status_code=403)
        except ValueError as e:
            return HTMLResponse(str(e), status_code=400)
        finally:
            conn.close()

    def team_page(request, conn, status_code=200, error='', submitted=None, focused=None):
        selection = work_team.filters(request.query_params)
        items, cursor = work_team.page(conn, request.state.user, selection)
        return render(request, conn, 'team', status_code=status_code, error=error,
            items=items, selection=selection, task_labels=work_tasks.LABELS,
            team_url=work_team.url(selection), list_url=work_team.url(selection,view='list'),
            board_url=work_team.url(selection,view='board'),
            first_url=work_team.url(selection,before=''),
            next_url=work_team.url(selection,before=cursor) if cursor else None,
            submitted=submitted or {}, focused=focused, saved=request.query_params.get('saved')=='1')

    @router.get('/work/team', response_class=HTMLResponse)
    def team(request: Request):
        conn = get_conn()
        try:
            return team_page(request,conn)
        except permissions.Denied:
            return HTMLResponse('An active staff account is required.',status_code=403)
        except (ValueError,TypeError):
            return HTMLResponse('Invalid team filters. Start again at /work/team.',status_code=400)
        finally: conn.close()

    @router.post('/work/team/{case_id}/{task_id}/{action}')
    async def team_change(request: Request, case_id: int, task_id: int, action: str):
        conn = get_conn()
        fields = {}
        try:
            selection = work_team.filters(request.query_params)
            fields = await posted(request)
            work_tasks.mutate(conn,request.state.user,case_id,task_id,int(fields.get('revision','')),action,fields)
            return RedirectResponse(work_team.url(selection)+'&saved=1',status_code=303)
        except permissions.Denied:
            return HTMLResponse('Contribution or action unavailable. Reload the team view.',status_code=403)
        except (ValueError,TypeError) as e:
            try:
                focused=work_team.one(conn,request.state.user,case_id,task_id)
                return team_page(request,conn,409 if isinstance(e,docs.Conflict) else 400,str(e),
                    {**fields,'_task_id':task_id,'_action':action},focused)
            except permissions.Denied:
                return HTMLResponse('Contribution unavailable.',status_code=404)
            except (ValueError,TypeError):
                return HTMLResponse('Invalid team filters. Start again at /work/team.',status_code=400)
        finally: conn.close()

    @router.get('/work/{case_id}', response_class=HTMLResponse)
    def show(request: Request, case_id: int):
        conn = get_conn()
        try:
            return detail(request, conn, case_id)
        except permissions.Denied:
            return HTMLResponse('Work item not found or unavailable to you.', status_code=404)
        finally:
            conn.close()

    @router.post('/work/{case_id}/{action}')
    async def change(request: Request, case_id: int, action: str):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            user = request.state.user
            # Verify visibility before returning action-specific validation errors.
            work.get(conn, user, case_id)
            revision = int(fields.get('revision', ''))
            if action == 'lead':
                work.confirm_lead(conn, user, case_id, revision, fields.get('lead_id'), fields.get('reason'))
            elif action == 'link':
                work.link_document(conn, user, case_id, revision, fields.get('document_id'))
            elif action == 'tasks':
                work_tasks.create(conn, user, case_id, fields)
            else:
                return HTMLResponse('Action not found.', status_code=404)
            return RedirectResponse('/work/' + str(case_id), status_code=303)
        except permissions.Denied:
            return HTMLResponse('Work item or action not available to you. Reload the page.', status_code=403)
        except (ValueError, TypeError) as e:
            try:
                return detail(request, conn, case_id, status_code=409 if isinstance(e, docs.Conflict) else 400,
                              error=str(e), submitted=fields)
            except permissions.Denied:
                return HTMLResponse('Work item not found or unavailable to you.', status_code=404)
        finally:
            conn.close()

    @router.post('/work/{case_id}/tasks/{task_id}/{action}')
    async def task_change(request: Request, case_id: int, task_id: int, action: str):
        conn = get_conn()
        try:
            fields = await posted(request)
            service = work_blockers.mutate if action in work_blockers.ACTIONS else work_tasks.mutate
            service(conn, request.state.user, case_id, task_id,
                              int(fields.get('revision', '')), action, fields)
            return RedirectResponse('/work/' + str(case_id) + '#task-' + str(task_id), status_code=303)
        except permissions.Denied:
            return HTMLResponse('Contribution or action not available to you. Reload the page.', status_code=403)
        except (ValueError, TypeError) as e:
            try:
                return detail(request, conn, case_id, status_code=409 if isinstance(e, docs.Conflict) else 400,
                              error=str(e), submitted={**fields, '_task_id': task_id, '_action': action})
            except permissions.Denied:
                return HTMLResponse('Work item not found or unavailable to you.', status_code=404)
        finally:
            conn.close()

    return router
