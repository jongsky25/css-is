"""Current-account internal task deadline forms; final approval stays private."""
import telegram_meeting_manage_routes as forms
import telegram_task_deadline as deadlines


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=deadlines,template='telegram_task_deadline.html',
                             field_sets={'change':deadlines.FIELDS},resource='Task deadline',max_body=12000,max_fields=10)
