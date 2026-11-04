"""Optional current-access mentions in exact private comment/reply previews."""
from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_task_create as proposals
import work
import work_discussion as discussion
import work_updates

SCOPE='work.mentions'
POST_ACTIONS=('work.comment','tasks.comment','work.reply','tasks.reply')


def enabled(conn,user):
    return work.enabled(conn) and links.authorized(conn,user['id'],'work.read') and links.authorized(conn,user['id'],SCOPE)


def prepare(conn,user,item,values):
    if not isinstance(values,list) or len(values)>20:raise actions.Unavailable('Choose up to twenty eligible colleagues.')
    ids=[proposals.number(v) for v in values]
    if len(set(ids))!=len(ids):raise actions.Unavailable('Choose each colleague only once.')
    if not ids:return []
    if not enabled(conn,user):raise actions.Unavailable('Colleague mentions require their separate current permission and host pilot.')
    ids=work_updates.validate_mentions(conn,item['id'],ids)
    result=[]
    for identifier in ids:
        account=work._account(conn,identifier)
        name=rows(conn,'''SELECT COALESCE(NULLIF(r.name,''),u.username) AS name FROM admin_user u
            LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.id=?''',(identifier,))[0]['name']
        result.append({**{k:account[k] for k in ('id','username','role','active','rp_id')},'name':name})
    return result


def add(clean,summary,expected,people):
    if people:
        clean['mentions']=[p['id'] for p in people]
        summary['mentions']=[{'id':p['id'],'name':common.clip(p['name'],100)} for p in people]
        expected['mentions']=people


def text(summary):
    people=summary.get('mentions',[])
    if not people:return ''
    return ('\nSelected colleague mentions:\n'+'\n'.join(p['name']+' (account '+str(p['id'])+')' for p in people)
            +'\nThese structured mentions create normal permitted in-app notices. Your own mention creates no self-notice. No source access is granted.')


def form_context(conn,user,mode,values,*,reply=False):
    context={'mentions_available':bool(enabled(conn,user)),'mention_people':[],
             'mention_selected':[str(v) for v in values.get('mentions',[])], 'mention_error':'','mention_loaded':False}
    if not context['mentions_available'] or not values.get('case_id'):return context
    try:
        case_id=proposals.number(values['case_id'])
        task_id=proposals.number(values.get('task_id')) if mode=='task' else None
        discussion.scope(conn,user,case_id,task_id)
        if reply and values.get('parent_id'):discussion.message(conn,case_id,task_id,proposals.number(values['parent_id']))
        context['mention_people']=work_updates.candidates(conn,user,case_id)
        context['mention_loaded']=True
    except ValueError:
        context['mention_error']='Choose a work item, task and parent you can currently read before loading colleague choices.'
    return context
