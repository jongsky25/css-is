"""Private officer transfer using native reassignment and existing submission history."""
import telegram_actions as actions
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_assign as assignment
import telegram_task_create as proposals
import work_reads

ACTION='tasks.reassign'
MODES={'reassign':ACTION}
PATH='/account/telegram/task-reassignment/'
FIELDS=assignment.FIELDS
choices=assignment.choices


class Adapter(assignment.Adapter):
    native_action='reassign'
    result_code='task_reassigned'
    authority_message='Only the concerned contributing-unit officer can reassign a To do, In progress or For review task. Work-lead status alone is insufficient.'

    def prepare(self,conn,user,raw):
        clean,summary,expected=super().prepare(conn,user,raw)
        if clean['owner_id']==summary['current_owner_id']:
            raise actions.Unavailable('Choose a different owner for reassignment.')
        return clean,summary,expected

    def text(self,summary):
        return ('Task reassignment preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']
                +'\nTask '+str(summary['task_id'])+' · '+summary['title']+'\nContributing unit: '+str(summary['unit_id'])
                +'\nCurrent owner account: '+str(summary['current_owner_id'] or 'not assigned')
                +'\nNew owner: '+summary['owner_name']+' (account '+str(summary['owner_id'])+')'
                +'\nCurrent status: '+summary['status'].replace('_',' ')+'\nNew status: to do'
                +'\nReassignment returns the task to To do for the new owner, including tasks previously In progress or For review.'
                +'\nTask deadline (unchanged): '+summary['due_date']+' · Asia/Manila\nReason:\n'+summary['reason']
                +'\nThe existing submission and history are preserved; submission contents stay in Office Connect.'
                +'\nThe new owner must already read every linked document. No document access is granted.'
                +'\nNormal membership/history/reminder rules apply. Blockers remain; this does not accept a task or approve an official document.')

    def receipt_text(self,conn,user,operation):
        if operation['result_code']=='task_deleted':return super().receipt_text(conn,user,operation)
        if operation['state']!='committed' or not operation['target_id']:return None
        case_id=proposals.number(operation['expected_revision'])
        task=work_reads.task(conn,user,case_id,operation['target_id'])
        return ('Recorded outcome: task reassigned.\nTask '+str(task['id'])+' · Work '+str(case_id)
                +'\nCurrent owner account: '+str(task['owner_id'] or 'not assigned')
                +'\nCurrent status: '+task['status'].replace('_',' ')+'\nOperation: '+operation['operation_id']
                +'\n/work_status '+str(case_id)+'\n'+links.origin()+'/work/'+str(case_id)
                +'\nRecovery reports the recorded outcome and current state; it never repeats the reassignment.')


dispatch.register(ACTION,{'prefix':'taskreassign','start':'/task_reassign','path':PATH+'reassign',
                          'confirm':'/taskreassign_confirm','receipt':'/taskreassign_receipt'},Adapter())
COMMANDS=('/task_reassign','/taskreassign_preview','/taskreassign_confirm','/taskreassign_receipt')
