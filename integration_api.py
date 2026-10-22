"""A19 v1 read contract. Session authority and domain services remain authoritative."""
from contextlib import contextmanager
from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar

from fastapi import FastAPI, Path, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

import auth
import documents
import documents_permissions as permissions
from documents_registry import snapshot
import tzutil as tz
import version
import work
import work_reads

MAX_ID = 9223372036854775807
API_ROOT = '/api/v1'
Identifier = Annotated[str, Path(pattern=r'^[1-9][0-9]{0,18}$')]
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
    read_only: Literal[True] = True
    authentication: Literal['registered_user_session'] = 'registered_user_session'
    openapi: str


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
                         description='An existing registered user session; API keys and bearer tokens are not supported by this increment.')
    api = FastAPI(title='Office Connect read API', version='1.0.0',
                  description='Permission-checked metadata and status reads. No write operations.',
                  docs_url=None, redoc_url=None, dependencies=[Security(cookie)],
                  servers=[{'url': API_ROOT}], root_path_in_servers=False)

    @contextmanager
    def read_context(request):
        # Open, consume and close on the same sync route worker (SQLite connections
        # must not be passed between a yielded dependency and an endpoint thread).
        conn = get_conn()
        try:
            with snapshot(conn):
                try:
                    user = permissions.actor(conn, getattr(request.state, 'user', None))
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

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Never echo submitted values, cookies, credentials or validation internals.
        return failure(400, 'invalid_request', 'One or more request parameters are invalid.')

    @api.exception_handler(HTTPException)
    async def http_error(request, exc):
        code, message = {
            404: ('not_found', 'Resource not found or unavailable to you.'),
            405: ('method_not_allowed', 'This API supports GET reads only.'),
        }.get(exc.status_code, ('request_failed', 'The request could not be completed.'))
        return failure(exc.status_code, code, message, exc.headers)

    @api.exception_handler(Exception)
    async def server_error(request, exc):
        return failure(500, 'internal_error', 'The request could not be completed. Retry later.')

    @api.middleware('http')
    async def read_boundary(request, call_next):
        # The parent middleware authenticates this namespace before dispatch,
        # including the generated contract and unknown paths. Keep this factory
        # fail-closed if it is accidentally mounted without that parent.
        if not getattr(request.state, 'user', None):
            return failure(401, 'authentication_required', 'A current signed-in session is required.')
        if request.method != 'GET':
            return failure(405, 'method_not_allowed', 'This API supports GET reads only.', {'Allow': 'GET'})
        if any(len(request.query_params.getlist(key)) > 1 for key in request.query_params):
            return failure(400, 'invalid_request', 'Duplicate request parameters are not supported.')
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    errors = {n: {'model': ErrorResponse} for n in (400, 401, 404, 405, 500)}

    @api.get('/', response_model=ApiInfo, responses=errors, operation_id='readApiInfo')
    def info():
        return ApiInfo(application_version=version.APP_VERSION, openapi=API_ROOT + '/openapi.json')

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
        for path in schema['paths'].values():
            for operation in path.values():
                operation.get('responses', {}).pop('422', None)
        for name in ('HTTPValidationError', 'ValidationError'):
            schema.get('components', {}).get('schemas', {}).pop(name, None)
        return schema

    api.openapi = supported_openapi
    return api
