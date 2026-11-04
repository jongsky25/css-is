"""Creator-only plain meeting edits; exact previews and atomic source/receipt writes."""
from datetime import date
import json
import re

import calendar_actions
from documents_storage import rows
import meet_relay
import office_calendar as oc
import room_actions
import rooms
import storage as st
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch

MODES={'reschedule':'calendar.reschedule','cancel':'calendar.cancel'}
PATH='/account/telegram/meeting/manage/'


def entry(conn,user,identifier):
    user=calendar_actions.actor(conn,user)
    record=oc.viewable_entry(conn,user,identifier)
    if not record or record['created_by']!=user['username']:
        raise actions.Unavailable('Meeting unavailable. Choose a meeting you created.')
    if (record['kind']!='meeting' or record.get('event_id') or record.get('rrule') or record.get('exdates')
            or record['source']!='app' or record['status']=='cancelled' or record.get('cancelled_at')
            or record.get('end_date') not in (None,'',record['start_date'])):
        raise actions.Unavailable('Use Office Connect for cancelled, imported, recurring, multi-day or activity-linked meetings.')
    if meet_relay.is_ours(record) or meet_relay.wants_link(record):
        raise actions.Unavailable('Use Office Connect to keep the managed video event in sync.')
    if any(r['status'] in ('requested','approved') for r in rooms.reservations_for_entry(conn,identifier)):
        raise actions.Unavailable('Manage the linked room request in Office Connect first. The meeting and booking must stay consistent.')
    return record


class Adapter:
    def __init__(self,mode):
        self.mode=mode;self.action=MODES[mode];self.prefix=mode

    def prepare(self,conn,user,raw):
        keys={'entry_id','day','start_time','end_time'} if self.mode=='reschedule' else {'entry_id'}
        if set(raw)!=keys or type(raw['entry_id']) not in (str,int) or not re.fullmatch('[1-9][0-9]{0,17}',str(raw['entry_id'])):
            raise actions.Unavailable('Choose an exact meeting entry number and supported fields.')
        record=entry(conn,user,int(raw['entry_id']))
        clean={'entry_id':record['id']}
        summary={'entry_id':record['id'],'title':common.clip(record['title'],120),'mode':self.mode,
                 'before_day':record['start_date'],'before_start':record['start_time'] or 'all day',
                 'before_end':record['end_time'] or 'not set','before_status':record['status']}
        if self.mode=='reschedule':
            if (any(not isinstance(raw[k],str) for k in ('day','start_time','end_time'))
                    or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',raw['day'])
                    or any(not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',raw[k]) for k in ('start_time','end_time'))
                    or raw['end_time']<=raw['start_time']):
                raise actions.Unavailable('Choose an exact date and same-day start/end times, with the end after the start.')
            date.fromisoformat(raw['day'])
            clean.update({k:raw[k] for k in ('day','start_time','end_time')})
            if (clean['day'],clean['start_time'],clean['end_time'])==(record['start_date'],record['start_time'],record['end_time']):
                raise actions.Unavailable('The meeting already has those dates and times.')
            st.cal_validate(record['title'],clean['day'],start_time=clean['start_time'],end_time=clean['end_time'])
            summary.update({k:clean[k] for k in ('day','start_time','end_time')})
        expected={'entry':room_actions.revision(record),
                  'revision_id':conn.execute('SELECT COALESCE(MAX(id),0) FROM calendar_entry_revision WHERE entry_id=?',(record['id'],)).fetchone()[0]}
        return clean,summary,expected

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if clean!=current or fresh!=expected:
            raise actions.Unavailable('The meeting changed. Review it and prepare a fresh preview.')

    def apply(self,conn,user,clean,operation_id):
        # The generic action engine holds BEGIN IMMEDIATE from revalidation
        # through source audit/outbox, preview consumption and operation receipt.
        record=entry(conn,user,clean['entry_id'])
        if self.mode=='reschedule':
            st.cal_update(conn,record['id'],by=user['username'],expected_sequence=record['sequence'],
                          expected_updated_at=record['updated_at'],start_date=clean['day'],end_date=None,
                          start_time=clean['start_time'],end_time=clean['end_time'],commit=False)
        else:
            st.cal_cancel(conn,record['id'],by=user['username'],commit=False)
        return {'state':'committed','result_entry_id':record['id'],
                'result_code':'calendar_rescheduled' if self.mode=='reschedule' else 'calendar_cancelled'}

    def queue_preview(self,conn,user,operation_id,context,now):
        if context['chat_id']<0:raise actions.Unavailable('Meeting management is private only.')
        conn.execute('UPDATE telegram_operation SET context_json=?,target_id=? WHERE operation_id=?',
                     (actions.packed(context),json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])['entry_id'],operation_id))
        # No outbound push: the signed-in form displays the exact pull command.

    def queue_receipt(self,conn,user,operation,context,now):
        pass  # Returned only in the original incoming private webhook response.

    def text(self,summary):
        text=('Meeting '+self.mode+' preview\nEntry '+str(summary['entry_id'])+' · '+summary['title']
              +'\nCurrent: '+summary['before_day']+' · '+summary['before_start']+' – '+summary['before_end']
              +' · '+summary['before_status']+' · Asia/Manila')
        if self.mode=='reschedule':
            text+='\nNew: '+summary['day']+' · '+summary['start_time']+' – '+summary['end_time']+' · Asia/Manila'
            text+='\nOnly this meeting’s date and times change. Its status, participants and other fields stay as stored.'
        else:
            text+='\nThis meeting will be marked cancelled in Office Connect; it is not deleted.'
        return text+'\nNo linked room is changed and no external video event is updated. Normal calendar change notices follow existing settings.'

    def check_receipt(self,conn,user,operation):
        if operation['result_entry_id']:
            record=oc.viewable_entry(conn,user,operation['result_entry_id'])
            if not record or record['created_by']!=user['username']:
                raise actions.Unavailable('Meeting receipt unavailable.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='calendar_deleted':
            return 'The meeting from operation '+operation['operation_id']+' was deleted. Recovery will not recreate it.'
        if operation['state']!='committed' or not operation['result_entry_id']:return None
        record=oc.viewable_entry(conn,user,operation['result_entry_id'])
        return ('Recorded outcome: meeting '+('rescheduled' if self.mode=='reschedule' else 'cancelled')+'.'
                +'\nCurrent meeting: '+record['start_date']+' · '+(record['start_time'] or 'all day')
                +' – '+(record['end_time'] or 'not set')+' · '+record['status']+' · Asia/Manila'
                +'\nOperation: '+operation['operation_id']+'\n'+links.origin()+'/calendar/entries/'+str(record['id'])
                +'\nRecovery reports the recorded outcome and current source state; it never repeats the change.')


for mode,action in MODES.items():
    dispatch.register(action,{'prefix':mode,'start':'/meeting_'+mode,'path':PATH+mode,
                             'confirm':'/'+mode+'_confirm','receipt':'/'+mode+'_receipt'},Adapter(mode))

COMMANDS=tuple(command for mode in MODES for command in
               ('/meeting_'+mode,'/'+mode+'_preview','/'+mode+'_confirm','/'+mode+'_receipt'))
