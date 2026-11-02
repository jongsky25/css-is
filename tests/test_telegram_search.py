"""Private metadata-only cross-source search with current source authorization."""
from datetime import timedelta

import pytest

import backups
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_search as search
from tests.test_work import workspace, document
from tests.test_telegram_bot import setup, submit, update, NOW
from tests.test_telegram_links import linking, claimed
from tests.test_telegram_menu import menu_env, command
from tests.test_telegram_work import work_env, seed as work_seed
from tests.test_telegram_documents import doc_env, seed as doc_seed
from tests.test_telegram_brief import grant


def meeting(env,title,day=None,**values):
    c,users,*_=env
    return st.cal_create(c,title,day or NOW.astimezone(search.common.ZONE).date().isoformat(),
                         by=users[3]['username'],**values)


def test_each_source_keeps_its_scope_and_valid_detail_commands(menu_env,monkeypatch):
    c,users,*_=menu_env
    grant(menu_env,'work.read',monkeypatch);grant(menu_env,'documents.read',monkeypatch)
    item,task=work_seed(menu_env,title='Budget work')
    c.execute('UPDATE work_task SET title=? WHERE id=?',('Budget task',task['id']));c.commit()
    doc=doc_seed(menu_env,subject='Budget document')
    eid=meeting(menu_env,'Budget meeting',audience='bureau')
    text=command(menu_env,'/find budget')['text']
    for title in ('Budget work','Budget task','Budget document','Budget meeting'):assert title in text
    for detail in (f"/task_status {item['id']} {task['id']}",f"/work_status {item['id']}",f"/document_status {doc['id']}"):
        assert detail in text
    assert '/calendar/entries/'+str(eid) in text
    assert 'Status: todo' in text and 'Workflow:' in text
    assert 'Work '+str(item['id']) in command(menu_env,f"/work_status {item['id']}",11)['text']
    assert 'Task '+str(task['id']) in command(menu_env,f"/task_status {item['id']} {task['id']}",12)['text']
    assert 'Document '+str(doc['id']) in command(menu_env,f"/document_status {doc['id']}",13)['text']
    assert '/find WORDS' in command(menu_env,'/menu',14)['text']


def test_document_scope_search_is_literal_unicode_metadata_only_and_not_retained(doc_env):
    c,*_=doc_env
    doc=doc_seed(doc_env,subject='Straße OnlyInSubject')
    c.execute("UPDATE document SET sender='OnlyInSender' WHERE id=?",(doc['id'],));c.commit()
    text=command(doc_env,'/find STRASSE')['text']
    assert 'Straße OnlyInSubject' in text and 'Meetings ·' not in text and 'My tasks ·' not in text
    for number,term in enumerate(('OnlyInSender','%',"' OR 1=1 --"),11):
        assert 'No matching permitted records' in command(doc_env,'/find '+term,number)['text']
    for table,col in (('telegram_update','payload_json'),('telegram_delivery','projection_json')):
        assert all('STRASSE' not in (r[0] or '') and 'OnlyInSubject' not in (r[0] or '') for r in c.execute(f'SELECT {col} FROM {table}'))


def test_task_ownership_and_hidden_linked_document_precede_limits(work_env,monkeypatch):
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing send'))
    c,users,*_=work_env
    visible,own=work_seed(work_env,title='Needle visible work')
    c.execute('UPDATE work_task SET title=? WHERE id=?',('Needle visible task',own['id']));c.commit()
    for i in range(4):
        item,task=work_seed(work_env,title='Needle hidden work')
        doc=document(c,users[0],item['unit_id'])
        import work
        work.link_document(c,users[0],item['id'],item['revision'],doc['id'])
        c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],))
        c.execute('DELETE FROM document_access WHERE document_id=?',(doc['id'],))
        c.execute('UPDATE work_task SET title=? WHERE id=?',('Needle hidden task',task['id']));c.commit()
    _,other=work_seed(work_env,owner=3,title='Needle accessible work')
    c.execute('UPDATE work_task SET title=?,submission=? WHERE id=?',('Needle other task','OnlyInOutput',other['id']));c.commit()
    text=command(work_env,'/find Needle')['text']
    assert 'Needle visible task' in text and 'Needle visible work' in text
    assert 'Needle hidden' not in text and 'Needle other task' not in text
    assert 'OnlyInOutput' not in text
    assert 'No matching permitted records' in command(work_env,'/find OnlyInOutput',11)['text']


def test_document_visibility_before_limit_and_archive_exclusion(doc_env):
    c,*_=doc_env
    visible=doc_seed(doc_env,subject='Needle visible document')
    for _ in range(4):doc_seed(doc_env,owner=3,subject='Needle hidden document')
    archived=doc_seed(doc_env,subject='Needle archived document')
    c.execute("UPDATE document SET archived_at='2026-10-25' WHERE id=?",(archived['id'],));c.commit()
    text=command(doc_env,'/find Needle')['text']
    assert 'Needle visible document' in text and 'hidden document' not in text and 'archived document' not in text
    assert 'More matches' not in text


