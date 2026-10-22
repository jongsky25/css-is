"""S1.4 synthetic reconciliation, concurrency and all-or-nothing adoption."""
import json
import sqlite3

import pytest
from starlette.testclient import TestClient

import auth
import supplies as s
import supplies_import as imports
import supplies_import_review as review
import supplies_stock as stock
from supplies_storage import Conflict, Denied, Disabled, Invalid
from tests.test_supplies import supplies_db, setup_catalog, create, key, hidden
from tests.test_supplies_import import workbook
from tests.conftest import session_token


def stage(c, u, data=None):
    return imports.preview_import(c, u[1], data or workbook(unit='Pack'), 'synthetic.xlsx', operation_key=key())['id']


def row_id(c, batch):
    return c.execute('SELECT id FROM supply_import_row WHERE batch_id=?', (batch,)).fetchone()[0]


def revision(c, batch):
    return c.execute('SELECT revision FROM supply_import_batch WHERE id=?', (batch,)).fetchone()[0]


def include(**changes):
    return dict(decision='include', item_choice='new', code='SYN-PAPER', description='Synthetic paper', unit='Ream',
                quantity='13', critical_level='3', target_level='20', reason='Counted 13 reams; card Pack label corrected after verification.', **changes)


def save(c, u, batch, fields=None, row=None, **kw):
    return review.save_decision(c, u[1], batch, row or row_id(c,batch), fields or include(),
                               expected_revision=kw.pop('expected_revision',revision(c,batch)), operation_key=kw.pop('operation_key',key()), **kw)


def finish(c, u, batch, **changes):
    fields={'count_date':'2026-10-19','basis':'Physical count at close of business; transactions after cutover start in the new ledger.', 'confirmed':'yes'}
    fields.update(changes)
    return review.finalize(c,u[1],batch,fields,expected_revision=revision(c,batch),operation_key=key())


def apply(c,u,batch,**kw):
    state=review.review_state(c,u[1],batch)
    return review.apply(c,u[1],batch,expected_revision=kw.pop('expected_revision',revision(c,batch)),
                        selection_sha256=kw.pop('selection_sha256',state['selection']['selection_sha256']),
                        operation_key=kw.pop('operation_key',key()),**kw)


def second_row(c,batch):
    # Synthetic staged evidence for multi-row atomicity scenarios.
    c.execute("INSERT INTO supply_import_row(batch_id,source_sheet,source_row,raw_json) VALUES (?,'Summary Sheet',8,?)",
              (batch,json.dumps({'name':'Synthetic second','source_sheet':'Summary Sheet','source_row':8})))
    c.commit()
    return c.execute('SELECT MAX(id) FROM supply_import_row').fetchone()[0]


def test_review_requires_decisions_and_confirmed_physical_count(supplies_db):
    c,u,_,_=supplies_db; setup_catalog(c,u); b=stage(c,u)
    with pytest.raises(Invalid,match='Every source row'): finish(c,u,b)
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0]==0
    for fields in ({'decision':'exclude','reason':''}, {**include(),'quantity':''}, {**include(),'critical_level':''}, {**include(),'quantity':'1.5'}):
        with pytest.raises(Invalid): save(c,u,b,fields)
    save(c,u,b)
    with pytest.raises(Invalid,match='Confirm'): finish(c,u,b,confirmed='')
    with pytest.raises(Invalid,match='future'): finish(c,u,b,count_date='2099-01-01')
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==0


def test_apply_exact_selection_exclusions_evidence_and_replay(supplies_db):
    c,u,_,_=supplies_db; setup_catalog(c,u); source=workbook(unit='Pack'); b=stage(c,u,source); excluded=second_row(c,b)
    original=c.execute('SELECT raw_json FROM supply_import_row WHERE id=?',(row_id(c,b),)).fetchone()[0]
    save(c,u,b); save(c,u,b,{'decision':'exclude','reason':'Unit unresolved; require recount.'},row=excluded)
    finish(c,u,b); rev=revision(c,b); digest=review.review_state(c,u[1],b)['selection']['selection_sha256']; op=key()
    first=apply(c,u,b,operation_key=op)
    assert first['status']=='applied'
    assert apply(c,u,b,expected_revision=rev,selection_sha256=digest,operation_key=op)==first
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0]==1
    movement=c.execute('SELECT quantity_delta,effective_date,source_id,source_line_id FROM supply_stock_movement').fetchone()
    assert tuple(movement)==(13,'2026-10-19',b,row_id(c,b))
    item=c.execute('SELECT code,unit,critical_level,target_level FROM supply_item').fetchone()
    assert tuple(item)==('SYN-PAPER','Ream',3,20)
    state=review.review_state(c,u[1],b)['selection']
    assert state['included_count']==state['excluded_count']==1 and len(state['posted'])==1
    assert state['rows'][1]['reason']=='Unit unresolved; require recount.'
    assert state['source_sha256']==imports.parse_workbook(source,'synthetic.xlsx')['source_sha256']
    assert c.execute('SELECT raw_json FROM supply_import_row WHERE id=?',(row_id(c,b),)).fetchone()[0]==original
    with pytest.raises(Conflict): apply(c,u,b)
    with pytest.raises(Conflict): save(c,u,b)
    with pytest.raises(sqlite3.IntegrityError): c.execute('UPDATE supply_import_review SET detail_json=?',('{}',))
    c.rollback()
    with pytest.raises(sqlite3.IntegrityError): c.execute("UPDATE supply_import_batch SET status='preview' WHERE id=?",(b,))
    c.rollback()


