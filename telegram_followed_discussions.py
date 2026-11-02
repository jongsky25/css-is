"""Private own saved discussion follows; metadata only and no preference writes."""
import os
import re

import documents_permissions as permissions
from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import work
import work_discussion as discussion

ACTION='work.follows.read'
COMMANDS=('/my_follows',)
FILTERS=('all','work','tasks')
USAGE='Use /my_follows [all|work|tasks] [BEFORE_WORK_ID:BEFORE_TASK_ID]. Use task 0 for a work-wide cursor. Saved follows only; lookup changes nothing.'
PAGE_SIZE=5
SCAN_LIMIT=200
BATCH_SIZE=50


def parse(text):
    parts=text.split();category='all';before=(0,0)
    if not parts or parts[0] not in COMMANDS or len(parts)>3:raise ValueError(USAGE)
    rest=parts[1:]
    if rest and rest[0] in FILTERS:category=rest.pop(0)
    if len(rest)>1:raise ValueError(USAGE)
    if rest:
        if not re.fullmatch('[1-9][0-9]{0,18}:(0|[1-9][0-9]{0,18})',rest[0]):raise ValueError(USAGE)
        before=tuple(map(int,rest[0].split(':')))
        if any(value>9223372036854775807 for value in before):raise ValueError(USAGE)
    return {'category':category,'before':before}


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action=ACTION)
    return user if (user and work.enabled(conn) and links.authorized(conn,user['id'],'work.read')
                    and switches.enabled('inbound') and switches.enabled('delivery')
                    and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct') else None


def detail(conn,user,case_id,task_id):
    found=rows(conn,'''SELECT case_id,task_id FROM work_follow
        WHERE user_id=? AND case_id=? AND task_id IS ?''',(user['id'],case_id,task_id))
    if not found:raise ValueError('Discussion follow unavailable.')
    _,item,task=discussion.scope(conn,user,case_id,task_id)
    wide=bool(conn.execute('SELECT 1 FROM work_follow WHERE user_id=? AND case_id=? AND task_id IS NULL',
                          (user['id'],case_id)).fetchone())
    return found[0],item,task,wide


def key(entry):return entry[0]['case_id'],entry[0]['task_id'] or 0


def page(conn,user,category,before):
    scope=permissions.RegistryScope(conn,user);cursor=before;scanned=0;found=[];continuation=None
    query=f'''SELECT f.case_id,f.task_id FROM work_follow f JOIN work_case wc ON wc.id=f.case_id
        WHERE f.user_id=:registry_actor
        AND (:category='all' OR (:category='work' AND f.task_id IS NULL) OR (:category='tasks' AND f.task_id IS NOT NULL))
        AND (:case_id=0 OR (f.case_id,COALESCE(f.task_id,0))<(:case_id,:task_id))
        AND (f.task_id IS NULL OR EXISTS(SELECT 1 FROM work_task t WHERE t.id=f.task_id AND t.case_id=f.case_id))
        AND {scope.work_view_sql('wc')}
        ORDER BY f.case_id DESC,COALESCE(f.task_id,0) DESC LIMIT :batch'''
    def parameters(batch):return {**scope.params,'category':category,'case_id':cursor[0],'task_id':cursor[1],'batch':batch}
    while scanned<SCAN_LIMIT:
        batch=min(BATCH_SIZE,SCAN_LIMIT-scanned);candidates=rows(conn,query,parameters(batch))
        if not candidates:break
        for candidate in candidates:
            cursor=(candidate['case_id'],candidate['task_id'] or 0);scanned+=1
            try:entry=detail(conn,user,candidate['case_id'],candidate['task_id'])
            except ValueError:continue
            found.append(entry)
            if len(found)>PAGE_SIZE:return found,None
        if len(candidates)<batch:break
        if scanned>=SCAN_LIMIT and rows(conn,query,parameters(1)):continuation=cursor
    return found,continuation


def line(entry,controls):
    follow,item,task,wide=entry
    source=links.origin()+'/work/'+str(item['id'])+'/discussion'
    if task:source+='?task_id='+str(task['id'])
    text=('Work '+str(item['id'])+' · '+common.clip(item['title'],110)
          +('\nTask '+str(task['id'])+' · '+common.clip(task['title'],110)
            +'\nTask-specific follow · Work-wide also '+('on' if wide else 'off') if task
            else '\nWork-wide follow · Covers work-level and all task discussions.')
          +'\nOpen discussion: '+source)
    if controls:
        text+='\nFollow controls: '+links.origin()+'/account/telegram/discussion-follow/change?case_id='+str(item['id'])
        if task:text+='&task_id='+str(task['id'])
    return text


def render(conn,clean,bot,now):
    if not conn.in_transaction:raise RuntimeError('Followed discussions require the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:return None
    link=found[0];context={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
                         'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,context,bot)
    if not user:return None
    query=clean['follows_query']
    if query=={'error':'usage'}:return USAGE
    entries,continuation=page(conn,user,query['category'],query['before'])
    controls=links.authorized(conn,user['id'],'work.follow')
    text='My followed discussions · '+query['category']+'\nSaved follows, ordered by work/task ID descending. Lookup changes nothing.'
    shown=[]
    for entry in entries[:PAGE_SIZE]:
        block=line(entry,controls)
        if common.units(text+'\n\n'+block)>3000:break
        text+='\n\n'+block;shown.append(entry)
    if not shown:text+='\nNo visible saved follows on this page.'
    cursor=key(shown[-1]) if shown and len(shown)<len(entries) else continuation
    if cursor:text+='\n'+('Next page: ' if shown else 'More source candidates remain. Continue: ')+'/my_follows '+query['category']+' '+str(cursor[0])+':'+str(cursor[1])
    text+='\nFilters: /my_follows work · /my_follows tasks\nWork-wide follows cover task discussions without adding task rows here. No other followers or hidden counts are shown.'
    if controls:text+='\nTo use follow controls, first send /discussion_follow. Links prefill source IDs only; changes still need a private preview and confirmation.'
    return text
