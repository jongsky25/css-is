"""Explicit own-notice read acknowledgement through exact private previews."""
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_discussion_updates as inbox
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_task_review as review
import telegram_work_actions as shared
import work
import work_updates

ACTION='work.updates.acknowledge'
MODES={'read':ACTION}
PATH='/account/telegram/update/'
FIELDS={'read':('notice_id','revision')}


class Adapter(review.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS['read']):raise actions.Unavailable('Choose only one notice and its exact notice revision.')
        clean={key:proposals.number(raw[key]) for key in FIELDS['read']}
        entry=inbox.detail(conn,user,clean['notice_id']);notice,item,task=entry
        if notice['revision']!=clean['revision'] or not 1<=notice['revision']<=notice['current_revision']:
            raise actions.Unavailable('The notice revision changed. Check its current details and prepare a fresh preview.')
        if notice['read_revision']>=notice['revision']:
            raise actions.Unavailable('This notice revision is already read. No acknowledgement is needed.')
        summary={'metadata':inbox.line(entry),'url':inbox.source(entry),'revision':notice['revision']}
        # Metadata only: no discussion body or task submission is fetched for a preview.
        return clean,summary,{**shared.source_state(conn,item,task),'notice':notice}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:
            raise actions.Unavailable('The notice, read marker or source changed. Prepare a fresh acknowledgement preview.')

    def queue_preview(self,conn,user,operation_id,context,now):
        clean=json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])
        notice,item,task=inbox.detail(conn,user,clean['notice_id'])
        conn.execute('UPDATE telegram_operation SET context_json=?,expected_revision=?,target_id=?,comment_id=?,comment_revision=? WHERE operation_id=?',
                     (actions.packed(context),str(item['id']),task['id'] if task else None,notice['comment_id'],notice['revision'],operation_id))

    def apply(self,conn,user,clean,operation_id):
        notice,item,task=inbox.detail(conn,user,clean['notice_id'])
        work_updates.mark_read_in_transaction(conn,user,item['id'],task['id'] if task else None,
                                              [(notice['comment_id'],clean['revision'])])
        return {'state':'committed','result_code':'notice_read'}

    def text(self,summary):
        return ('Discussion read acknowledgement preview\n'+summary['metadata']
                +'\nMark only notice revision '+str(summary['revision'])+' as read for your account.\n'+summary['url']
                +'\nRead the discussion before confirming; this preview contains metadata only.'
                +'\nA newer comment revision is not acknowledged. Native read markers apply to this comment for your account; this notice leaves the unread list.'
                +'\nNo other recipient, discussion text, task progress or notification preference changes.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Read acknowledgement receipt unavailable.')
        if operation['result_code'] in ('work_deleted','task_deleted'):return
        found=rows(conn,'SELECT id FROM work_notice WHERE comment_id=? AND user_id=?',
                   (operation['comment_id'],user['id']))
        if not found:raise actions.Unavailable(inbox.DENIED)
        notice,item,task=inbox.detail(conn,user,found[0]['id'])
        if (str(item['id'])!=operation['expected_revision'] or (task['id'] if task else None)!=operation['target_id']):
            raise actions.Unavailable(inbox.DENIED)

    def receipt_text(self,conn,user,operation):
        self.check_receipt(conn,user,operation)
        if operation['result_code'] in ('work_deleted','task_deleted'):
            return 'The source for this read acknowledgement was deleted. Recovery never recreates it or marks another message read.'
        if operation['state']!='committed':return None
        notice_id=rows(conn,'SELECT id FROM work_notice WHERE comment_id=? AND user_id=?',(operation['comment_id'],user['id']))[0]['id']
        entry=inbox.detail(conn,user,notice_id)
        return ('Recorded outcome: notice marked read.\n'+inbox.line(entry)
                +'\nRecorded acknowledged revision: '+str(operation['comment_revision'])
                +'\nCurrent read revision: '+str(entry[0]['read_revision'])+'\nOperation: '+operation['operation_id']
                +'\n'+inbox.source(entry)+'\nRecovery reports the recorded outcome and current metadata; it never marks a newer revision read.')


dispatch.register(ACTION,{'prefix':'updateread','start':'/update_read','path':PATH+'read',
                         'confirm':'/updateread_confirm','receipt':'/updateread_receipt'},Adapter('read'))
COMMANDS=('/update_read','/updateread_preview','/updateread_confirm','/updateread_receipt')
