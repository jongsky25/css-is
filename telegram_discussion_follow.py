"""Exact own discussion follow preferences; native future-notice rules stay authoritative."""
import json

from documents_storage import rows
import telegram_actions as actions
import telegram_calendar as common
import telegram_links as links
import telegram_meetings as dispatch
import telegram_task_create as proposals
import telegram_task_review as review
import telegram_work_actions as shared
import work
import work_discussion as discussion
import work_updates

ACTION='work.follow'
MODES={'change':ACTION}
PATH='/account/telegram/discussion-follow/'
FIELDS={'change':('case_id','task_id','choice')}


def own_state(conn,user,case_id,task_id):
    return rows(conn,'''SELECT task_id,created_at FROM work_follow WHERE case_id=? AND user_id=?
        AND (task_id IS ? OR task_id IS NULL) ORDER BY task_id''',(case_id,user['id'],task_id))


def source_url(case_id,task_id):
    return links.origin()+'/work/'+str(case_id)+'/discussion'+('?task_id='+str(task_id) if task_id is not None else '')


class Adapter(review.Adapter):
    def prepare(self,conn,user,raw):
        if set(raw)!=set(FIELDS['change']) or raw['choice'] not in ('follow','unfollow'):
            raise actions.Unavailable('Choose one work discussion or task discussion, and Follow or Unfollow.')
        work.writable(conn)
        case_id=proposals.number(raw['case_id']);task_id=proposals.number(raw['task_id'],optional=True)
        _,item,task=discussion.scope(conn,user,case_id,task_id)
        state=own_state(conn,user,case_id,task_id)
        current=any(row['task_id']==task_id for row in state)
        chosen=raw['choice']=='follow'
        if current==chosen:raise actions.Unavailable('This exact discussion is already '+('followed' if chosen else 'not followed')+'. No change is needed.')
        clean={'case_id':case_id,'task_id':task_id,'choice':raw['choice']}
        summary={**clean,'work_title':common.clip(item['title'],120),
                 'task_title':common.clip(task['title'],160) if task else None,
                 'work_follow':any(row['task_id'] is None for row in state)}
        return clean,summary,{**shared.source_state(conn,item,task),'own_follow':state}

    def revalidate(self,conn,user,clean,expected):
        current,_,fresh=self.prepare(conn,user,clean)
        if current!=clean or fresh!=expected:
            raise actions.Unavailable('The source or your selected/work-wide follow changed. Prepare a fresh preview.')

    def queue_preview(self,conn,user,operation_id,context,now):
        clean=json.loads(rows(conn,'SELECT fields_json FROM telegram_preview WHERE operation_id=?',(operation_id,))[0]['fields_json'])
        conn.execute('UPDATE telegram_operation SET context_json=?,expected_revision=?,target_id=? WHERE operation_id=?',
                     (actions.packed(context),str(clean['case_id']),clean['task_id'],operation_id))

    def apply(self,conn,user,clean,operation_id):
        work_updates.follow_in_transaction(conn,user,clean['case_id'],clean['task_id'],clean['choice']=='follow')
        return {'state':'committed','result_code':'discussion_followed' if clean['choice']=='follow' else 'discussion_unfollowed'}

    def text(self,summary):
        task_id=summary['task_id'];chosen=summary['choice']=='follow'
        target=('\nTask '+str(task_id)+' · '+summary['task_title'] if task_id is not None
                else '\nWork-wide follow: includes work-level and all task discussions in this work.')
        effect=('\nYour work-wide follow is currently '+('on' if summary['work_follow'] else 'off')+'.'
                +' A work-wide follow also covers this task; changing its task-specific follow does not change that.' if task_id is not None
                else '\nExisting task-specific follows stay in place.')
        return ('Discussion follow preview\nWork '+str(summary['case_id'])+' · '+summary['work_title']+target
                +'\nYour selected follow: '+('off → on' if chosen else 'on → off')+effect
                +'\n'+source_url(summary['case_id'],task_id)
                +'\n'+('Follow future discussion posts for your account.' if chosen else 'Remove only this exact follow for your account.')
                +'\nExisting notices and read markers stay unchanged. Direct mentions and replies may still notify you.'
                +'\nNo other account, task progress, formal approval or delivery preference changes. This does not enable Telegram/email delivery; existing native notice and delivery preferences still apply.')

    def check_receipt(self,conn,user,operation):
        if not work.enabled(conn):raise actions.Unavailable('Discussion follow receipt unavailable.')
        if operation['result_code'] in ('work_deleted','task_deleted'):return
        discussion.scope(conn,user,proposals.number(operation['expected_revision']),operation['target_id'])

    def receipt_text(self,conn,user,operation):
        self.check_receipt(conn,user,operation)
        if operation['result_code'] in ('work_deleted','task_deleted'):
            return 'The source for this follow operation was deleted. Recovery never recreates it or changes a replacement discussion.'
        if operation['state']!='committed':return None
        case_id=proposals.number(operation['expected_revision']);task_id=operation['target_id']
        current=work_updates.following(conn,user,case_id,task_id)
        work_follow=work_updates.following(conn,user,case_id)
        recorded='followed' if operation['result_code']=='discussion_followed' else 'unfollowed'
        return ('Recorded outcome: discussion '+recorded+'.\nWork '+str(case_id)
                +(' · Task '+str(task_id) if task_id is not None else ' · Work-wide discussion follow')
                +'\nCurrent exact follow: '+('on' if current else 'off')
                +('\nCurrent work-wide follow: '+('on' if work_follow else 'off')+'; it also covers this task.' if task_id is not None else '\nTask-specific follows remain independent.')
                +'\nOperation: '+operation['operation_id']+'\n'+source_url(case_id,task_id)
                +'\nRecovery reports the recorded outcome and current state; it never changes following again.')


dispatch.register(ACTION,{'prefix':'discussionfollow','start':'/discussion_follow','path':PATH+'change',
                         'confirm':'/discussionfollow_confirm','receipt':'/discussionfollow_receipt'},Adapter('change'))
COMMANDS=('/discussion_follow','/discussionfollow_preview','/discussionfollow_confirm','/discussionfollow_receipt')
