"""Browser consent, credential management and explicit MCP action confirmation."""
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import integration_access as access
import mcp_auth
import mcp_actions
import mcp_supply_drafts
import mcp_comment_drafts
import mcp_activity_announcements
import mcp_activity_creation
import mcp_activity_drafts
import mcp_activity_dates
import mcp_work_arrangements
import mcp_meal_requests
import mcp_room_approvals
import mcp_room_requests
import mcp_travel_submissions
import mcp_travel_reviews
import mcp_supply_approvals
import mcp_supply_submissions
import mcp_task_acceptances
import mcp_task_submissions
import mcp_task_acknowledgements
import mcp_travel_drafts
import mcp_personal_calendar
import mcp_report_views
import report_views
import work_comment_drafts
import documents
import supplies_storage
import documents_permissions as permissions
from request_security import same_origin_write
import ratelimit as rl
import storage as st
import tzutil as tz


def csrf(request):
    return hmac.new(auth._secret(), ('integration-access:' + request.cookies.get(auth.COOKIE_NAME,'')).encode(),
                    hashlib.sha256).hexdigest()


# Explicit allowlist: never expose the hosting environment or credential material.
MCP_PILOTS = (
    ('Approve plain room request and hold hours (browser review)', 'ROOM_APPROVALS', 'rooms:request:approve', ('get_room_approval_context', 'prepare_room_request_approval', 'get_room_approval_operation')),
    ('Approve full supply quantities and initial reservations (browser review)', 'SUPPLY_APPROVALS', 'supplies:request:approve', ('get_supply_approval_context', 'prepare_supply_request_approval', 'get_supply_approval_operation')),
    ('Accept submitted task as confirmed lead (exact browser review)', 'TASK_ACCEPTANCES', 'work:task:accept', ('get_task_acceptance_context', 'prepare_task_acceptance', 'get_task_acceptance_operation')),
    ('Publish first activity pinned update (browser confirmation; no email)', 'ACTIVITY_ANNOUNCEMENTS', 'activities:announcement:publish', ('get_activity_announcement_context', 'prepare_activity_announcement', 'get_activity_announcement_operation')),
    ('Create live activity from own private draft (browser confirmation)', 'ACTIVITY_CREATION', 'activities:draft:create', ('get_activity_creation_context', 'prepare_activity_from_draft', 'get_activity_creation_operation')),
    ('Save own private activity drafts (browser confirmation)', 'ACTIVITY_DRAFTS', 'activities:draft:save', ('get_activity_draft_context', 'prepare_activity_draft', 'get_activity_draft_operation')),
    ('Update upcoming unused activity dates (browser confirmation)', 'ACTIVITY_DATES', 'activities:dates:update', ('get_activity_date_context', 'prepare_activity_date_update', 'get_activity_date_operation')),
    ('File own work arrangement for approval (browser confirmation)', 'WORK_ARRANGEMENTS', 'work_arrangements:request', ('get_my_work_arrangement_context', 'prepare_work_arrangement_request', 'get_work_arrangement_operation')),
    ('Submit own standalone meal requests (browser confirmation)', 'MEAL_REQUESTS', 'meals:request', ('get_my_meal_request_context', 'prepare_meal_request', 'get_meal_request_operation')),
    ('Request a room for own meeting (browser confirmation)', 'ROOM_REQUESTS', 'rooms:request', ('get_my_room_request_context', 'prepare_room_request', 'get_room_request_operation')),
    ('Record own travel paper handover (browser confirmation)', 'TRAVEL_SUBMISSIONS', 'travel:filing:submit', ('get_my_travel_submission_context', 'prepare_travel_filing_submission', 'get_travel_submission_operation')),
    ('Request review of own travel papers (browser confirmation)', 'TRAVEL_REVIEW_REQUESTS', 'travel:review:request', ('get_my_travel_review_context', 'prepare_travel_review_request', 'get_travel_review_request_operation')),
    ('Submit own supply requests (browser confirmation)', 'SUPPLY_SUBMISSIONS', 'supplies:request:submit', ('prepare_supply_request_submission', 'get_supply_submission_operation')),
    ('Submit own assigned tasks for review (browser confirmation)', 'TASK_SUBMISSIONS', 'work:task:submit', ('prepare_task_submission', 'get_task_submission_operation')),
    ('Acknowledge own assigned tasks (browser confirmation)', 'TASK_ACKNOWLEDGEMENTS', 'work:task:acknowledge', ('prepare_task_acknowledgement', 'get_task_acknowledgement_operation')),
    ('Travel reimbursement drafts (browser confirmation)', 'TRAVEL_DRAFTS', 'travel:filing:draft', ('prepare_travel_reimbursement_draft', 'get_travel_draft_operation')),
    ('Personal calendar entries (browser confirmation)', 'PERSONAL_CALENDAR', 'calendar:entry:create', ('prepare_personal_calendar_entry', 'get_personal_calendar_operation')),
    ('Personal saved report views (browser confirmation)', 'REPORT_VIEWS', 'reports:view:save', ('prepare_saved_report_view', 'get_saved_report_view_operation')),
    ('Private task comment drafts (browser confirmation)', 'COMMENT_DRAFTS', 'work:comment:draft', ('prepare_task_comment_draft', 'get_task_comment_draft_operation')),
    ('New personal supply drafts (browser confirmation)', 'SUPPLY_DRAFTS', 'supplies:request:draft', ('prepare_supply_request_draft', 'get_supply_draft_operation')),
    ('Mark own work notice read (browser confirmation)', 'NOTIFICATION_WRITES', 'notifications:mark_read', ('mark_my_notification_read', 'get_mcp_operation')),
    ('Monthly CSM summaries', 'CSM', 'surveys:csm:read', ('get_csm_summary',)),
    ('Monthly CSM comparisons', 'CSM_TRENDS', 'surveys:csm_trends:read', ('compare_csm_months',)),
    ('Quarterly activity summaries', 'ACTIVITY_SURVEYS', 'surveys:activities:read', ('get_activity_survey_summary',)),
    ('Individual activity scorecards', 'ACTIVITY_DETAILS', 'surveys:activity_details:read', ('find_survey_activities', 'get_activity_survey_detail')),
    ('Unit activity summaries', 'UNIT_SURVEYS', 'surveys:units:read', ('find_survey_units', 'get_unit_activity_survey_summary')),
    ('Unit quarterly comparisons', 'UNIT_TRENDS', 'surveys:unit_trends:read', ('compare_unit_activity_surveys',)),
    ('Resource-person scores at one activity', 'PERSON_ACTIVITY_SURVEYS', 'surveys:person_activities:read', ('get_resource_person_activity_survey',)),
    ('Annual resource-person summaries', 'RESOURCE_PERSON_SURVEYS', 'surveys:resource_persons:read', ('get_resource_person_survey_summary',)),
    ('Resource-person discovery and comparisons', 'RESOURCE_PERSON_TRENDS', 'surveys:resource_person_trends:read', ('find_survey_resource_persons', 'compare_resource_person_surveys')),
    ('Unread work notices', 'NOTIFICATIONS', 'notifications:read', ('list_my_notifications',)),
    ('Room availability', 'AVAILABILITY', 'calendar:read', ('get_room_availability',)),
)


