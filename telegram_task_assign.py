"""Officer-confirmed initial task ownership using native contributor access checks."""
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_work_actions as shared
import work
import work_reads
import work_tasks

ACTION='tasks.assign'
MODES={'assign':ACTION}
PATH='/account/telegram/task-assignment/'
FIELDS=('case_id','task_id','owner_id','reason')


def choices(conn,user,mode):
    return {'people':rows(conn,'''SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name
        FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.active=1 ORDER BY name,u.id''')}


class Adapter:
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS):
            raise actions.Unavailable('Complete only the supported task assignment fields.')
        item=shared.require_work(conn,user,proposals.number(raw['case_id']))
        task=work_reads.task(conn,user,item['id'],proposals.number(raw['task_id']))
        if 'confirm' not in work_tasks.actions(conn,user,item,task):
            raise actions.Unavailable('Only the concerned contributing-unit officer can confirm a proposed task assignment. Work-lead status alone is insufficient.')
        owner_id=work_tasks._owner(conn,item['id'],proposals.number(raw['owner_id']))
        account=work._account(conn,owner_id)
        owner={k:account[k] for k in ('id','username','role','active','rp_id')}
        owner['name']=rows(conn,'''SELECT COALESCE(NULLIF(r.name,''),u.username) AS name
            FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id WHERE u.id=?''',(owner_id,))[0]['name']
        # Initial assignment keeps the existing target and repeats its native official-date rule.
        work_tasks._due(conn,item['id'],task['due_date'])
        clean={'case_id':item['id'],'task_id':task['id'],'owner_id':owner_id,
               'reason':proposals.text(raw['reason'],'Assignment reason',500,multiline=True)}
        summary={**clean,'work_title':common.clip(item['title'],120),'title':common.clip(task['title'],160),
                 'owner_name':common.clip(owner['name'],160),'proposed_owner_id':task['proposed_owner_id'],
                 'unit_id':task['unit_id'],'due_date':task['due_date'] or 'not set'}
        if common.units(self.text(summary))>3000:
            raise actions.Unavailable('This preview is too long. Shorten the reason or use Office Connect.')
        return clean,summary,{**shared.source_state(conn,item,task),'task_revision':task['revision'],'owner':owner}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:
            raise actions.Unavailable('The task, selected account, work or linked document changed. Prepare a fresh preview.')

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        work_tasks.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],'confirm',
                                        {'owner_id':clean['owner_id'],'reason':clean['reason']})
        return {'state':'committed','result_code':'task_assigned'}

    def queue_preview(self,conn,user,operation_id,context,now):
        preview=rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]
        clean=json.loads(preview['fields_json'])
        conn.execute('UPDATE telegram_operation SET context_json=?,target_id=?,expected_revision=? WHERE operation_id=?',
                     (actions.packed(context),clean['task_id'],str(clean['case_id']),operation_id))

    def text(self,summary):
        return ('Task assignment preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nContributing unit: '+str(summary['unit_id'])
                +'\nSuggested account: '+str(summary['proposed_owner_id'] or 'not set')
                +'\nAssign to: '+summary['owner_name']+' (account '+str(summary['owner_id'])+')'
                +'\nCurrent status: proposed\nNew status: to do\nTask deadline (unchanged): '+summary['due_date']+' · Asia/Manila'
                +'\nReason:\n'+summary['reason']
                +'\nThe selected person must already have access to every linked document. No document access is granted.'
                +'\nThis confirms initial ownership only. It does not acknowledge, submit or accept the task, or approve an official document.'
                +'\nNormal task membership, history and reminder rules apply.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Task assignment receipt unavailable.')
        case_id=proposals.number(operation['expected_revision'])
        work.get(conn,user,case_id)
        if operation['target_id']:work_reads.task(conn,user,case_id,operation['target_id'])

    def receipt_text(self,conn,user,operation):
        case_id=proposals.number(operation['expected_revision'])
        if operation['result_code']=='task_deleted':
            return 'The task for this operation was deleted. Recovery will not recreate it.\n/work_status '+str(case_id)
        if operation['state']!='committed' or not operation['target_id']:return None
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        return ('Recorded outcome: initial task assignment confirmed.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\nCurrent owner account: '+str(task['owner_id'] or 'not assigned')
                +'\nCurrent status: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports the recorded outcome and current state; it never repeats the assignment.')


dispatch.register(ACTION,{'prefix':'taskassign','start':'/task_assign','path':PATH+'assign',
                          'confirm':'/taskassign_confirm','receipt':'/taskassign_receipt'},Adapter())
COMMANDS=('/task_assign','/taskassign_preview','/taskassign_confirm','/taskassign_receipt')
