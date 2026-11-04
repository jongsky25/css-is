"""Signed-in initial task assignment form; final confirmation stays private."""
import telegram_meeting_manage_routes as forms
import telegram_task_assign as assignment


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=assignment,template='telegram_task_assign.html',
                             field_sets={'assign':assignment.FIELDS},form_context=assignment.choices,
                             resource='Task assignment',max_body=12000,max_fields=8)
