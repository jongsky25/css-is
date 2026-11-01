"""Current-account command discovery; no source records, grants or writes cached."""
import os

import auth
import documents
from documents_storage import rows
import supplies
import telegram_calendar as common
import telegram_links as links
import telegram_storage as switches
import travel
import work
import work_compat
import work_tasks

# Scope, group, label, instructions, prerequisites, source availability, webhook-only.
FEATURES=(
 ('calendar.read','Calendar','Calendar lookup','/calendar — next seven days; /calendar YYYY-MM-DD — one day.',(),None,False),
 ('calendar.create','Calendar','Meeting creation','/meeting — guided form, then exact private preview and confirmation.',('calendar.read',),None,False),
 ('rooms.read','Calendar','Room lookup','/room_slots — today’s slots; /my_rooms; /room_status REFERENCE.',(),None,False),
 ('rooms.request','Calendar','Room requests','/room_request — an existing meeting; preview and confirmation; pending approval.',('calendar.read','rooms.read'),None,False),
 ('work.read','Tasks and work','Work lookup','/my_summary; /my_tasks; /my_work; /task_status WORK_ID TASK_ID; /work_status WORK_ID.\nExample: /my_tasks overdue (also upcoming or review).',(),work.enabled,False),
 ('tasks.acknowledge','Tasks and work','Task acknowledgement','/task_ack WORK_ID TASK_ID — preview taking your task into progress.',('work.read',),work.enabled,True),
 ('tasks.submit','Tasks and work','Task submission','/task_submit WORK_ID TASK_ID — prepare output, preview, then confirm review submission.',('work.read',),work.enabled,True),
 ('documents.read','Documents','Document lookup','/documents; /find_documents WORDS; /document_status ID.\nExample: /find_documents budget',(),documents.enabled,True),
 ('supplies.read','Requests','Supplies','/my_supplies; /supply_status ID. Example: /my_supplies needs_action',(),supplies.enabled,True),
 ('travel.read','Requests','Travel','/my_travel; /travel_status ID — deadline, checklist and paper-review status.',(),travel.enabled,True),
 ('meals.read','Requests','Meals','/my_meals; /meal_status ID; /my_room_meals; /room_meal_status ID.',(),None,True),
 ('arrangements.read','Requests','Work arrangements','/my_arrangements; /arrangement_status ID — filing status; open the source for the schedule in force.',(),None,True),
)


def webhook():return os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct'


def user(conn,delivery,bot):
    if (delivery['chat_id']<=0 or delivery['topic_id'] is not None or delivery['registration_id'] is not None):return None
    found=rows(conn,'''SELECT u.id,u.username,u.role FROM telegram_connection c JOIN admin_user u ON u.id=c.account_id
        WHERE c.id=? AND c.generation=? AND c.state='active' AND c.telegram_user_id=? AND c.private_chat_id=?
        AND c.bot_identity=? AND c.bot_fingerprint=? AND u.active=1 AND u.must_change=0''',
        (delivery['connection_id'],delivery['generation'],delivery['chat_id'],delivery['chat_id'],bot[0],bot[2]))
    return found[0] if found and auth.valid_role(found[0]['role']) else None


def availability(conn,delivery,bot):
    actor=user(conn,delivery,bot)
    result=[]
    for scope,group,label,commands,dependencies,module,pull_only in FEATURES:
        if not actor:reason='link or reconnect your own account'
        elif not switches.enabled('inbound') or not switches.enabled('delivery') or not links.available() or len(links.origin() or '')>200:
            reason='private connection or host delivery is paused/not configured; contact your administrator'
        elif module is not None and not module(conn):reason='source module is paused; contact your administrator'
        elif any(not switches.enabled(s.replace('.','_')) for s in (scope,*dependencies)):
            reason='host pilot or a prerequisite is paused; contact your administrator'
        elif pull_only and not webhook():reason='this delivery mode does not support the feature; contact your administrator'
        elif any(not links.authorized(conn,actor['id'],s) for s in (scope,*dependencies)):
            missing=[links.SCOPES[s] for s in (scope,*dependencies) if not links.authorized(conn,actor['id'],s)]
            reason='missing consent: '+', '.join(missing)+'; review permissions and relink to add them'
        else:reason=''
        result.append({'scope':scope,'group':group,'label':label,'commands':commands,'reason':reason})
    return result


