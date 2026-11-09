"""Snapshot membership caching must never outlive its authority or workflow inputs."""
import pytest
import storage as st
import documents_actions as actions
import documents_permissions as permissions
from tests.test_documents import registry
from tests.bench_document_steps import seed_scenario


def setup(registry):
    c,u,unit,_=registry
    seed_scenario(c,u,unit,65,'ordinary')
    actions.clear_step_indexes()
    return c,u


def read(c,user,**kwargs):
    return actions.page(c,user,today=kwargs.pop('today','2026-11-07'),**kwargs)


def test_hits_reuse_membership_but_read_fresh_page_without_writes(registry,monkeypatch):
    c,u=setup(registry);before=c.total_changes
    first=read(c,u[0]);original=actions._page_records
    def no_scan(*args,**kwargs):
        assert not kwargs.get('scan'), 'unchanged snapshot must not classify the full scope twice'
        return original(*args,**kwargs)
    monkeypatch.setattr(actions,'_page_records',no_scan)
    second=read(c,u[0]);assert second==first
    next_page=read(c,u[0],before=first['next_before'],before_due=first['next_due'])
    assert next_page['counts']==first['counts']
    assert {x['document_id'] for x in first['cards']}.isdisjoint({x['document_id'] for x in next_page['cards']})
    assert c.total_changes==before


def test_other_connection_revocation_and_deadline_change(registry):
    c,u=setup(registry)
    assert read(c,u[0])['counts']['all']==65
    path=c.execute('PRAGMA database_list').fetchone()[2]
    writer=st.connect(path)
    try:
        writer.execute("UPDATE document SET due_date='2026-11-06'");writer.commit()
        assert read(c,u[0],overdue='1')['counts']['all']==65
        writer.execute("UPDATE document SET visibility='restricted'");writer.commit()
        assert read(c,u[0])['counts']['all']==0
        writer.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));writer.commit()
        with pytest.raises(permissions.Denied):read(c,u[0])
    finally:writer.close()


def test_rollback_and_new_write_cannot_reuse_uncommitted_generation(registry):
    c,u=setup(registry)
    before=read(c,u[0]);old=c.execute('SELECT token FROM document_step_generation').fetchone()[0]
    c.execute("UPDATE document SET due_date='2026-11-06'")
    assert read(c,u[0],overdue='1')['counts']['all']==65
    rolled=c.execute('SELECT token FROM document_step_generation').fetchone()[0]
    c.rollback();assert c.execute('SELECT token FROM document_step_generation').fetchone()[0]==old
    c.execute("UPDATE document SET due_date='2026-11-09'")
    assert c.execute('SELECT token FROM document_step_generation').fetchone()[0]!=rolled
    c.commit();assert read(c,u[0],overdue='1')['counts']['all']==0
    assert read(c,u[0])['counts']==before['counts']


def test_actor_and_calendar_day_are_separate(registry):
    c,u=setup(registry)
    c.execute("UPDATE document SET due_date='2026-11-07'");c.commit()
    assert read(c,u[0],overdue='1')['counts']['all']==0
    assert read(c,u[0],overdue='1',today='2026-11-08')['counts']['all']==65
    assert read(c,u[3])['counts']['all']==0


def test_snapshot_held_during_concurrent_write_uses_old_generation(registry):
    c,u=setup(registry);read(c,u[0])
    writer=st.connect(c.execute('PRAGMA database_list').fetchone()[2])
    try:
        c.execute('BEGIN');c.execute('SELECT token FROM document_step_generation').fetchone()
        writer.execute("UPDATE document SET status='closed'");writer.commit()
        assert read(c,u[0])['counts']['all']==65
        c.rollback()
        assert read(c,u[0])['counts']['all']==0
    finally:writer.close()


def test_bounded_index_falls_back_to_exact_streaming(registry,monkeypatch):
    c,u=setup(registry);expected=read(c,u[0]);actions.clear_step_indexes()
    monkeypatch.setattr(actions,'_INDEX_REFERENCES',10)
    assert read(c,u[0])==expected
    assert not actions._INDEXES


def test_schema_install_and_all_dependency_writes_rotate_generation(registry):
    c,u=setup(registry)
    # Exercise less obvious dependencies: reviewer directory, OIC and module switches.
    for sql,args in [
        ("UPDATE resource_person SET designation='New role'",()),
        ("UPDATE org_unit SET path=path||'/new'",()),
        ("UPDATE app_setting SET value='0' WHERE key='documents.enabled'",()),
        ('INSERT INTO document_access VALUES (1,?,?)',(u[0]['id'],'test')),
    ]:
        old=c.execute('SELECT token FROM document_step_generation').fetchone()[0]
        c.execute(sql,args);c.commit()
        assert c.execute('SELECT token FROM document_step_generation').fetchone()[0]!=old
    old=c.execute('SELECT token FROM document_step_generation').fetchone()[0]
    st.init_db(c)
    assert c.execute('SELECT token FROM document_step_generation').fetchone()[0]==old
    c.execute("CREATE TABLE document_future_fact(id INTEGER PRIMARY KEY, value TEXT)")
    st.init_db(c)
    assert c.execute('SELECT token FROM document_step_generation').fetchone()[0]!=old


def test_shared_work_revision_invalidates_all_affected_source_counts(registry):
    c,u,unit,_=registry
    seed_scenario(c,u,unit,10,'review_release_graph')
    actions.clear_step_indexes()
    first=read(c,u[0]);assert first['counts']['attention']==0
    c.execute('UPDATE work_task SET revision=revision+1');c.commit()
    changed=read(c,u[0]);assert changed['counts']['attention']==10
    assert all(card['state']=='attention' for card in changed['cards'])


