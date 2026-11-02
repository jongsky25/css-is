"""Guided single-meeting creation; full previews and receipts are private only."""
from datetime import date,datetime,timedelta
import json
import os
from contextlib import nullcontext
import re
import secrets
from uuid import uuid4

import calendar_actions as calendar
from documents_storage import rows,transaction
import office_calendar as oc
import storage as st
import telegram_actions as actions
import telegram_calendar as common
import telegram_groups as groups
import telegram_links as links
import telegram_transport as transport

PATH='/account/telegram/meeting'
ACTION='calendar.create'
META={
    'calendar.create':{'prefix':'meeting','start':'/meeting','path':PATH,'confirm':'/meeting_confirm','receipt':'/meeting_receipt'},
    'rooms.request':{'prefix':'room','start':'/room_request','path':'/account/telegram/room','confirm':'/room_confirm','receipt':'/room_receipt'},
}
COMMAND_ACTION={command:action for action,meta in META.items() for command in (meta['confirm'],meta['receipt'])}
KINDS={meta['prefix']+'_'+suffix:action for action,meta in META.items() for suffix in ('guide','preview','receipt','error')}


def register(action,meta,adapter):
    """Register another guided action using the same private preview/receipt contract."""
    META[action]=meta
    COMMAND_ACTION.update({meta[key]:action for key in ('confirm','receipt')})
    KINDS.update({meta['prefix']+'_'+suffix:action for suffix in ('guide','preview','receipt','error')})
    actions.ADAPTERS[action]=adapter



def context_from_preview(p):
    conn_sender=p.get('sender_id')
    return {k:p[k] for k in ('connection_id','generation','chat_id','topic_id','registration_id','registration_generation')} | {'sender_id':conn_sender}


def original_context(conn,p):
    connection=rows(conn,'SELECT telegram_user_id FROM telegram_connection WHERE id=?',(p['connection_id'],))
    if not connection:raise actions.Unavailable('Meeting context unavailable.')
    return context_from_preview({**p,'sender_id':connection[0]['telegram_user_id']})


def queue(conn,ctx,kind,identifier,now,*,key=None,expiry=None):
    # Private webhook actions are pulled explicitly; never enqueue a push.
    if ctx['chat_id']>0 and os.environ.get('CSS_TELEGRAM_REPLY_TRANSPORT')!='direct':
        return
    bot=transport.config()
    projection={'kind':kind,'id':identifier,'bot':bot[0],'fingerprint':bot[2]}
    conn.execute('''INSERT INTO telegram_delivery
        (dedupe_key,operation_id,connection_id,generation,chat_id,projection_json,expires_at,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING''',
        (key or kind+':'+identifier,identifier if kind.endswith(('_preview','_receipt')) else None,
         ctx['connection_id'],ctx['generation'],ctx['sender_id'],actions.packed(projection),
         expiry or links.stamp(now+timedelta(hours=24)),links.stamp(now),links.stamp(now)))


