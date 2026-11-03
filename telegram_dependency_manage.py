"""Exact, coordinator-authorized same-work dependency amendments in private Telegram."""
import hashlib
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_task_review as review
import telegram_work_actions as shared
import work_blockers as blockers
import work_reads

MODES={'add':'tasks.dependency_add','remove':'tasks.dependency_remove'}
PATH='/account/telegram/task-dependency/'
FIELDS={mode:('case_id','task_id','prerequisite_id','reason') for mode in MODES}


class Adapter(review.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS[self.mode]):raise actions.Unavailable('Complete only the supported dependency fields.')
        item=shared.require_work(conn,user,proposals.number(raw['case_id']))
        task=work_reads.task(conn,user,item['id'],proposals.number(raw['task_id']))
        if not blockers.authority(conn,user,item,task)[1]:
            raise actions.Unavailable('Current concerned-officer or confirmed work-lead authority is required for this active task.')
        prerequisite=work_reads.task(conn,user,item['id'],proposals.number(raw['prerequisite_id']))
        if prerequisite['id']==task['id']:raise actions.Unavailable('Choose another task in this work item.')
        exists=conn.execute('SELECT 1 FROM work_dependency WHERE task_id=? AND prerequisite_id=?',(task['id'],prerequisite['id'])).fetchone()
        if self.mode=='add':
            if exists:raise actions.Unavailable('This dependency already exists.')
            if prerequisite['status']=='cancelled':raise actions.Unavailable('Choose a prerequisite that has not been cancelled.')
            if conn.execute('''WITH RECURSIVE upstream(id) AS (
                SELECT ? UNION SELECT d.prerequisite_id FROM work_dependency d JOIN upstream u ON d.task_id=u.id)
                SELECT 1 FROM upstream WHERE id=?''',(prerequisite['id'],task['id'])).fetchone():
                raise actions.Unavailable('This dependency would create a cycle.')
        elif not exists:raise actions.Unavailable('This dependency is no longer present.')
        clean={'case_id':item['id'],'task_id':task['id'],'prerequisite_id':prerequisite['id'],
               'reason':proposals.text(raw['reason'],'Dependency change reason',500,multiline=True)}
        summary={**clean,'work_title':common.clip(item['title'],120),'title':common.clip(task['title'],160),
                 'status':task['status'],'prerequisite_title':common.clip(prerequisite['title'],160),
                 'prerequisite_status':prerequisite['status']}
        if common.units(self.text(summary))>3000:raise actions.Unavailable('This preview is too long. Shorten the reason or use Office Connect.')
        edges=rows(conn,'''SELECT d.* FROM work_dependency d JOIN work_task t ON t.id=d.task_id
            WHERE t.case_id=? ORDER BY d.task_id,d.prerequisite_id''',(item['id'],))
        graph=hashlib.sha256(json.dumps([prerequisite,edges],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return clean,summary,{**shared.source_state(conn,item,task),'graph':graph}

    def queue_preview(self,conn,user,operation_id,context,now):
        super().queue_preview(conn,user,operation_id,context,now)
        clean=json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])
        conn.execute('UPDATE telegram_operation SET dependency_task_id=? WHERE operation_id=?',(clean['prerequisite_id'],operation_id))

    def apply(self,conn,user,clean,operation_id):
        task=work_reads.task(conn,user,clean['case_id'],clean['task_id'])
        blockers.mutate_in_transaction(conn,user,clean['case_id'],clean['task_id'],task['revision'],'dependency_'+self.mode,
                                       {'prerequisite_id':clean['prerequisite_id'],'reason':clean['reason']})
        return {'state':'committed','result_code':'dependency_added' if self.mode=='add' else 'dependency_removed'}

    def text(self,summary):
        effect=('This task will require this prerequisite to be Done before submission/acceptance. The prerequisite is already Done.'
                if summary['prerequisite_status']=='done' else 'This task will wait for this prerequisite to be Done before submission/acceptance.') if self.mode=='add' else 'Remove only this prerequisite link. Other prerequisites, recorded blockers and changed-decision reviews still apply.'
        return ('Task dependency preview: '+self.mode+'\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nDependent task '+str(summary['task_id'])+' · '+summary['title']+'\nTask state (unchanged): '+summary['status'].replace('_',' ')
                +'\nPrerequisite task '+str(summary['prerequisite_id'])+' · '+summary['prerequisite_title']
                +'\nPrerequisite state (unchanged): '+summary['prerequisite_status'].replace('_',' ')
                +'\nDirection: task '+str(summary['task_id'])+' depends on task '+str(summary['prerequisite_id'])+'.\n'+effect
                +'\nReason:\n'+summary['reason']+'\nYour entered reason appears in Telegram and normal work history.'
                +'\nNo task is completed or automatically submitted. Ownership, progress, submissions, recorded blockers and all deadlines stay unchanged. No access or document approval is granted.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='task_deleted':return super().receipt_text(conn,user,operation)
        if operation['state']!='committed' or not operation['target_id']:return None
        case_id=proposals.number(operation['expected_revision'])
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        if operation['result_code']=='prerequisite_deleted':
            detail='The prerequisite for this operation was deleted. Recovery will not recreate it or use a replacement with the same number.'
        else:
            prerequisite=work_reads.task(conn,user,case_id,operation['dependency_task_id'])
            present=conn.execute('SELECT 1 FROM work_dependency WHERE task_id=? AND prerequisite_id=?',(task['id'],prerequisite['id'])).fetchone()
            detail=('Prerequisite task '+str(prerequisite['id'])+'\nCurrent link: '+('present' if present else 'absent')
                    +'\nCurrent prerequisite state: '+prerequisite['status'].replace('_',' '))
        return ('Recorded outcome: dependency '+('added' if self.mode=='add' else 'removed')+'.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\n'+detail+'\nCurrent task state: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n'+links.origin()+'/work/'+str(case_id)+'#task-'+str(task['id'])+'\nRecovery reports recorded outcome/current state; it never repeats the change.')


for mode,action in MODES.items():
    prefix='taskdep'+mode
    dispatch.register(action,{'prefix':prefix,'start':'/task_dependency_'+mode,'path':PATH+mode,
                              'confirm':'/'+prefix+'_confirm','receipt':'/'+prefix+'_receipt'},Adapter(mode))
COMMANDS=tuple(command for mode in MODES for command in
               ('/task_dependency_'+mode,'/taskdep'+mode+'_preview','/taskdep'+mode+'_confirm','/taskdep'+mode+'_receipt'))
