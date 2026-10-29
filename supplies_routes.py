"""Authenticated Supplies catalog/settings with session-bound form tokens."""
import hashlib
import hmac
import json
import re
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response, JSONResponse, HTMLResponse

import auth
import supplies
import supplies_stock as stock
import supplies_grid as inventory_grid
import supplies_stock_dashboard as stock_dashboard
import dashboard_pdf
import supplies_import as imports
import supplies_import_review as review
import supplies_requests as requests_service
import supplies_shop as shop
from supplies_status import STEPS as request_steps
import supplies_approvals as approvals
import supplies_backorders as backorders
import supplies_issues as issues
import supplies_acknowledgments as acknowledgments
import supplies_print as print_views
import supplies_corrections as corrections
import supplies_notify as notify
import supplies_dashboard as dashboard_views
import supplies_replenishment as replenishment
import supplies_replenishment_flow as replenishment_flow
import supplies_deliveries as deliveries
import supplies_reports as reports
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
        can_configure = user['role'] == 'admin'
        can_approve = bool(conn.execute("SELECT 1 FROM supply_role_grant WHERE user_id=? AND role='request_approver' AND revoked_at IS NULL",(user['id'],)).fetchone())
        can_maintain = permissions.has_role(conn, user, 'custodian')
        can_audit = permissions.has_role(conn, user, 'auditor')
        can_replenish_approve = permissions.has_role(conn, user, 'replenishment_approver')
        return templates.TemplateResponse(request, 'supplies/' + template + '.html', {
            'nav_active': 'supplies', 'enabled': supplies.enabled(conn), 'csrf': csrf(request),
            'can_configure': can_configure, 'can_approve': can_approve,
            'can_maintain': can_maintain, 'can_audit': can_audit,
            'can_replenish_approve': can_replenish_approve,
            'can_read_stock': can_maintain or can_audit,
            'requester_only': not (can_configure or can_approve or can_maintain or can_audit or can_replenish_approve),
            'new_key': lambda: str(uuid4()), 'error': '', 'submitted': {}, 'stage': None, 'steps': request_steps, 'user_id': user['id'],
            'plural': requests_service._plural, **values,
        }, status_code=status_code)

    def failure(request, exc):
        status = 404 if isinstance(exc, Missing) else 403 if isinstance(exc, Denied) else 409 if isinstance(exc, Conflict) else 422
        return templates.TemplateResponse(request, 'supplies/error.html', {
            'nav_active': 'supplies', 'enabled': False, 'can_configure': False,
            'can_maintain': False, 'error': str(exc), 'status': status,
        }, status_code=status)

    def report_result(request, conn, kind):
        return reports.report(conn, request.state.user, kind,
                              as_of=request.query_params.get('as_of'),
                              item_id=request.query_params.get('item_id'))

    @router.get('/supplies/reports/{kind}')
    def supply_report(request: Request, kind: str):
        conn = get_conn()
        try:
            return render(request, conn, 'report', report=report_result(request, conn, kind))
        except (Denied, Invalid, Conflict, Missing) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/reports/{kind}/print')
    def supply_report_print(request: Request, kind: str):
        conn = get_conn()
        try:
            return render(request, conn, 'report_print', report=report_result(request, conn, kind))
        except (Denied, Invalid, Conflict, Missing) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/reports/{kind}/xlsx')
    def supply_report_xlsx(request: Request, kind: str):
        conn = get_conn()
        try:
            result = report_result(request, conn, kind)
            filename = 'supplies-' + kind + '.xlsx'
            return Response(reports.xlsx_bytes(result),
                            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            headers={'Content-Disposition': f'attachment; filename="{filename}"',
                                     'Cache-Control': 'no-store'})
        except (Denied, Invalid, Conflict, Missing) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    def catalog_page(request, conn, *, error='', status_code=200, submitted=None):
        params = request.query_params
        linked_view=params.get('interactive')=='1'
        linked={}
        if linked_view:
            linked={field:params.get(field,'active' if field=='active' else '') for field in inventory_grid.FILTERS}
            data=inventory_grid.page(conn,request.state.user,{**linked,'page':params.get('page','1')})
            result={'items':data['data'],'count':data['last_row'],'page':data['page'],
                    'has_next':data['page']<data['last_page'],'last_page':data['last_page'],
                    'query':linked['q'],'include_inactive':linked['active']!='active'}
        else:
            result = supplies.catalog(conn, request.state.user, query=params.get('q', ''),
                                      include_inactive=params.get('inactive') == '1', page=params.get('page', '1'))
        def page_url(page):
            if linked_view:return '/supplies/items?'+urlencode({**linked,'interactive':'1','page':page})
            return '/supplies/items?' + urlencode({'q': result['query'],
                      'inactive': '1' if result['include_inactive'] else '0', 'page': page})
        return render(request, conn, 'catalog', status_code=status_code, error=error,
                      linked_view=linked_view,inventory_display=inventory_grid.display,
                      linked_export='/supplies/inventory-export.csv?'+urlencode(linked),
                      stock_dashboard_url='/supplies/stock-dashboard?'+urlencode({'q':result['query'],'active':'all' if result['include_inactive'] else 'active'}),
                      submitted=submitted or {}, page_url=page_url, inventory_units=inventory_grid.units(conn, request.state.user),
                      inventory_columns=inventory_grid.COLUMNS, physical_states=inventory_grid.PHYSICAL,
                      availability_states=inventory_grid.AVAILABLE, stock_labels=notify.LABELS, **result)

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
                      availability=availability(conn, item_id), warning=notify.status(conn, request.state.user, item_id),
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

    def replenishment_fields(fields):
        lines = []
        for i in range(20):
            item_id = fields.get(f'item_id_{i}', '')
            if not item_id:
                continue
            lines.append({'item_id': item_id, 'requested_quantity': fields.get(f'quantity_{i}', ''),
                          'intended_target': fields.get(f'target_{i}', ''),
                          'estimated_unit_cost': fields.get(f'cost_{i}', ''),
                          'override_reason': fields.get(f'reason_{i}', '')})
        return {**fields, 'lines': lines}

    def replenishment_form(request, conn, *, draft=None, error='', status_code=200, submitted=None):
        permissions.require_custodian(conn, request.state.user)
        suggestions = replenishment.suggest_replenishment(conn, request.state.user)
        chosen = request.query_params.get('item', '')
        if chosen:
            chosen = supplies.integer(chosen, 'Item', 1)
        selected_suggestion = next((item for item in suggestions if item['id'] == chosen), None)
        more_open = bool(draft and len(draft['lines']) > 5) or bool(submitted and any(
            submitted.get(f'item_id_{i}') for i in range(5,20)))
        return render(request, conn, 'replenishment_form', draft=draft, suggestions=suggestions,
                      chosen=chosen, selected_suggestion=selected_suggestion, more_open=more_open,
                      lines=draft['lines'] if draft else [], error=error,
                      status_code=status_code, submitted=submitted or {})

    def settings_page(request, conn, *, error='', status_code=200, submitted=None):
        values = supplies.configuration(conn, request.state.user, page=request.query_params.get('page', '1'))
        return render(request, conn, 'settings', error=error, status_code=status_code,
                      submitted=submitted or {}, **values)

    async def posted(request, max_fields=180):
        form = await request.form(max_files=0, max_fields=max_fields, max_part_size=16384)
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
        conn = get_conn()
        try:
            return render(request, conn, 'dashboard', **dashboard_views.dashboard(conn, request.state.user))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/replenishments')
    def replenishments(request: Request):
        conn = get_conn()
        try:
            records = replenishment.list_replenishments(conn, request.state.user)
            can_stock = permissions.has_role(conn,request.state.user,'custodian') or permissions.has_role(conn,request.state.user,'auditor')
            suggestions = replenishment.suggest_replenishment(conn, request.state.user) if can_stock else []
            return render(request, conn, 'replenishments', records=records, suggestions=suggestions)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/replenishments/new')
    def new_replenishment(request: Request):
        conn = get_conn()
        try:
            return replenishment_form(request,conn)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request,exc)
        finally:
            conn.close()

    @router.post('/supplies/replenishments')
    async def create_replenishment(request: Request):
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request)
            result = replenishment.save_replenishment(conn,request.state.user,replenishment_fields(fields),operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/replenishments/'+str(result['id']),status_code=303)
        except (Denied,Invalid,Conflict) as exc:
            if isinstance(exc,Denied):return failure(request,exc)
            return replenishment_form(request,conn,error=str(exc),status_code=409 if isinstance(exc,Conflict) else 422,submitted=fields)
        finally:
            conn.close()

    @router.get('/supplies/replenishments/{replenishment_id}')
    def replenishment_detail(request: Request, replenishment_id: int):
        conn=get_conn()
        try:
            draft=replenishment_flow.review_inputs(conn,request.state.user,replenishment_id)
            custodians=rows(conn,'''SELECT DISTINCT u.id,u.username FROM admin_user u
              JOIN supply_role_grant g ON g.user_id=u.id
              WHERE u.active=1 AND g.role='custodian' AND g.revoked_at IS NULL ORDER BY u.username''')
            return render(request,conn,'replenishment',draft=draft,custodians=custodians)
        except (Denied,Invalid,Conflict) as exc:
            return failure(request,exc)
        finally:
            conn.close()

    async def replenishment_action(request, replenishment_id, action):
        conn=get_conn();fields={}
        try:
            fields=await posted(request)
            revision=fields.get('revision');key=fields.get('operation_key')
            if action=='submit':
                result=replenishment_flow.submit_replenishment(conn,request.state.user,replenishment_id,
                    expected_revision=revision,operation_key=key,review_reason=fields.get('review_reason',''))
            elif action=='decide':
                decision_lines=[{'revision_line_id':name[len('approved_'):],
                                 'approved_quantity':value,'reason':fields.get('line_reason_'+name[len('approved_'):],'')}
                                for name,value in fields.items() if name.startswith('approved_')]
                result=replenishment_flow.decide_replenishment(conn,request.state.user,replenishment_id,
                    {'decision':fields.get('decision'),'reason':fields.get('reason',''),'lines':decision_lines},
                    expected_revision=revision,submitted_revision=fields.get('submitted_revision'),operation_key=key)
            elif action=='order':
                order_lines=[{'line_id':name[len('ordered_'):],'ordered_quantity':value}
                             for name,value in fields.items() if name.startswith('ordered_')]
                result=replenishment_flow.record_order(conn,request.state.user,replenishment_id,
                    {**fields,'lines':order_lines},expected_revision=revision,operation_key=key)
            else:
                cancel_lines=[{'line_id':name[len('cancel_'):],'cancelled_quantity':value}
                              for name,value in fields.items() if name.startswith('cancel_') and value]
                result=replenishment_flow.cancel_replenishment_remainder(conn,request.state.user,replenishment_id,
                    {'reason':fields.get('reason',''),'lines':cancel_lines},expected_revision=revision,operation_key=key)
            return RedirectResponse('/supplies/replenishments/'+str(result['id']),status_code=303)
        except (Denied,Invalid,Conflict) as exc:
            if isinstance(exc,Denied):return failure(request,exc)
            try:
                draft=replenishment_flow.review_inputs(conn,request.state.user,replenishment_id)
                custodians=rows(conn,'''SELECT DISTINCT u.id,u.username FROM admin_user u
                  JOIN supply_role_grant g ON g.user_id=u.id
                  WHERE u.active=1 AND g.role='custodian' AND g.revoked_at IS NULL ORDER BY u.username''')
                return render(request,conn,'replenishment',draft=draft,custodians=custodians,error=str(exc),
                              status_code=409 if isinstance(exc,Conflict) else 422,submitted=fields)
            except (Denied,Invalid,Conflict) as read_exc:return failure(request,read_exc)
        finally:
            conn.close()

    @router.post('/supplies/replenishments/{replenishment_id}/submit')
    async def submit_replenishment(request: Request, replenishment_id: int):
        return await replenishment_action(request,replenishment_id,'submit')

    @router.post('/supplies/replenishments/{replenishment_id}/decide')
    async def decide_replenishment(request: Request, replenishment_id: int):
        return await replenishment_action(request,replenishment_id,'decide')

    @router.post('/supplies/replenishments/{replenishment_id}/order')
    async def order_replenishment(request: Request, replenishment_id: int):
        return await replenishment_action(request,replenishment_id,'order')

    @router.post('/supplies/replenishments/{replenishment_id}/cancel-remainder')
    async def cancel_replenishment(request: Request, replenishment_id: int):
        return await replenishment_action(request,replenishment_id,'cancel')

    @router.get('/supplies/replenishments/{replenishment_id}/edit')
    def edit_replenishment(request: Request, replenishment_id: int):
        conn=get_conn()
        try:
            draft=replenishment.get_replenishment(conn,request.state.user,replenishment_id)
            if draft['prepared_by']!=request.state.user['id'] or draft['status'] not in ('draft','returned'):
                raise Denied('Only the preparer can edit this draft.')
            return replenishment_form(request,conn,draft=draft)
        except (Denied,Invalid,Conflict) as exc:
            return failure(request,exc)
        finally:
            conn.close()

    def delivery_form(request, conn, replenishment_id, *, error='', status_code=200, submitted=None):
        permissions.require_custodian(conn, request.state.user)
        draft = replenishment_flow.review_inputs(conn, request.state.user, replenishment_id)
        if draft['status'] not in ('approved','ordered','partially_received'):
            raise Conflict('This replenishment has no open approved delivery.')
        for line in draft['lines']:
            line['item_revision'] = supplies._item(conn,line['item_id'])['revision']
        return render(request,conn,'delivery_form',draft=draft,today=tz.today_local().isoformat(),
                      submitted=submitted or {},error=error,status_code=status_code)

    @router.get('/supplies/replenishments/{replenishment_id}/deliveries/new')
    def new_delivery(request: Request, replenishment_id: int):
        conn=get_conn()
        try:return delivery_form(request,conn,replenishment_id)
        except (Denied,Invalid,Conflict) as exc:return failure(request,exc)
        finally:conn.close()

    @router.post('/supplies/replenishments/{replenishment_id}/deliveries')
    async def receive_delivery(request: Request, replenishment_id: int):
        conn=get_conn();fields={}
        try:
            fields=await posted(request)
            lines=[]
            for name,value in fields.items():
                if not name.startswith('delivered_') or not value:
                    continue
                line_id=name[len('delivered_'):]
                lines.append({'replenishment_line_id':line_id,'delivered_quantity':value,
                              'accepted_quantity':fields.get('accepted_'+line_id,''),
                              'rejected_quantity':fields.get('rejected_'+line_id,''),
                              'rejection_reason':fields.get('rejection_reason_'+line_id,''),
                              'expected_item_revision':fields.get('item_revision_'+line_id,''),
                              'unit_cost':fields.get('unit_cost_'+line_id,''),
                              'expiry_date':fields.get('expiry_date_'+line_id,'')})
            result=deliveries.receive_delivery(conn,request.state.user,replenishment_id,
                {**fields,'lines':lines},expected_revision=fields.get('revision'),
                operation_key=fields.get('operation_key'))
            return RedirectResponse(f"/supplies/replenishments/{replenishment_id}/deliveries/{result['id']}",status_code=303)
        except (Denied,Invalid,Conflict) as exc:
            if isinstance(exc,Denied):return failure(request,exc)
            try:return delivery_form(request,conn,replenishment_id,error=str(exc),
                                     status_code=409 if isinstance(exc,Conflict) else 422,submitted=fields)
            except (Denied,Invalid,Conflict) as read_exc:return failure(request,read_exc)
        finally:conn.close()

    @router.get('/supplies/replenishments/{replenishment_id}/deliveries/{delivery_id}')
    def delivery_detail(request: Request, replenishment_id: int, delivery_id: int):
        conn=get_conn()
        try:return render(request,conn,'delivery',delivery=deliveries.get_delivery(conn,request.state.user,
                                                                                   replenishment_id,delivery_id))
        except (Denied,Invalid,Conflict) as exc:return failure(request,exc)
        finally:conn.close()

    @router.post('/supplies/replenishments/{replenishment_id}/save')
    async def update_replenishment(request: Request, replenishment_id: int):
        conn=get_conn(); fields={}
        try:
            fields=await posted(request)
            result=replenishment.save_replenishment(conn,request.state.user,replenishment_fields(fields),
                       replenishment_id=replenishment_id,expected_revision=fields.get('revision'),operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/replenishments/'+str(result['id']),status_code=303)
        except (Denied,Invalid,Conflict) as exc:
            if isinstance(exc,Denied):return failure(request,exc)
            try:
                draft=replenishment.get_replenishment(conn,request.state.user,replenishment_id)
                return replenishment_form(request,conn,draft=draft,error=str(exc),status_code=409 if isinstance(exc,Conflict) else 422,submitted=fields)
            except (Denied,Invalid,Conflict) as read_exc:return failure(request,read_exc)
        finally:
            conn.close()

    @router.get('/supplies/items')
    def catalog(request: Request):
        conn = get_conn()
        try:
            response=catalog_page(request, conn)
            if request.query_params.get('interactive')=='1':response.headers.update({'Cache-Control':'no-store','Pragma':'no-cache'})
            return response
        except (Denied, Invalid) as exc:
            response=failure(request, exc)
            if request.query_params.get('interactive')=='1':response.headers['Cache-Control']='no-store'
            return response
        finally:
            conn.close()

    inventory_headers = {'Cache-Control':'no-store', 'Pragma':'no-cache'}

    def inventory_error(exc):
        code = 403 if isinstance(exc, Denied) else 409 if isinstance(exc, Conflict) else 400
        return JSONResponse({'error':str(exc)}, status_code=code, headers=inventory_headers)

    @router.get('/supplies/stock-dashboard')
    def supply_stock_dashboard(request: Request):
        conn=get_conn()
        try:
            result=stock_dashboard.report(conn,request.state.user,request.query_params)
            response=render(request,conn,'stock_dashboard',dashboard=result,stock_labels=notify.LABELS,
                            inventory_units=inventory_grid.units(conn,request.state.user))
            response.headers.update(inventory_headers)
            return response
        except (Denied,Invalid,Conflict) as exc:
            response=failure(request,exc);response.headers.update(inventory_headers);return response
        finally:
            conn.close()

    @router.get('/supplies/stock-dashboard/export.pdf')
    def supply_stock_pdf(request:Request):
        conn=get_conn()
        try:
            data=stock_dashboard.report(conn,request.state.user,request.query_params,presentation=True)
            return Response(dashboard_pdf.supplies(data),media_type='application/pdf',headers={**inventory_headers,
                'Content-Disposition':'attachment; filename="office-connect-supplies-stock-report.pdf"'})
        except (Denied,Invalid,Conflict) as exc:
            back='/supplies/stock-dashboard?'+urlencode({key:request.query_params.get(key,'active' if key=='active' else '') for key in ('q','unit','active')})
            return HTMLResponse(dashboard_pdf.error_html(exc,back),status_code=403 if isinstance(exc,Denied) else 400,
                                headers=inventory_headers)
        finally:
            conn.close()

    @router.get('/supplies/stock-dashboard/presentation-data')
    def supply_stock_presentation(request: Request):
        conn=get_conn()
        try:
            return JSONResponse(stock_dashboard.report(conn,request.state.user,request.query_params,
                                                       presentation=True),headers=inventory_headers)
        except (Denied,Invalid,Conflict) as exc:
            return inventory_error(exc)
        finally:
            conn.close()

    @router.get('/supplies/inventory-data')
    def inventory_data(request: Request):
        conn = get_conn()
        try:
            return JSONResponse(inventory_grid.page(conn, request.state.user, request.query_params), headers=inventory_headers)
        except (Denied, Invalid, Conflict) as exc:
            return inventory_error(exc)
        finally:
            conn.close()

    @router.get('/supplies/inventory-export.csv')
    def inventory_export(request: Request):
        conn = get_conn()
        try:
            content, count = inventory_grid.export_csv(conn, request.state.user, request.query_params)
            return Response(content, media_type='text/csv', headers={**inventory_headers,
                'Content-Disposition':'attachment; filename="supply-inventory.csv"', 'X-Export-Rows':str(count)})
        except (Denied, Invalid, Conflict) as exc:
            return inventory_error(exc)
        finally:
            conn.close()

    @router.get('/supplies/inventory-views')
    def inventory_views(request: Request):
        conn = get_conn()
        try:
            return JSONResponse({'views':inventory_grid.views(conn, request.state.user)}, headers=inventory_headers)
        except (Denied, Invalid, Conflict) as exc:
            return inventory_error(exc)
        finally:
            conn.close()

    @router.post('/supplies/inventory-views')
    async def inventory_save_view(request: Request):
        conn = get_conn()
        try:
            if (not request.cookies.get(auth.COOKIE_NAME) or not hmac.compare_digest(
                    request.headers.get('X-CSRF-Token', '').encode('utf-8'), csrf(request).encode('ascii'))):
                raise Denied('The form expired. Reload the page and try again.')
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 32768:
                    raise Invalid('The inventory view request is too large.')
                body.extend(chunk)
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError, RecursionError):
                raise Invalid('Send a valid inventory view request.') from None
            return JSONResponse(inventory_grid.save_view(conn, request.state.user, data), headers=inventory_headers)
        except (Denied, Invalid, Conflict) as exc:
            return inventory_error(exc)
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

    def request_form(request, conn, draft=None, *, submitted=None, error='', status_code=200, view='', query=''):
        user, identity = requests_service.requester(conn, request.state.user)
        if draft is not None and draft['requester_id'] != user['id']:
            raise Missing('Supply request not found or unavailable to you.')
        if draft is not None and draft['approval_status'] not in ('draft','returned'):
            raise Conflict('Only draft or returned requests can be edited.')
        if draft is None and view != 'list':                      # Supplies 2.1: a new request starts from the picture grid
            values = submitted or {}
            editing = int(values['request_id']) if str(values.get('request_id', '')).isdigit() else None
            return render(request, conn, 'request_grid', identity=identity, query=query, request_id=editing,
                          cards=shop.shop_items(conn, query, editing), form_values=values,
                          quantities={k[4:]: v for k, v in values.items() if k.startswith('qty_')},
                          error=error, status_code=status_code)
        items = rows(conn, 'SELECT id,code,description,unit FROM supply_item WHERE active=1 ORDER BY code')
        chosen = [ln.get('item_id') for ln in ((submitted or draft or {}).get('lines') or [])]
        items = [{**i, 'search': shop.search_text(i['description'], i['code'])} for i in shop.narrow(items, query, chosen)] \
            if query else [{**i, 'search': shop.search_text(i['description'], i['code'])} for i in items]
        return render(request, conn, 'request_form', draft=draft, identity=identity, items=items, query=query,
                      max_lines=requests_service.MAX_LINES, form_values=submitted if submitted is not None else draft,
                      error=error, status_code=status_code)

    @router.get('/supplies/issuance')
    def issuance_queue(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'issuance', **issues.issuance_queue(conn, request.state.user,
                          page=request.query_params.get('page', '1'), query=request.query_params.get('q', ''),
                          state=request.query_params.get('status', '')))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/issues')
    def releases(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'issues', **issues.list_issues(conn, request.state.user,
                          page=request.query_params.get('page', '1'), query=request.query_params.get('q', ''),
                          state=request.query_params.get('status', ''), mine=request.query_params.get('mine')=='1'))
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
            back = fields.get('back', '')                              # Supplies 3.3: the request page can ask to come back to it
            return RedirectResponse(back if re.fullmatch(r'/supplies/requests/\d+', back) else '/supplies/issues/' + str(issue_id),
                                    status_code=303)
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
                          page=request.query_params.get('page', '1'), query=request.query_params.get('q', ''),
                          state=request.query_params.get('status', '')))
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
                          page=request.query_params.get('page', '1'), query=request.query_params.get('q', ''),
                          state=request.query_params.get('status', '')))
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
            params = request.query_params
            page, query = params.get('page', '1'), params.get('q', '')
            status = params.get('status')
            tab = 'active' if status is None else ('' if status == 'all' else status)     # Supplies 3.1: Active, Completed, All
            data = requests_service.my_requests(conn, request.state.user, page=page, query=query, state=tab)
            needs = []
            if tab in ('active', 'completed', '') and not query and page in ('1', ''):
                needs = requests_service.my_requests(conn, request.state.user, state='needs_action')['requests']
            needs_ids = {e['id'] for e in needs}
            entries = [e for e in data['requests'] if e['id'] not in needs_ids]
            return render(request, conn, 'requests', **{**data, 'requests': entries, 'total': data['total'] - (len(data['requests']) - len(entries))},
                          needs=needs, tab=tab,
                          pictures=shop.items_for(conn, needs + entries), steps=request_steps)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/new')
    def new_request(request: Request):
        conn = get_conn()
        try:
            return request_form(request, conn, view=request.query_params.get('view', ''),
                                query=request.query_params.get('q', '')[:100])
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    def cart_page(request, conn, fields, *, error='', status_code=200, notes=(), reason=''):
        """Supplies 2.2: what the requester picked, with pictures and editable numbers, before it is sent."""
        user, identity = requests_service.requester(conn, request.state.user)
        asked = {l['item_id']: l['requested_quantity'] for l in shop.quantities_from(fields)}
        request_id = int(fields['request_id']) if str(fields.get('request_id', '')).isdigit() else None
        cards = [{**c, 'qty': asked[str(c['id'])]} for c in shop.shop_items(conn, '', request_id) if str(c['id']) in asked]
        if not cards:
            return request_form(request, conn, submitted=fields, view='grid', status_code=422,
                                error='Choose at least one item first.')
        return render(request, conn, 'request_cart', identity=identity, cards=cards, request_id=request_id,
                      form_values=fields, error=error, status_code=status_code, notes=notes, reason=reason)

    def cart_from_request(request, conn, entry):
        """Supplies 2.3: a saved draft or a returned request opens in the cart; what was returned is shown on top."""
        user, _ = requests_service.requester(conn, request.state.user)
        if entry['requester_id'] != user['id']:
            raise Missing('Supply request not found or unavailable to you.')
        if entry['approval_status'] not in ('draft', 'returned'):
            raise Conflict('Only draft or returned requests can be edited.')
        fields = {'purpose': entry['purpose'], 'date_needed': entry['date_needed'] or '',
                  'request_id': str(entry['id']), 'revision': str(entry['revision'])}
        notes = []
        for line in entry['lines']:
            if line.get('active', 1):
                fields[f"qty_{line['item_id']}"] = str(line['requested_quantity'])
            else:
                notes.append(f"{line['description_snapshot']} is no longer in the catalog, so it was left out.")
        reason = next((e['reason'] for e in reversed(entry['events']) if e['decision'] == 'returned' and e['reason']), '')
        if entry['approval_status'] == 'returned' and not reason:
            reason = 'Your approver asked for a correction.'
        return cart_page(request, conn, fields, notes=notes, reason=reason if entry['approval_status'] == 'returned' else '')

    @router.get('/supplies/requests/{request_id}/again')
    def request_again(request: Request, request_id: int):
        """Supplies 2.3: a past request's items in a new cart, held to what can be requested now. Nothing is saved until sent."""
        conn = get_conn()
        try:
            user, _ = requests_service.requester(conn, request.state.user)
            entry = requests_service.get_request(conn, request.state.user, request_id)
            if entry['requester_id'] != user['id']:
                raise Missing('Supply request not found or unavailable to you.')
            cards = {str(c['id']): c for c in shop.shop_items(conn)}
            fields, notes = {'purpose': entry['purpose'] or ''}, []
            for line in entry['lines']:
                card, asked = cards.get(str(line['item_id'])), int(line['requested_quantity'])
                name = line.get('description_snapshot') or line['item_id']
                if not card:
                    notes.append(f'{name} is no longer in the catalog, so it was left out.')
                elif card['max'] <= 0:
                    notes.append(f'{name} is out of stock right now, so it was left out.')
                elif asked > card['max']:
                    fields[f"qty_{line['item_id']}"] = str(card['max'])
                    notes.append(f"Only {card['max']} {card['unit']} of {name} can be requested now, so that is what is in your cart.")
                else:
                    fields[f"qty_{line['item_id']}"] = str(asked)
            if not shop.quantities_from(fields):
                return request_form(request, conn, submitted=fields, view='grid', status_code=200,
                                    error='None of the items in that request can be requested right now. ' + ' '.join(notes))
            return cart_page(request, conn, fields, notes=notes)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/requests/review')
    async def review_request(request: Request):
        conn = get_conn()
        try:
            fields = await posted(request, max_fields=500)
            if fields.get('step') == 'grid':
                return request_form(request, conn, submitted=fields, view='grid')
            return cart_page(request, conn, fields)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/requests/send')
    async def send_request(request: Request):
        """Save the cart as a draft and, for Send, submit it in the same step. A failed submit keeps the saved draft."""
        conn = get_conn()
        fields = {}
        try:
            fields = await posted(request, max_fields=500)
            request_id = int(fields['request_id']) if str(fields.get('request_id', '')).isdigit() else None
            try:
                saved = requests_service.save_draft(
                    conn, request.state.user, {**fields, 'lines': shop.quantities_from(fields)}, request_id=request_id,
                    expected_revision=fields.get('revision') if request_id else None, operation_key=fields.get('operation_key'))
                if fields.get('act') != 'send':
                    return RedirectResponse('/supplies/requests/' + str(saved['id']), status_code=303)
                try:
                    sent = requests_service.submit(conn, request.state.user, saved['id'], expected_revision=saved['revision'],
                                                   operation_key=fields.get('submit_operation_key'))
                except (Invalid, Conflict) as exc:
                    return cart_page(request, conn, {**fields, 'request_id': saved['id'], 'revision': saved['revision']},
                                     error=f'Your request is saved as a draft but was not sent: {exc}',
                                     status_code=409 if isinstance(exc, Conflict) else 422)
                return RedirectResponse('/supplies/requests/' + str(sent['id']), status_code=303)
            except (Invalid, Conflict) as exc:
                return cart_page(request, conn, fields, error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/{request_id}')
    def request_detail(request: Request, request_id: int):
        conn = get_conn()
        try:
            result = requests_service.get_request(conn, request.state.user, request_id)
            stage = dashboard_views.request_stage(conn, request.state.user, request_id) if result['is_owner'] else None
            return render(request, conn, 'request', supply_request=result, stage=stage)
        except (Denied, Invalid) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/requests/{request_id}/edit')
    def edit_request(request: Request, request_id: int):
        conn = get_conn()
        try:
            entry = requests_service.get_request(conn, request.state.user, request_id)
            if request.query_params.get('view') == 'list':
                return request_form(request, conn, entry)
            return cart_from_request(request, conn, entry)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    async def request_change(request, action, request_id=None):
        conn = get_conn()
        fields = {}
        lines = []
        try:
            fields = await posted(request, max_fields=500 if action == 'save' else 180)
            args = {'operation_key': fields.get('operation_key')}
            if action == 'save':
                lines = []
                for i in range(requests_service.MAX_LINES):
                    item, quantity = fields.get(f'item_{i}', ''), fields.get(f'quantity_{i}', '')
                    if item or quantity:
                        lines.append({'item_id': item, 'requested_quantity': quantity})
                lines += shop.quantities_from(fields)                  # the picture grid (Supplies 2.1)
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
                                        error=str(exc), status_code=409 if isinstance(exc, Conflict) else 422,
                                        view='grid' if fields.get('view') == 'grid' else 'list')
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

    def correction_page(request, conn, kind, parent_id, *, submitted=None, impact=None, error='', status_code=200):
        context = corrections.form_context(conn, request.state.user, kind, parent_id)
        entity = 'items' if kind == 'stocktake' else 'receipts' if kind == 'receipt_reversal' else 'issues'
        action = 'stocktake' if kind == 'stocktake' else 'returns' if kind == 'return' else 'reverse'
        return render(request, conn, 'correction_form', **context, impact=impact, submitted=submitted or {},
                      action_url=f'/supplies/{entity}/{parent_id}/{action}', back_url=f'/supplies/{entity}/{parent_id}',
                      error=error, status_code=status_code)

    def correction_endpoints(kind):
        def form(request: Request, parent_id: int):
            conn = get_conn()
            try:
                return correction_page(request, conn, kind, parent_id)
            except (Denied, Invalid, Conflict) as exc:
                return failure(request, exc)
            finally:
                conn.close()

        async def change(request: Request, parent_id: int):
            conn, fields = get_conn(), {}
            try:
                fields = await posted(request)
                if request.url.path.endswith('/preview'):
                    impact = corrections.preview(conn, request.state.user, kind, parent_id, fields)
                    return correction_page(request, conn, kind, parent_id, submitted=fields, impact=impact)
                callback = {'return': corrections.post_return, 'stocktake': corrections.post_stocktake,
                            'issue_reversal': corrections.reverse_issue, 'receipt_reversal': corrections.reverse_receipt}[kind]
                result = callback(conn, request.state.user, parent_id, fields, operation_key=fields.get('operation_key'))
                return RedirectResponse('/supplies/corrections/' + str(result['id']), status_code=303)
            except (Denied, Invalid, Conflict) as exc:
                if isinstance(exc, Denied):
                    return failure(request, exc)
                try:
                    return correction_page(request, conn, kind, parent_id, submitted=fields, error=str(exc),
                                           status_code=409 if isinstance(exc, Conflict) else 422)
                except (Denied, Invalid, Conflict) as render_exc:
                    return failure(request, render_exc)
            finally:
                conn.close()
        return form, change

    for path, kind in (
        ('/supplies/issues/{parent_id}/returns', 'return'),
        ('/supplies/items/{parent_id}/stocktake', 'stocktake'),
        ('/supplies/issues/{parent_id}/reverse', 'issue_reversal'),
        ('/supplies/receipts/{parent_id}/reverse', 'receipt_reversal'),
    ):
        form, change = correction_endpoints(kind)
        router.add_api_route(path, form, methods=['GET'], name=kind + '_form')
        router.add_api_route(path + '/preview', change, methods=['POST'], name=kind + '_preview')
        router.add_api_route(path, change, methods=['POST'], name=kind + '_post')

    @router.get('/supplies/corrections/{correction_id}')
    def correction_detail(request: Request, correction_id: int):
        conn = get_conn()
        try:
            return render(request, conn, 'correction_history',
                          **corrections.get_correction(conn, request.state.user, correction_id))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/{entity}/{entity_id}/corrections')
    def correction_history(request: Request, entity: str, entity_id: int):
        conn = get_conn()
        try:
            context = corrections.history(conn, request.state.user, entity, entity_id,
                                          page=request.query_params.get('page', '1'))
            return render(request, conn, 'correction_history', **context)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/warnings')
    def warning_list(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'warnings', **notify.list_warnings(conn, request.state.user,
                          page=request.query_params.get('page', '1'), query=request.query_params.get('q', ''),
                          state=request.query_params.get('status', '')))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/warnings/reconcile')
    async def reconcile_warnings(request: Request):
        conn = get_conn()
        try:
            fields = await posted(request)
            notify.reconcile_alerts(conn, request.state.user, operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/warnings', status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/notices')
    def notice_list(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'notices', **notify.list_notices(conn, request.state.user,
                          page=request.query_params.get('page', '1'), unread=request.query_params.get('unread')=='1'))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/notices/{notice_id}')
    def notice_detail(request: Request, notice_id: int):
        conn = get_conn()
        try:
            notice = notify.get_notice(conn, request.state.user, notice_id)
            return render(request, conn, 'notice', notice=notice,
                          current_warning=notify.status(conn, request.state.user, notice['item_id']))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.post('/supplies/notices/{notice_id}/read')
    async def notice_read(request: Request, notice_id: int):
        conn = get_conn()
        try:
            fields = await posted(request)
            notify.mark_read(conn, request.state.user, notice_id, operation_key=fields.get('operation_key'))
            return RedirectResponse('/supplies/notices/' + str(notice_id), status_code=303)
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    @router.get('/supplies/activity')
    def stock_activity(request: Request):
        conn = get_conn()
        try:
            return render(request, conn, 'activity', **dashboard_views.queue(conn, request.state.user, 'activity',
                          page=request.query_params.get('page','1'),query=request.query_params.get('q',''),
                          state=request.query_params.get('status','')))
        except (Denied, Invalid, Conflict) as exc:
            return failure(request, exc)
        finally:
            conn.close()

    return router
