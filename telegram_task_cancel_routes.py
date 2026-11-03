"""Signed-in task cancellation reason form; final confirmation remains private."""
import telegram_meeting_manage_routes as forms
import telegram_task_cancel as cancellation


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=cancellation,template='telegram_task_cancel.html',
                             field_sets={'cancel':cancellation.FIELDS},resource='Task cancellation',max_body=12000,max_fields=8)
