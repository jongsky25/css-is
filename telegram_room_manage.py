"""Own-room withdrawal/date moves under exact private preview/receipt transactions."""
from datetime import date
import hashlib
import json
import re

import calendar_actions
from documents_storage import rows
import room_actions
import rooms
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import tzutil as tz

MODES={'withdraw':'rooms.withdraw','move':'rooms.move'}
PATH='/account/telegram/room/manage/'


def source(conn,user,identifier):
    user=calendar_actions.actor(conn,user)
    record=rooms.get_reservation(conn,identifier)
    if not record or record['requester_user_id']!=user['id']:
        raise actions.Unavailable('Room request unavailable to this account.')
    rooms.transactional_plain(conn,record,user['id'])
    if record['status'] not in ('requested','approved'):
        raise actions.Unavailable('Only a pending request or approved booking can be managed.')
    return record


def stamp(conn,record):
    head=conn.execute("SELECT incarnation,revision,deleted FROM telegram_change_head WHERE entity='room' AND source_id=?",(record['id'],)).fetchone()
    slots=rows(conn,'''SELECT rs.*,s.start_time,s.end_time,s.label,s.sort,s.active,s.code FROM room_reservation_slot rs
        JOIN room_slot s ON s.id=rs.slot_id WHERE rs.reservation_id=? ORDER BY rs.slot_id''',(record['id'],))
    return {'hash':hashlib.sha256(actions.packed([record,slots]).encode()).hexdigest(),
            'head':list(head) if head else None}


