"""Signed-in no-script preparation of one own-notice acknowledgement."""
import telegram_meeting_manage_routes as forms
import telegram_update_read as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_update_read.html',
                             query_fields=('notice_id','revision'),field_sets=manage.FIELDS,resource='Read acknowledgement',max_body=4096,max_fields=5)
