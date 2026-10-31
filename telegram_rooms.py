"""Private read-only room availability and owner-bound request status."""
from datetime import date, timedelta
from contextlib import nullcontext
import re
from urllib.parse import urlencode

from documents_storage import transaction
import rooms
import telegram_calendar as common
import telegram_links as links

USAGE = 'Use /room_slots [YYYY-MM-DD], /my_rooms [START END] (maximum 31 days), or /room_status CR-YYYY-NNNN. Asia/Manila time.'
REFERENCE = re.compile(r'CR-[0-9]{4}-[0-9]{4}\Z')


def validate(query):
    if query=={'error':'usage'}:
        return
    if not isinstance(query,dict):
        raise ValueError(USAGE)
    mode=query.get('mode')
    if mode=='slots' and set(query)=={'mode','day'}:
        common.validate(query['day'],query['day'],'blend')
    elif mode=='mine' and set(query)=={'mode','start','end'}:
        common.validate(query['start'],query['end'],'blend')
    elif mode=='status' and set(query)=={'mode','reference'} and isinstance(query['reference'],str) and REFERENCE.fullmatch(query['reference']):
        pass
    else:
        raise ValueError(USAGE)


def parse(text,now):
    parts=text.split();today=now.astimezone(common.ZONE).date()
    if parts and parts[0]=='/room_slots' and len(parts) in (1,2):
        query={'mode':'slots','day':parts[1] if len(parts)==2 else today.isoformat()}
    elif parts and parts[0]=='/my_rooms' and len(parts) in (1,3):
        query={'mode':'mine','start':parts[1] if len(parts)==3 else today.isoformat(),
               'end':parts[2] if len(parts)==3 else (today+timedelta(days=30)).isoformat()}
    elif parts and parts[0]=='/room_status' and len(parts)==2:
        query={'mode':'status','reference':parts[1].upper()}
    else:
        raise ValueError(USAGE)
    validate(query)
    return query


def actor(conn,delivery,bot):
    return common.actor(conn,delivery,bot,action='rooms.read')


def descriptor(projection,bot):
    if (not isinstance(projection,dict) or set(projection)!={'kind','bot','fingerprint','query'}
            or projection['kind']!='rooms' or projection['bot']!=bot[0] or projection['fingerprint']!=bot[2]):
        return False
    try:
        validate(projection['query'])
        return True
    except (ValueError,TypeError):
        return False


def slot_text(conn,day,today):
    view=rooms.day_view(conn,date.fromisoformat(day),today=today)
    text='Private conference-room slots · Asia/Manila\n'+day
    if view['closed']:
        text+='\n'+common.clip(view['closed'],180)
    shown=0
    for slot in view['hours']:
        line=common.clip(slot['label'],80)+': '+slot['state']
        if common.units(text+'\n'+line)>2700:
            break
        text+='\n'+line;shown+=1
    if not view['hours']:
        text+='\nNo room slots configured.'
    elif shown<len(view['hours']):
        text+='\nMore slots are available on the signed-in page.'
    text+='\nRequested means pending approval and does not hold a booking. Availability is a current snapshot.'
    return text+'\nOpen conference room: '+links.origin()+'/rooms?'+urlencode({'week':day,'day':day})


def request_line(conn,record):
    status=record['status']
    if status=='requested':
        status='requested (standby; no booking held)' if record['standby'] else 'requested (awaiting approval; no booking held)'
    elif status=='approved':
        status='approved (booked)'
    hours=common.clip(rooms.hours_text(conn,record),140)
    return common.clip(record['ref_code'],20)+' · '+record['day']+'\n'+hours+'\n'+common.clip(status,80)


def render(conn,delivery,projection,bot,now, *, commit=True):
    if not descriptor(projection,bot):
        return None
    if not commit and not conn.in_transaction:
        raise RuntimeError("Caller-owned rendering requires a transaction")
    with transaction(conn) if commit else nullcontext():
        user=actor(conn,delivery,bot)
        if not user:
            return None
        query=projection['query']
        if query=={'error':'usage'}:
            return USAGE
        today=now.astimezone(common.ZONE).date()
        if query['mode']=='slots':
            return slot_text(conn,query['day'],today)
        if query['mode']=='status':
            record=rooms.get_by_ref(conn,query['reference'],requester_user_id=user['id'])
            text=('Private room request · Asia/Manila\n'+request_line(conn,record)) if record else 'Room request unavailable to this account.'
        else:
            records=rooms.list_for_user(conn,user['id'],start=query['start'],end=query['end'],limit=11)
            text='My room requests · Asia/Manila\n'+query['start']+' – '+query['end']
            shown=0
            for record in records[:10]:
                line=request_line(conn,record)
                if common.units(text+'\n\n'+line)>2700:
                    break
                text+='\n\n'+line;shown+=1
            if not records:
                text+='\nNo requests in this range.'
            if shown<len(records):
                text+='\nMore requests are available on the signed-in page. Narrow the dates to see more here.'
        return text+'\n\nOpen my requests: '+links.origin()+'/rooms/mine'
