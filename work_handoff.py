"""Shared draft pointers and contribution handoffs, without Drive or approval side effects."""
import json
import re
from urllib.parse import urlparse, parse_qs, urlencode
import documents as docs
import documents_permissions as permissions
from documents_operations import validate_drive_url
from documents_storage import rows, transaction
import tzutil as tz
import work
import work_compat


def link(value, draft=False):
    value=work._text(value,'Google file link',2048)
    canonical,fid=validate_drive_url(value)
    parsed=urlparse(value)
    kind='Drive'
    match=re.fullmatch(r'/(document|spreadsheets|presentation)/d/[A-Za-z0-9_-]{10,200}(?:/.*)?',parsed.path)
    if parsed.hostname=='docs.google.com' and match:
        category=match.group(1)
        kind={'document':'Docs','spreadsheets':'Sheets','presentation':'Slides'}[category]
        canonical=f'https://docs.google.com/{category}/d/{fid}/edit'
    if draft and kind not in ('Docs','Sheets'):
        raise ValueError('Choose a Google Docs or Google Sheets working draft.')
    keys=parse_qs(parsed.query).get('resourcekey',[])
    if keys:
        if len(keys)!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',keys[0]):
            raise ValueError('The Google file resource key is invalid.')
        canonical+='?'+urlencode({'resourcekey':keys[0]})
    return canonical,fid,kind


def current(conn,case_id):
    result=rows(conn,'SELECT * FROM work_draft WHERE case_id=? ORDER BY id DESC LIMIT 1',(case_id,))
    return result[0] if result else None


def can_manage(conn,user,case):
    return work.can_link(conn,user,case)


def can_handoff(conn,user,case,task):
    return task['status']!='cancelled' and (task['owner_id']==user['id'] or case['lead_id']==user['id']
           or work.officer(conn,user,case) or work.officer(conn,user,task))


def writable(conn,user,case_id):
    user=permissions.actor(conn,user);case=work.get(conn,user,case_id)
    work.writable(conn);work_compat.require_open(conn,case_id)
    return user,case


def set_draft(conn,user,case_id,expected,fields,clear=False):
    with transaction(conn):
        user,case=writable(conn,user,case_id)
        if not can_manage(conn,user,case):raise permissions.Denied('The creator, accountable lead or concerned officer must choose the working draft.')
        old=current(conn,case_id)
        if (old['id'] if old else 0)!=expected:raise docs.Conflict('The working draft changed. Review the current draft before saving.')
        reason=work._text(fields.get('reason'),'Reason for draft change',2000)
        if clear:
            if not old or not old['url']:raise ValueError('There is no current working draft to clear.')
            title,url,fid,kind='No working draft','','',''
        else:
            title=work._text(fields.get('title'),'Draft name',250)
            url,fid,kind=link(fields.get('url'),draft=True)
            if old and (old['title'],old['url'])==(title,url):raise ValueError('This is already the current working draft.')
        did=conn.execute('INSERT INTO work_draft(case_id,title,url,file_id,kind,actor_id,reason,created_at) VALUES (?,?,?,?,?,?,?,?)',
                         (case_id,title,url,fid,kind,user['id'],reason,tz.now_iso())).lastrowid
        work._event(conn,user,case_id,'draft_changed',{'reason':reason,'draft_id':did,'previous_draft_id':old['id'] if old else None,'title':title})
        return did


def files(conn,case_id):
    return rows(conn,'''SELECT f.* FROM work_support_file f WHERE case_id=? AND NOT EXISTS(
        SELECT 1 FROM work_support_retired r WHERE r.file_id=f.id) ORDER BY f.id DESC''',(case_id,))


def add_file(conn,user,case_id,fields):
    with transaction(conn):
        user,case=writable(conn,user,case_id)
        title=work._text(fields.get('title'),'Supporting file name',250)
        url,fid,_=link(fields.get('url'))
        if any(f['file_id']==fid for f in files(conn,case_id)):raise docs.Conflict('This supporting file is already listed.')
        sid=conn.execute('INSERT INTO work_support_file(case_id,title,url,file_id,actor_id,created_at) VALUES (?,?,?,?,?,?)',
                        (case_id,title,url,fid,user['id'],tz.now_iso())).lastrowid
        work._event(conn,user,case_id,'support_added',{'reason':title,'support_id':sid})
        return sid


