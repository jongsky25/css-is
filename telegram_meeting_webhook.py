"""Private meeting/room actions using one-time incoming-webhook replies."""
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_links as links
import telegram_meetings as meetings
import telegram_storage as switches
import telegram_transport as transport

COMMANDS=('/meeting','/room_request','/meeting_preview','/room_preview',
          '/meeting_confirm','/room_confirm','/meeting_receipt','/room_receipt')
ACTION={command:('calendar.create' if command.startswith('/meeting') else 'rooms.request') for command in COMMANDS}
for action,meta in meetings.META.items():
    ACTION.update({command:action for command in (meta['start'],meta['confirm'],meta['receipt'],'/'+meta['prefix']+'_preview')})
COMMANDS=tuple(ACTION)
STARTS=tuple(meta['start'] for meta in meetings.META.values())


def accepts(conn,clean):
    """Group-origin confirmations keep the existing asynchronous membership path."""
    if clean['chat_id']<=0 or clean['command'] not in COMMANDS:return False
    command=clean['command']
    if command in STARTS:return True
    key='token_hash' if command.endswith('_confirm') else 'operation_id'
    table='telegram_preview' if key=='token_hash' else 'telegram_operation'
    found=rows(conn,'SELECT * FROM '+table+' WHERE '+key+'=? AND action=?',
               (clean.get('meeting_argument'),ACTION[command]))
    if not found:return True
    try:
        ctx=meetings.original_context(conn,found[0]) if key=='token_hash' else json.loads(found[0]['context_json'] or '{}')
        return ctx.get('chat_id',0)>=0
    except (ValueError,TypeError):return True


def handle(conn,clean,bot,now):
    # Any late domain/expiry/receipt error must roll back its business mutation
    # before intake records a neutral one-time reply.
    conn.execute('SAVEPOINT private_meeting_webhook')
    try:
        connection=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
        if not connection:raise actions.Unavailable('Action unavailable.')
        connection=connection[0];command=clean['command'];action=ACTION[command]
        ctx={'connection_id':connection['id'],'generation':connection['generation'],'sender_id':clean['sender_id'],
             'chat_id':clean['chat_id'],'topic_id':None,'registration_id':None,'registration_generation':None}
        user,_,_=actions.authority(conn,ctx,action)
        if command in STARTS:
            identifier=meetings.observe(conn,clean,connection,bot,now,action)
            kind=meetings.META[action]['prefix']+'_guide'
        else:
            if command.endswith('_confirm'):
                found=rows(conn,'SELECT * FROM telegram_preview WHERE token_hash=? AND action=?',
                           (clean['meeting_argument'],action))
                if not found:raise actions.Unavailable('Confirmation unavailable.')
                result=actions.confirm_digest(conn,ctx,clean['meeting_argument'],now,commit=False)
                identifier=result['operation_id'];kind=meetings.META[action]['prefix']+'_receipt'
            else:
                identifier=clean['meeting_argument']
                # Recovery verifies actor/connection/context, including pending previews.
                actions.recover(conn,ctx,action,identifier,commit=False)
                kind=meetings.META[action]['prefix']+('_preview' if command.endswith('_preview') else '_receipt')
        delivery={'connection_id':ctx['connection_id'],'generation':ctx['generation'],'chat_id':ctx['chat_id'],
                  'topic_id':None,'registration_id':None}
        projection={'kind':kind,'id':identifier,'bot':bot[0],'fingerprint':bot[2]}
        text=meetings.render(conn,delivery,projection,now,commit=False)
        if (not text or transport.config()!=bot or not switches.enabled('inbound') or not switches.enabled('delivery')
                or not links.available()):raise actions.Unavailable('Reply unavailable.')
        actions.authority(conn,ctx,action)
        if kind.endswith('_receipt'):
            text+='\nRecover: '+meetings.META[action]['receipt']+' '+identifier+'\nMore options: /menu'
    except ValueError:
        conn.execute('ROLLBACK TO private_meeting_webhook')
        label={'tasks.create':'Task proposal','tasks.deadline':'Task deadline'}.get(ACTION.get(clean['command']),'Meeting or room')
        text=label+' action unavailable, expired or changed. Review Office Connect and your current permissions. Use the original operation receipt command to recover a confirmed result; otherwise prepare a fresh preview.'
    finally:
        conn.execute('RELEASE private_meeting_webhook')
    return text