class Adapter:
    def __init__(self,mode):self.mode=mode;self.action=MODES[mode]

    def prepare(self,conn,user,raw):
        try:return self._prepare(conn,user,raw)
        except rooms.RoomError as error:raise actions.Unavailable(str(error)) from None

    def _prepare(self,conn,user,raw):
        keys={'room_id','day'} if self.mode=='move' else {'room_id'}
        if set(raw)!=keys or type(raw['room_id']) not in (int,str):
            raise actions.Unavailable('Choose an exact room request number and supported fields.')
        identifier=str(raw['room_id'])
        if re.fullmatch(r'CR-[0-9]{4}-[0-9]{4,18}',identifier):
            found=rooms.get_by_ref(conn,identifier,requester_user_id=user['id'])
            if not found:raise actions.Unavailable('Room request unavailable to this account.')
            identifier=str(found['id'])
        if not re.fullmatch('[1-9][0-9]{0,17}',identifier):raise actions.Unavailable('Choose a valid room reference or request number.')
        record=source(conn,user,int(identifier))
        clean={'room_id':record['id']}
        children=rows(conn,"SELECT id FROM room_reservation WHERE moves_reservation_id=? AND source='move' AND status='requested' ORDER BY id LIMIT 6",(record['id'],))
        if len(children)>5:raise actions.Unavailable('Use Office Connect to review these linked move requests.')
        child_records=[source(conn,user,c['id']) for c in children]
        expected={'room':stamp(conn,record),'children':{str(r['id']):stamp(conn,r) for r in child_records}}
        summary={'reference':record['ref_code'],'title':common.clip(record['title'],120),'day':record['day'],
                 'status':record['status'],'hours':rooms.hours_text(conn,record),'children':[r['ref_code'] for r in child_records],
                 'is_move_child':bool(record['moves_reservation_id']),'linked':bool(record['calendar_entry_id'])}
        if record['moves_reservation_id']:
            original=rooms.get_reservation(conn,record['moves_reservation_id'])
            if not original or original['requester_user_id']!=user['id']:
                raise actions.Unavailable('Review the original booking in Office Connect.')
            expected['parent']=stamp(conn,original)
            summary['parent_status']=original['status']
        if self.mode=='move':
            if not isinstance(raw['day'],str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',raw['day']):
                raise actions.Unavailable('Choose an exact new office date.')
            date.fromisoformat(raw['day'])
            if raw['day']==record['day']:raise actions.Unavailable('This request is already on that date.')
            if child_records:raise actions.Unavailable('A move is already waiting for approval. Review it in Office Connect.')
            if record['source']=='move' and record['status']=='requested':
                raise actions.Unavailable('Withdraw the pending move before preparing another; the original booking stays held.')
            rooms.precheck(conn,raw['day'],record['slot_ids'],today=tz.today_local())
            if record['calendar_entry_id']:
                if not links.authorized(conn,user['id'],'calendar.read'):
                    raise actions.Unavailable('Linked moves also require current calendar read consent.')
                _,entry=room_actions.meeting(conn,user,record['calendar_entry_id'])
                if raw['day']!=entry['start_date']:
                    raise actions.Unavailable('The new room date must match the linked meeting. Update the meeting in Office Connect first.')
                expected.update(entry_id=entry['id'],entry=room_actions.revision(entry),
                                entry_revision=conn.execute('SELECT COALESCE(MAX(id),0) FROM calendar_entry_revision WHERE entry_id=?',(entry['id'],)).fetchone()[0])
            clean['day']=raw['day'];summary['new_day']=raw['day']
        return clean,summary,expected

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if clean!=current or fresh!=expected:raise actions.Unavailable('The request, linked booking or hours changed. Prepare a new preview.')

    def apply(self,conn,user,clean,operation_id):
        try:
            record=source(conn,user,clean['room_id'])
            if self.mode=='withdraw':
                result=rooms.withdraw(conn,record['id'],user['id'],actor=user['username'],commit=False)
                code='room_withdrawn'
            else:
                result=rooms.request_move(conn,record['id'],clean['day'],user,today=tz.today_local(),commit=False)
                code='room_date_changed' if result['id']==record['id'] else 'room_move_requested'
        except rooms.RoomError as error:raise actions.Unavailable(str(error)) from None
        return {'state':'committed','result_room_id':result['id'],'result_code':code}

    def queue_preview(self,conn,user,operation_id,context,now):
        preview=rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        conn.execute('UPDATE telegram_operation SET context_json=?,target_id=? WHERE operation_id=?',
                     (actions.packed(context),json.loads(preview['fields_json'])['room_id'],operation_id))

    def text(self,summary):
        text=('Room '+self.mode+' preview\n'+common.clip(summary['reference'],40)+' · '+summary['title']
              +'\nCurrent: '+summary['day']+' · '+common.clip(summary['hours'],240)+' · '+summary['status']+' · Asia/Manila')
        if self.mode=='withdraw':
            text+='\nWithdraw this request. Any approved hours it holds will be released.'
            if summary['children']:text+='\nAlso withdraw these pending moves: '+', '.join(summary['children'])
            if summary['is_move_child'] and summary['status']=='requested':
                text+='\nOriginal booking is unchanged; current status: '+summary['parent_status']+'.'
                if summary['parent_status']=='approved':text+=' Its approved hours stay held.'
        else:
            text+='\nNew date: '+summary['new_day']+' · same hours · Asia/Manila'
            text+=('\nSubmit a new move request. The old approved booking stays held until the new request is approved. No new hours are booked now.'
                   if summary['status']=='approved' else '\nChange this pending request in place. It stays pending approval; no hours are booked.')
        return text+'\nThe linked calendar meeting is not changed. Normal room notices follow existing settings.'

    def check_receipt(self,conn,user,operation):
        if operation['result_room_id']:
            record=rooms.get_reservation(conn,operation['result_room_id'])
            if not record or record['requester_user_id']!=user['id']:raise actions.Unavailable('Room receipt unavailable.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='room_deleted':return 'The room record for this operation was deleted. Recovery will not recreate it.'
        if operation['state']!='committed' or not operation['result_room_id']:return None
        record=rooms.get_reservation(conn,operation['result_room_id'])
        outcome={'room_withdrawn':'room request withdrawn','room_date_changed':'pending room request date changed',
                 'room_move_requested':'room move requested; approval remains separate'}[operation['result_code']]
        status={'requested':'requested (pending approval; no booking held)','approved':'approved (booked)'}.get(record['status'],record['status'])
        text=('Recorded outcome: '+outcome+'.\nCurrent request: '+record['ref_code']+' · '+record['day']+' · '+status+' · Asia/Manila')
        if operation['result_code']=='room_move_requested':
            parent=rooms.get_reservation(conn,operation['target_id'])
            if parent and parent['requester_user_id']==user['id']:
                text+='\nOriginal booking: '+parent['ref_code']+' · '+parent['day']+' · '+parent['status']
        return text+'\nOperation: '+operation['operation_id']+'\n'+links.origin()+'/rooms/mine\nRecovery reports the outcome and current state; it never repeats the action.'


for mode,action in MODES.items():
    dispatch.register(action,{'prefix':mode,'start':'/room_'+mode,'path':PATH+mode,
                             'confirm':'/'+mode+'_confirm','receipt':'/'+mode+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in ('/room_'+mode,'/'+mode+'_preview','/'+mode+'_confirm','/'+mode+'_receipt'))
