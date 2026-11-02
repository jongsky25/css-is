"""Private metadata-only document lookup, current policy and ephemeral search."""
import pytest

import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_documents as reads
from tests.test_work import workspace, document
from tests.test_telegram_bot import setup, update, submit, NOW
from tests.test_telegram_links import linking, claimed


@pytest.fixture
def doc_env(linking,monkeypatch):
    c,_,_,client,_=linking
    monkeypatch.setenv('CSS_TELEGRAM_DOCUMENTS_READ_ENABLED','1')
    _,_,code=claimed(linking,scopes=['documents.read'])
    submit(client,update(2,text='/confirm '+code));bot.process_updates(c,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing provider call'))
    return linking


def command(env,text='/documents',number=10):
    response=submit(env[3],update(number,text=text))
    assert response.status_code==200
    return response.json()


def seed(env,owner=0,subject='Synthetic document'):
    c,users,*_=env
    unit=c.execute("SELECT id FROM org_unit WHERE path='WORK/D1'").fetchone()[0]
    return document(c,users[owner],unit,subject=subject)


def test_document_lookup_search_and_fresh_workflow_status(doc_env):
    c,*_=doc_env
    doc=seed(doc_env)
    text=command(doc_env)['text']
    assert doc['number'] in text and 'Synthetic document' in text
    assert 'Synthetic document' in command(doc_env,'/find_documents synthetic',11)['text']
    c.execute("UPDATE document SET status='in_review',instruction_state='pending' WHERE id=?",(doc['id'],));c.commit()
    text=command(doc_env,'/document_status '+str(doc['id']),12)['text']
    assert 'in review' in text and 'awaiting routing instruction' in text and 'Approval:' in text
    assert '/documents/'+str(doc['id']) in text
    assert reads.common.units(text)<=4096


def test_private_and_restricted_records_do_not_leak(doc_env):
    c,*_=doc_env
    other=seed(doc_env,owner=3,subject='Other staff secret')
    own=seed(doc_env,subject='Restricted secret')
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(own['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=?',(own['id'],));c.commit()
    text=command(doc_env)['text']
    assert 'Other staff secret' not in text and 'Restricted secret' not in text
    denied=command(doc_env,'/document_status '+str(other['id']),11)['text']
    assert denied==command(doc_env,'/document_status 99999',12)['text']
    assert denied==command(doc_env,'/document_status '+str(own['id']),13)['text']


def test_search_text_and_rendered_subject_never_persist_in_telegram_rows(doc_env):
    c,*_=doc_env
    seed(doc_env,subject='EphemeralSearchNeedle subject')
    assert 'EphemeralSearchNeedle' in command(doc_env,'/find_documents EphemeralSearchNeedle')['text']
    for table,column in [('telegram_update','payload_json'),('telegram_delivery','projection_json')]:
        assert all('EphemeralSearchNeedle' not in (r[0] or '') for r in c.execute(f'SELECT {column} FROM {table}'))


def test_metadata_search_excludes_sender_and_literal_wildcards(doc_env):
    c,*_=doc_env
    doc=seed(doc_env)
    c.execute("UPDATE document SET sender='OnlyInSenderNeedle' WHERE id=?",(doc['id'],));c.commit()
    assert 'No matching' in command(doc_env,'/find_documents OnlyInSenderNeedle')['text']
    assert 'No matching' in command(doc_env,'/find_documents %',11)['text']
    assert 'No matching' in command(doc_env,"/find_documents ' OR 1=1 --",12)['text']


def test_paging_filters_visibility_before_limit(doc_env):
    c,*_=doc_env
    for i in range(7):seed(doc_env,subject='Visible document '+str(i))
    for i in range(7):seed(doc_env,owner=3,subject='Hidden document '+str(i))
    text=command(doc_env)['text']
    assert 'Visible document' in text and 'Hidden document' not in text
    next_command=text.split('Next page: ')[1].splitlines()[0]
    second=command(doc_env,next_command,11)['text']
    assert 'Visible document' in second and 'Next page:' not in second
    assert reads.common.units(text)<=4096


@pytest.mark.parametrize('change',['grant','flag','module','disconnect','account'])
def test_permission_changes_block_new_reads(doc_env,monkeypatch,change):
    c,users,_,_,payload=doc_env
    seed(doc_env)
    if change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='documents.read'",(links.stamp(NOW),));c.commit()
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_DOCUMENTS_READ_ENABLED','0')
    elif change=='module':st.set_setting(c,'documents.enabled','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    monkeypatch.setattr(reads.permissions,'RegistryScope',lambda *a:pytest.fail('Revoked source query'))
    assert 'method' not in command(doc_env)


@pytest.mark.parametrize('text',['/documents -1','/documents 9223372036854775808','/find_documents','/document_status nope','/find_documents '+'x'*81])
def test_invalid_arguments_do_not_query_documents(doc_env,monkeypatch,text):
    monkeypatch.setattr(reads.permissions,'RegistryScope',lambda *a:pytest.fail('Invalid source query'))
    assert command(doc_env,text)['text']==reads.USAGE


def test_own_lookup_works_with_work_module_paused_and_duplicate_is_not_replayed(doc_env):
    c,*_=doc_env
    seed(doc_env);st.set_setting(c,'work.enabled','0')
    assert 'Synthetic document' in command(doc_env)['text']
    assert 'method' not in command(doc_env)
    assert bot.deliver(c,NOW)==0


def test_group_and_direct_mode_cannot_read_documents(doc_env,monkeypatch):
    seed(doc_env)
    message=update(10,text='/documents');message['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(doc_env[3],message).json()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(doc_env,'/documents',11)


def test_unrelated_read_grant_does_not_grant_document_access(doc_env):
    c,*_=doc_env
    seed(doc_env)
    c.execute("UPDATE telegram_grant SET action='work.read' WHERE action='documents.read'");c.commit()
    assert 'method' not in command(doc_env)


def test_canonical_alias_resolves_current_permitted_record(doc_env):
    c,*_=doc_env
    old=seed(doc_env,subject='Old alias')
    current=seed(doc_env,subject='Current canonical')
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(current['id'],old['id']));c.commit()
    text=command(doc_env,'/document_status '+str(old['id']))['text']
    assert 'Current canonical' in text and 'Old alias' not in text
    assert 'Old alias' not in command(doc_env,'/documents',11)['text']
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(old['id'],current['id']));c.commit()
    assert 'unavailable' in command(doc_env,'/document_status '+str(old['id']),12)['text']


def test_final_reply_fence_honors_revocation_during_render(doc_env,monkeypatch):
    c,*_=doc_env
    seed(doc_env)
    render=reads.render
    def revoked(*args):
        text=render(*args)
        c2=args[0]
        c2.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='documents.read'",(links.stamp(NOW),))
        return text
    monkeypatch.setattr(reads,'render',revoked)
    assert 'method' not in command(doc_env)
    assert not c.execute("SELECT 1 FROM telegram_delivery WHERE dedupe_key LIKE 'task-response:%'").fetchone()
