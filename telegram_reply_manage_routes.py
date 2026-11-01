"""Signed-in no-script reply forms; the original private chat owns final confirmation."""
import telegram_meeting_manage_routes as forms
import telegram_mentions as mentioning
import telegram_reply_manage as manage


def context(conn,user,mode,values):return mentioning.form_context(conn,user,mode,values,reply=True)


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_reply_manage.html',
                             field_sets=manage.FIELDS,resource='Discussion reply',max_body=14000,max_fields=27, multi_fields=('mentions',),
                             query_fields=('case_id','task_id','parent_id'),value_context=context)
