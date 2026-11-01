"""Private task previews, explicit confirmation and durable action receipts."""
import json
import re
import unicodedata

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_menu as menu
import telegram_storage as switches
import telegram_transport as transport
import telegram_work as reads
import work
import work_reads
import work_tasks
import work_compat

COMMANDS = ('/task_ack', '/task_submit', '/task_preview', '/task_confirm', '/task_receipt')
USAGE = ('Use /task_ack WORK_ID TASK_ID or /task_submit WORK_ID TASK_ID. '
         'Review the exact preview, then send its /task_confirm command. No change happens before confirmation.')
PATH = '/account/telegram/task'


def parse(text):
    parts = text.split()
    if parts and parts[0] in COMMANDS[:2] and len(parts) == 3:
        query = reads.parse('/task_status ' + ' '.join(parts[1:]))
        return {'command': parts[0], 'ids': query['ids']}
    if parts and parts[0] in COMMANDS[2:] and len(parts) == 2:
        pattern = '[A-Za-z0-9_-]{43}' if parts[0] == '/task_confirm' else '[a-f0-9]{32}'
        if re.fullmatch(pattern, parts[1]):
            return {'command': parts[0], 'argument': actions.digest(parts[1]) if parts[0] == '/task_confirm' else parts[1]}
    raise ValueError(USAGE)


def context(conn, connection):
    return {'connection_id': connection['id'], 'generation': connection['generation'],
            'sender_id': connection['telegram_user_id'], 'chat_id': connection['private_chat_id'],
            'topic_id': None, 'registration_id': None, 'registration_generation': None}


class Adapter:
    def __init__(self, action):
        self.action = action

    def prepare(self, conn, user, fields):
        if not work.enabled(conn) or set(fields) != {'case_id','task_id','reason','submission'}:
            raise actions.Unavailable('Task action unavailable.')
        if any(type(fields[k]) is not int or fields[k] <= 0 for k in ('case_id','task_id')):
            raise actions.Unavailable('Task action unavailable.')
        work.writable(conn)
        item = work.get(conn, user, fields['case_id'])
        task = work_reads.task(conn, user, item['id'], fields['task_id'])
        work_compat.require_open(conn, item['id'])
        if task['owner_id'] != user['id'] or self.action not in work_tasks.actions(conn, user, item, task):
            raise actions.Unavailable('This task action is unavailable to this account or workflow state.')
        clean = {**fields, 'reason': work._text(fields['reason'], 'Reason or progress note', 500),
                 'submission': work._text(fields['submission'], 'Output or evidence', 1800) if self.action == 'submit' else ''}
        for key in ('reason','submission'):
            clean[key] = ''.join(ch if ch=='\n' or not unicodedata.category(ch).startswith('C') else ' ' for ch in clean[key])
        summary = {'action': self.action, 'case_id': item['id'], 'task_id': task['id'],
                   'title': common.clip(task['title'],160), 'status': task['status'],
                   'next_status': 'for_review' if self.action == 'submit' else 'in_progress',
                   'reason': clean['reason'], 'submission': clean['submission']}
        if common.units(summary['title']+summary['reason']+summary['submission'])>2600:
            raise actions.Unavailable('The private preview is too long. Shorten the output or note.')
        return clean, summary, {'revision':task['revision'], 'case_revision':item['revision']}

    def revalidate(self, conn, user, clean, expected):
        fresh, _, revision = self.prepare(conn, user, clean)
        if fresh != clean or revision != expected:
            raise actions.Unavailable('The task or work item changed. Prepare a new preview.')

    def apply(self, conn, user, clean, operation_id):
        task = work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        work_tasks.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],self.action,
                                        {'reason':clean['reason'],'submission':clean['submission']})
        return {'state':'committed','result_code':'task_submitted' if self.action=='submit' else 'task_acknowledged'}

    def queue_preview(self, conn, user, operation_id, ctx, now):
        # Store source routing only. No rendered preview or submission in deliveries.
        preview = rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean = json.loads(preview['fields_json'])
        conn.execute('UPDATE telegram_operation SET target_id=?,context_json=? WHERE operation_id=?',
                     (clean['task_id'], actions.packed({'case_id':clean['case_id'],'task_id':clean['task_id']}), operation_id))

    def check_receipt(self, conn, user, operation):
        if not work.enabled(conn):
            raise actions.Unavailable('Task receipt unavailable.')
        try:
            target = json.loads(operation['context_json'])
            task = work_reads.task(conn,user,target['case_id'],target['task_id'])
        except (ValueError,TypeError,KeyError):
            raise actions.Unavailable('Task receipt unavailable.') from None
        if task['owner_id'] != user['id']:
            raise actions.Unavailable('Task receipt unavailable.')


for action in ('acknowledge','submit'):
    actions.ADAPTERS['tasks.'+action] = Adapter(action)


