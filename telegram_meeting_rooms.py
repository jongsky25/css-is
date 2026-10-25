"""Separate room child outcomes under the confirmed guided meeting intent.

Domain refusals roll back only the child savepoint. Unexpected failures roll back
its parent transaction too; neither path commits or calls a provider here.
"""
import json
import re
from uuid import uuid4

from documents_storage import rows
import room_actions
import rooms
import telegram_actions as actions
import telegram_links as links
import telegram_room_requests as requests


def consent(conn,user):
    if not all(links.authorized(conn,user['id'],scope) for scope in ('rooms.read','rooms.request')):
        raise actions.Unavailable('Room read and room-request consent and pilots are required. Remove the optional room request or relink with those permissions.')


def prepare(conn,user,raw):
    consent(conn,user)
    if not isinstance(raw,dict) or set(raw)!={'from_time','to_time'}:
        raise actions.Unavailable('Choose exact room start and end hours.')
    slots=requests.block(conn,raw)
    return dict(raw),slots


def precheck(conn,clean,expected):
    try:
        rooms.precheck(conn,clean['day'],[s['id'] for s in expected['room_slots']],today=room_actions.tz.today_local())
    except rooms.RoomError as error:
        raise actions.Unavailable(str(error)) from None


def apply(conn,user,clean,operation_id):
    parent=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=?',(operation_id,))[0]
    ctx=json.loads(parent['context_json'])
    actions.authority(conn,ctx,'rooms.request')
    fields,summary,expected=requests.ADAPTER.prepare(conn,user,clean)
    child_id=uuid4().hex
    conn.execute('''INSERT INTO telegram_operation
        (operation_id,parent_operation_id,actor_id,connection_id,generation,action,client_key,input_hash,
         context_hash,context_json,state,result_entry_id,created_at,updated_at)
        VALUES (?,?,?,?,?,'rooms.request',?,?,?,?,'pending',?,?,?)''',
        (child_id,operation_id,user['id'],parent['connection_id'],parent['generation'],'meeting-room:'+operation_id,
         actions.fingerprint('rooms.request',fields,expected,summary),parent['context_hash'],parent['context_json'],
         clean['entry_id'],parent['created_at'],parent['created_at']))
    room_id=None
    conn.execute('SAVEPOINT meeting_room_child')
    try:
        record=room_actions.request_in_transaction(conn,user,clean['entry_id'],[s['id'] for s in expected['slots']],expected['entry_revision'])
        room_id=record['id']
    except rooms.RoomError:
        conn.execute('ROLLBACK TO meeting_room_child')
    except BaseException:
        conn.execute('ROLLBACK TO meeting_room_child')
        raise
    finally:
        conn.execute('RELEASE meeting_room_child')
    actions.authority(conn,ctx,'rooms.request')
    conn.execute('UPDATE telegram_operation SET state=?,result_room_id=?,result_code=? WHERE operation_id=?',
                 ('committed' if room_id else 'failed',room_id,'room_requested' if room_id else 'room_unavailable',child_id))
    return room_id


def retry_parent(conn,user,identifier,entry_id=None):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):
        raise actions.Unavailable('Original meeting operation unavailable.')
    found=rows(conn,"""SELECT * FROM telegram_operation WHERE operation_id=? AND actor_id=? AND action='calendar.create'
        AND state='partial' AND result_code='meeting_room_failed' AND result_entry_id IS NOT NULL""",(identifier,user['id']))
    if not found or (entry_id is not None and found[0]['result_entry_id']!=entry_id):
        raise actions.Unavailable('Original meeting operation unavailable. Recover its receipt before preparing a new room request.')
    room_actions.meeting(conn,user,found[0]['result_entry_id'])
    return found[0]


def children(conn,operation):
    return rows(conn,'SELECT * FROM telegram_operation WHERE parent_operation_id=? ORDER BY rowid DESC LIMIT 20',(operation['operation_id'],))


def check_receipt(conn,user,operation):
    consent(conn,user)
    for child in children(conn,operation):
        requests.ADAPTER.check_receipt(conn,user,child)


def receipt_text(conn,user,operation):
    if not operation['result_entry_id']:
        return 'The meeting for operation '+operation['operation_id']+' was deleted. Nothing will be recreated. Review Office Connect.'
    result=('Meeting saved.\nOperation: '+operation['operation_id']+'\n'
            +links.origin()+'/calendar/entries/'+str(operation['result_entry_id']))
    history=children(conn,operation)
    submitted=next((child for child in history if child['state']=='committed' and child['result_room_id']),None)
    if submitted:
        record=rooms.get_reservation(conn,submitted['result_room_id'])
        next_step=('Administrative Section decides the pending request.' if record['status']=='requested'
                   else 'Review the current decision in My room requests; no further action was submitted.')
        return result+'\n'+requests.ADAPTER.receipt_text(conn,user,submitted)+'\nNext: '+next_step
    if any(child['result_code'] in ('room_deleted','calendar_deleted') for child in history):
        return result+'\nThe room child record was deleted. Nothing will be recreated. Review My room requests in Office Connect.'
    child=history[-1] if history else None
    return (result+'\nRoom request failed; no booking held.'
            +('\nRoom child operation: '+child['operation_id'] if child else '')
            +'\nNext: you choose new room hours and confirm a fresh room-only preview for this saved meeting. Send /room_request, then open:\n'
            +links.origin()+'/account/telegram/room?parent_operation_id='+operation['operation_id']
            +'\nThis operation will never create the meeting again.')