def test_decision_replay_revision_and_reopen_finalized_selection(supplies_db):
    c,u,_,_=supplies_db; setup_catalog(c,u); b=stage(c,u); op=key()
    first=save(c,u,b,operation_key=op)
    assert save(c,u,b,operation_key=op,expected_revision=1)==first
    with pytest.raises(Conflict): save(c,u,b,expected_revision=1)
    finish(c,u,b); state=review.review_state(c,u[1],b)['selection']; rev=revision(c,b)
    save(c,u,b,{**include(),'quantity':'0'})
    assert review.review_state(c,u[1],b)['selection'] is None
    with pytest.raises(Conflict): review.apply(c,u[1],b,expected_revision=rev,selection_sha256=state['selection_sha256'],operation_key=key())
    finish(c,u,b); apply(c,u,b)
    assert c.execute('SELECT quantity_delta FROM supply_stock_movement').fetchone()[0]==0


def test_unresolved_excluded_only_duplicate_mapping_and_wrong_row(supplies_db):
    c,u,_,_=supplies_db; setup_catalog(c,u); b=stage(c,u); r2=second_row(c,b)
    save(c,u,b,{'decision':'exclude','reason':'Await unit reconciliation'})
    with pytest.raises(Invalid,match='Every'): finish(c,u,b)
    save(c,u,b,{'decision':'exclude','reason':'Await count'},row=r2)
    with pytest.raises(Invalid,match='at least one'): finish(c,u,b)
    save(c,u,b); save(c,u,b,row=r2)
    with pytest.raises(Invalid,match='distinct'): finish(c,u,b)
    b2=stage(c,u)
    with pytest.raises(Denied): save(c,u,b2,row=r2)


@pytest.mark.parametrize('change',['stock','revision','inactive','code_collision','failure_mid_batch'])
def test_atomic_conflicts_and_failure_leave_no_partial_items_or_thresholds(supplies_db, monkeypatch, change):
    c,u,_,_=supplies_db; setup_catalog(c,u); existing=create(c,u[1])['id']; b=stage(c,u); r2=second_row(c,b)
    save(c,u,b)
    fields={**include(),'item_choice':f'{existing}:1'}
    save(c,u,b,fields,row=r2); finish(c,u,b)
    if change=='stock':
        stock.post_opening(c,u[1],existing,{'quantity':'2','effective_date':'2026-10-19','reason':'Earlier verified count'},expected_revision=1,operation_key=key())
    elif change=='revision':
        c.execute('UPDATE supply_item SET revision=revision+1 WHERE id=?',(existing,));c.commit()
    elif change=='inactive':
        c.execute('UPDATE supply_item SET active=0 WHERE id=?',(existing,));c.commit()
    elif change=='code_collision':
        create(c,u[1],code='SYN-PAPER')
    else:
        original=stock._post_opening
        def fail(conn,user,item,**kw):
            if item['id']==existing: raise RuntimeError('Synthetic failure after first item')
            return original(conn,user,item,**kw)
        monkeypatch.setattr(stock,'_post_opening',fail)
    before=[tuple(x) for x in c.execute('SELECT * FROM supply_item ORDER BY id')]
    movements=c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]
    with pytest.raises(RuntimeError if change=='failure_mid_batch' else Conflict): apply(c,u,b)
    assert [tuple(x) for x in c.execute('SELECT * FROM supply_item ORDER BY id')]==before
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==movements
    assert c.execute('SELECT status FROM supply_import_batch WHERE id=?',(b,)).fetchone()[0]=='reviewed'
    assert c.execute("SELECT COUNT(*) FROM supply_import_review WHERE kind='apply'").fetchone()[0]==0


def test_same_source_in_another_batch_cannot_be_applied(supplies_db):
    c,u,_,_=supplies_db; setup_catalog(c,u); data=workbook(); a=stage(c,u,data); b=stage(c,u,data)
    save(c,u,a); finish(c,u,a)
    save(c,u,b,{**include(),'code':'OTHER-CODE'});finish(c,u,b)
    apply(c,u,a)
    with pytest.raises(Conflict,match='already been applied'): apply(c,u,b)
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0]==1


