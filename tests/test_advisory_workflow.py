"""Private advisory foundation with synthetic accounts and no outbound effects."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import uuid

import pytest

import activity_advisory as aa
import advisory_storage
import advisory_workflow as aw
import documents as docs
import documents_operations as ops
import documents_permissions as permissions
import storage as st


FIELDS = {'headline':'Synthetic advisory','attention':'Staff','body':'Please review.',
          'rows':[], 'qr_url':'https://office.test/e/synthetic','contact_name':'Test contact',
          'contact_phone':'','contact_email':'contact@example.invalid'}


@pytest.fixture
def drafts(db_path,monkeypatch):
    conn=st.connect(db_path); st.init_db(conn)
    users=[]
    for name,role in [('draft-author','encoder'),('draft-stranger','admin'),('draft-reviewer','viewer')]:
        uid=st.create_admin_user(conn,name,'hash','salt',role,active=True)
        users.append(st.get_admin_user_by_id(conn,uid))
    unit=st.add_org_unit(conn,'Synthetic division','division','TEST/D1')
    other=st.add_org_unit(conn,'Other division','division','TEST/D2')
    ev=st.create_event(conn,'Synthetic activity','2026-12-15',created_by=users[0]['username'])
    ev=st.get_event(conn,ev['event_token'])
    st.set_setting(conn,'documents.enabled','1'); st.set_setting(conn,'work.enabled','1');conn.commit()
    monkeypatch.setattr(aw,'_render',lambda fields,number:{'pdf':b'%PDF-'+aw.encoded([fields,number]).encode(),
                                                           'png':b'PNG-'+aw.encoded([fields,number]).encode()})
    import mailer
    monkeypatch.setattr(mailer,'send',lambda *a,**k:pytest.fail('Unexpected outbound email'))
    yield conn,users,unit,other,ev,db_path
    conn.close()


def options(c,ev,unit,**kwargs):
    return dict(unit_id=unit,audience='internal',external='',expected_revision=0,
                expected_source=aw.source_hash(c,ev),operation_key=str(uuid.uuid4()),**kwargs)


def create(data,fields=None):
    c,users,unit,_,ev,_=data
    return aw.save_draft(c,users[0],ev['event_token'],fields or FIELDS,**options(c,ev,unit))


def test_identity_noop_replay_audience_and_exact_bytes(drafts,monkeypatch):
    c,users,unit,_,ev,_=drafts
    opts=options(c,ev,unit)
    first=aw.save_draft(c,users[0],ev['event_token'],FIELDS,**opts)
    assert first['ordinal']==1 and first['revision']==1
    assert st.get_setting(c,'advisory.default_contact_name','')==''
    assert aw.save_draft(c,users[0],ev['event_token'],FIELDS,**opts)['id']==first['id']
    with pytest.raises(docs.Conflict):
        aw.save_draft(c,users[0],ev['event_token'],{**FIELDS,'headline':'Changed'},**opts)
    opts.update(operation_key=str(uuid.uuid4()),expected_revision=1)
    assert aw.save_draft(c,users[0],ev['event_token'],FIELDS,**opts)['ordinal']==1
    assert c.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM document_job').fetchone()[0]==0
    old=aw.artifact(c,users[0],first['id'],first['current_revision'],'pdf')
    opts.update(operation_key=str(uuid.uuid4()),audience='both',external='ONE@example.invalid, one@example.invalid',summary='Add external audience')
    second=aw.save_draft(c,users[0],ev['event_token'],FIELDS,**opts)
    assert second['number']==first['number'] and second['ordinal']==2
    assert second['payload']['external']==['one@example.invalid']
    monkeypatch.setattr(aw,'_render',lambda *a:pytest.fail('Read must not render'))
    assert aw.artifact(c,users[0],first['id'],first['current_revision'],'pdf')==old
    assert len(aw.history(c,users[0],first['id']))==2
    assert c.execute('SELECT COUNT(*) FROM advisory_record').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM document WHERE id=?',(first['document_id'],)).fetchone()[0]==1


def test_visibility_counts_and_current_actor(drafts):
    c,users,unit,other,ev,_=drafts
    first=create(drafts)
    assert aw.list_visible(c,users[0])['total']==1
    assert aw.list_visible(c,users[0],unit_id=other)['total']==0
    # users[1] is a Super Administrator: owner decision (Nov 25, 2026) lets it see every advisory.
    assert aw.list_visible(c,users[1])['total']==1 and aw.get_visible(c,users[1],first['id'])['id']==first['id']
    for user in users[2:]:
        assert aw.list_visible(c,user)['total']==0
        with pytest.raises(permissions.Denied): aw.get_visible(c,user,first['id'])
        with pytest.raises(permissions.Denied): aw.artifact(c,user,first['id'],first['current_revision'],'pdf')
        with pytest.raises(permissions.Denied): aw.history(c,user,first['id'])
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    with pytest.raises(permissions.Denied):aw.get_visible(c,{**users[0],'active':1,'role':'admin'},first['id'])


def test_generic_bypasses_and_old_mutations_are_refused(drafts):
    c,users,unit,_,ev,_=drafts
    first=create(drafts); doc=docs.raw(c,first['document_id'])
    assert not permissions.can_release(c,users[0],doc)
    with pytest.raises(ValueError,match='Open the advisory screen'):docs.mutate(c,users[0],doc['id'],doc['revision'],'review',{'decision':'approved'})
    with pytest.raises(ValueError):ops.queue(c,users[0],doc['id'],doc['revision'],'dispatch',{})
    with pytest.raises(ValueError):ops.attach(c,users[0],doc['id'],doc['revision'],'https://drive.google.com/file/d/x/view','minor','change')
    with pytest.raises(ValueError):ops.version(c,doc)
    with pytest.raises(ValueError):aa.save(c,ev,FIELDS,users[0])
    with pytest.raises(ValueError):aa.set_published(c,ev['id'],True)
    assert docs.raw(c,doc['id'])['approved_version'] is None
    assert c.execute('SELECT COUNT(*) FROM document_job').fetchone()[0]==0


def test_stale_source_and_draft_conflict_without_partial_writes(drafts):
    c,users,unit,_,ev,_=drafts
    first=create(drafts); opts=options(c,ev,unit); opts['expected_revision']=1;opts['summary']='Update'
    c.execute('UPDATE event SET venue=? WHERE id=?',('New venue',ev['id']));c.commit()
    with pytest.raises(docs.Conflict,match='Activity details changed'):
        aw.save_draft(c,users[0],ev['event_token'],{**FIELDS,'headline':'Changed'},**opts)
    ev=st.get_event(c,ev['event_token']);opts['expected_source']=aw.source_hash(c,ev)
    new=aw.save_draft(c,users[0],ev['event_token'],{**FIELDS,'headline':'Changed'},**opts)
    assert new['snapshot']==first['snapshot']
    opts['operation_key']=str(uuid.uuid4())
    with pytest.raises(docs.Conflict):aw.save_draft(c,users[0],ev['event_token'],FIELDS,**opts)
    assert len(aw.history(c,users[0],first['id']))==2


def test_legacy_public_freezes_and_failure_rolls_back(drafts,monkeypatch):
    c,users,unit,_,ev,_=drafts
    legacy=aa.save(c,ev,FIELDS,users[0]);aa.set_published(c,ev['id'],True)
    frozen=aw._render(aa.get(c,ev['id']),legacy['number'])
    opts=options(c,ev,unit,expected_legacy_revision=legacy['revision'])
    first=aw.save_draft(c,users[0],ev['event_token'],{**FIELDS,'headline':'Private replacement'},**opts)
    assert first['number']==legacy['number']
    assert aa.get(c,ev['id'])['headline']==legacy['headline']
    assert aw.existing_public(c,ev['id'],'pdf')==frozen['pdf']
    monkeypatch.setattr(aw,'_render',lambda *a:(_ for _ in ()).throw(ValueError('render failed')))
    opts.update(expected_revision=1,summary='Another version',operation_key=str(uuid.uuid4()))
    with pytest.raises(ValueError,match='render failed'):
        aw.save_draft(c,users[0],ev['event_token'],{**FIELDS,'headline':'Oops'},**opts)
    assert len(aw.history(c,users[0],first['id']))==1
    assert aw.existing_public(c,ev['id'],'pdf')==frozen['pdf']


def test_install_and_immutable_history(drafts):
    c,users,_,_,_,_=drafts
    first=create(drafts)
    advisory_storage.install(c);c.commit()
    assert aw.get_visible(c,users[0],first['id'])['number']==first['number']
    for table in ('advisory_revision','advisory_artifact','advisory_existing_public','advisory_save_request'):
        if table=='advisory_existing_public':continue
        with pytest.raises(sqlite3.IntegrityError):c.execute(f'DELETE FROM {table}')
        c.rollback()


@pytest.mark.parametrize('audience,external',[('bad',''),('internal','a@example.invalid'),('external',''),('both','not an address')])
def test_recipient_validation_is_atomic(drafts,audience,external):
    c,users,unit,_,ev,_=drafts
    opts=options(c,ev,unit);opts.update(audience=audience,external=external)
    with pytest.raises(ValueError):aw.save_draft(c,users[0],ev['event_token'],FIELDS,**opts)
    assert aw.for_event(c,ev['id']) is None and aa.get(c,ev['id']) is None


def test_two_simultaneous_saves_have_one_winner(drafts):
    c,users,unit,_,ev,path=drafts
    opts=options(c,ev,unit)
    def write():
        conn=st.connect(path)
        try:
            return aw.save_draft(conn,users[0],ev['event_token'],FIELDS,**{**opts,'operation_key':str(uuid.uuid4())})['id']
        except docs.Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:write(),range(2)))
    assert results.count('conflict')==1
    assert c.execute('SELECT COUNT(*) FROM advisory_record').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM advisory_revision').fetchone()[0]==1


def test_modules_disabled_and_initial_render_failure_leave_no_rows(drafts,monkeypatch):
    c,users,unit,_,ev,_=drafts
    st.set_setting(c,'work.enabled','0');c.commit()
    with pytest.raises(ValueError):create(drafts)
    st.set_setting(c,'work.enabled','1');c.commit()
    monkeypatch.setattr(aw,'_render',lambda *a:(_ for _ in ()).throw(ValueError('render failed')))
    with pytest.raises(ValueError):create(drafts)
    assert aa.get(c,ev['id']) is None
    assert c.execute('SELECT COUNT(*) FROM advisory_record').fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM document WHERE type='advisory'").fetchone()[0]==0


def test_filtered_register_pages_share_visibility_and_total(drafts):
    c,users,unit,other,ev,_=drafts
    first=create(drafts)
    ev2=st.create_event(c,'Second private draft','2026-12-16',created_by=users[0]['username'])
    ev2=st.get_event(c,ev2['event_token'])
    second=aw.save_draft(c,users[0],ev2['event_token'],FIELDS,**options(c,ev2,other))
    page=aw.list_visible(c,users[0],limit=1)
    assert page['total']==2 and page['items'][0]['id']==second['id'] and page['older']==second['id']
    older=aw.list_visible(c,users[0],limit=1,before=page['older'])
    assert older['total']==2 and older['items'][0]['id']==first['id'] and older['older'] is None
    filtered=aw.list_visible(c,users[0],unit_id=unit)
    assert filtered['total']==1 and [r['id'] for r in filtered['items']]==[first['id']]
    c.execute('DELETE FROM document_access WHERE document_id=?',(second['document_id'],));c.commit()
    assert aw.list_visible(c,users[0])['total']==1
    with pytest.raises(permissions.Denied):aw.get_visible(c,users[0],second['id'])
    vid=c.execute('SELECT version_id FROM advisory_revision WHERE id=?',(first['current_revision'],)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE document_file_version SET fingerprint='changed' WHERE id=?",(vid,))
    c.rollback()
