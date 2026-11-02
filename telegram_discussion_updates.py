"""Private own-notice metadata inbox; never projects discussion text or marks it read."""
import os
import re

import documents_permissions as permissions
from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import work

ACTION='work.updates.read'
COMMANDS=('/my_updates','/update_status')
FILTERS={'all':None,'mentions':'mention','replies':'reply','following':'following'}
USAGE='Use /my_updates [all|mentions|replies|following] [BEFORE_ID] or /update_status NOTICE_ID. Metadata only; read discussion in Office Connect.'
DENIED='Discussion update unavailable to this account. Open Office Connect to check current source access.'
PAGE_SIZE=5
SCAN_LIMIT=200
BATCH_SIZE=50


def number(value):
    if not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>9223372036854775807:raise ValueError(USAGE)
    return int(value)


def parse(text):
    parts=text.split()
    if not parts or parts[0] not in COMMANDS:raise ValueError(USAGE)
    if parts[0]=='/update_status':
        if len(parts)!=2:raise ValueError(USAGE)
        return {'command':parts[0],'id':number(parts[1])}
    if len(parts)>3:raise ValueError(USAGE)
    category='all';before=0
    if len(parts)>1:
        if parts[1] in FILTERS:
            category=parts[1]
            if len(parts)==3:before=number(parts[2])
        elif len(parts)==2:before=number(parts[1])
        else:raise ValueError(USAGE)
    return {'command':parts[0],'category':category,'before':before}


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action=ACTION)
    return user if (user and work.enabled(conn) and links.authorized(conn,user['id'],'work.read')
                    and switches.enabled('inbound') and switches.enabled('delivery')
                    and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct') else None


SELECT='''SELECT n.id,n.comment_id,n.user_id,n.revision,n.reason,n.created_at,
    c.case_id,c.task_id,COALESCE(r.revision,0) AS read_revision,
    (SELECT MAX(v.revision) FROM work_comment_revision v WHERE v.comment_id=c.id) AS current_revision
    FROM work_notice n JOIN work_comment c ON c.id=n.comment_id
    LEFT JOIN work_comment_read r ON r.comment_id=n.comment_id AND r.user_id=n.user_id'''


def detail(conn,user,identifier):
    found=rows(conn,SELECT+' WHERE n.id=? AND n.user_id=?',(identifier,user['id']))
    if not found or found[0]['reason'] not in ('mention','reply','following') or found[0]['current_revision'] is None:raise ValueError(DENIED)
    notice=found[0];item=work.get(conn,user,notice['case_id'])
    task=None
    if notice['task_id'] is not None:
        selected=rows(conn,'SELECT id,title FROM work_task WHERE id=? AND case_id=?',(notice['task_id'],item['id']))
        if not selected:raise ValueError(DENIED)
        task=selected[0]
    return notice,item,task


def page(conn,user,category,before):
    # Own recipient and source visibility are filtered before the bounded current-source scan.
    scope=permissions.RegistryScope(conn,user);cursor=before;scanned=0;found=[];continuation=None
    query=f'''SELECT n.id FROM work_notice n JOIN work_comment c ON c.id=n.comment_id
        JOIN work_case wc ON wc.id=c.case_id
        LEFT JOIN work_comment_read r ON r.comment_id=n.comment_id AND r.user_id=n.user_id
        WHERE n.user_id=:registry_actor AND COALESCE(r.revision,0)<n.revision
        AND n.reason IN ('mention','reply','following') AND (:reason IS NULL OR n.reason=:reason)
        AND (:before=0 OR n.id<:before) AND {scope.work_view_sql('wc')}
        ORDER BY n.id DESC LIMIT :batch'''
    while scanned<SCAN_LIMIT:
        batch=min(BATCH_SIZE,SCAN_LIMIT-scanned)
        candidates=rows(conn,query,{**scope.params,'reason':FILTERS[category],'before':cursor,'batch':batch})
        if not candidates:break
        for candidate in candidates:
            cursor=candidate['id'];scanned+=1
            try:entry=detail(conn,user,cursor)
            except ValueError:continue
            if entry[0]['read_revision']>=entry[0]['revision']:continue
            found.append(entry)
            if len(found)>PAGE_SIZE:return found,None
        if len(candidates)<batch:break
        if scanned>=SCAN_LIMIT and rows(conn,query,{**scope.params,'reason':FILTERS[category],'before':cursor,'batch':1}):continuation=cursor
    return found,continuation


def line(entry):
    notice,item,task=entry
    return ('Update '+str(notice['id'])+' · '+{'mention':'Mention','reply':'Reply','following':'Following'}[notice['reason']]
            +'\nWork '+str(item['id'])+' · '+common.clip(item['title'],110)
            +('\nTask '+str(task['id'])+' · '+common.clip(task['title'],110) if task else '\nWork-level discussion')
            +'\nComment '+str(notice['comment_id'])+' · Notice revision '+str(notice['revision'])+' · Current revision '+str(notice['current_revision'])
            +'\nStatus: '+('unread' if notice['read_revision']<notice['revision'] else 'already read')
            +' · '+common.clip(notice['created_at'],32))


def source(entry):
    notice,item,task=entry
    return (links.origin()+'/work/'+str(item['id'])+'/discussion?focus='+str(notice['comment_id'])
            +('&task_id='+str(task['id']) if task else '')+'#message-'+str(notice['comment_id']))


def render(conn,clean,bot,now):
    if not conn.in_transaction:raise RuntimeError('Discussion inbox requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:return None
    link=found[0];context={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
                         'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,context,bot)
    if not user:return None
    query=clean['updates_query']
    if query=={'error':'usage'}:return USAGE
    if query['command']=='/update_status':
        try:entry=detail(conn,user,query['id'])
        except ValueError:return DENIED
        return (line(entry)+'\nOpen discussion: '+source(entry)
                +'\nBack: /my_updates\nMetadata only. Read discussion and manage read status in Office Connect; this lookup marks nothing read.')
    entries,continuation=page(conn,user,query['category'],query['before'])
    text='My unread discussion updates · '+query['category']+' · newest notice first\nMetadata only; lookup does not mark messages read.'
    shown=[]
    for entry in entries[:PAGE_SIZE]:
        block=line(entry)+'\nDetails: /update_status '+str(entry[0]['id'])+'\n'+source(entry)
        if common.units(text+'\n\n'+block)>3000:break
        text+='\n\n'+block;shown.append(entry[0])
    if not shown:text+='\nNo unread updates found on this page.'
    if shown and len(shown)<len(entries):text+='\nNext page: /my_updates '+query['category']+' '+str(shown[-1]['id'])
    elif continuation:text+='\nMore source candidates remain. Continue: /my_updates '+query['category']+' '+str(continuation)
    return text+'\nFilters: /my_updates mentions · /my_updates replies · /my_updates following\nDiscussion text and read-state changes stay in Office Connect; other recipients and counts are not disclosed.'
