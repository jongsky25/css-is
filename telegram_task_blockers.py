"""Private blocker flags and permitted prerequisite/follow-up metadata; no resolution writes."""
import os
import re

from documents_storage import rows
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import work
import work_blockers
import work_decisions
import work_reads
import work_updates

ACTION='tasks.blockers.read'
COMMANDS=('/task_blockers',)
USAGE='Use /task_blockers WORK_ID TASK_ID [BEFORE_ID]. Blocker/prerequisite metadata only; resolve issues in Office Connect.'
DENIED='Task blocker information unavailable to this account.'
PAGE_SIZE=5


def parse(text):
    parts=text.split()
    if not parts or parts[0] not in COMMANDS or len(parts) not in (3,4):raise ValueError(USAGE)
    if any(not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>9223372036854775807 for value in parts[1:]):raise ValueError(USAGE)
    return {'ids':[int(value) for value in parts[1:]]}


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action=ACTION)
    return user if (user and work.enabled(conn) and links.authorized(conn,user['id'],'work.read')
                    and switches.enabled('inbound') and switches.enabled('delivery')
                    and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct') else None


def followup(conn,item,task):
    if not task['blocker_reason']:return 'Follow-up: no recorded blocker'
    identifier=task['blocker_owner_id']
    if identifier and work_updates.permitted(conn,identifier,item['id']):
        owner=rows(conn,'''SELECT COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u
            LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.id=? AND u.active=1''',(identifier,))
        label=common.clip(owner[0]['name'],80)+' (account '+str(identifier)+')' if owner else 'unavailable account'
    else:label='unavailable account; ask the lead/officer in Office Connect'
    return 'Follow-up owner: '+label+'\nFollow-up due: '+common.clip(task['blocker_due_date'] or 'not set',32)+' · Asia/Manila'


def render(conn,clean,bot,now):
    if not conn.in_transaction:raise RuntimeError('Task blocker lookup requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:return None
    link=found[0]
    context={'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
             'topic_id':clean['topic_id'],'registration_id':None}
    user=actor(conn,context,bot)
    if not user:return None
    query=clean['blocker_query']
    if query=={'error':'usage'}:return USAGE
    case_id,task_id,*cursor=query['ids']
    try:
        item=work.get(conn,user,case_id)
        task=work_reads.task(conn,user,case_id,task_id)
    except ValueError:return DENIED
    # Native dependency writes require the same case. Refuse inconsistent edges
    # rather than project a foreign or missing source through the permitted task.
    if conn.execute('''SELECT 1 FROM work_dependency d LEFT JOIN work_task p ON p.id=d.prerequisite_id
        WHERE d.task_id=? AND (p.id IS NULL OR p.case_id<>?) LIMIT 1''',(task_id,case_id)).fetchone():return DENIED
    recorded=bool(task['blocker_reason']);direction=bool(work_decisions.pending(conn,task_id))
    waiting=work_blockers.waiting(conn,task)
    text=('Task blockers · Work '+str(case_id)+' · Task '+str(task_id)+'\n'+common.clip(task['title'],120)
          +'\nWork: '+common.clip(item['title'],100)+'\nTask state: '+task['status'].replace('_',' ')
          +'\nNative blocker check: '+('waiting' if waiting else 'clear')
          +'\nRecorded blocker: '+('yes' if recorded else 'no')
          +'\nUnresolved changed-decision review: '+('yes' if direction else 'no')+'\n'+followup(conn,item,task))
    if item['status']=='completed' or task['status'] in ('done','cancelled'):
        text+='\nHistorical state: task/work lifecycle rules also apply; this lookup enables no action.'
    text+='\n\nUnfinished prerequisite tasks (newest ID first)'
    records=rows(conn,'''SELECT p.id,p.title,p.status,p.due_date FROM work_dependency d JOIN work_task p ON p.id=d.prerequisite_id
        WHERE d.task_id=? AND p.case_id=? AND p.status<>'done' AND (?=0 OR p.id<?)
        ORDER BY p.id DESC LIMIT ?''',(task_id,case_id,cursor[0] if cursor else 0,cursor[0] if cursor else 0,PAGE_SIZE+1))
    shown=[]
    for row in records[:PAGE_SIZE]:
        entry=('Task '+str(row['id'])+' · '+common.clip(row['title'],120)+'\nState: '+row['status'].replace('_',' ')
               +' · Due: '+common.clip(row['due_date'] or 'not set',32)
               +'\n'+links.origin()+'/work/'+str(case_id)+'#task-'+str(row['id']))
        if common.units(text+'\n\n'+entry)>3000:break
        text+='\n\n'+entry;shown.append(row)
    if not records:text+='\nNo unfinished prerequisites on this page.'
    if shown and len(shown)<len(records):text+='\nNext page: /task_blockers '+str(case_id)+' '+str(task_id)+' '+str(shown[-1]['id'])
    return (text+'\n\nOnly Done satisfies a prerequisite; Cancelled remains waiting until explicitly addressed in Office Connect.'
            +'\nOther task permissions/state/review rules still apply even when the blocker check is clear.'
            +'\nResolve in Office Connect: '+links.origin()+'/work/'+str(case_id)+'#task-'+str(task_id)
            +'\nMetadata only. No blocker reasons, decision notes or submissions are shown; no task or dependency was changed.')
