"""Discussion-derived work proposals and decisions; no formal document approval authority."""
import json
import documents as docs
import documents_permissions as permissions
from documents_storage import rows, transaction
import tzutil as tz
import work
import work_discussion as discussion
import work_tasks
import work_compat


def can_decide(conn, user, case):
    return case['lead_id']==user['id'] or work.officer(conn,user,case)


def source(conn, user, case_id, comment_id):
    user=permissions.actor(conn,user)
    case=work.get(conn,user,case_id)
    found=rows(conn,'SELECT * FROM work_comment WHERE id=? AND case_id=?',(comment_id,case_id))
    if not found:
        raise permissions.Denied('Source message unavailable.')
    return user,case,discussion.message(conn,case_id,found[0]['task_id'],comment_id)


def checked_source(conn,user,case_id,comment_id,revision):
    user,case,message=source(conn,user,case_id,comment_id)
    work.writable(conn)
    work_compat.require_open(conn,case_id)
    if message['revision']!=revision:
        raise docs.Conflict('The source message changed. Review its latest text before continuing.')
    return user,case,message


def source_url(case_id, comment_id, task_id=None):
    return f'/work/{case_id}/discussion?message={comment_id}' + (f'&task_id={task_id}' if task_id else '') + '#message-history'


def task_source(conn, user, case_id, task_id):
    work.get(conn,user,case_id)
    found=rows(conn,'''SELECT s.*,c.task_id AS thread_task_id,r.body FROM work_task_source s
        JOIN work_task t ON t.id=s.task_id JOIN work_comment c ON c.id=s.comment_id
        JOIN work_comment_revision r ON r.comment_id=s.comment_id AND r.revision=s.source_revision
        WHERE s.task_id=? AND t.case_id=?''',(task_id,case_id))
    if not found:return None
    result=found[0];result['url']=source_url(case_id,result['comment_id'],result['thread_task_id'])
    return result


def propose(conn,user,case_id,comment_id,revision,fields):
    with transaction(conn):
        user,case,message=checked_source(conn,user,case_id,comment_id,revision)
        if conn.execute('SELECT 1 FROM work_task_source WHERE comment_id=?',(comment_id,)).fetchone():
            raise docs.Conflict('This message already has a proposed task. Open its linked contribution.')
        task=work_tasks.create_in_transaction(conn,user,case_id,fields)
        conn.execute('INSERT INTO work_task_source VALUES (?,?,?)',(task['id'],comment_id,revision))
        work._event(conn,user,case_id,'task_from_message',{'task_id':task['id'],'title':task['title'],
                    'comment_id':comment_id,'source_revision':revision})
        return task


def pending(conn,task_id):
    return rows(conn,'''SELECT d.id,d.body FROM work_decision d JOIN work_decision_task t ON t.decision_id=d.id
        LEFT JOIN work_decision_resolution r ON r.decision_id=d.id AND r.task_id=t.task_id
        WHERE t.task_id=? AND d.kind='change' AND r.task_id IS NULL
        AND NOT EXISTS(SELECT 1 FROM work_decision newer WHERE newer.supersedes_id=d.id) ORDER BY d.id''',(task_id,))


