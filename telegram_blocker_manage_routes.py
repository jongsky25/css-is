"""Signed-in blocker forms; final task change stays in the original private confirmation."""
import telegram_meeting_manage_routes as forms
import telegram_blocker_manage as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_blocker_manage.html',
                             field_sets=manage.FIELDS,form_context=manage.choices,resource='Task blocker',max_body=14000,max_fields=9)
