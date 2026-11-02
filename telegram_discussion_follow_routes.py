"""Signed-in no-script preparation of exact own follow/unfollow changes."""
import telegram_meeting_manage_routes as forms
import telegram_discussion_follow as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_discussion_follow.html',
                             field_sets=manage.FIELDS,resource='Discussion following',max_body=4096,max_fields=6,
                             query_fields=('case_id','task_id'))
