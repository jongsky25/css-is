"""Signed-in accepted-task reopening form; final confirmation remains private."""
import telegram_meeting_manage_routes as forms
import telegram_task_reopen as reopening


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=reopening,template='telegram_task_reopen.html',
                             field_sets={'reopen':reopening.FIELDS},resource='Task reopening',max_body=12000,max_fields=8)
