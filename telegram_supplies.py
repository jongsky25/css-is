"""Private owner-only supply-request metadata and collection status."""
import re

from documents_storage import rows
import supplies
import supplies_dashboard as dashboard
import telegram_calendar as common
import telegram_links as links

COMMANDS=('/my_supplies','/supply_status')
FILTERS=('all','active','needs_action','completed')
USAGE='Use /my_supplies [all|active|needs_action|completed] [PAGE] or /supply_status REQUEST_ID. Read only.'


def number(value,maximum):
    if not re.fullmatch('[1-9][0-9]{0,9}',value) or int(value)>maximum:
        raise ValueError(USAGE)
    return int(value)


def parse(text):
    parts=text.split()
    if not parts or parts[0] not in COMMANDS:
        raise ValueError(USAGE)
    if parts[0]=='/supply_status' and len(parts)==2:
        return {'command':parts[0],'id':number(parts[1],2147483647)}
    if parts[0]=='/my_supplies':
        args=parts[1:];filter_='all'
        if args and args[0] in FILTERS:
            filter_,args=args[0],args[1:]
        if len(args)<=1:
            return {'command':parts[0],'filter':filter_,'page':number(args[0],10000) if args else 1}
    raise ValueError(USAGE)


def actor(conn,delivery,bot):
    user=common.actor(conn,delivery,bot,action='supplies.read')
    return user if user and supplies.enabled(conn) else None


def line(record,stage,detail=False):
    # Requester stage is the source UI policy. Its submitted sentence can name
    # approvers, so use a fixed sentence in that one state.
    sentence='Awaiting approval in Office Connect.' if record['approval_status']=='submitted' else stage['sentence']
    return ('Request '+str(record['id'])+' · '+common.clip(record['control_number'] or 'Draft (no control number)',40)
            +'\nApproval: '+common.clip(record['approval_status'],30).replace('_',' ')
            +'\nCollection: '+common.clip(stage['label'],60)+'\n'+common.clip(sentence,220)
            +'\nNeeded: '+common.clip(record['date_needed'] or 'not set',32)
            +('\nBack: /my_supplies' if detail else '\nDetails: /supply_status '+str(record['id']))
            +'\n'+links.origin()+'/supplies/requests/'+str(record['id']))


def render(conn,clean,bot,now):
    if not conn.in_transaction:
        raise RuntimeError('Supply lookup requires the intake transaction')
    found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
    if not found:
        return None
    link=found[0]
    user=actor(conn,{'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
                     'topic_id':clean['topic_id'],'registration_id':None},bot)
    if not user:
        return None
    query=clean['supply_query']
    if query=={'error':'usage'}:
        return USAGE
    if query['command']=='/supply_status':
        records=rows(conn,'''SELECT id,control_number,approval_status,date_needed FROM supply_request
            WHERE id=? AND requester_id=?''',(query['id'],user['id']))
        if not records:
            return 'Supply request unavailable to this account.'
        stage=dashboard.request_stage(conn,user,query['id'])
        if not stage:
            return 'Supply request unavailable to this account.'
        return line(records[0],stage,detail=True)+'\nRead only: approval, handover and receipt confirmation remain in Office Connect.'
    result=dashboard.queue(conn,user,'requests',page=query['page'],limit=5,
                           state='' if query['filter']=='all' else query['filter'])
    text='My supply requests · '+query['filter']+' · Page '+str(query['page'])
    for record in result['requests']:
        text+='\n\n'+line(record,record['stage'])
    if not result['requests']:
        text+='\nNo requests on this page.'
    if result['has_next']:
        text+= ('\nNext page: /my_supplies '+query['filter']+' '+str(query['page']+1)
                if query['page']<10000 else '\nUse a narrower filter or open Office Connect for more requests.')
    return text+'\n\nOpen my requests: '+links.origin()+'/supplies/requests'
