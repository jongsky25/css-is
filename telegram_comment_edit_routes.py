"""Signed-in no-script preparation of exact author-owned comment edits."""
import telegram_meeting_manage_routes as forms
import telegram_comment_edit as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_comment_edit.html',
                             field_sets=manage.FIELDS,resource='Comment edit',max_body=14000,max_fields=8)
