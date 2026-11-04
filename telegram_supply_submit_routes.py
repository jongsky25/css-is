"""Signed-in no-script selection of one own supply request and current revision."""
import telegram_meeting_manage_routes as forms
import telegram_supply_submit as manage


def make_router(templates,get_conn):
    return forms.make_router(templates,get_conn,manager=manage,template='telegram_supply_submit.html',
                             field_sets=manage.FIELDS,query_fields=('request_id','revision'),
                             resource='Supply submission',max_body=4096,max_fields=5)