def test_meetings_use_source_visibility_kind_title_and_manila_range(menu_env):
    c,users,*_=menu_env
    today=NOW.astimezone(search.common.ZONE).date()
    meeting(menu_env,'Needle visible meeting',audience='bureau')
    for _ in range(4):meeting(menu_env,'Needle secret meeting',audience='people',people=[users[3]['id']])
    meeting(menu_env,'Needle outside window',(today+timedelta(days=31)).isoformat(),audience='bureau')
    meeting(menu_env,'Needle not a meeting',kind='travel',audience='bureau')
    meeting(menu_env,'Ordinary title',audience='bureau',note='OnlyInMeetingNotes',meeting_url='https://example.invalid/OnlyInMeetingURL')
    text=command(menu_env,'/find Needle')['text']
    assert 'Needle visible meeting' in text
    for hidden in ('Needle secret','Needle outside','Needle not a meeting'):assert hidden not in text
    assert 'through '+(today+timedelta(days=30)).isoformat() in text
    assert 'More matches' not in text
    assert 'No matching permitted records' in command(menu_env,'/find OnlyInMeeting',11)['text']


def test_meeting_recurrences_keep_occurrence_links_and_calendar_details(menu_env):
    eid=meeting(menu_env,'Recurring Needle',day='2026-10-26',audience='bureau',rrule='FREQ=WEEKLY;BYDAY=MO;UNTIL=20261130')
    text=command(menu_env,'/find Needle')['text']
    assert '/calendar 2026-10-26' in text and '/calendar 2026-11-02' in text
    assert '/calendar/entries/'+str(eid)+'?date=2026-10-26' in text
    assert 'More matches available' in text


@pytest.mark.parametrize('change',['flag','grant','module'])
def test_revoked_or_paused_source_is_not_queried(doc_env,monkeypatch,change):
    c,*_=doc_env
    if change=='flag':monkeypatch.setenv('CSS_TELEGRAM_DOCUMENTS_READ_ENABLED','0')
    elif change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=?",(links.stamp(NOW),));c.commit()
    else:st.set_setting(c,'documents.enabled','0')
    monkeypatch.setattr(search.permissions,'RegistryScope',lambda *a:pytest.fail('Unavailable source queried'))
    text=command(doc_env,'/find anything')['text']
    assert 'No search sources' in text and 'Documents ·' not in text
    assert '/find WORDS' not in command(doc_env,'/menu',11)['text']


@pytest.mark.parametrize('change',['inactive','disconnect','restore','fingerprint','direct','group','topic'])
def test_private_identity_and_transport_lifecycle_fences(menu_env,monkeypatch,change):
    c,users,path,_,payload=menu_env
    if change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='fingerprint':c.execute("UPDATE telegram_connection SET bot_fingerprint='other'");c.commit()
    elif change=='direct':monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    packet=update(10,text='/find Needle')
    if change=='group':packet['message']['chat']={'id':-100,'type':'group'}
    if change=='topic':packet['message']['message_thread_id']=7
    assert 'method' not in submit(menu_env[3],packet).json()


@pytest.mark.parametrize('text',['/find','/find '+'x'*81,'/find a\x00b','/find a\nb'])
def test_invalid_input_never_queries_business_sources(menu_env,monkeypatch,text):
    monkeypatch.setattr(search.office_calendar,'items_between',lambda *a,**kw:pytest.fail('Invalid query read source'))
    assert command(menu_env,text)['text']==search.USAGE


def test_bounded_unicode_results_and_duplicate_updates_make_no_business_writes(menu_env,monkeypatch):
    c,*_=menu_env
    grant(menu_env,'work.read',monkeypatch);grant(menu_env,'documents.read',monkeypatch)
    for _ in range(3):
        doc_seed(menu_env,subject='Needle '+'📑'*150)
        item,task=work_seed(menu_env,title='Needle '+'📑'*150)
        c.execute('UPDATE work_task SET title=? WHERE id=?',('Needle '+'📑'*150,task['id']));c.commit()
        meeting(menu_env,'Needle '+'📑'*150,audience='bureau')
    tables=('document','work_case','work_task','calendar_entry','telegram_grant')
    before={table:list(c.execute('SELECT * FROM '+table)) for table in tables}
    text=command(menu_env,'/find Needle')['text']
    assert search.common.units(text)<=4096 and 'More matches' in text
    assert 'method' not in command(menu_env,'/find Needle')
    assert before=={table:list(c.execute('SELECT * FROM '+table)) for table in tables}
    assert not c.execute('SELECT count(*) FROM telegram_operation').fetchone()[0]
