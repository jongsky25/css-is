"""Signed-in task review forms; final confirmation stays in the original private chat."""
import telegram_meeting_manage_routes as forms
import telegram_task_review as review


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=review,template='telegram_task_review.html',
                             field_sets={mode:review.FIELDS for mode in review.MODES},resource='Task review',
                             max_body=12000,max_fields=8)
