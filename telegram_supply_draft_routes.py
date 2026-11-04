"""Signed-in, no-script supplies catalog selection and draft preparation."""
import telegram_meeting_manage_routes as forms
import telegram_supply_draft as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_supply_draft.html',
                             field_sets=manage.FIELDS,value_context=manage.choices,query_fields=('q','after'),
                             resource='Supply draft',max_body=16000,max_fields=15)
