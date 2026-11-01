"""Use the shared actor-bound, script-free action form for room management."""
import telegram_meeting_manage_routes as forms
import telegram_room_manage as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_room_manage.html',
                             target='room_id',dated_mode='move',date_fields=('day',),resource='Room')
