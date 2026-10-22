"""A19/A20 API v1. Sessions, scoped credentials and domain services own authority."""
from contextlib import contextmanager
import asyncio
from datetime import date, datetime
import hashlib
import hmac
import json
import os
import re
import sqlite3
from typing import Annotated, Generic, Literal, TypeVar

from fastapi import FastAPI, Header, Path, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException
from starlette._utils import get_route_path

import auth
import documents
import documents_permissions as permissions
from documents_registry import snapshot
import integration_operations as operations
import integration_access as access
import ratelimit as rl
from request_security import same_origin_write
import tzutil as tz
import version
import work
import work_reads

MAX_ID = 9223372036854775807
API_ROOT = '/api/v1'
Identifier = Annotated[str, Path(pattern=r'^[1-9][0-9]{0,18}$')]
OPERATION_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
OperationIdentifier = Annotated[str, Path(pattern=OPERATION_PATTERN)]
T = TypeVar('T')


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Error(Model):
    code: str
    message: str


class ErrorResponse(Model):
    error: Error


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def is_api(path):
    return path == API_ROOT or path.startswith(API_ROOT + '/')


def failure(status, code, message, headers=None):
    return JSONResponse({'error': {'code': code, 'message': message}}, status_code=status,
                        headers={'Cache-Control': 'private, no-store', **(headers or {})})


class PageQuery(Model):
    limit: int = Field(default=25, ge=1, le=100)
    before: int = Field(default=0, ge=0, le=MAX_ID)


class DocumentQuery(PageQuery):
    q: str = Field(default='', max_length=200)
    queue: Literal['all', 'IN', 'OUT', 'mine', 'review', 'release', 'archived'] = 'all'


class PageInfo(Model):
    limit: int
    has_more: bool
    next_before: str | None


class Page(Model, Generic[T]):
    data: list[T]
    page: PageInfo


class Links(Model):
    self: str
    web: str


class DocumentRead(Model):
    id: str
    number: str
    subject: str
    direction: Literal['IN', 'OUT']
    type: str
    status: str
    verification: str
    revision: int
    due_date: date | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    archived_at: AwareDatetime | None
    links: Links


class WorkRead(Model):
    id: str
    title: str
    unit_id: str
    lead_id: str | None
    revision: int
    due_date: date | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    links: Links


class TaskRead(Model):
    id: str
    work_item_id: str
    title: str
    status: Literal['proposed', 'todo', 'in_progress', 'for_review', 'done', 'cancelled']
    owner_id: str | None
    revision: int
    due_date: date | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    links: Links


class ApiInfo(Model):
    api_version: Literal['1'] = '1'
    application_version: str
    read_only: bool = False
    authentication: Literal['registered_user_session','scoped_read_credential'] = 'registered_user_session'
    openapi: str


class WriteContext(Model):
    csrf_token: str


