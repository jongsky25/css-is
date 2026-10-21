"""Authenticated Supplies catalog/settings with session-bound form tokens."""
import hashlib
import hmac
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

import auth
import supplies
import supplies_stock as stock
import supplies_import as imports
import supplies_import_review as review
import supplies_requests as requests_service
import supplies_approvals as approvals
import supplies_backorders as backorders
import supplies_issues as issues
import supplies_acknowledgments as acknowledgments
import supplies_print as print_views
from supplies_allocations import availability
import tzutil as tz
import supplies_permissions as permissions
from supplies_storage import Conflict, Denied, Invalid, Missing, rows
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool


def csrf(request):
    return hmac.new(auth._secret(), ('supplies:' + request.cookies.get(auth.COOKIE_NAME, '')).encode(),
                    hashlib.sha256).hexdigest()


def make_router(templates, get_conn):
    router = APIRouter()

    def render(request, conn, template, *, status_code=200, **values):
        user = permissions.require_actor(conn, request.state.user)
        return templates.TemplateResponse(request, 'supplies/' + template + '.html', {
            'nav_active': 'supplies', 'enabled': supplies.enabled(conn), 'csrf': csrf(request),
            'can_configure': user['role'] == 'admin',
            'can_approve': bool(conn.execute("SELECT 1 FROM supply_role_grant WHERE user_id=? AND role='request_approver' AND revoked_at IS NULL",(user['id'],)).fetchone()),
            'can_maintain': permissions.has_role(conn, user, 'custodian'),
            'can_audit': permissions.has_role(conn, user, 'auditor'),
            'can_read_stock': (permissions.has_role(conn, user, 'custodian') or
                               permissions.has_role(conn, user, 'auditor')),
            'new_key': lambda: str(uuid4()), 'error': '', 'submitted': {}, **values,
        }, status_code=status_code)

    def failure(request, exc):
        status = 404 if isinstance(exc, Missing) else 403 if isinstance(exc, Denied) else 409 if isinstance(exc, Conflict) else 422
        return templates.TemplateResponse(request, 'supplies/error.html', {
            'nav_active': 'supplies', 'enabled': False, 'can_configure': False,
            'can_maintain': False, 'error': str(exc), 'status': status,
        }, status_code=status)

    def catalog_page(request, conn, *, error='', status_code=200, submitted=None):
        params = request.query_params
        result = supplies.catalog(conn, request.state.user, query=params.get('q', ''),
                                  include_inactive=params.get('inactive') == '1', page=params.get('page', '1'))
        def page_url(page):
            return '/supplies/items?' + urlencode({'q': result['query'],
                      'inactive': '1' if result['include_inactive'] else '0', 'page': page})
        return render(request, conn, 'catalog', status_code=status_code, error=error,
                      submitted=submitted or {}, page_url=page_url, **result)

    def item_page(request, conn, item_id, *, error='', status_code=200, submitted=None):
        item = supplies.get_item(conn, request.state.user, item_id)
        events = []
        card = None
        if permissions.has_role(conn, request.state.user, 'custodian') or permissions.has_role(conn, request.state.user, 'auditor'):
            card = stock.stock_card(conn, request.state.user, item_id, page=request.query_params.get('page', '1'))
            item = card['item']
            events = rows(conn, '''SELECT e.action,e.created_at,u.username FROM supply_event e
              JOIN admin_user u ON u.id=e.actor_id WHERE e.entity_type='item' AND e.entity_id=?
              ORDER BY e.id DESC LIMIT 50''', (item_id,))
        totals = {k: card[k] for k in ('on_hand','recorded','movement_count')} if card else stock.stock_totals(conn, request.state.user, item_id)
        return render(request, conn, 'item', item=item, events=events, card=card, totals=totals,
                      availability=availability(conn, item_id),
                      today=tz.today_local().isoformat(), error=error,
                      status_code=status_code, submitted=submitted or {})

    def receipt_form(request, conn, *, error='', status_code=200, submitted=None):
        permissions.require_custodian(conn, request.state.user)
        items = rows(conn, 'SELECT id,code,description,unit,revision FROM supply_item WHERE active=1 ORDER BY code,id')
        return render(request, conn, 'receipt_form', items=items, today=tz.today_local().isoformat(),
                      submitted=submitted or {}, error=error, status_code=status_code)

    def receipt_fields(fields):
        lines = []
        for i in range(5):
            choice = fields.get(f'item_choice_{i}', '')
            quantity = fields.get(f'quantity_{i}', '')
            cost = fields.get(f'unit_cost_{i}', '')
            expiry = fields.get(f'expiry_date_{i}', '')
            if not any((choice, quantity, cost, expiry)):
                continue
            parts = choice.split(':', 1)
            lines.append({'item_id': parts[0], 'expected_revision': parts[1] if len(parts)>1 else '',
                          'accepted_quantity': quantity, 'unit_cost': cost, 'expiry_date': expiry})
        return {**fields, 'lines': lines}

    def settings_page(request, conn, *, error='', status_code=200, submitted=None):
        values = supplies.configuration(conn, request.state.user, page=request.query_params.get('page', '1'))
        return render(request, conn, 'settings', error=error, status_code=status_code,
                      submitted=submitted or {}, **values)

    async def posted(request):
        form = await request.form(max_files=0, max_fields=60, max_part_size=16384)
        if not request.cookies.get(auth.COOKIE_NAME) or not hmac.compare_digest(str(form.get('csrf', '')), csrf(request)):
            raise Denied('The form expired. Reload the page and try again.')
        return dict(form)

    async def uploaded(request):
        # Bound the complete multipart body even when Content-Length is absent/false.
        parts, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > imports.MAX_UPLOAD + 65536:
                raise Invalid('The upload exceeds the 8 MiB workbook limit.')
            parts.append(chunk)
        async def receive():
            return {'type': 'http.request', 'body': b''.join(parts), 'more_body': False}
        bounded = Request(request.scope, receive=receive)
        async with bounded.form(max_files=1, max_fields=3, max_part_size=16384) as form:
            if not request.cookies.get(auth.COOKIE_NAME) or not hmac.compare_digest(str(form.get('csrf', '')), csrf(request)):
                raise Denied('The form expired. Reload the page and try again.')
            upload = form.get('workbook')
            if not isinstance(upload, UploadFile):
                raise Invalid('Choose an XLSX stock workbook.')
            return await upload.read(imports.MAX_UPLOAD + 1), upload.filename, form.get('operation_key')

    def import_page(request, conn, *, error='', status_code=200):
        values = imports.list_previews(conn, request.state.user, page=request.query_params.get('page', '1'))
        return render(request, conn, 'import', error=error, status_code=status_code, **values)

    async def mutation(request, callback, *, view, item_id=None):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            result = callback(conn, request.state.user, fields)
            target = ('/supplies/settings' if view == 'settings' else
                      '/supplies/receipts/' + str(result['id']) if view == 'receipt' else
                      '/supplies/items/' + str(result['id']))
            return RedirectResponse(target, status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if isinstance(exc, Denied):
                return failure(request, exc)
            status = 409 if isinstance(exc, Conflict) else 422
            try:
                if view == 'settings':
                    return settings_page(request, conn, error=str(exc), status_code=status, submitted=fields)
                if view == 'receipt':
                    return receipt_form(request, conn, error=str(exc), status_code=status, submitted=fields)
                if view == 'item':
                    return item_page(request, conn, item_id, error=str(exc), status_code=status, submitted=fields)
                return catalog_page(request, conn, error=str(exc), status_code=status, submitted=fields)
            except (Denied, Invalid, Conflict) as render_exc:
                return failure(request, render_exc)
        finally:
            conn.close()

    @router.get('/supplies')
    def home(request: Request):
        return RedirectResponse('/supplies/items', status_code=303)

    @router.get('/supplies/items')
    def catalog(request: Request):
        conn = get_conn()
        try:
            return catalog_page(request, conn)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/items/{item_id}')
    def item(request: Request, item_id: int):
        conn = get_conn()
        try:
            return item_page(request, conn, item_id)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/settings')
    def settings(request: Request):
        conn = get_conn()
        try:
            return settings_page(request, conn)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/items')
    async def create(request: Request):
        return await mutation(request, lambda c, u, f: supplies.create_item(c, u, f,
                              operation_key=f.get('operation_key')), view='catalog')

    @router.post('/supplies/items/{item_id}/update')
    async def update(request: Request, item_id: int):
        return await mutation(request, lambda c, u, f: supplies.update_item(c, u, item_id, f,
            expected_revision=f.get('revision'), operation_key=f.get('operation_key')), view='item', item_id=item_id)

    @router.post('/supplies/items/{item_id}/deactivate')
    async def deactivate(request: Request, item_id: int):
        return await mutation(request, lambda c, u, f: supplies.deactivate_item(c, u, item_id,
            expected_revision=f.get('revision'), operation_key=f.get('operation_key'), reason=f.get('reason')),
            view='item', item_id=item_id)

    @router.post('/supplies/settings/enabled')
    async def enable(request: Request):
        return await mutation(request, lambda c, u, f: supplies.set_enabled(c, u, f.get('enabled'),
            expected_revision=f.get('revision'), operation_key=f.get('operation_key')), view='settings')

    @router.post('/supplies/settings/grants')
    async def grant(request: Request):
        return await mutation(request, lambda c, u, f: supplies.grant_role(c, u, f.get('user_id'),
            f.get('role'), f.get('unit_id'), operation_key=f.get('operation_key')), view='settings')

    @router.post('/supplies/settings/grants/{grant_id}/revoke')
    async def revoke(request: Request, grant_id: int):
        return await mutation(request, lambda c, u, f: supplies.revoke_role(c, u, grant_id,
            expected_revision=f.get('revision'), operation_key=f.get('operation_key')), view='settings')

    @router.post('/supplies/items/{item_id}/opening')
    async def opening(request: Request, item_id: int):
        return await mutation(request, lambda c, u, f: stock.post_opening(c, u, item_id, f,
            expected_revision=f.get('revision'), operation_key=f.get('operation_key')), view='item', item_id=item_id)

    @router.get('/supplies/receipts')
    def receipts(request: Request):
        conn = get_conn()
        try:
            values = stock.list_receipts(conn, request.state.user, page=request.query_params.get('page', '1'))
            return render(request, conn, 'receipts', **values)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/receipts/new')
    def new_receipt(request: Request):
        conn = get_conn()
        try:
            return receipt_form(request, conn)
        except Denied as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/receipts/{receipt_id}')
    def receipt(request: Request, receipt_id: int):
        conn = get_conn()
        try:
            result = stock.get_receipt(conn, request.state.user, receipt_id)
            return render(request, conn, 'receipt', receipt=result)
        except Denied as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/receipts')
    async def receive(request: Request):
        return await mutation(request, lambda c, u, f: stock.post_receipt(c, u, receipt_fields(f),
            operation_key=f.get('operation_key')), view='receipt')

    def request_form(request, conn, draft=None, *, submitted=None, error='', status_code=200):
        user, identity = requests_service.requester(conn, request.state.user)
        if draft is not None and draft['requester_id'] != user['id']:
            raise Missing('Supply request not found or unavailable to you.')
        if draft is not None and draft['approval_status'] not in ('draft','returned'):
            raise Conflict('Only draft or returned requests can be edited.')
        items = rows(conn, 'SELECT id,code,description,unit FROM supply_item WHERE active=1 ORDER BY code')
        return render(request, conn, 'request_form', draft=draft, identity=identity, items=items,
                      max_lines=requests_service.MAX_LINES, form_values=submitted if submitted is not None else draft,
                      error=error, status_code=status_code)

    @router.get('/supplies/issuance')
    def issuance_queue(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'issuance', **issues.issuance_queue(conn, request.state.user,
                          page=request.query_params.get('page', '1')))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/issues')
    def releases(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'issues', **issues.list_issues(conn, request.state.user,
                          page=request.query_params.get('page', '1')))
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/issues/{issue_id}')
    def release_detail(request: Request, issue_id: int):
        conn = get_conn()
        try:
            return render(request, conn, 'issue', release=issues.get_issue(conn, request.state.user, issue_id),
                          today=tz.today_local().isoformat())
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/issues/{issue_id}/acknowledge')
    async def acknowledge_issue(request: Request, issue_id: int):
        return await acknowledge_change(request, issue_id, paper=False)

    @router.post('/supplies/issues/{issue_id}/paper-acknowledgment')
    async def paper_acknowledgment(request: Request, issue_id: int):
        return await acknowledge_change(request, issue_id, paper=True)

    async def acknowledge_change(request, issue_id, *, paper):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            callback = acknowledgments.record_paper_acknowledgment if paper else acknowledgments.acknowledge_issue
            callback(conn, request.state.user, issue_id, fields,
                     expected_revision=fields.get('revision'), operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/issues/' + str(issue_id), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if not isinstance(exc, Denied):
                try:
                    return render(request, conn, 'issue', release=issues.get_issue(conn, request.state.user, issue_id),
                                  today=tz.today_local().isoformat(), submitted=fields, error=str(exc),
                                  status_code=409 if isinstance(exc, Conflict) else 422)
                except (Denied, Invalid, Conflict) as read_exc:
                    return failure(request, read_exc)
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/{request_id}/print')
    def request_print(request: Request, request_id: int):
        conn = get_conn()
        try:
            values = print_views.request_print(conn, request.state.user, request_id,
                       revision=request.query_params.get('revision'))
            return templates.TemplateResponse(request, 'supplies/print.html', values)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/issues/{issue_id}/print')
    def release_print(request: Request, issue_id: int):
        conn = get_conn()
        try:
            return templates.TemplateResponse(request, 'supplies/print.html',
                       print_views.release_print(conn, request.state.user, issue_id))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/{request_id}/issues/new')
    def issue_form(request: Request, request_id: int):
        conn = get_conn()
        try:
            return render(request, conn, 'issue_form', **issues.prepare_issue(conn, request.state.user, request_id))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/requests/{request_id}/issues')
    async def post_issue(request: Request, request_id: int):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            lines = []
            for name, value in fields.items():
                if name.startswith('issue_quantity_') and value != '':
                    line_id = supplies.integer(name[len('issue_quantity_'):], 'Request line', 1)
                    lines.append({'line_id': line_id, 'issued_quantity': value,
                                  'version': fields.get('version_' + str(line_id))})
            result = issues.post_issue(conn, request.state.user, request_id, {**fields, 'lines': lines},
                      expected_revision=fields.get('revision'), operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/issues/' + str(result['id']), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if not isinstance(exc, Denied):
                try:
                    return render(request, conn, 'issue_form', **issues.prepare_issue(conn, request.state.user, request_id),
                                  submitted=fields, error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422)
                except (Denied, Invalid, Conflict) as read_exc:
                    return failure(request, read_exc)
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/awaiting-stock')
    def awaiting_stock(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'awaiting_stock', **backorders.awaiting_stock(conn, request.state.user,
                          page=request.query_params.get('page', '1')))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/allocations/refresh')
    async def refresh_reservations(request: Request):
        conn = get_conn()
        try:
            fields = await posted(request)
            backorders.refresh_reservations(conn, request.state.user, operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/awaiting-stock', status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/requests/{request_id}/cancel-remainder')
    async def cancel_remainder(request: Request, request_id: int):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            lines = [{'line_id': name[len('cancel_'):], 'version': value}
                     for name, value in fields.items() if name.startswith('cancel_')]
            result = backorders.cancel_remainder(conn, request.state.user, request_id, {**fields, 'lines': lines},
                      expected_revision=fields.get('revision'), operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/requests/' + str(result['id']), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if not isinstance(exc, Denied):
                try:
                    current = requests_service.get_request(conn, request.state.user, request_id)
                    return render(request, conn, 'request', supply_request=current, submitted=fields,
                                  error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422)
                except (Denied, Invalid, Conflict) as read_exc:
                    return failure(request, read_exc)
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/approvals')
    def approval_index(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'approvals', **approvals.inbox(conn, request.state.user,
                          page=request.query_params.get('page', '1')))
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/requests/{request_id}/decide')
    async def decide_request(request: Request, request_id: int):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            lines = []
            for name, value in fields.items():
                if name.startswith('approved_'):
                    line_id = supplies.integer(name[len('approved_'):], 'Submitted line', 1)
                    lines.append({'revision_line_id': line_id, 'approved_quantity': value,
                                  'reason': fields.get('reduction_' + str(line_id), '')})
            result = approvals.decide_request(conn, request.state.user, request_id, {**fields, 'lines': lines},
                       expected_revision=fields.get('revision'), submitted_revision=fields.get('submitted_revision'),
                       operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/requests/' + str(result['id']), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if not isinstance(exc, Denied):
                try:
                    current = requests_service.get_request(conn, request.state.user, request_id)
                    return render(request, conn, 'request', supply_request=current, submitted=fields,
                                  error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422)
                except (Denied, Invalid, Conflict) as read_exc:
                    return failure(request, read_exc)
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests')
    def request_index(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'requests', **requests_service.my_requests(conn, request.state.user,
                          page=request.query_params.get('page', '1')))
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/new')
    def new_request(request: Request):
        conn = get_conn()
        try:
            return request_form(request, conn)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/{request_id}')
    def request_detail(request: Request, request_id: int):
        conn = get_conn()
        try:
            result = requests_service.get_request(conn, request.state.user, request_id)
            return render(request, conn, 'request', supply_request=result)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/{request_id}/edit')
    def edit_request(request: Request, request_id: int):
        conn = get_conn()
        try:
            return request_form(request, conn, requests_service.get_request(conn, request.state.user, request_id))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    async def request_change(request, action, request_id=None):
        conn = get_conn()
        fields = {}
        lines = []
        try:
            fields = await posted(request)
            args = {'operation_key': fields.get('operation_key')}
            if action == 'save':
                lines = []
                for i in range(requests_service.MAX_LINES):
                    item, quantity = fields.get(f'item_{i}', ''), fields.get(f'quantity_{i}', '')
                    if item or quantity:
                        lines.append({'item_id': item, 'requested_quantity': quantity})
                result = requests_service.save_draft(conn, request.state.user, {**fields, 'lines': lines},
                          request_id=request_id, expected_revision=fields.get('revision'), **args)
            elif action == 'submit':
                result = requests_service.submit(conn, request.state.user, request_id,
                          expected_revision=fields.get('revision'), **args)
            else:
                result = requests_service.withdraw(conn, request.state.user, request_id, reason=fields.get('reason'),
                          expected_revision=fields.get('revision'), **args)
            return RedirectResponse('/supplies/requests/' + str(result['id']), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if action == 'save' and not isinstance(exc, Denied):
                try:
                    draft = requests_service.get_request(conn, request.state.user, request_id) if request_id else None
                    return request_form(request, conn, draft, submitted={**fields, 'lines': lines},
                                        error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422)
                except (Denied, Invalid, Conflict) as render_exc:
                    return failure(request, render_exc)
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/requests')
    async def create_request(request: Request):
        return await request_change(request, 'save')

    @router.post('/supplies/requests/{request_id}/save')
    async def save_request(request: Request, request_id: int):
        return await request_change(request, 'save', request_id)

    @router.post('/supplies/requests/{request_id}/submit')
    async def submit_request(request: Request, request_id: int):
        return await request_change(request, 'submit', request_id)

    @router.post('/supplies/requests/{request_id}/withdraw')
    async def withdraw_request(request: Request, request_id: int):
        return await request_change(request, 'withdraw', request_id)

    @router.get('/supplies/import')
    def import_index(request: Request):
        conn = get_conn()
        try:
            return import_page(request, conn)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/import/{batch_id}')
    def import_detail(request: Request, batch_id: int):
        conn = get_conn()
        try:
            with stock._snapshot(conn):
                preview = imports.get_preview(conn, request.state.user, batch_id, page=request.query_params.get('page', '1'))
                return render(request, conn, 'import_preview', preview=preview,
                              **review.review_state(conn, request.state.user, batch_id))
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/import/{batch_id}/rows/{row_id}')
    async def import_decision(request: Request, batch_id: int, row_id: int):
        return await import_change(request, batch_id, 'decision', row_id)

    @router.post('/supplies/import/{batch_id}/finalize')
    async def import_finalize(request: Request, batch_id: int):
        return await import_change(request, batch_id, 'finalize')

    @router.post('/supplies/import/{batch_id}/apply')
    async def import_apply(request: Request, batch_id: int):
        return await import_change(request, batch_id, 'apply')

    async def import_change(request, batch_id, action, row_id=None):
        conn = get_conn()
        try:
            fields = await posted(request)
            page = supplies.integer(fields.get('page', '1'), 'Page', 1)
            args = {'expected_revision': fields.get('revision'), 'operation_key': fields.get('operation_key')}
            if action == 'decision':
                review.save_decision(conn, request.state.user, batch_id, row_id, fields, **args)
            elif action == 'finalize':
                review.finalize(conn, request.state.user, batch_id, fields, **args)
            else:
                review.apply(conn, request.state.user, batch_id, selection_sha256=fields.get('selection_sha256'), **args)
            return RedirectResponse('/supplies/import/' + str(batch_id) + '?page=' + str(page), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/import/preview')
    async def import_upload(request: Request):
        conn = get_conn()
        try:
            permissions.require_custodian(conn, request.state.user)
            supplies.require_enabled(conn)
            data, filename, key = await uploaded(request)
            def process():
                # Parsing is bounded CPU work; the worker owns its SQLite connection.
                worker_conn = get_conn()
                try:
                    return imports.preview_import(worker_conn, request.state.user, data, filename, operation_key=key)
                finally:
                    worker_conn.close()
            result = await run_in_threadpool(process)
            return RedirectResponse('/supplies/import/' + str(result['id']), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            if isinstance(exc, Denied):
                return failure(request, exc)
            try:
                return import_page(request, conn, error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422)
            except (Denied, Invalid) as denied:
                return failure(request, denied)
        finally:
            conn.close()

    return router
