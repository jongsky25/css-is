"""Signed-in discussion preparation; original private chat owns final confirmation."""
import telegram_meeting_manage_routes as forms
import telegram_mentions as mentioning
import telegram_comment_manage as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_comment_manage.html',
                             field_sets=manage.FIELDS,resource='Discussion comment',max_body=14000,max_fields=26, multi_fields=('mentions',),
                             query_fields=('case_id','task_id'),value_context=mentioning.form_context)
