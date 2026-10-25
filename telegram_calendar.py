"""Private, delegated calendar lookup. Queue metadata only; render current permitted data."""
import base64
from datetime import date, timedelta
import hashlib
import hmac
import json
import re
import unicodedata
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import auth
from documents_storage import rows, transaction
import office_calendar as calendar
from request_security import safe_local_return
import telegram_links as links

ZONE = ZoneInfo('Asia/Manila')
LAYERS = ('entries', 'holidays', 'rooms')
MAX_DAYS = 31
MAX_ITEMS = 2000
PAGE_SIZE = 10
TTL = 600
USAGE = 'Use /calendar or /calendar YYYY-MM-DD YYYY-MM-DD [blend|mine|section|division|bureau]. Maximum 31 days, Asia/Manila.'


class Unavailable(ValueError):
    pass


def units(text):
    return len(text.encode('utf-16-le')) // 2


def signature(body):
    return hmac.new(auth._secret(), b'telegram-calendar-cursor\0'+body.encode(), hashlib.sha256).hexdigest()


def encode(value):
    body=base64.urlsafe_b64encode(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).decode().rstrip('=')
    return body+'.'+signature(body)


def decode(token,now):
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1200}\.[a-f0-9]{64}',token):
        raise Unavailable('Paging token unavailable. Run /calendar again.')
    body,tag=token.split('.')
    if not hmac.compare_digest(tag,signature(body)):
        raise Unavailable('Paging token unavailable. Run /calendar again.')
    try:
        value=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        if (not isinstance(value,dict) or set(value)!={'u','c','g','b','s','e','q','o','t','v'}
                or any(type(value[k]) is not int for k in ('u','c','o','t'))
                or value['u']<=0 or value['c']<=0 or not 1<=value['o']<=MAX_ITEMS
                or value['t']<=int(now.timestamp()) or value['t']>int(now.timestamp())+TTL+60
                or not re.fullmatch(r'[a-f0-9]{32}',value['g'])
                or not re.fullmatch(r'[a-f0-9]{64}',value['b']) or not re.fullmatch(r'[a-f0-9]{64}',value['v'])):
            raise ValueError()
        validate(value['s'],value['e'],value['q'])
        return value
    except (ValueError,TypeError,KeyError,RecursionError):
        raise Unavailable('Paging token expired or changed. Run /calendar again.') from None