def record(conn,user,case_id,comment_id,revision,fields):
    with transaction(conn):
        user,case,message=checked_source(conn,user,case_id,comment_id,revision)
        if not can_decide(conn,user,case):
            raise permissions.Denied('Only the accountable lead or concerned officer can record a work decision.')
        if conn.execute('SELECT 1 FROM work_decision WHERE comment_id=? AND source_revision=?',(comment_id,revision)).fetchone():
            raise docs.Conflict('A decision already uses this message revision. Open it or use a new message to record a change.')
        kind=fields.get('kind')
        if kind not in ('coordination','change'):raise ValueError('Choose a supported work decision type.')
        body=work._text(fields.get('body'),'Decision and reason',4000)
        ids=fields.get('affected_tasks',[])
        if not isinstance(ids,list) or not 1<=len(ids)<=20:raise ValueError('Choose between 1 and 20 affected contributions.')
        ids=sorted({int(i) for i in ids})
        expected=fields.get('task_revisions',{})
        if not isinstance(expected,dict):raise ValueError('Reload the affected contributions.')
        tasks=[]
        for tid in ids:
            found=rows(conn,'SELECT * FROM work_task WHERE id=? AND case_id=?',(tid,case_id))
            if not found:raise ValueError('Choose contributions in this work item.')
            task=found[0];work._check_revision(task,int(expected.get(str(tid),0)));tasks.append(task)
        previous=int(fields['supersedes_id']) if fields.get('supersedes_id') else None
        if previous:
            old=rows(conn,'SELECT * FROM work_decision WHERE id=? AND case_id=?',(previous,case_id))
            if not old:raise ValueError('Choose a prior decision from this work item.')
            if conn.execute('SELECT 1 FROM work_decision WHERE supersedes_id=?',(previous,)).fetchone():
                raise docs.Conflict('This decision has already been replaced. Review its latest successor.')
            old_ids={r[0] for r in conn.execute('SELECT task_id FROM work_decision_task WHERE decision_id=?',(previous,))}
            if not old_ids.issubset(ids):raise ValueError('Include every contribution affected by the previous decision so its review is not lost.')
            if kind!='change':raise ValueError('Replacing a decision requires a change in work direction and review of affected work.')
        did=drevision=version=None
        if fields.get('document_id'):
            did=int(fields['document_id'])
            linked={d['id']:d for d in work.linked_documents(conn,user,case_id)}
            if did not in linked:raise ValueError('Choose correspondence already linked to this work item.')
            doc=docs.raw(conn,did)
            expected_docs=fields.get('document_revisions',{})
            if not isinstance(expected_docs,dict) or doc['revision']!=int(expected_docs.get(str(did),0)):
                raise docs.Conflict('The referenced correspondence changed. Review it again.')
            drevision,version=doc['revision'],doc['current_version']
        now=tz.now_iso()
        decision=conn.execute('''INSERT INTO work_decision(case_id,comment_id,source_revision,actor_id,authority,kind,body,
            supersedes_id,document_id,document_revision,document_version_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (case_id,comment_id,revision,user['id'],'Accountable lead' if case['lead_id']==user['id'] else 'Concerned officer',kind,body,previous,did,drevision,version,now)).lastrowid
        for task in tasks:
            conn.execute('INSERT INTO work_decision_task VALUES (?,?,?)',(decision,task['id'],json.dumps(task,sort_keys=True)))
            if kind=='change':
                conn.execute('UPDATE work_task SET revision=revision+1,updated_at=? WHERE id=?',(now,task['id']))
        work._event(conn,user,case_id,'decision_recorded',{'decision_id':decision,'reason':body,'kind':kind,'affected_tasks':ids})
        return decision


def detail(conn,user,case_id,decision_id):
    user=permissions.actor(conn,user);case=work.get(conn,user,case_id)
    found=rows(conn,'''SELECT d.*,r.body AS source_body,c.task_id AS thread_task_id
        FROM work_decision d JOIN work_comment c ON c.id=d.comment_id
        JOIN work_comment_revision r ON r.comment_id=d.comment_id AND r.revision=d.source_revision
        WHERE d.id=? AND d.case_id=?''',(decision_id,case_id))
    if not found:raise permissions.Denied('Work decision unavailable.')
    decision=found[0]
    successor=conn.execute('SELECT id FROM work_decision WHERE supersedes_id=?',(decision_id,)).fetchone()
    decision['successor_id']=successor[0] if successor else None
    decision['url']=source_url(case_id,decision['comment_id'],decision['thread_task_id'])
    affected=rows(conn,'''SELECT t.*,dt.snapshot_json,r.outcome AS resolution,r.reason AS resolution_reason,
        r.actor_id AS resolver_id,r.created_at AS resolved_at FROM work_decision_task dt JOIN work_task t ON t.id=dt.task_id
        LEFT JOIN work_decision_resolution r ON r.decision_id=dt.decision_id AND r.task_id=t.id WHERE dt.decision_id=? ORDER BY t.id''',(decision_id,))
    for task in affected:task['snapshot']=json.loads(task.pop('snapshot_json'))
    return case,decision,affected


def resolve(conn,user,case_id,decision_id,task_id,revision,outcome,reason):
    with transaction(conn):
        user=permissions.actor(conn,user);case,decision,affected=detail(conn,user,case_id,decision_id)
        work.writable(conn);work_compat.require_open(conn,case_id)
        if not can_decide(conn,user,case):raise permissions.Denied('A lead or concerned officer must review changed work.')
        task=next((t for t in affected if t['id']==task_id),None)
        if not task:raise permissions.Denied('Affected contribution unavailable.')
        if decision['successor_id'] or decision['kind']!='change' or task['resolution']:
            raise docs.Conflict('This review has already been resolved or replaced. Reload the decision.')
        work._check_revision(task,revision)
        reason=work._text(reason,'Review explanation',2000)
        if outcome not in ('retain','revise'):raise ValueError('Choose whether the contribution is still valid or needs revision.')
        if outcome=='revise' and task['status']=='cancelled':
            raise ValueError('A cancelled contribution cannot be restarted. Propose replacement work and explain that outcome instead.')
        if outcome=='revise' and task['status'] in ('done','for_review'):
            work_tasks.mutate_in_transaction(conn,user,case_id,task_id,revision,
                'reopen' if task['status']=='done' else 'return',{'reason':reason})
        else:
            conn.execute('UPDATE work_task SET revision=revision+1,updated_at=? WHERE id=?',(tz.now_iso(),task_id))
        conn.execute('INSERT INTO work_decision_resolution VALUES (?,?,?,?,?,?,?)',(decision_id,task_id,user['id'],revision,outcome,reason,tz.now_iso()))
        work._event(conn,user,case_id,'decision_reviewed',{'decision_id':decision_id,'task_id':task_id,
                    'title':task['title'],'reason':reason,'outcome':outcome})
