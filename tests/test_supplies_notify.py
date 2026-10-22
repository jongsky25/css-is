"""S4.1 thresholds, durable warning delivery, episodes, retries and scoped notices."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_notify as notify
import supplies_corrections as corrections
import supplies_stock as stock
import supplies_permissions as permissions
from supplies_storage import Conflict, Denied, Missing, install
from tests.test_supplies import supplies_db, key, create, fields, setup_catalog, hidden
from tests.test_supplies_requests import request_db, get
from tests.test_supplies_approvals import approval_db
from tests.test_supplies_backorders import ready, cancel, receipt
from tests.test_supplies_issues import issue
from tests.test_supplies_corrections import correction
from tests.conftest import session_token


def notices(c):return c.execute('SELECT COUNT(*) FROM supply_notice').fetchone()[0]


def opening(c,u,item,quantity):
    return stock.post_opening(c,u[1],item,{'quantity':quantity,'effective_date':'2026-10-19','reason':'Synthetic count'},expected_revision=1,operation_key=key())


@pytest.mark.parametrize('on_hand,reserved,threshold,physical,availability',[
    (0,0,0,'Out of stock','Out of stock'),(0,0,5,'Out of stock','Out of stock'),
    (5,0,5,'Normal','Available'),(4,0,5,'Critical','Low available'),
    (5,5,5,'Normal','Fully reserved'),(4,4,5,'Critical','Fully reserved'),
    (10,6,5,'Normal','Low available'),(10,5,5,'Normal','Available'),(1,0,0,'Normal','Available')])
def test_warning_boundaries(on_hand,reserved,threshold,physical,availability):
    result=notify.classify(on_hand,reserved,threshold)
    assert (result['physical_label'],result['availability_label'])==(physical,availability)


def test_unrecorded_stock_is_not_a_stockout_and_zero_opening_is(approval_db):
    c,u,_,_,item=approval_db;other=create(c,u[1],code='ZERO',critical_level=0)['id']
    assert notify.status(c,u[1],other)['physical_label']=='Stock not recorded'
    assert not notify.list_warnings(c,u[1])['warnings'] and notices(c)==0
    opening(c,u,other,0)
    assert notify.list_warnings(c,u[1])['warnings'][0]['id']==other
    assert notices(c)==1


def test_reservations_issue_stockout_and_recovery_create_expected_versions(approval_db):
    c,u,_,_,item=approval_db;r=ready(c,u,item,10)
    assert notify.status(c,u[1],item)['availability_label']=='Fully reserved'
    assert notices(c)==1
    release=issue(c,u,r,10)['id']
    assert notify.status(c,u[1],item)['physical_label']=='Out of stock' and notices(c)==2
    assert [r[0] for r in c.execute('SELECT version FROM supply_notice ORDER BY id')]==[1,2]
    correction(c,u,'return',release,5)
    assert notify.status(c,u[1],item)['availability_label']=='Available'
    assert c.execute('SELECT COUNT(*) FROM supply_notice WHERE resolved_at IS NOT NULL').fetchone()[0]==2
    correction(c,u,'stocktake',item,1)
    assert notices(c)==3
    assert c.execute('SELECT COUNT(*) FROM supply_alert_episode').fetchone()[0]==2


def test_partial_recovery_and_refresh_do_not_spam_but_halving_worsens(approval_db):
    c,u,_,_,item=approval_db;correction(c,u,'stocktake',item,4)
    assert notices(c)==1
    correction(c,u,'stocktake',item,3)
    notify.reconcile_alerts(c,u[1],operation_key=key())
    assert notices(c)==1
    correction(c,u,'stocktake',item,2)
    assert notices(c)==2
    correction(c,u,'stocktake',item,4)
    correction(c,u,'stocktake',item,2)
    assert notices(c)==2
    correction(c,u,'stocktake',item,1)
    assert notices(c)==3
    for _ in range(3):
        notify.reconcile_alerts(c,u[1],operation_key=key())
        notify.list_warnings(c,u[1]);notify.list_notices(c,u[1])
    assert notices(c)==3


def test_threshold_edits_recalculate_and_resolve_without_stock_mutation(approval_db):
    c,u,_,_,item=approval_db;original=[tuple(r) for r in c.execute('SELECT * FROM supply_stock_movement')]
    s.update_item(c,u[1],item,fields(critical_level=11),expected_revision=1,operation_key=key())
    assert notices(c)==1 and notify.status(c,u[1],item)['physical_label']=='Critical'
    s.update_item(c,u[1],item,fields(critical_level=10),expected_revision=2,operation_key=key())
    assert not notify.list_warnings(c,u[1])['warnings']
    assert notify.list_notices(c,u[1],unread=True)['unread_count']==0
    s.update_item(c,u[1],item,fields(critical_level=0),expected_revision=3,operation_key=key())
    correction(c,u,'stocktake',item,0)
    assert notices(c)==2
    assert original==[tuple(r) for r in c.execute("SELECT * FROM supply_stock_movement WHERE kind='opening'")]


def test_delivery_failure_cannot_undo_stock_and_retry_never_replays_it(approval_db,monkeypatch):
    c,u,_,_,item=approval_db
    def fail(*a,**kw):raise RuntimeError('Synthetic notice failure')
    with monkeypatch.context() as patch:
        patch.setattr(notify,'_deliver',fail)
        result=correction(c,u,'stocktake',item,2)
        assert result['on_hand']==2 and stock.stock_totals(c,u[1],item)['on_hand']==2
        assert c.execute('SELECT COUNT(*) FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0]==1
        assert c.execute('SELECT attempts FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0]==1
        assert not notices(c)
    before=[tuple(r) for r in c.execute('SELECT * FROM supply_stock_movement')]
    notify.reconcile_alerts(c,u[1],operation_key=key())
    assert notices(c)==1 and not notify.list_warnings(c,u[1])['pending_count']
    assert before==[tuple(r) for r in c.execute('SELECT * FROM supply_stock_movement')]


def test_pending_low_recovery_and_recurrence_keep_distinct_episodes(approval_db,monkeypatch):
    c,u,_,_,item=approval_db
    def fail(*a,**kw):raise RuntimeError('Synthetic unavailable delivery')
    with monkeypatch.context() as patch:
        patch.setattr(notify,'_deliver',fail)
        for count in (4,10,2):correction(c,u,'stocktake',item,count)
    notify.process_pending(c)
    assert notices(c)==2
    found=c.execute('SELECT resolved_at FROM supply_alert_episode ORDER BY id').fetchall()
    assert found[0][0] is not None and found[1][0] is None
    assert stock.stock_totals(c,u[1],item)['on_hand']==2


def test_current_recipients_only_new_custodian_receives_active_version_once(approval_db):
    c,u,_,_,item=approval_db;correction(c,u,'stocktake',item,4)
    s.grant_role(c,u[0],u[4]['id'],'auditor',operation_key=key())
    assert notices(c)==1
    s.grant_role(c,u[0],u[3]['id'],'custodian',operation_key=key())
    assert notices(c)==2 and len(notify.list_notices(c,u[3])['notices'])==1
    for _ in range(2):notify.reconcile_alerts(c,u[1],operation_key=key())
    assert notices(c)==2
    assert notify.list_warnings(c,u[4])['warnings']
    for who in (0,2,4):
        with pytest.raises(Denied):notify.list_notices(c,u[who])
    foreign=notify.list_notices(c,u[3])['notices'][0]['id']
    with pytest.raises(Missing):notify.get_notice(c,u[1],foreign)
    own=notify.list_notices(c,u[1])['notices'][0]['id']
    grant=c.execute("SELECT id FROM supply_role_grant WHERE user_id=? AND role='custodian' AND revoked_at IS NULL",(u[1]['id'],)).fetchone()[0]
    s.revoke_role(c,u[0],grant,expected_revision=1,operation_key=key())
    with pytest.raises(Denied):notify.get_notice(c,u[1],own)
    with pytest.raises(Denied):notify.mark_read(c,u[1],own,operation_key=key())
    data={'quantity':'1','reason':'Synthetic further loss','effective_date':'2026-10-20','confirmed':'yes'}
    data['preview_token']=corrections.preview(c,u[3],'stocktake',item,data)['preview_token']
    corrections.post_stocktake(c,u[3],item,data,operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_notice WHERE recipient_id=?',(u[1]['id'],)).fetchone()[0]==1


def test_notice_read_is_authorized_idempotent_and_allowed_when_disabled(approval_db):
    c,u,_,_,item=approval_db;correction(c,u,'stocktake',item,2)
    notice=notify.list_notices(c,u[1])['notices'][0];op=key()
    assert notify.get_notice(c,u[1],notice['id'])['read_at'] is None
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
    result=notify.mark_read(c,u[1],notice['id'],operation_key=op)
    assert notify.mark_read(c,u[1],notice['id'],operation_key=op)==result
    assert notify.list_notices(c,u[1],unread=True)['unread_count']==0
    notify.reconcile_alerts(c,u[1],operation_key=key())
    assert notices(c)==1
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[1]['id'],));c.commit()
    with pytest.raises(Denied):notify.mark_read(c,u[1],notice['id'],operation_key=op)


def test_deactivation_resolves_history_and_repeated_install_preserves_evidence(approval_db):
    c,u,_,_,item=approval_db;correction(c,u,'stocktake',item,1)
    s.deactivate_item(c,u[1],item,expected_revision=1,operation_key=key(),reason='Synthetic retired item')
    assert not notify.list_warnings(c,u[1])['warnings']
    assert notify.list_notices(c,u[1])['notices'][0]['resolved_at']
    for table in ('supply_notice','supply_alert_event'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(f'DELETE FROM {table}')
        c.rollback()
    before=[tuple(r) for r in c.execute('SELECT * FROM supply_notice')];install(c);install(c)
    assert before==[tuple(r) for r in c.execute('SELECT * FROM supply_notice')]
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_competing_dispatchers_do_not_duplicate_deliveries(approval_db,monkeypatch):
    c,u,_,path,item=approval_db
    def fail(*a,**kw):raise RuntimeError('Synthetic pending warning')
    with monkeypatch.context() as patch:
        patch.setattr(notify,'_deliver',fail);correction(c,u,'stocktake',item,2)
    barrier=Barrier(2)
    def worker(_):
        conn=st.connect(path)
        try:barrier.wait();return notify.process_pending(conn)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
    assert sum(results)==1 and notices(c)==1


def test_gets_are_read_only_http_scopes_csrf_and_disabled_notice_read(approval_db,app_mod):
    c,u,_,path,item=approval_db;correction(c,u,'stocktake',item,2);notice=notify.list_notices(c,u[1])['notices'][0]
    old=app_mod.DB;app_mod.DB=path
    try:
        with TestClient(app_mod.app) as client:
            client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
            tables=('supply_notice','supply_alert_event','supply_alert_episode','supply_item_alert','supply_operation','supply_event','supply_stock_movement')
            before={table:[tuple(r) for r in c.execute(f'SELECT * FROM {table}')] for table in tables}
            for url in ('/supplies/warnings','/supplies/notices',f"/supplies/notices/{notice['id']}"):
                assert client.get(url).status_code==200
            assert before=={table:[tuple(r) for r in c.execute(f'SELECT * FROM {table}')] for table in tables}
            assert notify.get_notice(c,u[1],notice['id'])['read_at'] is None
            page=client.get(f"/supplies/notices/{notice['id']}")
            fields={'csrf':hidden(page.text,'csrf'),'operation_key':key()};target=f"/supplies/notices/{notice['id']}/read"
            assert client.post(target,data={**fields,'csrf':'bad'}).status_code==403
            assert client.post(target,data=fields,headers={'Origin':'https://foreign.example'}).status_code==403
            c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'");c.commit()
            assert client.post(target,data=fields,follow_redirects=False).status_code==303
            page=client.get('/supplies/warnings');fields={'csrf':hidden(page.text,'csrf'),'operation_key':key()}
            assert client.post('/supplies/warnings/reconcile',data=fields,follow_redirects=False).status_code==303
            client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
            for url in ('/supplies/warnings','/supplies/notices',f"/supplies/notices/{notice['id']}"):
                assert client.get(url).status_code==403
    finally:app_mod.DB=old


def test_original_stock_retry_and_failed_delivery_are_independent(approval_db,monkeypatch):
    c,u,_,_,item=approval_db;r=ready(c,u,item,10)
    from tests.test_supplies_issues import data
    import supplies_issues as issues
    fields=data(c,u,r,10);op=key()
    def fail(*a,**kw):raise RuntimeError('Synthetic notice failure')
    with monkeypatch.context() as patch:
        patch.setattr(notify,'_deliver',fail)
        first=issues.post_issue(c,u[1],r,fields,expected_revision=3,operation_key=op)
        assert issues.post_issue(c,u[1],r,fields,expected_revision=3,operation_key=op)==first
    before=c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]
    assert issues.post_issue(c,u[1],r,fields,expected_revision=3,operation_key=op)==first
    assert before==c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0]==2
    assert stock.stock_totals(c,u[1],item)['on_hand']==0 and notices(c)==2


def test_warning_enqueue_failure_rolls_back_uncommitted_business_change(approval_db,monkeypatch):
    c,u,_,_,item=approval_db
    before=[tuple(r) for r in c.execute('SELECT * FROM supply_stock_movement')]
    def fail(*a,**kw):raise RuntimeError('Synthetic queue persistence failure')
    monkeypatch.setattr(notify,'enqueue',fail)
    with pytest.raises(RuntimeError):correction(c,u,'stocktake',item,2)
    assert before==[tuple(r) for r in c.execute('SELECT * FROM supply_stock_movement')]
    assert stock.stock_totals(c,u[1],item)['on_hand']==10


def test_warning_notice_pagination_and_read_replay_payload_conflict(approval_db):
    c,u,_,_,item=approval_db
    for _ in range(13):
        correction(c,u,'stocktake',item,1)
        correction(c,u,'stocktake',item,10)
        correction(c,u,'stocktake',item,0)
        correction(c,u,'stocktake',item,10)
    first=notify.list_notices(c,u[1]);second=notify.list_notices(c,u[1],page=2)
    assert len(first['notices'])==25 and first['has_next'] and len(second['notices'])==1
    op=key();notify.mark_read(c,u[1],first['notices'][0]['id'],operation_key=op)
    with pytest.raises(Conflict):notify.mark_read(c,u[1],first['notices'][1]['id'],operation_key=op)
    for i in range(26):
        other=create(c,u[1],code=f'LOW-{i:02d}')['id'];opening(c,u,other,0)
    first=notify.list_warnings(c,u[1]);second=notify.list_warnings(c,u[1],page=2)
    assert len(first['warnings'])==25 and first['has_next'] and len(second['warnings'])==1


def test_bounded_backlog_retry_makes_progress_without_requeueing_unchanged_items(approval_db,monkeypatch):
    c,u,_,_,item=approval_db
    def fail(*a,**kw):raise RuntimeError('Synthetic dispatcher downtime')
    with monkeypatch.context() as patch:
        patch.setattr(notify,'process_pending',fail)
        for i in range(6):
            other=create(c,u[1],code=f'QUEUE-{i}')['id'];opening(c,u,other,0)
    count=c.execute('SELECT COUNT(*) FROM supply_alert_event').fetchone()[0]
    assert notify.process_pending(c,limit=2)==2
    notify.reconcile_alerts(c,u[1],operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_alert_event').fetchone()[0]==count
    assert not notify.list_warnings(c,u[1])['pending_count'] and notices(c)==6