class Acknowledge(Model):
    revision: int = Field(strict=True, ge=1, le=MAX_ID - 1)
    reason: str = Field(strict=True, min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError('A reason is required.')
        value.encode('utf-8')
        return value


class Submit(Acknowledge):
    submission: str = Field(strict=True, min_length=1, max_length=8000)

    @field_validator('submission')
    @classmethod
    def meaningful_submission(cls, value):
        if not value.strip():
            raise ValueError('Output or evidence is required.')
        value.encode('utf-8')
        return value


class OperationLinks(Model):
    self: str
    task: str
    web: str


class OperationRead(Model):
    id: str
    action: Literal['acknowledge', 'submit']
    status: Literal['succeeded'] = 'succeeded'
    work_item_id: str
    task_id: str
    result_revision: int
    result_status: Literal['in_progress', 'for_review']
    completed_at: AwareDatetime
    links: OperationLinks


def operation_read(row):
    return OperationRead(id=row['operation_id'], action=row['action'], result_status=operations.RESULT_STATUS[row['action']],
        work_item_id=str(row['case_id']),
        task_id=str(row['task_id']), result_revision=row['result_revision'], completed_at=_stamp(row['completed_at']),
        links=OperationLinks(self=f"{API_ROOT}/operations/{row['operation_id']}",
            task=f"{API_ROOT}/work-items/{row['case_id']}/tasks/{row['task_id']}",
            web=f"/work/{row['case_id']}#task-{row['task_id']}"))


def csrf_token(request):
    return hmac.new(auth._secret(), ('integration-v1:' + request.cookies.get(auth.COOKIE_NAME, '')).encode(),
                    hashlib.sha256).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON member')
        result[key] = value
    return result


def _id(value):
    value = int(value)
    if not 1 <= value <= MAX_ID:
        raise ApiError(400, 'invalid_request', 'The resource identifier is invalid.')
    return value


def _stamp(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=tz.LOCAL_TZ) if parsed.tzinfo is None else parsed


def _nullable_id(value):
    return str(value) if value is not None else None


def document_read(row):
    # Explicit projections exclude bodies, email metadata, file URLs, grants,
    # instructions, drafts, receipts and internal operation diagnostics.
    return DocumentRead(id=str(row['id']), number=row['number'], subject=row['subject'],
        direction=row['direction'], type=row['type'], status=row['status'], verification=row['verification'],
        revision=row['revision'], due_date=row['due_date'] or None,
        created_at=_stamp(row['created_at']), updated_at=_stamp(row['updated_at']),
        archived_at=_stamp(row['archived_at']),
        links=Links(self=f"{API_ROOT}/documents/{row['id']}", web=f"/documents/{row['id']}"))


def work_read(row):
    return WorkRead(id=str(row['id']), title=row['title'], unit_id=str(row['unit_id']),
        lead_id=_nullable_id(row['lead_id']), revision=row['revision'], due_date=row['due_date'] or None,
        created_at=_stamp(row['created_at']), updated_at=_stamp(row['updated_at']),
        links=Links(self=f"{API_ROOT}/work-items/{row['id']}", web=f"/work/{row['id']}"))


def task_read(row):
    return TaskRead(id=str(row['id']), work_item_id=str(row['case_id']), title=row['title'],
        status=row['status'], owner_id=_nullable_id(row['owner_id']), revision=row['revision'],
        due_date=row['due_date'] or None, created_at=_stamp(row['created_at']), updated_at=_stamp(row['updated_at']),
        links=Links(self=f"{API_ROOT}/work-items/{row['case_id']}/tasks/{row['id']}", web=f"/work/{row['case_id']}"))


def page_info(limit, next_before):
    return PageInfo(limit=limit, has_more=next_before is not None,
                    next_before=str(next_before) if next_before is not None else None)


def make_app(get_conn):
    cookie = APIKeyCookie(name=auth.COOKIE_NAME, scheme_name='UserSession', auto_error=False,
                         description='An existing registered user session. Required for task writes, write context and operation receipts.')
    bearer = HTTPBearer(scheme_name='IntegrationRead',auto_error=False,
                        description='A delegated read credential for this deployment and API v1; selected metadata scopes and current owner permissions apply.')
    api = FastAPI(title='Office Connect API', version='1.3.0',
                  description='Permission-checked metadata reads, task acknowledgement and submission for review with durable recovery receipts.',
                  docs_url=None, redoc_url=None, dependencies=[Security(cookie),Security(bearer)],
                  servers=[{'url': API_ROOT}], root_path_in_servers=False)

    @contextmanager
    def read_context(request):
        # Open, consume and close on the same sync route worker (SQLite connections
        # must not be passed between a yielded dependency and an endpoint thread).
        conn = get_conn()
        try:
            with snapshot(conn):
                try:
                    if getattr(request.state,'integration',None):
                        user,credential = access.authenticate(conn,request)
                        if credential['id'] != request.state.integration['id']:
                            raise access.InvalidCredential('Credential changed.')
                    else:
                        user = permissions.actor(conn, getattr(request.state, 'user', None))
                except access.InvalidCredential:
                    raise ApiError(401,'authentication_required','A valid integration credential is required.') from None
                except permissions.Denied:
                    raise ApiError(401, 'authentication_required', 'A current signed-in session is required.') from None
                yield conn, user
        except permissions.Denied:
            # Missing and inaccessible resources have an identical response.
            raise ApiError(404, 'not_found', 'Resource not found or unavailable to you.') from None
        finally:
            conn.close()

    @api.exception_handler(ApiError)
    async def api_error(request, exc):
        return failure(exc.status, exc.code, exc.message)

    @api.exception_handler(operations.OperationError)
    async def operation_error(request, exc):
        return failure(exc.status, exc.code, exc.message)

    @api.exception_handler(permissions.Denied)
    async def unavailable(request, exc):
        return failure(404, 'not_found', 'Resource not found or unavailable to you.')

    @api.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
            message = ('Check the operation result, then retry the same request and key if needed.'
                       if request.method == 'POST' else 'The database is busy. Retry this read later.')
            return failure(503, 'temporarily_unavailable',
                           message, {'Retry-After': '1'})
        return failure(500, 'internal_error', 'The request could not be completed. Check the operation result before retrying.')

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Never echo submitted values, cookies, credentials or validation internals.
        return failure(400, 'invalid_request', 'One or more request parameters are invalid.')

    @api.exception_handler(HTTPException)
    async def http_error(request, exc):
        code, message = {
            404: ('not_found', 'Resource not found or unavailable to you.'),
            405: ('method_not_allowed', 'This method is not supported for this resource.'),
        }.get(exc.status_code, ('request_failed', 'The request could not be completed.'))
        return failure(exc.status_code, code, message, exc.headers)

    @api.exception_handler(Exception)
    async def server_error(request, exc):
        message = ('The request could not be completed. Check the operation result before retrying.'
                   if request.method == 'POST' else 'The request could not be completed. Retry later.')
        return failure(500, 'internal_error', message)

    @api.middleware('http')
    async def api_boundary(request, call_next):
        # The parent middleware authenticates this namespace before dispatch,
        # including the generated contract and unknown paths. Keep this factory
        # fail-closed if it is accidentally mounted without that parent.
        if not getattr(request.state, 'user', None):
            return failure(401, 'authentication_required', 'A current signed-in session is required.')
        credential = getattr(request.state,'integration',None)
        if credential:
            # Bound admitted audit writes even for denied methods/scopes.
            if not rl.allow('integration_read',str(request.state.user['id'])):
                return failure(429,'rate_limited','Too many integration reads. Retry later.',{'Retry-After':'60'})
            resource,required = access.resource(get_route_path(request.scope))
            if request.method!='GET' or resource=='unsupported' or (required and required not in credential['scopes']):
                return failure(403,'insufficient_scope','This credential does not allow this operation.')
        task_action = re.fullmatch(r'/work-items/[^/]+/tasks/[^/]+/(acknowledge|submit)', get_route_path(request.scope))
        allowed = 'POST' if task_action else 'GET'
        if request.method != allowed:
            return failure(405, 'method_not_allowed', 'This method is not supported for this resource.', {'Allow': allowed})
        if any(len(request.query_params.getlist(key)) > 1 for key in request.query_params):
            return failure(400, 'invalid_request', 'Duplicate request parameters are not supported.')
        if request.method == 'POST':
            canonical = os.environ.get('CSS_BASE_URL') or ('https://' + os.environ['SPACE_HOST'] if os.environ.get('SPACE_HOST') else None)
            supplied = request.headers.getlist('x-csrf-token')
            if (not same_origin_write(request, canonical) or len(supplied) != 1
                    or not hmac.compare_digest(supplied[0].encode(), csrf_token(request).encode())):
                return failure(403, 'request_verification_failed', 'Fetch the current write context and verify the request origin.')
            keys = request.headers.getlist('idempotency-key')
            if len(keys) != 1 or not re.fullmatch(OPERATION_PATTERN, keys[0]) or request.query_params:
                return failure(400, 'invalid_request', 'Use one new UUID v4 operation key and no query parameters.')
            types = request.headers.getlist('content-type')
            if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                return failure(415, 'unsupported_media_type', 'Send an application/json request body.')
            # Submission has a larger bounded body for output plus reason;
            # acknowledgement retains its original cap.
            body_limit = 65536 if task_action.group(1) == 'submit' else 8192
            # Bound streamed and chunked requests before FastAPI parses the body.
            payload = bytearray()
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > body_limit:
                    return failure(413, 'request_too_large', 'The request body exceeds the supported size.')
            try:
                json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object)
            except (ValueError, UnicodeError, RecursionError):
                return failure(400, 'invalid_request', 'Send a valid JSON object without duplicate members.')
            request._body = bytes(payload)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    def audit_read(request,status):
        conn = get_conn()
        try:
            access.record_use(conn,request.state.user,request.state.integration['id'],
                              get_route_path(request.scope),request.method,status)
        finally:
            conn.close()

    @api.middleware('http')
    async def integration_audit(request,call_next):
        response = await call_next(request)
        if getattr(request.state,'integration',None) and response.status_code!=429:
            try:
                await asyncio.to_thread(audit_read,request,response.status_code)
            except sqlite3.OperationalError:
                return failure(503,'temporarily_unavailable','The read could not be recorded. Retry later.',{'Retry-After':'1'})
            except Exception:
                return failure(500,'internal_error','The read could not be recorded. Retry later.')
        return response

    errors = {n: {'model': ErrorResponse} for n in (400, 401, 403, 404, 405, 429, 500, 503)}
    write_errors = {**errors, **{n: {'model': ErrorResponse} for n in (403, 409, 413, 415)}}

    @api.get('/', response_model=ApiInfo, responses=errors, operation_id='readApiInfo')
    def info(request: Request):
        credential = bool(getattr(request.state,'integration',None))
        return ApiInfo(application_version=version.APP_VERSION, openapi=API_ROOT + '/openapi.json',
                       read_only=credential,authentication='scoped_read_credential' if credential else 'registered_user_session')

    @api.get('/write-context', response_model=WriteContext, responses=errors, operation_id='readWriteContext')
    def write_context(request: Request):
        with read_context(request) as (conn, user):
            operations.session_actor(conn, auth.parse_token(request.cookies.get(auth.COOKIE_NAME)))
            return WriteContext(csrf_token=csrf_token(request))

    @api.get('/operations/{operation_id}', response_model=OperationRead, responses=errors, operation_id='readTaskOperation')
    def operation_detail(request: Request, operation_id: OperationIdentifier):
        with read_context(request) as (conn, user):
            user = operations.session_actor(conn, auth.parse_token(request.cookies.get(auth.COOKIE_NAME)))
            return operation_read(operations.find(conn, user, operation_id))

    @api.post('/work-items/{work_item_id}/tasks/{task_id}/acknowledge', response_model=OperationRead,
              responses=write_errors, operation_id='acknowledgeWorkTask')
    def acknowledge_task(request: Request, work_item_id: Identifier, task_id: Identifier, data: Acknowledge,
                         idempotency_key: Annotated[str, Header(pattern=OPERATION_PATTERN)],
                         x_csrf_token: Annotated[str, Header(pattern=r'^[0-9a-f]{64}$')],
                         origin: Annotated[str, Header(max_length=4096)]):
        conn = get_conn()
        try:
            return operation_read(operations.acknowledge(conn,
                auth.parse_token(request.cookies.get(auth.COOKIE_NAME)), _id(work_item_id), _id(task_id),
                idempotency_key, data.revision, data.reason))
        finally:
            conn.close()

    @api.post('/work-items/{work_item_id}/tasks/{task_id}/submit', response_model=OperationRead,
              responses=write_errors, operation_id='submitWorkTask')
    def submit_task(request: Request, work_item_id: Identifier, task_id: Identifier, data: Submit,
                    idempotency_key: Annotated[str, Header(pattern=OPERATION_PATTERN)],
                    x_csrf_token: Annotated[str, Header(pattern=r'^[0-9a-f]{64}$')],
                    origin: Annotated[str, Header(max_length=4096)]):
        conn = get_conn()
        try:
            return operation_read(operations.submit(conn,
                auth.parse_token(request.cookies.get(auth.COOKIE_NAME)), _id(work_item_id), _id(task_id),
                idempotency_key, data.revision, data.reason, data.submission))
        finally:
            conn.close()

    @api.get('/documents', response_model=Page[DocumentRead], responses=errors, operation_id='listDocuments')
    def document_list(request: Request, query: Annotated[DocumentQuery, Query()]):
        with read_context(request) as (conn, user):
            result = documents.list_page(conn, user, query.q, query.queue,
                before=query.before, limit=query.limit, totals=False, snippets=False)
            return Page[DocumentRead](data=[document_read(row) for row in result['documents']],
                                      page=page_info(query.limit, result['next_before']))

    @api.get('/documents/{document_id}', response_model=DocumentRead, responses=errors, operation_id='readDocument')
    def document_detail(request: Request, document_id: Identifier):
        with read_context(request) as (conn, user):
            # Browser detail redirects merged receipts; never serialize the obsolete
            # source's subject/status when only the canonical target is readable.
            row = work.resolved_document(conn, _id(document_id))
            permissions.require_view(conn, user, row)
            return document_read(row)

    @api.get('/work-items', response_model=Page[WorkRead], responses=errors, operation_id='listWorkItems')
    def work_list(request: Request, query: Annotated[PageQuery, Query()]):
        with read_context(request) as (conn, user):
            selected, next_before = work.list_page(conn, user, before=query.before, limit=query.limit)
            return Page[WorkRead](data=[work_read(row) for row in selected], page=page_info(query.limit, next_before))

    @api.get('/work-items/{work_item_id}', response_model=WorkRead, responses=errors, operation_id='readWorkItem')
    def work_detail(request: Request, work_item_id: Identifier):
        with read_context(request) as (conn, user):
            return work_read(work.get(conn, user, _id(work_item_id)))

    @api.get('/work-items/{work_item_id}/tasks', response_model=Page[TaskRead], responses=errors, operation_id='listWorkTasks')
    def task_list(request: Request, work_item_id: Identifier, query: Annotated[PageQuery, Query()]):
        with read_context(request) as (conn, user):
            selected, next_before = work_reads.tasks_page(conn, user, _id(work_item_id), before=query.before, limit=query.limit)
            return Page[TaskRead](data=[task_read(row) for row in selected], page=page_info(query.limit, next_before))

    @api.get('/work-items/{work_item_id}/tasks/{task_id}', response_model=TaskRead, responses=errors, operation_id='readWorkTask')
    def task_detail(request: Request, work_item_id: Identifier, task_id: Identifier):
        with read_context(request) as (conn, user):
            return task_read(work_reads.task(conn, user, _id(work_item_id), _id(task_id)))

    generate_openapi = api.openapi

    def supported_openapi():
        schema = generate_openapi()
        # FastAPI inserts its default 422 declaration even with our validation
        # handler. The supported contract returns the documented ErrorResponse/400.
        for name,path in schema['paths'].items():
            for method,operation in path.items():
                operation.get('responses', {}).pop('422', None)
                if method!='get' or name in ('/write-context','/operations/{operation_id}'):
                    operation['security']=[{'UserSession':[]}]
                elif name.startswith('/documents'):
                    operation['x-integration-scope']='documents:read'
                elif name.startswith('/work-items'):
                    operation['x-integration-scope']='work:read'
        for name in ('HTTPValidationError', 'ValidationError'):
            schema.get('components', {}).get('schemas', {}).pop(name, None)
        return schema

    api.openapi = supported_openapi
    return api