def preview_text(conn, ctx, operation_id, now):
    found = rows(conn,'SELECT * FROM telegram_preview WHERE operation_id=?',(operation_id,))
    if not found or not found[0]['action'].startswith('tasks.'):
        raise actions.Unavailable('Task preview unavailable.')
    p = found[0]
    user, adapter, bot = actions.authority(conn,ctx,p['action'])
    if (any(p[k] != ctx[k] for k in ('connection_id','generation','chat_id','topic_id','registration_id','registration_generation'))
            or p['actor_id']!=user['id'] or p['bot_identity']!=bot[0] or p['bot_fingerprint']!=bot[2]
            or p['state']!='pending' or p['expires_at']<=links.stamp(now)):
        raise actions.Unavailable('Task preview expired or unavailable.')
    adapter.revalidate(conn,user,json.loads(p['fields_json']),json.loads(p['expected_json']))
    summary=json.loads(p['summary_json'])
    token=actions.derive_token(operation_id,p['token_nonce'])
    if actions.digest(token)!=p['token_hash']:
        raise actions.Unavailable('Task preview unavailable.')
    text = ('Task '+str(summary['task_id'])+' · Work '+str(summary['case_id'])+'\n'+summary['title']
            +'\nAction: '+summary['action']+'\nStatus: '+summary['status']+' → '+summary['next_status']
            +'\nNote: '+summary['reason'])
    if summary['submission']:
        text += '\nSubmit this output for review:\n'+summary['submission']
    return (text+'\nExpires: '+p['expires_at']+' (UTC)\nConfirm exactly this preview:\n/task_confirm '+token
            +'\nOperation: '+operation_id+'\nRecover: /task_receipt '+operation_id)


def receipt_text(conn, ctx, operation_id):
    found=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=?',(operation_id,))
    if not found or found[0]['action'] not in ('tasks.acknowledge','tasks.submit'):
        raise actions.Unavailable('Task receipt unavailable.')
    op=found[0]
    receipt=actions.recover(conn,ctx,op['action'],operation_id,commit=False)
    target=json.loads(op['context_json'])
    user=actions.authority(conn,ctx,op['action'])[0]
    task=work_reads.task(conn,user,target['case_id'],target['task_id'])
    return ('Task operation '+operation_id+'\nRecorded outcome: '+receipt['state']+' · '+str(receipt['result_code'] or 'awaiting confirmation')
            +'\nCurrent status: '+work_reads.task(conn,actions.authority(conn,ctx,op['action'])[0],target['case_id'],target['task_id'])['status']
            +menu.task_next(conn,user,work.get(conn,user,target['case_id']),task)
            +'\n'+links.origin()+'/work/'+str(target['case_id']))


def handle(conn, clean, bot, now):
    """Called under intake's writer lock; rollback partial action failures locally."""
    conn.execute('SAVEPOINT telegram_task_action')
    try:
        connection=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
        if not connection or not links.available():
            raise actions.Unavailable('Task action unavailable.')
        ctx=context(conn,connection[0])
        if not reads.actor(conn,{'connection_id':ctx['connection_id'],'generation':ctx['generation'],
                               'chat_id':ctx['chat_id'],'topic_id':None,'registration_id':None},bot):
            raise actions.Unavailable('Task action unavailable.')
        query=clean['task_query']
        if query=={'error':'usage'}:
            raise actions.Unavailable(USAGE)
        command=query['command']
        if command in COMMANDS[:2]:
            action='tasks.acknowledge' if command=='/task_ack' else 'tasks.submit'
            user, adapter, _=actions.authority(conn,ctx,action)
            item=work.get(conn,user,query['ids'][0]);task=work_reads.task(conn,user,item['id'],query['ids'][1])
            if task['owner_id']!=user['id']:
                raise actions.Unavailable('Task action unavailable.')
            if command=='/task_submit':
                text='Prepare your output in the signed-in form, then retrieve and confirm its private preview:\n'+links.origin()+PATH+'?case_id='+str(item['id'])+'&task_id='+str(task['id'])
            else:
                result=actions.issue(conn,ctx,action,'telegram-task-'+str(bot[0])+'-'+str(clean['update_id']),
                    {'case_id':item['id'],'task_id':task['id'],'reason':'Acknowledged through private Telegram confirmation.','submission':''},now,commit=False)
                text=preview_text(conn,ctx,result['operation_id'],now) if result.get('preview') else receipt_text(conn,ctx,result['operation_id'])
        elif command=='/task_preview':
            text=preview_text(conn,ctx,query['argument'],now)
        elif command=='/task_confirm':
            p=rows(conn,'SELECT action FROM telegram_preview WHERE token_hash=?',(query['argument'],))
            if not p or p[0]['action'] not in ('tasks.acknowledge','tasks.submit'):
                raise actions.Unavailable('Task confirmation unavailable.')
            result=actions.confirm_digest(conn,ctx,query['argument'],now,commit=False)
            text=receipt_text(conn,ctx,result['operation_id'])
        else:
            text=receipt_text(conn,ctx,query['argument'])
        if transport.config()!=bot or not switches.enabled('delivery') or not switches.enabled('inbound'):
            raise actions.Unavailable('Task delivery paused.')
    except ValueError:
        conn.execute('ROLLBACK TO telegram_task_action')
        text='Task action unavailable or changed. Check your task, permissions and current preview in Office Connect. '+USAGE
    finally:
        conn.execute('RELEASE telegram_task_action')
    return text