def retire_file(conn,user,case_id,support_id,reason):
    with transaction(conn):
        user,case=writable(conn,user,case_id)
        found=next((f for f in files(conn,case_id) if f['id']==support_id),None)
        if not found:raise docs.Conflict('This file is no longer in the supporting list. Reload the page.')
        if found['actor_id']!=user['id'] and not can_manage(conn,user,case):raise permissions.Denied('Only the person who added this file or a work coordinator can remove it.')
        reason=work._text(reason,'Reason for removing the link',2000)
        conn.execute('INSERT INTO work_support_retired VALUES (?,?,?,?)',(support_id,user['id'],reason,tz.now_iso()))
        work._event(conn,user,case_id,'support_removed',{'reason':reason,'support_id':support_id,'title':found['title']})


def post(conn,user,case_id,task_id,revision,draft_id,note,support_id=None):
    with transaction(conn):
        user,case=writable(conn,user,case_id)
        found=rows(conn,'SELECT * FROM work_task WHERE id=? AND case_id=?',(task_id,case_id))
        if not found or not can_handoff(conn,user,case,found[0]):raise permissions.Denied('This contribution handoff is not available to you.')
        task=found[0];work._check_revision(task,revision)
        draft=current(conn,case_id)
        if (draft['id'] if draft else 0)!=draft_id:raise docs.Conflict('The working draft changed. Review it before recording this handoff.')
        if support_id is not None and not any(f['id']==support_id for f in files(conn,case_id)):
            raise ValueError('Choose an active supporting file from this work item.')
        note=work._text(note,'Handoff note',4000)
        hid=conn.execute('''INSERT INTO work_handoff(case_id,task_id,actor_id,note,task_snapshot_json,draft_id,support_id,created_at)
            VALUES (?,?,?,?,?,?,?,?)''',(case_id,task_id,user['id'],note,json.dumps(task,sort_keys=True),draft_id or None,support_id,tz.now_iso())).lastrowid
        work._event(conn,user,case_id,'handoff_recorded',{'task_id':task_id,'title':task['title'],'reason':note,'handoff_id':hid})
        return hid


def page(conn,user,case_id,task_id=None,before=None,draft_before=None,file_before=None):
    user=permissions.actor(conn,user);case=work.get(conn,user,case_id)
    tasks=rows(conn,'SELECT * FROM work_task WHERE case_id=? ORDER BY id',(case_id,))
    if task_id is not None and not any(t['id']==task_id for t in tasks):raise permissions.Denied('Contribution unavailable.')
    notes=rows(conn,'''SELECT h.*,d.title AS draft_title,d.url AS draft_url,f.title AS support_title,f.url AS support_url
        FROM work_handoff h LEFT JOIN work_draft d ON d.id=h.draft_id LEFT JOIN work_support_file f ON f.id=h.support_id
        WHERE h.case_id=? AND (? IS NULL OR h.task_id=?) AND (? IS NULL OR h.id<?) ORDER BY h.id DESC LIMIT 31''',
        (case_id,task_id,task_id,before,before))
    for note in notes:note['snapshot']=json.loads(note.pop('task_snapshot_json'))
    history=rows(conn,'SELECT * FROM work_draft WHERE case_id=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT 11',(case_id,draft_before,draft_before))
    archived=rows(conn,'''SELECT f.*,r.reason AS removal_reason FROM work_support_file f JOIN work_support_retired r ON r.file_id=f.id WHERE f.case_id=? AND (? IS NULL OR f.id<?) ORDER BY f.id DESC LIMIT 11''',(case_id,file_before,file_before))
    return dict(archived_files=archived[:10],file_cursor=archived[9]['id'] if len(archived)>10 else None,case=case,draft=current(conn,case_id),support_files=files(conn,case_id),tasks=tasks,
                handoff_tasks=[t for t in tasks if can_handoff(conn,user,case,t)],
                notes=notes[:30],next_cursor=notes[29]['id'] if len(notes)>30 else None,
                draft_history=history[:10],draft_cursor=history[9]['id'] if len(history)>10 else None,
                can_manage=can_manage(conn,user,case),viewer_id=user['id'],selected_task=task_id)
