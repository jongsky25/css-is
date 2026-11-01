"""Signed-in submission preparation; final confirmation stays in private Telegram."""
import hmac
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import auth
from documents_storage import rows
import ratelimit
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_tasks as tasks
from telegram_link_routes import PRIVATE, csrf


def make_router(templates, get_conn):
    router = APIRouter()

    def current(conn, request):
        user=links.current(conn,auth.parse_token(request.cookies.get(auth.COOKIE_NAME)))
        found=rows(conn,"SELECT * FROM telegram_connection WHERE account_id=? AND state='active'",(user['id'],))
        if not found or bot.reply_transport()!='webhook' or not bot.storage.enabled('delivery'):
            raise ValueError('Task submission unavailable.')
        ctx=tasks.context(conn,found[0])
        actions.authority(conn,ctx,'tasks.submit')
        return user,ctx

    @router.get(tasks.PATH)
    def page(request:Request):
        conn=get_conn()
        try:
            user,ctx=current(conn,request)
            query=tasks.parse('/task_submit '+request.query_params.get('case_id','')+' '+request.query_params.get('task_id',''))
            fields={'case_id':query['ids'][0],'task_id':query['ids'][1],'reason':'Submission prepared in Office Connect.','submission':'Placeholder for preparation only.'}
            clean,summary,expected=actions.ADAPTERS['tasks.submit'].prepare(conn,user,fields)
            return templates.TemplateResponse(request,'telegram_task.html',{'show_scope':False,'csrf':csrf(request),
                'case_id':clean['case_id'],'task_id':clean['task_id'],'title':summary['title'],'revision':expected['revision'],
                'case_revision':expected['case_revision'],'key':secrets.token_hex(16)},headers=PRIVATE)
        except ValueError:
            return HTMLResponse('Task submission unavailable. Check ownership, permissions and current workflow state.',status_code=403,headers=PRIVATE)
        finally:conn.close()

    @router.post(tasks.PATH)
    async def prepare(request:Request):
        conn=None
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>12000:raise ValueError('Form too large.')
            request._body=bytes(body)
            form=await request.form(max_fields=9,max_files=0)
            if (set(form)!={'csrf','case_id','task_id','revision','case_revision','key','reason','submission'}
                    or any(len(form.getlist(k))!=1 for k in form)
                    or not hmac.compare_digest(str(form['csrf']).encode(),csrf(request).encode())):
                raise ValueError('Form expired. Reload and try again.')
            if not ratelimit.allow('integration_issue',str(request.state.user['id'])):
                return HTMLResponse('Too many previews. Try again later.',status_code=429,headers=PRIVATE)
            conn=get_conn();user,ctx=current(conn,request)
            query=tasks.parse('/task_submit '+str(form['case_id'])+' '+str(form['task_id']))
            fields={'case_id':query['ids'][0],'task_id':query['ids'][1],'reason':str(form['reason']),'submission':str(form['submission'])}
            # Check form revisions under the same writer lock as preview creation.
            from documents_storage import transaction
            with transaction(conn):
                _,_,expected=actions.ADAPTERS['tasks.submit'].prepare(conn,user,fields)
                if str(expected['revision'])!=str(form['revision']) or str(expected['case_revision'])!=str(form['case_revision']):
                    raise ValueError('The task changed. Reload and prepare a new preview.')
                result=actions.issue(conn,ctx,'tasks.submit',str(form['key']),fields,bot.now_utc(),commit=False)
            return templates.TemplateResponse(request,'telegram_task.html',{'show_scope':False,'operation_id':result['operation_id']},headers=PRIVATE)
        except ValueError:
            return HTMLResponse('Submission preview unavailable or changed. Reload the form and check your output and task.',status_code=400,headers=PRIVATE)
        finally:
            if conn is not None:conn.close()
    return router