@pytest.mark.parametrize('change',[
    None,
    'UPDATE work_task SET revision=revision+1',
    "UPDATE document SET status='closed' WHERE id=1",
    'UPDATE document SET current_version=NULL WHERE id=1',
    "UPDATE document SET visibility='restricted',lead_id=NULL WHERE id=1",
])
def test_batch_review_matches_uncached_authority_and_exact_hash(registry,change):
    import documents
    import documents_registry
    import work_review
    c,u,unit,_=registry
    seed_scenario(c,u,unit,20,'review_release_graph')
    if change:c.execute(change);c.commit()
    docs=[documents.raw(c,n) for n in range(1,21)]
    before=c.total_changes
    with documents_registry.snapshot(c):
        batch=work_review.ReadBatch(c,u[0])
        expected=work_review.summaries(c,u[0],docs)
        assert {d['id']:value for d in docs if (value:=batch.summary(d)) is not None}==expected
        compact=work_review.ReadBatch(c,u[0],scope=permissions.RegistryScope(c,u[0]))
        assert {d['id']:value for d in docs if (value:=compact.summary(d,details=False)) is not None}=={
            did:{k:value[k] for k in ('case','current')} for did,value in expected.items()}

        for actor in u[1:]:
            expected=work_review.summaries(c,actor,docs)
            scoped=work_review.ReadBatch(c,actor,scope=permissions.RegistryScope(c,actor))
            assert {d['id']:value for d in docs if (value:=scoped.summary(d,details=False)) is not None}=={
                did:{k:value[k] for k in ('case','current')} for did,value in expected.items()}
    assert c.total_changes==before


def test_generation_distinguishes_noop_case_and_new_columns(registry):
    c,*_=registry
    c.execute('CREATE TABLE document_cache_probe(id INTEGER PRIMARY KEY, value TEXT COLLATE NOCASE)')
    st.init_db(c)
    c.execute("INSERT INTO document_cache_probe VALUES (1,'x')")
    token=lambda:c.execute('SELECT token FROM document_step_generation').fetchone()[0]
    before=token()
    c.execute('UPDATE document_cache_probe SET value=value')
    assert token()==before
    c.execute("UPDATE document_cache_probe SET value='X'")
    assert token()!=before
    before=token()
    c.execute('ALTER TABLE document_cache_probe ADD COLUMN extra TEXT')
    st.init_db(c)
    assert token()!=before
    before=token()
    c.execute("UPDATE document_cache_probe SET extra='new'")
    assert token()!=before


@pytest.mark.parametrize('change',[None,"UPDATE work_task SET status='todo' WHERE case_id=1",
                                  "UPDATE work_task SET status='cancelled' WHERE case_id=1"])
def test_batch_release_gate_matches_all_linked_cases(registry,change):
    import documents
    import documents_registry
    import work_completion
    c,u,unit,_=registry
    seed_scenario(c,u,unit,20,'review_release_graph')
    # A document can require both its review case and another completion case.
    c.execute("INSERT INTO work_completion_requirement VALUES (1,11,?,'Synthetic','2026-11-01')",(u[0]['id'],))
    if change:c.execute(change)
    c.commit()
    def outcome(check,doc):
        try:check(doc);return None
        except ValueError as error:return str(error)
    before=c.total_changes
    with documents_registry.snapshot(c):
        batch=work_completion.ReadBatch(c)
        for did in [1,2,11,12,1,11]:
            doc=documents.raw(c,did)
            assert outcome(batch.release_gate,doc)==outcome(lambda d:work_completion.release_gate(c,d),doc)
    assert c.total_changes==before


@pytest.mark.parametrize('alias',[False,True])
@pytest.mark.parametrize('signed',[False,True])
def test_compact_review_reads_preserve_hash_without_full_document_reads(registry,monkeypatch,alias,signed):
    import documents
    import documents_registry
    import work_review
    c,u,unit,_=registry
    seed_scenario(c,u,unit,10,'review_release_graph')
    if signed:
        vid=c.execute('''INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,parent_id,actor_id,created_at)
            VALUES (2,'https://example.test/signed','fake-signed','signed-hash','signed',2,?,'2026-11-01')''',(u[0]['id'],)).lastrowid
        c.execute('UPDATE document SET current_version=?,signed_version=? WHERE id=2',(vid,vid));c.commit()
    if alias:c.execute('UPDATE document SET canonical_id=2 WHERE id=1');c.commit()
    # Compare against the original full-record loader, including canonical resolution.
    original=work_review._review_source
    monkeypatch.setattr(work_review,'_review_source',documents.raw)
    expected=work_review.snapshot(c,1,2)
    monkeypatch.setattr(work_review,'_review_source',original)
    assert work_review.snapshot(c,1,2)==expected
    docs=[documents.raw(c,n) for n in range(2,11)]
    expected=work_review.summaries(c,u[0],docs)
    with documents_registry.snapshot(c):
        scope=permissions.RegistryScope(c,u[0])
        def full_record_read(*args,**kwargs):
            raise AssertionError('Compact review must not fetch full document records')
        monkeypatch.setattr(documents,'raw',full_record_read)
        batch=work_review.ReadBatch(c,u[0],scope=scope)
        for doc in docs:
            assert batch.summary(doc,details=False)=={
                k:expected[doc['id']][k] for k in ('case','current')}
