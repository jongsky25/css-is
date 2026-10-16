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
        fields = dict(await request.form())
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
            latest = next((event for event in events if event['task_id']==task['id'] and event['action'] in ('task_return','task_submit','task_reassign','task_reopen','task_cancel','task_accept')), None)
            task['return_note'] = latest['note'] if latest and latest['action']=='task_return' else ''
            task['task_history'] = [event for event in events if event['task_id']==task['id']]
            if task['primary']:
                next_steps.append(task)
        unfinished = [task for task in tasks if task['mandatory'] and task['status'] not in ('done','cancelled')]

        return render(request, conn, 'detail', status_code=status_code, error=error, case=case,
                      tasks=tasks, task_labels=work_tasks.LABELS, counts=counts, next_steps=next_steps, unfinished=unfinished, blocked=blocked, can_link=work.can_link(conn, user, case),
                      documents=work.linked_documents(conn, user, case_id), history=events,
                      choices=work.document_choices(conn, user, request.query_params.get('q', '')),
                      officer=work.officer(conn, user, case), submitted=submitted or {})

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
        return render(request, conn, 'discussion', status_code=status_code, error=error,
                      thread_url='/work/' + str(case_id) + '/discussion' + ('?task_id=' + str(task_id) if task_id else '?'),
                      selected=selected, revisions=revisions[:30], older_history=revisions[29]['revision'] if len(revisions)>30 else None,
                      reply=reply, submitted=submitted or {}, **values)

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
                                     int(fields.get('revision', '')), fields.get('body'))
            elif fields.get('action') == 'post':
                cid = work_discussion.post(conn, request.state.user, case_id, fields.get('body'), task_id,
                                          int(fields['parent_id']) if fields.get('parent_id') else None)
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
            work_tasks.mutate(conn, request.state.user, case_id, task_id,
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