def validate(start,end,scope):
    if (not isinstance(start,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',start)
            or not isinstance(end,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',end)
            or scope not in calendar.SCOPES):
        raise Unavailable(USAGE)
    try:
        first,last=date.fromisoformat(start),date.fromisoformat(end)
        if not 0<=(last-first).days<MAX_DAYS:
            raise ValueError()
    except ValueError:
        raise Unavailable(USAGE) from None


def parse(text,now):
    parts=text.split()
    if parts and parts[0]=='/calendar_next':
        if len(parts)!=2:
            raise Unavailable('Paging token unavailable. Run /calendar again.')
        value=decode(parts[1],now)
        return {'start':value['s'],'end':value['e'],'scope':value['q'],'cursor':parts[1]}
    if parts==['/calendar']:
        first=now.astimezone(ZONE).date()
        return {'start':first.isoformat(),'end':(first+timedelta(days=6)).isoformat(),'scope':'blend','cursor':None}
    if len(parts) not in (2,3,4) or parts[0]!='/calendar':
        raise Unavailable(USAGE)
    first,last=parts[1],parts[2] if len(parts)>=3 else parts[1]
    scope=parts[3] if len(parts)==4 else 'blend'
    validate(first,last,scope)
    return {'start':first,'end':last,'scope':scope,'cursor':None}


def actor(conn,delivery,bot,action='calendar.read'):
    found=rows(conn,'''SELECT c.account_id,u.username,u.role FROM telegram_connection c
        JOIN admin_user u ON u.id=c.account_id WHERE c.id=? AND c.generation=? AND c.state='active'
        AND c.telegram_user_id=? AND c.private_chat_id=? AND u.active=1 AND u.must_change=0''',
        (delivery['connection_id'],delivery['generation'],delivery['chat_id'],delivery['chat_id']))
    if (not found or delivery['chat_id']<=0 or delivery['topic_id'] is not None or delivery['registration_id'] is not None
            or not links.authorized(conn,found[0]['account_id'],action)
            or not links.origin() or len(links.origin())>200):
        return None
    user=found[0]
    return {'id':user['account_id'],'username':user['username'],'role':user['role']}


def descriptor(projection,bot):
    if (not isinstance(projection,dict) or set(projection)!={'kind','bot','fingerprint','query'}
            or projection['kind']!='calendar' or projection['bot']!=bot[0] or projection['fingerprint']!=bot[2]):
        return False
    query=projection['query']
    if query=={'error':'usage'}:
        return True
    if not isinstance(query,dict) or set(query)!={'start','end','scope','cursor'}:
        return False
    try:
        validate(query['start'],query['end'],query['scope'])
        return query['cursor'] is None or isinstance(query['cursor'],str) and len(query['cursor'])<=1300
    except ValueError:
        return False


def clip(value,limit):
    return ''.join(c if not unicodedata.category(c).startswith('C') else ' ' for c in str(value or ''))[:limit]


def project(item,base):
    path=safe_local_return(item.get('url'),default='')
    if not (path.startswith('/calendar/entries/') or path.startswith('/rooms?')):
        path='/calendar?'+urlencode({'day':item['start']})
    status=item['status']
    if item['layer']=='rooms':
        status=('requested standby (not booked)' if 'provisional (standby)' in item['flags'] else 'requested (not booked)') if status=='tentative' else 'approved'
    return {'key':item['key'],'title':clip(item['title'],120),'kind':clip(item['kind'],30),
            'status':clip(status,40),'start':item['start'],'end':item['end'],
            'start_time':item['start_time'],'end_time':item['end_time'],'all_day':item['all_day'],
            'owner':clip(item['owner_label'],60),'venue':clip(item['venue'],80),'url':base+path}


def line(item):
    dates=item['start']+((' – '+item['end']) if item['end']!=item['start'] else '')
    times='All day' if item['all_day'] else (item['start_time'] or 'Time not set')+('–'+item['end_time'] if item['end_time'] else '')
    location=' · '.join(value for value in (item['venue'],item['owner']) if value)
    return f"{item['title']} [{item['kind']}; {item['status']}]\n{dates} · {times}"+('\n'+location if location else '')+'\n'+item['url']


def page(conn,delivery,query,bot,now):
    user=actor(conn,delivery,bot)
    if not user:
        return None
    if query=={'error':'usage'}:
        raise Unavailable(USAGE)
    validate(query['start'],query['end'],query['scope'])
    ctx=calendar.viewer_context(conn,user)
    if query['scope'] not in {scope['key'] for scope in calendar.scope_choices(ctx)}:
        raise Unavailable('That calendar scope is unavailable. Open your signed-in calendar.')
    cursor=decode(query['cursor'],now) if query['cursor'] else None
    if cursor and (cursor['u']!=user['id'] or cursor['c']!=delivery['connection_id'] or cursor['g']!=delivery['generation']
            or cursor['b']!=bot[2] or (cursor['s'],cursor['e'],cursor['q'])!=(query['start'],query['end'],query['scope'])):
        raise Unavailable('Paging token unavailable for this connection. Run /calendar again.')
    items=calendar.items_between(conn,user,query['start'],query['end'],scope=query['scope'],layers=LAYERS)
    if len(items)>MAX_ITEMS:
        raise Unavailable('Too many calendar results. Choose a shorter date range or open Office Connect.')
    projected=[project(item,links.origin()) for item in items]
    digest=hashlib.sha256(json.dumps(projected,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if cursor and cursor['v']!=digest:
        raise Unavailable('The calendar or your access changed. Run /calendar again for current results.')
    offset=cursor['o'] if cursor else 0
    header=f"Private calendar · Asia/Manila\n{query['start']} – {query['end']} · {calendar.SCOPE_LABELS[query['scope']]}"
    shown=[]
    for item in projected[offset:offset+PAGE_SIZE]:
        if units(header+'\n\n'+'\n\n'.join(line(i) for i in [*shown,item]))>2700:
            break
        shown.append(item)
    next_token=None
    if offset+len(shown)<len(projected):
        next_token=encode({'u':user['id'],'c':delivery['connection_id'],'g':delivery['generation'],'b':bot[2],
            's':query['start'],'e':query['end'],'q':query['scope'],'o':offset+len(shown),
            't':int(now.timestamp())+TTL,'v':digest})
    text=header+'\n\n'+('\n\n'.join(line(item) for item in shown) if shown else 'No calendar items in this range.')
    if next_token:
        text+='\n\nNext page (valid 10 minutes):\n/calendar_next '+next_token
    text+='\n\nOpen calendar: '+links.origin()+'/calendar?'+urlencode({'day':query['start'],'scope':query['scope']})
    if units(text)>4096:
        raise Unavailable('Open your signed-in calendar for this result.')
    return {'text':text,'items':shown,'next_token':next_token}


def render(conn,delivery,projection,bot,now):
    if not descriptor(projection,bot):
        return None
    # One current snapshot; network I/O happens only after releasing the writer lock.
    with transaction(conn):
        try:
            result=page(conn,delivery,projection['query'],bot,now)
            return result['text'] if result else None
        except Unavailable as error:
            return str(error) if actor(conn,delivery,bot) else None
