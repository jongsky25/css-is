"""Current private coordinator review queue; metadata only, no prepared writes."""
import os
import re

import documents_permissions as permissions
from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import telegram_work_actions as shared
import work
import work_reads
import work_tasks

ACTION='tasks.review.read'
COMMANDS=('/review_queue','/review_task')
USAGE='Use /review_queue [BEFORE_ID] or /review_task WORK_ID TASK_ID. Metadata only; review the submission in Office Connect.'
PAGE_SIZE=5
SCAN_LIMIT=200
BATCH_SIZE=50
DENIED='Task review unavailable to this account. Open Office Connect to check current source rights and blockers.'


def parse(text):
    parts=text.split()
    if not parts or parts[0] not in COMMANDS:raise ValueError(USAGE)
    if not (parts[0]=='/review_queue' and len(parts) in (1,2) or parts[0]=='/review_task' and len(parts)==3):
        raise ValueError(USAGE)
    if any(not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>9223372036854775807 for value in parts[1:]):
        raise ValueError(USAGE)
    return {'command':parts[0],'ids':[int(value) for value in parts[1:]]}


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action=ACTION)
    return user if (user and work.enabled(conn) and links.authorized(conn,user['id'],'work.read')
                    and switches.enabled('inbound') and switches.enabled('delivery')
                    and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct') else None


def eligible(conn,user,case_id,task_id):
    item=shared.require_work(conn,user,case_id)
    task=work_reads.task(conn,user,case_id,task_id)
    allowed=set(work_tasks.actions(conn,user,item,task)) & {'accept','return'}
    if not allowed:raise ValueError(DENIED)
    if type(task['owner_id']) is not int or task['owner_id']<=0:raise ValueError(DENIED)
    work_tasks._owner(conn,item['id'],task['owner_id'])
    return item,task,allowed


def page(conn,user,before=0):
    # SQL visibility/coordinator filtering precedes the bounded native source scan.
    scope=permissions.RegistryScope(conn,user)
    found=[];cursor=before;scanned=0;continuation=None
    query=f'''SELECT t.id,t.case_id FROM work_task t JOIN work_case wc ON wc.id=t.case_id
            WHERE t.status='for_review' AND wc.status<>'completed'
            AND (wc.lead_id=:registry_actor OR {scope.officer_sql('wc',concerned=False)})
            AND {scope.work_view_sql('wc')} AND (:before=0 OR t.id<:before)
            ORDER BY t.id DESC LIMIT :batch'''
    while scanned<SCAN_LIMIT:
        batch=min(BATCH_SIZE,SCAN_LIMIT-scanned)
        candidates=rows(conn,query,{**scope.params,'before':cursor,'batch':batch})
        if not candidates:break
        for candidate in candidates:
            cursor=candidate['id'];scanned+=1
            try:entry=eligible(conn,user,candidate['case_id'],candidate['id'])
            except ValueError:continue
            found.append(entry)
            if len(found)>PAGE_SIZE:return found,None
        if len(candidates)<batch:break
        if scanned>=SCAN_LIMIT and rows(conn,query,{**scope.params,'before':cursor,'batch':1}):continuation=cursor
    return found,continuation


def line(conn,item,task):
    name=rows(conn,'''SELECT COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u
        LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.id=?''',(task['owner_id'],))[0]['name']
    return ('Task '+str(task['id'])+' · Work '+str(item['id'])+'\n'+common.clip(task['title'],120)
            +'\nWork: '+common.clip(item['title'],100)+'\nOwner: '+common.clip(name,80)+' (account '+str(task['owner_id'])+')'
            +'\nStatus: for review · Due: '+common.clip(task['due_date'] or 'not set',32)+' · Asia/Manila')


def guidance(conn,user,item,task,allowed):
    text='';offered=False
    for mode,label in (('accept','Accept'),('return','Return for changes')):
        if mode in allowed and links.authorized(conn,user['id'],'tasks.'+mode):
            offered=True
            text+='\n'+label+': /task_'+mode+' (private preview and confirmation required)'
    if offered:text='\nUse work '+str(item['id'])+' and task '+str(task['id'])+' in the signed-in review form.'+text
    else:text+='\nTelegram review actions need their separate permissions; review this task in Office Connect.'
    if 'accept' not in allowed:text+='\nAcceptance is blocked by current source rules; review blockers in Office Connect.'
    return text+'\nReview submission: '+links.origin()+'/work/'+str(item['id'])


def render(conn,clean,bot,now):
    if not conn.in_transaction:raise RuntimeError('Review queue requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:return None
    link=found[0]
    context={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
             'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,context,bot)
    if not user:return None
    query=clean['review_query']
    if query=={'error':'usage'}:return USAGE
    if query['command']=='/review_task':
        try:item,task,allowed=eligible(conn,user,*query['ids'])
        except ValueError:return DENIED
        return (line(conn,item,task)+guidance(conn,user,item,task,allowed)
                +'\nBack: /review_queue\nMetadata only. Existing task permissions, blockers and confirmation still apply.')
    entries,continuation=page(conn,user,query['ids'][0] if query['ids'] else 0)
    text='Tasks I can review · newest task first\nMetadata only. Review submission contents in Office Connect.'
    shown=[]
    for item,task,allowed in entries[:PAGE_SIZE]:
        entry=line(conn,item,task)+'\nDetails: /review_task '+str(item['id'])+' '+str(task['id'])
        if common.units(text+'\n\n'+entry)>3000:break
        text+='\n\n'+entry;shown.append(task)
    if not shown:text+='\nNo reviewable tasks found on this page.'
    if shown and len(shown)<len(entries):text+='\nNext page: /review_queue '+str(shown[-1]['id'])
    elif continuation:text+='\nMore permitted source candidates remain. Continue: /review_queue '+str(continuation)
    return text+'\nOpen work: '+links.origin()+'/work\nOnly current eligible reviews are shown; other tasks and counts are not disclosed.'