class Adapter:
    def prepare(self,conn,user,raw):
        if set(raw)-{'room'}!={'title','day','start_time','end_time','venue','audience','owner_org_id','people'}:
            raise actions.Unavailable('Complete the meeting fields; recurring and other actions are unavailable.')
        title=raw['title'];venue=raw['venue']
        if (not isinstance(title,str) or not 1<=len(title.strip())<=120 or not isinstance(venue,str) or len(venue)>120
                or any(any(ord(x)<32 for x in v) for v in (title,venue))):
            raise actions.Unavailable('Use a title up to 120 characters and a venue up to 120 characters, without control characters.')
        # Exact office dates and times; no inferred midnight rollover or natural language.
        day=raw['day'];start=raw['start_time'];end=raw['end_time']
        if not all(isinstance(v,str) for v in (day,start,end)) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
            raise actions.Unavailable('Choose an exact date and start/end time.')
        date.fromisoformat(day)
        if not all(re.fullmatch(r'([01][0-9]|2[0-3]):[0-5][0-9]',v) for v in (start,end)) or end<=start:
            raise actions.Unavailable('End time must be after start time on the same office date.')
        people=raw['people']
        if not isinstance(people,list) or len(people)>12 or any(type(v) not in (str,int) or not re.fullmatch('[0-9]{1,18}',str(v)) for v in people):
            raise actions.Unavailable('Choose at most twelve active participants.')
        ids=sorted(set(int(v) for v in people))
        unit=str(raw['owner_org_id'] or '')
        if unit and not re.fullmatch('[0-9]{1,18}',unit):raise actions.Unavailable('Choose a unit from the list.')
        units={str(v['id']):v['label'] for v in oc.unit_choices(conn)}
        if unit and unit not in units:raise actions.Unavailable('Choose an existing unit.')
        directory={v['user_id']:v['name'] for v in oc.people_choices(conn)}
        if any(i not in directory or len(directory[i])>120 for i in ids):raise actions.Unavailable('One of the chosen participants is unavailable. Reload the form.')
        clean={'title':title.strip(),'day':day,'start_time':start,'end_time':end,'venue':venue.strip(),
               'audience':raw['audience'],'owner_org_id':unit,'people':ids}
        room_slots=None
        if 'room' in raw:
            import telegram_meeting_rooms as combined
            clean['room'],room_slots=combined.prepare(conn,user,raw['room'])
        fields,participants,tags=calendar.prepare(conn,user,self.form(clean))
        duration=(int(end[:2])*60+int(end[3:]))-(int(start[:2])*60+int(start[3:]))
        expected={'people':{str(i):directory[i] for i in ids},'unit':units.get(unit,'')}
        summary={**clean,'duration_minutes':duration,'timezone':'Asia/Manila','participant_labels':expected['people'],
                 'unit_label':expected['unit'],'room':'No room requested; no booking held.'}
        if room_slots is not None:
            expected['room_slots']=room_slots
            summary['room']=('Also submit one internal room request for yourself: '+clean['room']['from_time']+' – '+clean['room']['to_time']
                +' · Asia/Manila, on '+day+'. Requested hours: '+', '.join(s['label'] for s in room_slots)
                +'. Requested duration: '+str(sum(int(s['end_time'][:2])*60+int(s['end_time'][3:])-int(s['start_time'][:2])*60-int(s['start_time'][3:]) for s in room_slots))+' minutes. Pending Administrative Section approval; no booking held. If the room request fails, keep the meeting and retry the room separately.')
        if common.units(self.text(summary))>3400:raise actions.Unavailable('This preview is too long. Use fewer participants or Office Connect.')
        return clean,summary,expected

    def form(self,clean):
        return {'title':clean['title'],'start_date':clean['day'],'start_time':clean['start_time'],'end_time':clean['end_time'],
                'venue':clean['venue'],'kind':'meeting','status':'confirmed','audience':clean['audience'],
                'owner_org_id':clean['owner_org_id'],'people':[str(i) for i in clean['people']],
                'extra_org_ids':[],'repeat':'none','until':'','tags':''}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:raise actions.Unavailable('Participant, unit or room-hour choices changed. Start a new preview.')

    def apply(self,conn,user,clean,operation_id):
        fields,people,tags=calendar.prepare(conn,user,self.form(clean))
        eid=calendar.create_in_transaction(conn,user,fields,people,tags)
        if 'room' in clean:
            import telegram_meeting_rooms as combined
            rid=combined.apply(conn,user,{'entry_id':eid,**clean['room']},operation_id)
            return {'state':'committed' if rid else 'partial','result_entry_id':eid,'result_room_id':rid,
                    'result_code':'meeting_room_requested' if rid else 'meeting_room_failed'}
        return {'state':'committed','result_entry_id':eid,'result_code':'calendar_created'}

    def queue_receipt(self,conn,user,operation,context,now):
        queue(conn,context,'meeting_receipt',operation['operation_id'],now)

    def receipt_text(self,conn,user,operation):
        if operation['result_code'] in ('meeting_room_requested','meeting_room_failed','room_deleted'):
            import telegram_meeting_rooms as combined
            return combined.receipt_text(conn,user,operation)
        if operation['result_code']=='calendar_deleted':return 'The meeting from operation '+operation['operation_id']+' was deleted in Office Connect. It will not be recreated.'
        if operation['result_code']=='retained_key' or operation['state']!='committed' or not operation['result_entry_id']:return None
        return 'Meeting created in Office Connect. This action did not request or book a room.\nOperation: '+operation['operation_id']+'\n'+links.origin()+'/calendar/entries/'+str(operation['result_entry_id'])

    def check_receipt(self,conn,user,operation):
        if operation['result_code'] in ('meeting_room_requested','meeting_room_failed','room_deleted'):
            import telegram_meeting_rooms as combined
            combined.check_receipt(conn,user,operation)
        if operation['result_entry_id'] and not oc.viewable_entry(conn,user,operation['result_entry_id']):
            raise actions.Unavailable('Meeting receipt unavailable.')

    def queue_preview(self,conn,user,operation_id,context,now):
        conn.execute('UPDATE telegram_operation SET context_json=? WHERE operation_id=?',(actions.packed(context),operation_id))
        p=rows(conn,'SELECT * FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean=json.loads(p['fields_json'])
        if 'room' in clean:
            import telegram_meeting_rooms as combined
            combined.precheck(conn,clean,json.loads(p['expected_json']))
        queue(conn,context,'meeting_preview',operation_id,now,expiry=p['expires_at'])

    def text(self,summary):
        names='\n'.join(common.clip(name,120)+' (account '+i+')' for i,name in summary['participant_labels'].items()) or 'None selected'
        audience={'people':'Only selected people (and creator)','bureau':'Everyone in the bureau','unit':'Owning unit and selected people'}[summary['audience']]
        return ('Meeting preview\n'+summary['title']+'\n'+summary['day']+' · '+summary['start_time']+' – '+summary['end_time']
                +' · Asia/Manila\nDuration: '+str(summary['duration_minutes'])+' minutes\nVenue: '+(summary['venue'] or 'Not set')
                +'\nAudience: '+audience+'\nOwning unit: '+(summary['unit_label'] or 'None')+'\nParticipants:\n'+names
                +'\n'+summary['room']+'\nOne non-recurring confirmed meeting. No automatic video link.')


ADAPTER=Adapter()
actions.ADAPTERS[ACTION]=ADAPTER


def observe(conn,clean,connection,bot,now,action=ACTION):
    group=groups.route(conn,clean['chat_id'],clean['topic_id'],bot) if clean['chat_id']<0 else None
    ctx={'connection_id':connection['id'],'generation':connection['generation'],'sender_id':clean['sender_id'],
         'chat_id':clean['chat_id'],'topic_id':clean['topic_id'],'registration_id':group['id'] if group else None,
         'registration_generation':group['generation'] if group else None}
    user,_,_=actions.authority(conn,ctx,action)
    identifier=secrets.token_hex(16)
    expires=links.stamp(now+timedelta(minutes=10))
    conn.execute('''INSERT INTO telegram_meeting_origin
        (id,account_id,connection_id,generation,context_json,bot_identity,bot_fingerprint,created_at,expires_at,action)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',(identifier,user['id'],ctx['connection_id'],ctx['generation'],actions.packed(ctx),bot[0],bot[2],links.stamp(now),expires,action))
    queue(conn,ctx,META[action]['prefix']+'_guide',identifier,now,expiry=expires)
    return identifier


def origin(conn,user,identifier,now,action=ACTION):
    found=rows(conn,'SELECT * FROM telegram_meeting_origin WHERE id=? AND account_id=? AND action=?',(identifier,user['id'],action))
    bot=transport.config()
    if not found or not bot or found[0]['expires_at']<=links.stamp(now) or found[0]['bot_identity']!=bot[0] or found[0]['bot_fingerprint']!=bot[2]:
        raise actions.Unavailable('That action request expired. Send '+META[action]['start']+' again.')
    ctx=json.loads(found[0]['context_json'])
    actor,_,_=actions.authority(conn,ctx,action)
    if actor['id']!=user['id']:raise actions.Unavailable('Action request unavailable.')
    return ctx


def delivery_context(conn,d,p,now):
    if not isinstance(p,dict) or set(p)!={'kind','id','bot','fingerprint'} or p['kind'] not in KINDS:return None
    action=KINDS[p['kind']];suffix=p['kind'].split('_',1)[1]
    bot=transport.config()
    if not bot or p['bot']!=bot[0] or p['fingerprint']!=bot[2] or d['chat_id']<=0 or d['topic_id'] is not None or d['registration_id'] is not None:return None
    try:
        if suffix=='guide':
            connection=rows(conn,'SELECT account_id AS id FROM telegram_connection WHERE id=?',(d['connection_id'],))[0]
            ctx=origin(conn,connection,p['id'],now,action)
        else:
            found=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=? AND action=?',(p['id'],action))
            if not found or not found[0]['context_json']:return None
            ctx=json.loads(found[0]['context_json'])
            user,adapter,_=actions.authority(conn,ctx,action)
            if suffix=='receipt':adapter.check_receipt(conn,user,found[0])
            if suffix=='preview':
                previews=rows(conn,'SELECT * FROM telegram_preview WHERE operation_id=?',(p['id'],))
                if not previews or previews[0]['state']!='pending' or previews[0]['expires_at']<=links.stamp(now):return None
                adapter.revalidate(conn,user,json.loads(previews[0]['fields_json']),json.loads(previews[0]['expected_json']))
        user,_,_=actions.authority(conn,ctx,action)
        if ctx['connection_id']!=d['connection_id'] or ctx['generation']!=d['generation'] or ctx['sender_id']!=d['chat_id']:return None
        return ctx,user
    except (ValueError,IndexError,KeyError,TypeError):return None


def render(conn,d,p,now, *, commit=True):
    if not commit and not conn.in_transaction:
        raise RuntimeError('Caller-owned meeting rendering requires a transaction')
    with transaction(conn) if commit else nullcontext():
        allowed=delivery_context(conn,d,p,now)
        if not allowed:return None
        ctx,user=allowed;action=KINDS[p['kind']];meta=META[action];adapter=actions.ADAPTERS[action]
        suffix=p['kind'].split('_',1)[1]
        if suffix=='guide':
            return 'Prepare the exact action on your signed-in page, then confirm its preview here before the displayed deadline. Full details and receipts stay private.\n'+links.origin()+meta['path']+'?origin='+p['id']
        if suffix=='error':return 'Confirmation unavailable or changed. Check Office Connect or use '+meta['receipt']+' OPERATION before preparing another action.'
        if suffix=='preview':
            preview=rows(conn,'SELECT * FROM telegram_preview WHERE operation_id=?',(p['id'],))[0]
            if not preview['token_nonce']:return None
            token=actions.derive_token(p['id'],preview['token_nonce'])
            if actions.digest(token)!=preview['token_hash']:return None
            adapter.revalidate(conn,user,json.loads(preview['fields_json']),json.loads(preview['expected_json']))
            deadline=datetime.fromisoformat(preview['expires_at']).astimezone(common.ZONE).strftime('%Y-%m-%d %H:%M:%S Asia/Manila')
            return adapter.text(json.loads(preview['summary_json']))+'\nConfirm exactly this preview before '+deadline+':\n'+meta['confirm']+' '+token+'\nOperation: '+p['id']+'\nRecover status: '+meta['receipt']+' '+p['id']
        operation=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=?',(p['id'],))[0]
        adapter.check_receipt(conn,user,operation)
        if operation['state'] in ('committed','partial','failed'):
            text=adapter.receipt_text(conn,user,operation)
            if text:return text
        return 'Action '+operation['operation_id']+' status: '+operation['state']+'. Review Office Connect or the original preview before preparing another action.'


def intake_action(conn,clean,connection,bot,now):
    action=COMMAND_ACTION[clean['command']]
    key='token_hash' if clean['command']==META[action]['confirm'] else 'operation_id'
    value=clean['meeting_argument']
    table='telegram_preview' if key=='token_hash' else 'telegram_operation'
    found=rows(conn,'SELECT * FROM '+table+' WHERE '+key+'=? AND connection_id=? AND generation=? AND action=?',
               (value,connection['id'],connection['generation'],action))
    if not found:raise actions.Unavailable('Confirmation unavailable.')
    ctx=original_context(conn,found[0]) if key=='token_hash' else json.loads(found[0]['context_json'] or '{}')
    actions.authority(conn,ctx,action)
    return {'kind':'meeting_action','command':clean['command'],'argument':value,'bot':bot[0],'fingerprint':bot[2]}


def process_one(conn,now,allow_group=True):
    token=uuid4().hex
    with transaction(conn):
        found=rows(conn,"SELECT * FROM telegram_update WHERE state='queued' OR (state='processing' AND lease_until<=?) ORDER BY id LIMIT 1",(links.stamp(now),))
        if not found:return False
        update=found[0]
        try:p=json.loads(update['payload_json'] or '{}')
        except ValueError:return False
        if not isinstance(p,dict) or p.get('kind')!='meeting_action':return False
        action=COMMAND_ACTION.get(p.get('command'));confirming=bool(action and p['command']==META[action]['confirm'])
        preview=rows(conn,'SELECT * FROM '+('telegram_preview' if confirming else 'telegram_operation')+' WHERE '+('token_hash' if confirming else 'operation_id')+'=? AND connection_id=? AND generation=? AND action=?',
                     (p.get('argument'),update['connection_id'],update['generation'],action))
        ctx=(original_context(conn,preview[0]) if confirming else json.loads(preview[0]['context_json'] or '{}')) if preview else None
        if ctx and ctx['chat_id']<0 and not allow_group:return 'defer'
        conn.execute("UPDATE telegram_update SET state='processing',claim_token=?,lease_until=? WHERE id=?",(token,links.stamp(now+timedelta(minutes=2)),update['id']))
    success=False
    try:
        bot=transport.config()
        if (not ctx or update['chat_id']!=update['sender_id'] or update['sender_id']!=ctx['sender_id']
                or set(p)!={'kind','command','argument','bot','fingerprint'} or not bot or p['bot']!=bot[0] or p['fingerprint']!=bot[2]
                or update['received_at']<=links.stamp(now-timedelta(hours=24))):raise actions.Unavailable('Action unavailable.')
        if confirming:actions.confirm_digest(conn,ctx,p['argument'],now)
        else:
            result=actions.recover(conn,ctx,action,p['argument'])
            with transaction(conn):queue(conn,ctx,META[action]['prefix']+'_receipt',result['operation_id'],now,key='action-recover:'+str(update['id']))
        success=True
    except ValueError:
        if ctx and preview:
            with transaction(conn):queue(conn,ctx,META[action]['prefix']+'_error',preview[0]['operation_id'],now,key='action-error:'+str(update['id']))
    with transaction(conn):
        conn.execute("UPDATE telegram_update SET state=?,payload_json=NULL,claim_token=NULL,lease_until=NULL,attempts=attempts+1,error_code=? WHERE id=? AND state='processing' AND claim_token=?",
                     ('processed' if success else 'cancelled',None if success else 'action_unavailable',update['id'],token))
    return 'group' if ctx and ctx['chat_id']<0 else 'private'