def test_current_authority_flag_and_hash_guard(supplies_db):
    c,u,_,_=supplies_db; setup_catalog(c,u); b=stage(c,u);save(c,u,b);finish(c,u,b)
    with pytest.raises(Conflict,match='selection changed'):apply(c,u,b,selection_sha256='a'*64)
    with pytest.raises(Denied):review.apply(c,u[0],b,expected_revision=revision(c,b),selection_sha256='a'*64,operation_key=key())
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    with pytest.raises(Disabled):apply(c,u,b)
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==0


def test_http_full_review_apply_csrf_and_readonly(supplies_db,app_mod):
    c,u,_,path=supplies_db;setup_catalog(c,u);b=stage(c,u); old=app_mod.DB;app_mod.DB=path
    target=f'/supplies/import/{b}'
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            page=client.get(target);assert page.status_code==200
            token=hidden(page.text,'csrf')
            def post(suffix,fields):
                return client.post(target+suffix,data={'csrf':token,'operation_key':key(),'revision':str(revision(c,b)),**fields},follow_redirects=False)
            assert post(f'/rows/{row_id(c,b)}',{**include(),'csrf':'bad'}).status_code==403
            assert post(f'/rows/{row_id(c,b)}',include()).status_code==303
            assert post('/finalize',{'count_date':'2026-10-19','basis':'Verified count and cutover','confirmed':'yes'}).status_code==303
            page=client.get(target);assert 'Apply finalized opening balances' in page.text and 'SYN-PAPER' in page.text
            digest=review.review_state(c,u[1],b)['selection']['selection_sha256']
            assert post('/apply',{'selection_sha256':digest}).status_code==303
            page=client.get(target);assert 'Applied: 1 opening balances recorded' in page.text
            assert 'No inventory balances have changed' not in page.text and 'Save row decision' not in page.text
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            assert client.get(target).status_code==403
            assert post('/apply',{'selection_sha256':digest}).status_code==403
    finally:app_mod.DB=old


def test_existing_mapping_thresholds_and_retries_after_apply(supplies_db):
    c,u,_,_=supplies_db;setup_catalog(c,u);item=create(c,u[1])['id'];b=stage(c,u)
    fields={**include(),'item_choice':f'{item}:1'};op=key()
    result=save(c,u,b,fields,operation_key=op);finish(c,u,b);apply(c,u,b)
    assert save(c,u,b,fields,expected_revision=1,operation_key=op)==result
    assert tuple(c.execute('SELECT critical_level,target_level,revision FROM supply_item WHERE id=?',(item,)).fetchone())==(3,20,2)
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0]==1
    assert c.execute("SELECT COUNT(*) FROM supply_event WHERE entity_type='item' AND action='import_opening'").fetchone()[0]==1
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'",(u[0]['id'],u[1]['id']));c.commit()
    with pytest.raises(Denied):save(c,u,b,fields,expected_revision=1,operation_key=op)


def test_audit_failure_rolls_back_all_stock_and_review(supplies_db,monkeypatch):
    import storage as st
    c,u,_,_=supplies_db;setup_catalog(c,u);b=stage(c,u);save(c,u,b);finish(c,u,b)
    def failure(*args,**kwargs):raise RuntimeError('Synthetic audit failure')
    monkeypatch.setattr(st,'audit',failure)
    with pytest.raises(RuntimeError,match='audit failure'):apply(c,u,b)
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM supply_operation WHERE action='import_apply'").fetchone()[0]==0
    assert c.execute('SELECT status FROM supply_import_batch').fetchone()[0]=='reviewed'


def test_two_connections_cannot_apply_same_review_twice(supplies_db):
    import storage as st
    c,u,_,path=supplies_db;setup_catalog(c,u);b=stage(c,u);save(c,u,b);finish(c,u,b)
    rev=revision(c,b);digest=review.review_state(c,u[1],b)['selection']['selection_sha256']
    other=st.connect(path)
    try:
        apply(c,u,b)
        with pytest.raises(Conflict):review.apply(other,u[1],b,expected_revision=rev,selection_sha256=digest,operation_key=key())
        assert other.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==1
    finally:other.close()


def test_additive_installer_preserves_applied_review(supplies_db):
    from supplies_storage import install
    c,u,_,_=supplies_db;setup_catalog(c,u);b=stage(c,u);save(c,u,b);finish(c,u,b);apply(c,u,b)
    before=[tuple(r) for r in c.execute('SELECT * FROM supply_import_review ORDER BY id')]
    install(c);install(c)
    assert [tuple(r) for r in c.execute('SELECT * FROM supply_import_review ORDER BY id')]==before
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
