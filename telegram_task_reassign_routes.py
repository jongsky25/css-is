"""Signed-in officer task transfer form; final confirmation stays private."""
import telegram_meeting_manage_routes as forms
import telegram_task_reassign as reassignment


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=reassignment,template='telegram_task_reassign.html',
                             field_sets={'reassign':reassignment.FIELDS},form_context=reassignment.choices,
                             resource='Task reassignment',max_body=12000,max_fields=8)
