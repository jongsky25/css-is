"""Versioned OCR interpretation corrections using isolated synthetic records."""
import json
import pytest
import documents as docs
import documents_permissions as permissions
import documents_understanding as understanding
import storage as storage
from test_documents import registry, register
from test_documents_understanding import reviewed


def correction(**changes):
    return {**reviewed(),'review_confirmed':'yes','reason':'Checked the signed source, page 2',**changes}


def test_review_preserves_original_and_every_revision_without_rerouting(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    before_notices=conn.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]
    first=understanding.revise(conn,users[0],doc['id'],doc['revision'],correction(need_0_output='Revised matrix',need_0_deadline='2026-12-01'))
    assert first['revision']==doc['revision']+1 and first['reconcile']==1
    assert first['due_date']==doc['due_date'] and first['lead_id']==doc['lead_id']
    assert conn.execute('SELECT COUNT(*) FROM document_assignment').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM document_notice').fetchone()[0]>before_notices
    history,more=understanding.history(conn,doc['id'])
    assert not more and [item['revision'] for item in history]==[2,1]
    assert history[1]['values']['need_0_output']=='Comments matrix'
    assert history[0]['values']['need_0_output']=='Revised matrix'
    assert history[0]['actor_id']==users[0]['id'] and history[0]['reason']==correction()['reason']
    event=json.loads(conn.execute("SELECT detail_json FROM document_event WHERE action='understanding_review'").fetchone()[0])
    assert event=={'review_revision':2,'reason':correction()['reason']}
    understanding.revise(conn,users[1],doc['id'],first['revision'],correction(need_0_output='Final matrix'))
    assert understanding.read(conn,doc['id'])['need_0_output']=='Final matrix'
    history,_=understanding.history(conn,doc['id'])
    assert [item['revision'] for item in history]==[3,2,1]
    assert history[0]['actor_id']==users[1]['id']


def test_legacy_document_can_capture_review_and_migration_is_repeatable(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit)
    storage.init_db(conn)
    storage.init_db(conn)
    assert understanding.history(conn,doc['id'])==([],False)
    understanding.revise(conn,users[0],doc['id'],doc['revision'],correction())
    entries,_=understanding.history(conn,doc['id'])
    assert len(entries)==1 and entries[0]['revision']==1


def test_stale_retries_do_not_overwrite_or_duplicate(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    understanding.revise(conn,users[0],doc['id'],doc['revision'],correction(need_0_output='First correction'))
    with pytest.raises(docs.Conflict):
        understanding.revise(conn,users[0],doc['id'],doc['revision'],correction(need_0_output='Stale overwrite'))
    assert understanding.read(conn,doc['id'])['need_0_output']=='First correction'
    assert len(understanding.history(conn,doc['id'])[0])==2


@pytest.mark.parametrize('change',[
    {'review_confirmed':''},{'reason':''},{'need_0_confirmed':''},{'focus_confirmed':''},
    {'focus_primary':'unsupported'},{'need_0_deadline':'2026-02-30'},{'needs_status':'information_only'}])
def test_invalid_review_is_atomic(registry,change):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    saved=understanding.read(conn,doc['id'])
    with pytest.raises(ValueError):
        understanding.revise(conn,users[0],doc['id'],doc['revision'],correction(**change))
    assert understanding.read(conn,doc['id'])==saved
    assert docs.raw(conn,doc['id'])['revision']==doc['revision']
    assert conn.execute('SELECT COUNT(*) FROM document_understanding_revision').fetchone()[0]==0


@pytest.mark.parametrize('state',['closed','cancelled','released','awaiting_acknowledgment','in_review','approved','signed','ready_to_release'])
def test_frozen_document_states_block_review(registry,state):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    conn.execute('UPDATE document SET status=? WHERE id=?',(state,doc['id']));conn.commit()
    with pytest.raises(permissions.Denied):
        understanding.revise(conn,users[0],doc['id'],doc['revision'],correction())
    assert conn.execute('SELECT COUNT(*) FROM document_understanding_revision').fetchone()[0]==0


def test_view_access_does_not_grant_edit_and_restricted_record_stays_private(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    conn.execute('INSERT INTO document_access VALUES (?,?,?)',(doc['id'],users[3]['id'],'explicit'));conn.commit()
    assert docs.get(conn,users[3],doc['id'])
    with pytest.raises(permissions.Denied): understanding.revise(conn,users[3],doc['id'],doc['revision'],correction())
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],));conn.commit()
    with pytest.raises(permissions.Denied): understanding.revise(conn,users[1],doc['id'],doc['revision'],correction())


@pytest.mark.parametrize('field,value',[('archived_at','2026-11-06'),('canonical_id',999),('direction','OUT')])
def test_archived_merged_and_outgoing_records_block_review(registry,field,value):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    if field=='canonical_id': value=register(conn,users[0],unit)['id']
    conn.execute('UPDATE document SET '+field+'=? WHERE id=?',(value,doc['id']));conn.commit()
    with pytest.raises(ValueError): understanding.revise(conn,users[0],doc['id'],doc['revision'],correction())


def test_pending_director_instruction_allows_review_but_never_assigns(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    conn.execute("UPDATE document SET instruction_state='pending' WHERE id=?",(doc['id'],));conn.commit()
    updated=understanding.revise(conn,users[1],doc['id'],doc['revision'],correction())
    assert updated['instruction_state']=='pending' and updated['lead_id']==doc['lead_id']


def test_history_is_bounded_and_paginated(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    for index in range(12):
        doc=understanding.revise(conn,users[0],doc['id'],doc['revision'],correction(need_0_output=f'Matrix {index}'))
    entries,more=understanding.history(conn,doc['id'])
    assert len(entries)==10 and more
    older,more=understanding.history(conn,doc['id'],entries[-1]['revision'])
    assert [item['revision'] for item in older]==[3,2,1] and not more


def test_audit_failure_rolls_back_snapshot_history_and_document_revision(registry,monkeypatch):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    before=understanding.read(conn,doc['id'])
    def fail(*args,**kwargs): raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(docs,'event',fail)
    with pytest.raises(RuntimeError): understanding.revise(conn,users[0],doc['id'],doc['revision'],correction())
    assert understanding.read(conn,doc['id'])==before
    assert conn.execute('SELECT COUNT(*) FROM document_understanding_revision').fetchone()[0]==0
    assert docs.raw(conn,doc['id'])['revision']==doc['revision']


def test_explicit_clear_keeps_original_as_history(registry):
    conn,users,unit,_=registry
    doc=register(conn,users[0],unit,**reviewed())
    understanding.revise(conn,users[0],doc['id'],doc['revision'],{
        'needs_status':'unclear','reason':'Source attachment replaced; prior reading needs review','review_confirmed':'yes'})
    assert understanding.read(conn,doc['id'])['need_0_action']==''
    entries,_=understanding.history(conn,doc['id'])
    assert entries[1]['values']['need_0_action']=='Submit comments'
