"""Signed-in no-script dependency forms; writes require the original private confirmation."""
import telegram_meeting_manage_routes as forms
import telegram_dependency_manage as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_dependency_manage.html',
                             field_sets=manage.FIELDS,resource='Task dependency',max_body=10000,max_fields=7)
