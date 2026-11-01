"""Signed-in no-script reply forms; the original private chat owns final confirmation."""
import telegram_meeting_manage_routes as forms
import telegram_reply_manage as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_reply_manage.html',
                             field_sets=manage.FIELDS,resource='Discussion reply',max_body=12000,max_fields=7)