def account_link():
    origin=links.origin()
    return '\nManage permissions: '+origin+'/account/telegram' if origin and len(origin)<=200 else '\nOpen your signed-in Telegram account page in Office Connect.'


def render(conn,delivery,bot,now):
    actor=user(conn,delivery,bot)
    if not actor:
        if links.pending_confirmation(conn,delivery['chat_id'],bot,now):
            return 'Office Connect link awaiting confirmation. Send /status in this original private chat to retrieve the final command. Do not send /start again while waiting.'+account_link()
        return ('Office Connect private menu\nLink your own account with /start before using business commands.'
                +account_link()+'\nNever send your Office Connect password here.')
    text='Office Connect · your private menu'
    ready=[f for f in availability(conn,delivery,bot) if not f['reason']]
    for group in ('Calendar','Tasks and work','Documents','Requests'):
        entries=[f for f in ready if f['group']==group]
        if entries:text+='\n\n'+group+'\n'+'\n'.join(f['commands'] for f in entries)
    if not ready:text+='\nNo business commands are enabled and consented for this connection yet.'
    if webhook() and any(f['scope'] in ('calendar.read','work.read','documents.read') for f in ready):
        text+='\n\nSearch\n/find WORDS — search enabled, consented metadata; meetings cover the next 31 days.'
    if webhook() and any(f['scope'] in ('calendar.read','work.read','rooms.read','supplies.read','travel.read','meals.read','arrangements.read') for f in ready):
        text+='\n\nDaily brief\n/brief — your calendar, task summary and request statuses; selected, permitted sections only.'
    return (text+'\n\nAccount\n/status — availability and missing permissions. /menu or /help — this menu.'
            +'\n/disconnect — revoke this connection.'+account_link()
            +'\nUse IDs/references shown in your own results. Current record permissions and workflow rules still apply.'
            +'\nMissing a feature? Use /status. Relinking does not enable a paused host pilot.')


def status(conn,delivery,bot,now):
    actor=user(conn,delivery,bot)
    if not actor:return 'Office Connect Telegram connection: not linked or needs reconnection. Use /start to link your own account.'+account_link()
    features=availability(conn,delivery,bot)
    ready=[f['label'] for f in features if not f['reason']]
    blocked=[f['label']+': '+f['reason'] for f in features if f['reason']]
    text='Office Connect Telegram connection: active.\nAvailable for you: '+(', '.join(ready) or 'no business features yet')
    if blocked:text+='\n\nOther features\n'+'\n'.join(blocked)
    return text+'\n\nUse /menu for your available commands.'+account_link()+'\nRelink only to add explicit consent; no record access is granted automatically.'


def task_next(conn,actor,item,task, *, detail=False):
    text=('' if detail else '\nDetails: /task_status '+str(task['case_id'])+' '+str(task['id']))+'\nBack: /my_tasks'
    if not webhook() or not switches.enabled('inbound') or not switches.enabled('delivery') or not work.enabled(conn):return text
    try:work_compat.require_open(conn,item['id'])
    except ValueError:return text
    allowed=work_tasks.actions(conn,actor,item,task)
    for action,command in (('acknowledge','/task_ack'),('submit','/task_submit')):
        if task['owner_id']==actor['id'] and action in allowed and links.authorized(conn,actor['id'],'work.read') and links.authorized(conn,actor['id'],'tasks.'+action):
            text+='\nNext: '+command+' '+str(task['case_id'])+' '+str(task['id'])+' (preview and confirmation required)'
    return text
