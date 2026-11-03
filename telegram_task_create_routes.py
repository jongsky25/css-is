"""Script-free current-account task proposal forms through the shared action workflow."""
import telegram_meeting_manage_routes as forms
import telegram_task_create as task_create


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=task_create,template='telegram_task_create.html',
                             field_sets={'create':task_create.FIELDS},form_context=task_create.choices,
                             resource='Task proposal',max_body=20000,max_fields=10)