def make_router(templates, get_conn, mcp_readiness=None, *, invalidate_activity_dates=None):
    router = APIRouter()
    private = {'Cache-Control':'private, no-store','Referrer-Policy':'same-origin'}

    def payload(request):
        return auth.parse_token(request.cookies.get(auth.COOKIE_NAME))

    def screen(request, *, admin=False, error='', status=200, secret=''):
        conn = get_conn()
        try:
            entries,next_cursor = access.listing(conn,payload(request),admin,request.query_params.get('before',''))
            now = int(time.time())
            for row in entries:
                row['scope_labels'] = [access.SCOPES[s] for s in json.loads(row['scopes_json'])]
                row['status'] = 'Revoked' if row['revoked_at'] is not None else 'Expired' if row['expires_at']<=now else 'Active'
                for field in ('issued_at','expires_at','last_used_at'):
                    row[field+'_label'] = datetime.fromtimestamp(row[field],timezone.utc).astimezone(tz.LOCAL_TZ).isoformat(timespec='minutes') if row[field] else 'Not used yet'
            mcp_entries = [] if admin else mcp_auth.owner_grants(conn, request.state.user['id'])
            for row in mcp_entries:
                row['status'] = 'Revoked' if row['revoked_at'] is not None else 'Expired' if row['expires_at']<=now else 'Active'
                for field in ('created_at','expires_at'):
                    row[field+'_label'] = datetime.fromtimestamp(row[field],timezone.utc).astimezone(tz.LOCAL_TZ).isoformat(timespec='minutes')
            return templates.TemplateResponse(request,'integration_access.html',
                {'show_scope':False,'entries':entries,'admin':admin,'error':error,'secret':secret,
                 'csrf':csrf(request),'scopes':access.SCOPES,'next_cursor':next_cursor,
                 'mcp_entries':mcp_entries}, status_code=status,headers=private)
        except access.InvalidCredential:
            return HTMLResponse('Sign in with the required access to manage connected tools.',status_code=403,headers=private)
        finally:
            conn.close()

    async def posted(request, create=False):
        # Bound the complete body before parsing; do not reflect any submitted secret.
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>8192:
                raise ValueError('The form is too large. Reload and try again.')
        request._body = bytes(data)
        form = await request.form(max_fields=10,max_files=0)
        allowed = {'csrf','name','scopes','days','password','consent'} if create else {'csrf'}
        if (set(form)-allowed or any(len(form.getlist(k))!=1 for k in form if k!='scopes')
                or not hmac.compare_digest(str(form.get('csrf','')).encode(),csrf(request).encode())):
            raise ValueError('The form expired or is invalid. Reload and try again.')
        return form

    @router.get('/account/integrations',response_class=HTMLResponse)
    def own(request: Request):
        return screen(request)

    @router.get('/account/integrations/mcp', response_class=HTMLResponse)
    async def readiness(request: Request):
        def own_connections():
            conn = get_conn()
            try:
                user = access._session(conn, payload(request))
                return mcp_auth.owner_grants(conn, user['id'])
            finally:
                conn.close()

        try:
            entries = await asyncio.to_thread(own_connections)
        except access.InvalidCredential:
            return HTMLResponse('Sign in again to check your connection.', status_code=403, headers=private)
        state = await mcp_readiness() if mcp_readiness else {'enabled': False, 'tools': [], 'catalog_ok': False, 'build': {}}
        now = int(time.time())
        for row in entries:
            row['status'] = 'Revoked' if row['revoked_at'] is not None else 'Refresh expired' if row['expires_at'] <= now else 'Grant active'
            row['expires_label'] = datetime.fromtimestamp(row['expires_at'], timezone.utc).astimezone(tz.LOCAL_TZ).isoformat(timespec='minutes')
        pilots = []
        for label, flag, scope, names in MCP_PILOTS:
            flag = 'CSS_MCP_' + flag + '_ENABLED'
            pilots.append({'label': label, 'flag': flag, 'scope': scope,
                           'enabled': os.environ.get(flag) == '1',
                           'registered': state['catalog_ok'] and set(names).issubset(state['tools']),
                           'names': names})
        return templates.TemplateResponse(request, 'mcp_readiness.html',
            {'show_scope': False, 'state': state, 'pilots': pilots, 'entries': entries}, headers=private)

    @router.get('/admin/integrations',response_class=HTMLResponse)
    def admin_list(request: Request):
        return screen(request,admin=True)

    def action_origin(request):
        canonical = os.environ.get('CSS_BASE_URL')
        if not canonical and os.environ.get('SPACE_HOST'):
            canonical = 'https://' + os.environ['SPACE_HOST']
        parts = access._origin(canonical or str(request.base_url))
        if parts is None:
            raise mcp_actions.ActionError('invalid_origin', 'The deployment origin is unavailable.')
        scheme, host, port = parts
        host = '[' + host + ']' if ':' in host else host
        return scheme + '://' + host + (':' + str(port) if port != (443 if scheme == 'https' else 80) else '')

    def action_screen(request, operation_id, confirm_digest=None, *, kind='notice'):
        conn = get_conn()
        try:
            origin = action_origin(request)
            service = {'notice': mcp_actions, 'supply': mcp_supply_drafts, 'comment': mcp_comment_drafts, 'report': mcp_report_views, 'calendar': mcp_personal_calendar, 'travel': mcp_travel_drafts, 'ack': mcp_task_acknowledgements, 'submit': mcp_task_submissions, 'supply_submit': mcp_supply_submissions, 'travel_review': mcp_travel_reviews, 'travel_submit': mcp_travel_submissions, 'room': mcp_room_requests, 'meal': mcp_meal_requests, 'wa': mcp_work_arrangements, 'activity_dates': mcp_activity_dates, 'activity_draft': mcp_activity_drafts, 'activity_creation': mcp_activity_creation, 'activity_announcement': mcp_activity_announcements, 'accept': mcp_task_acceptances, 'supply_approval': mcp_supply_approvals, 'room_approval': mcp_room_approvals}[kind]
            result = service.browser(conn, payload(request), origin + '/mcp', origin,
                                         operation_id, confirm_digest=confirm_digest)
            if kind == 'activity_dates' and confirm_digest is not None and result['status'] == 'completed' and invalidate_activity_dates:
                invalidate_activity_dates()
            return templates.TemplateResponse(request, {'notice': 'mcp_action.html', 'supply': 'mcp_supply_draft.html', 'comment': 'mcp_comment_draft.html', 'report': 'mcp_report_view.html', 'calendar': 'mcp_personal_calendar.html', 'travel': 'mcp_travel_draft.html', 'ack': 'mcp_task_acknowledgement.html', 'submit': 'mcp_task_submission.html', 'supply_submit': 'mcp_supply_submission.html', 'travel_review': 'mcp_travel_review.html', 'travel_submit': 'mcp_travel_submission.html', 'room': 'mcp_room_request.html', 'meal': 'mcp_meal_request.html', 'wa': 'mcp_work_arrangement.html', 'activity_dates': 'mcp_activity_dates.html', 'activity_draft': 'mcp_activity_draft.html', 'activity_creation': 'mcp_activity_creation.html', 'activity_announcement': 'mcp_activity_announcement.html', 'accept': 'mcp_task_acceptance.html', 'supply_approval': 'mcp_supply_approval.html', 'room_approval': 'mcp_room_approval.html'}[kind],
                {'show_scope': False, 'result': result, 'csrf': csrf(request)}, headers=private)
        except (permissions.Denied, supplies_storage.Denied):
            return HTMLResponse('Action not found or unavailable to you. Sign in with the account that prepared it.', status_code=404, headers=private)
        except mcp_actions.ActionError as exc:
            # All action error messages are fixed server-owned text.
            return HTMLResponse(str(exc), status_code=409, headers=private)
        except (supplies_storage.Invalid, supplies_storage.Conflict, documents.Conflict):
            if kind == 'report':
                return HTMLResponse('Report view unavailable. Review My saved report views, the name and the ten-view limit.', status_code=409, headers=private)
            return HTMLResponse('Draft unavailable. Review the current target, fields and your access in Office Connect.', status_code=409, headers=private)
        finally:
            conn.close()

    @router.get('/account/integrations/mcp/actions/{operation_id}', response_class=HTMLResponse)
    def action_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id)

    async def confirm_action(request, operation_id, *, kind='notice'):
        canonical = action_origin(request)
        if not same_origin_write(request, canonical):
            return HTMLResponse('Request verification failed.', status_code=403, headers=private)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2048:
                return HTMLResponse('The confirmation form is too large.', status_code=413, headers=private)
        request._body = bytes(raw)
        form = await request.form(max_fields=3, max_files=0)
        if (set(form) != {'csrf', 'preview_digest', 'confirm'}
                or any(len(form.getlist(k)) != 1 for k in form)
                or form.get('confirm') != 'yes'
                or not hmac.compare_digest(str(form.get('csrf', '')).encode(), csrf(request).encode())):
            return HTMLResponse('The confirmation expired or is invalid. Reload the preview.', status_code=403, headers=private)
        if not rl.allow('mcp_action', str(request.state.user['id'])):
            return HTMLResponse('Too many confirmations. Retry later with the same link.', status_code=429, headers=private)
        return await asyncio.to_thread(action_screen, request, operation_id, str(form['preview_digest']), kind=kind)

    @router.post('/account/integrations/mcp/actions/{operation_id}', response_class=HTMLResponse)
    async def action_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id)

    @router.get('/account/integrations/mcp/supply-drafts/{operation_id}', response_class=HTMLResponse)
    def supply_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='supply')

    @router.post('/account/integrations/mcp/supply-drafts/{operation_id}', response_class=HTMLResponse)
    async def supply_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='supply')

    @router.get('/account/integrations/mcp/comment-drafts/{operation_id}', response_class=HTMLResponse)
    def comment_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='comment')

    @router.post('/account/integrations/mcp/comment-drafts/{operation_id}', response_class=HTMLResponse)
    async def comment_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='comment')

    @router.get('/account/integrations/mcp/comment-drafts/saved/{draft_id}', response_class=HTMLResponse)
    def saved_comment_draft(request: Request, draft_id: int):
        conn = get_conn()
        try:
            user = st.session_actor(conn, payload(request))
            if not user:
                raise permissions.Denied('Sign in again.')
            draft = work_comment_drafts.get(conn, user, draft_id)
            return templates.TemplateResponse(request, 'work_comment_draft.html',
                {'show_scope': False, 'draft': draft}, headers=private)
        except permissions.Denied:
            return HTMLResponse('Private draft not found or unavailable to you.', status_code=404, headers=private)
        finally:
            conn.close()

    @router.get('/account/integrations/mcp/activity-announcements/{operation_id}', response_class=HTMLResponse)
    def activity_announcement_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='activity_announcement')

    @router.post('/account/integrations/mcp/activity-announcements/{operation_id}', response_class=HTMLResponse)
    async def activity_announcement_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='activity_announcement')

    @router.get('/account/integrations/mcp/activity-creation/{operation_id}', response_class=HTMLResponse)
    def activity_creation_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='activity_creation')

    @router.post('/account/integrations/mcp/activity-creation/{operation_id}', response_class=HTMLResponse)
    async def activity_creation_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='activity_creation')

    @router.get('/account/integrations/mcp/activity-drafts/{operation_id}', response_class=HTMLResponse)
    def activity_draft_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='activity_draft')

    @router.post('/account/integrations/mcp/activity-drafts/{operation_id}', response_class=HTMLResponse)
    async def activity_draft_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='activity_draft')

    @router.get('/account/integrations/mcp/activity-dates/{operation_id}', response_class=HTMLResponse)
    def activity_date_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='activity_dates')

    @router.post('/account/integrations/mcp/activity-dates/{operation_id}', response_class=HTMLResponse)
    async def activity_date_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='activity_dates')

    @router.get('/account/integrations/mcp/work-arrangement-requests/saved/{operation_id}', response_class=HTMLResponse)
    def work_arrangement_source(request: Request, operation_id: str):
        conn = get_conn()
        try:
            user = st.session_actor(conn, payload(request))
            if not user:
                raise permissions.Denied('Sign in again.')
            record = mcp_work_arrangements.source(conn, user, operation_id)
            return templates.TemplateResponse(request, 'mcp_work_arrangement_source.html',
                {'show_scope': False, 'record': record}, headers=private)
        except (permissions.Denied, ValueError):
            return HTMLResponse('Work arrangement source unavailable to you.', status_code=404, headers=private)
        finally:
            conn.close()

    @router.get('/account/integrations/mcp/work-arrangement-requests/{operation_id}', response_class=HTMLResponse)
    def work_arrangement_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='wa')

    @router.post('/account/integrations/mcp/work-arrangement-requests/{operation_id}', response_class=HTMLResponse)
    async def work_arrangement_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='wa')

    @router.get('/account/integrations/mcp/meal-requests/{operation_id}', response_class=HTMLResponse)
    def meal_request_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='meal')

    @router.post('/account/integrations/mcp/meal-requests/{operation_id}', response_class=HTMLResponse)
    async def meal_request_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='meal')

    @router.get('/account/integrations/mcp/room-approvals/{operation_id}', response_class=HTMLResponse)
    def room_approval_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='room_approval')

    @router.post('/account/integrations/mcp/room-approvals/{operation_id}', response_class=HTMLResponse)
    async def room_approval_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='room_approval')

    @router.get('/account/integrations/mcp/room-requests/{operation_id}', response_class=HTMLResponse)
    def room_request_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='room')

    @router.post('/account/integrations/mcp/room-requests/{operation_id}', response_class=HTMLResponse)
    async def room_request_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='room')

    @router.get('/account/integrations/mcp/travel-submissions/{operation_id}', response_class=HTMLResponse)
    def travel_submission_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='travel_submit')

    @router.post('/account/integrations/mcp/travel-submissions/{operation_id}', response_class=HTMLResponse)
    async def travel_submission_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='travel_submit')

    @router.get('/account/integrations/mcp/travel-review-requests/{operation_id}', response_class=HTMLResponse)
    def travel_review_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='travel_review')

    @router.post('/account/integrations/mcp/travel-review-requests/{operation_id}', response_class=HTMLResponse)
    async def travel_review_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='travel_review')

    @router.get('/account/integrations/mcp/supply-approvals/{operation_id}', response_class=HTMLResponse)
    def supply_approval_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='supply_approval')

    @router.post('/account/integrations/mcp/supply-approvals/{operation_id}', response_class=HTMLResponse)
    async def supply_approval_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='supply_approval')

    @router.get('/account/integrations/mcp/supply-submissions/{operation_id}', response_class=HTMLResponse)
    def supply_submission_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='supply_submit')

    @router.post('/account/integrations/mcp/supply-submissions/{operation_id}', response_class=HTMLResponse)
    async def supply_submission_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='supply_submit')

    @router.get('/account/integrations/mcp/task-acceptances/{operation_id}', response_class=HTMLResponse)
    def task_acceptance_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='accept')

    @router.post('/account/integrations/mcp/task-acceptances/{operation_id}', response_class=HTMLResponse)
    async def task_acceptance_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='accept')

    @router.get('/account/integrations/mcp/task-submissions/{operation_id}', response_class=HTMLResponse)
    def task_submission_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='submit')

    @router.post('/account/integrations/mcp/task-submissions/{operation_id}', response_class=HTMLResponse)
    async def task_submission_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='submit')

    @router.get('/account/integrations/mcp/task-acknowledgements/{operation_id}', response_class=HTMLResponse)
    def task_acknowledgement_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='ack')

    @router.post('/account/integrations/mcp/task-acknowledgements/{operation_id}', response_class=HTMLResponse)
    async def task_acknowledgement_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='ack')

    @router.get('/account/integrations/mcp/travel-drafts/{operation_id}', response_class=HTMLResponse)
    def travel_draft_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='travel')

    @router.post('/account/integrations/mcp/travel-drafts/{operation_id}', response_class=HTMLResponse)
    async def travel_draft_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='travel')

    @router.get('/account/integrations/mcp/personal-calendar/{operation_id}', response_class=HTMLResponse)
    def personal_calendar_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='calendar')

    @router.post('/account/integrations/mcp/personal-calendar/{operation_id}', response_class=HTMLResponse)
    async def personal_calendar_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='calendar')

    @router.get('/account/integrations/mcp/report-views/{operation_id}', response_class=HTMLResponse)
    def report_view_preview(request: Request, operation_id: str):
        return action_screen(request, operation_id, kind='report')

    @router.post('/account/integrations/mcp/report-views/{operation_id}', response_class=HTMLResponse)
    async def report_view_confirm(request: Request, operation_id: str):
        return await confirm_action(request, operation_id, kind='report')

    def report_view_screen(request, view_id=None):
        conn = get_conn()
        try:
            user = st.session_actor(conn, payload(request))
            if not user:
                raise permissions.Denied('Sign in again.')
            selected = report_views.get(conn, user, view_id) if view_id is not None else None
            entries = report_views.listing(conn, user) if view_id is None else []
            return templates.TemplateResponse(request, 'saved_report_views.html',
                {'show_scope': False, 'nav_active': 'reports', 'selected': selected, 'views': entries}, headers=private)
        except permissions.Denied:
            return HTMLResponse('Saved report view not found or unavailable to you.', status_code=404, headers=private)
        except ValueError:
            return HTMLResponse('This saved report selection is unavailable. Review My saved report views.', status_code=409, headers=private)
        finally:
            conn.close()

    @router.get('/reports/saved', response_class=HTMLResponse)
    def report_view_list(request: Request):
        return report_view_screen(request)

    @router.get('/reports/saved/{view_id}', response_class=HTMLResponse)
    def saved_report_view(request: Request, view_id: int):
        return report_view_screen(request, view_id)

    def create_credential(request,form):
        if not rl.allow('integration_issue',str(request.state.user['id'])):
            return screen(request,error='Too many attempts. Try again in 15 minutes.',status=429)
        if (form.get('consent')!='yes' or form.get('days') not in ('7','30','90')
                or not isinstance(form.get('password'),str) or not 1<=len(form['password'])<=1024):
            return screen(request,error='Choose access and expiry, confirm consent, and enter your current password.',status=400)
        conn = get_conn()
        try:
            identity = access._session(conn,payload(request))
            account = st.get_admin_user_by_id(conn,identity['id'])
            if not auth.verify_password(form['password'],account['pw_hash'],account['salt']):
                return screen(request,error='The password could not be verified.',status=400)
            token = access.issue(conn,payload(request),account['pw_hash'],form.get('name',''),
                form.getlist('scopes'),int(form['days']),access.audience(request))
        except (ValueError,UnicodeError):
            return screen(request,error='The credential could not be created. Check your access, tool name and selected permissions.',status=400)
        finally:
            conn.close()
        return screen(request,secret=token)

    @router.post('/account/integrations')
    async def create(request: Request):
        try:
            form = await posted(request,create=True)
        except ValueError:
            return await asyncio.to_thread(screen,request,error='The form expired or is invalid. Reload and try again.',status=400)
        # Database, PBKDF2 and rendering stay on one worker, off the event loop.
        return await asyncio.to_thread(create_credential,request,form)

    def revoke_credential(request,key,admin):
        conn = get_conn()
        try:
            access.revoke(conn,payload(request),key,admin)
        except access.InvalidCredential:
            return screen(request,admin=admin,error='Credential not found or unavailable to you.',status=404)
        finally:
            conn.close()
        return RedirectResponse('/admin/integrations' if admin else '/account/integrations',status_code=303,headers=private)

    async def remove(request,key,admin):
        try:
            await posted(request)
        except ValueError:
            return await asyncio.to_thread(screen,request,admin=admin,error='The form expired or is invalid. Reload and try again.',status=400)
        return await asyncio.to_thread(revoke_credential,request,key,admin)

    @router.post('/account/integrations/{key}/revoke')
    async def own_revoke(request: Request,key: str):
        return await remove(request,key,False)

    @router.post('/admin/integrations/{key}/revoke')
    async def admin_revoke(request: Request,key: str):
        return await remove(request,key,True)

    @router.post('/account/mcp/{key}/revoke')
    async def own_mcp_revoke(request: Request,key: str):
        try:
            await posted(request)
            conn = get_conn()
            try:
                mcp_auth.revoke_owner_grant(conn, request.state.user['id'], key)
            finally:
                conn.close()
        except ValueError:
            return await asyncio.to_thread(screen, request,
                error='Connection not found or form expired. Reload and try again.', status=400)
        return RedirectResponse('/account/integrations',status_code=303,headers=private)

    return router
