"""One self-owned pending request linked to an already permitted calendar meeting."""
import re

from documents_storage import rows
import room_actions
import rooms
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch

ACTION='rooms.request'
PATH='/account/telegram/room'


def block(conn,raw):
    for k in ('from_time','to_time'):
        if not isinstance(raw[k],str) or not re.fullmatch(r'[0-2][0-9]:[0-5][0-9]',raw[k]):
            raise actions.Unavailable('Choose configured start and end hours.')
    slots=rooms.list_slots(conn)
    first=next((s['id'] for s in slots if s['start_time']==raw['from_time']),None)
    last=next((s['id'] for s in slots if s['end_time']==raw['to_time']),None)
    if raw['to_time']<=raw['from_time']:raise actions.Unavailable('End hour must be after start hour.')
    try:
        slot_ids=rooms.slot_range(conn,first,last)
    except rooms.RoomError as error:raise actions.Unavailable(str(error)) from None
    catalog={s['id']:s for s in slots}
    selected=[catalog[sid] for sid in slot_ids]
    if any(a['end_time']!=b['start_time'] for a,b in zip(selected,selected[1:])):
        raise actions.Unavailable('Choose one continuous block of configured room hours.')
    return selected


class Adapter:
    def prepare(self,conn,user,raw):
        if not isinstance(raw,dict) or set(raw)-{'parent_operation_id'}!={'entry_id','from_time','to_time'}:
            raise actions.Unavailable('Choose a meeting and one consecutive block of room hours.')
        identifier=raw['entry_id']
        if type(identifier) not in (int,str) or not re.fullmatch('[0-9]{1,18}',str(identifier)) or int(identifier)<=0:
            raise actions.Unavailable('Meeting unavailable for a linked room request.')
        user,entry=room_actions.meeting(conn,user,int(identifier))
        selected=block(conn,raw)
        clean={'entry_id':entry['id'],'from_time':raw['from_time'],'to_time':raw['to_time']}
        if 'parent_operation_id' in raw:
            import telegram_meeting_rooms as combined
            combined.retry_parent(conn,user,raw['parent_operation_id'],entry['id'])
            clean['parent_operation_id']=raw['parent_operation_id']
        expected={'entry_revision':room_actions.revision(entry),'slots':selected}
        duration=sum(int(s['end_time'][:2])*60+int(s['end_time'][3:])-int(s['start_time'][:2])*60-int(s['start_time'][3:]) for s in selected)
        summary={'entry_id':entry['id'],'title':entry['title'],'day':entry['start_date'],
                 'meeting_time':(entry['start_time'] or 'Not set')+' – '+(entry['end_time'] or 'Not set'),
                 'calendar_status':entry['status'],'from_time':clean['from_time'],'to_time':clean['to_time'],'hours':[s['label'] for s in selected],'duration_minutes':duration,
                 'requester':user['username'],'timezone':'Asia/Manila'}
        if 'parent_operation_id' in clean:summary['parent_operation_id']=clean['parent_operation_id']
        if common.units(self.text(summary))>3200:raise actions.Unavailable('The preview is too long. Use the signed-in room workflow.')
        return clean,summary,expected

    def validate(self,conn,user,clean,expected):
        try:
            room_actions.validate(conn,user,clean['entry_id'],[s['id'] for s in expected['slots']],expected['entry_revision'])
        except rooms.RoomError as error:raise actions.Unavailable(str(error)) from None

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:raise actions.Unavailable('The meeting or room hours changed. Prepare a new preview.')
        self.validate(conn,user,clean,expected)

    def queue_preview(self,conn,user,operation_id,context,now):
        import json
        preview=rows(conn,'SELECT * FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean=json.loads(preview['fields_json']);expected=json.loads(preview['expected_json'])
        self.validate(conn,user,clean,expected)
        if 'parent_operation_id' in clean:
            conn.execute('UPDATE telegram_operation SET parent_operation_id=? WHERE operation_id=?',(clean['parent_operation_id'],operation_id))
        conn.execute('UPDATE telegram_operation SET context_json=? WHERE operation_id=?',(actions.packed(context),operation_id))
        dispatch.queue(conn,context,'room_preview',operation_id,now,expiry=preview['expires_at'])

    def apply(self,conn,user,clean,operation_id):
        _,_,expected=self.prepare(conn,user,clean)
        try:
            record=room_actions.request_in_transaction(conn,user,clean['entry_id'],[s['id'] for s in expected['slots']],expected['entry_revision'])
        except rooms.RoomError as error:raise actions.Unavailable(str(error)) from None
        return {'state':'committed','result_entry_id':clean['entry_id'],'result_room_id':record['id'],'result_code':'room_requested'}

    def queue_receipt(self,conn,user,operation,context,now):
        dispatch.queue(conn,context,'room_receipt',operation['operation_id'],now)

    def check_receipt(self,conn,user,operation):
        if operation['result_entry_id']:room_actions.meeting(conn,user,operation['result_entry_id'],for_write=False)
        if operation['result_room_id']:
            record=rooms.get_reservation(conn,operation['result_room_id'])
            if not record or record['requester_user_id']!=user['id']:
                raise actions.Unavailable('Room receipt unavailable.')
            if operation['result_entry_id'] and record['calendar_entry_id']!=operation['result_entry_id']:
                raise actions.Unavailable('The request link changed. Review it in Office Connect.')

    def text(self,summary):
        return ('Room request preview\nMeeting: '+summary['title']+' (entry '+str(summary['entry_id'])+')\n'
                +summary['day']+' · Asia/Manila\nMeeting time: '+summary['meeting_time']+'\nCalendar status: '+summary['calendar_status']
                +'\nRequested block: '+summary['from_time']+' – '+summary['to_time']+'\nRequested hours: '+', '.join(summary['hours'])+'\nRequested duration: '+str(summary['duration_minutes'])+' minutes'
                +'\nRequester: '+summary['requester']+'\nOne internal request for yourself; no meals, standby or repeats.'
                +('\nRoom-only retry for meeting operation: '+summary['parent_operation_id'] if 'parent_operation_id' in summary else '')
                +'\nPending Administrative Section approval. No booking is held. No meeting is created or edited.')

    def receipt_text(self,conn,user,operation):
        if operation['state']=='failed' and operation['result_code']=='room_unavailable':
            return ('Room child operation '+operation['operation_id']+' failed; no booking held. The meeting was saved.\n'
                    +links.origin()+'/calendar/entries/'+str(operation['result_entry_id'])
                    +'\nSend /room_request and prepare new hours for the saved meeting. Nothing is recreated by recovery.')
        if operation['result_code'] in ('room_deleted','calendar_deleted'):
            return 'The linked meeting or room record for operation '+operation['operation_id']+' was deleted. Nothing will be recreated. Review My room requests in Office Connect.'
        if operation['result_code']=='retained_key' or operation['state']!='committed' or not operation['result_room_id']:return None
        record=rooms.get_reservation(conn,operation['result_room_id'])
        status={'requested':'requested (pending approval; no booking held)','approved':'approved (booked)'}.get(record['status'],record['status'])
        return ('Room request receipt\n'+record['ref_code']+' · '+record['day']+' · Asia/Manila\n'+rooms.hours_text(conn,record)
                +'\nCurrent status: '+status+'\nOperation: '+operation['operation_id']+'\n'+links.origin()+'/rooms/mine'
                +'\nMeeting: '+links.origin()+'/calendar/entries/'+str(operation['result_entry_id']))


ADAPTER=Adapter()
actions.ADAPTERS[ACTION]=ADAPTER
