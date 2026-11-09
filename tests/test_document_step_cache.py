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
        ('UPDATE resource_person SET designation=designation',()),
        ('UPDATE org_unit SET path=path',()),
        ("UPDATE app_setting SET value=value WHERE key='documents.enabled'",()),
        ('INSERT INTO document_access VALUES (1,?,?)',(u[0]['id'],'test')),
    ]:
        old=c.execute('SELECT token FROM document_step_generation').fetchone()[0]
        c.execute(sql,args);c.commit()
        assert c.execute('SELECT token FROM document_step_generation').fetchone()[0]!=old
    old=c.execute('SELECT token FROM document_step_generation').fetchone()[0]
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
