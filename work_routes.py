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
                'error': '', 'people': people, 'names': {u['id']: u['name'] for u in people},
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
            event['note'] = json.loads(event['detail_json']).get('reason', '')
        return render(request, conn, 'detail', status_code=status_code, error=error, case=case,
                      documents=work.linked_documents(conn, user, case_id), history=events,
                      choices=work.document_choices(conn, user, request.query_params.get('q', '')),
                      officer=work.officer(conn, user, case), submitted=submitted or {})

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

    return router
