"""Lead/date filters keep grid, preferences and exports within the same authority."""
import csv
import io
import json
from datetime import date

import pytest

import documents_grid as grid
import storage as st
from tests.test_documents import registry
from tests.test_document_registry_pagination import seed_many
from tests.test_document_registry_views import state, create


def test_lead_date_selection_before_pagination_export_and_permission_recheck(registry):
    conn, users, unit, _ = registry
    ids = seed_many(conn, users[0], unit, 65, subject='Leadneedle')
    hidden = seed_many(conn, users[0], unit, 10, subject='Leadneedle hidden', visibility='restricted')
    seed_many(conn, users[0], unit, 5, subject='Unrelated')
    conn.execute("UPDATE document SET lead_id=?,due_date='2026-11-15',status='in_action'", (users[1]['id'],))
    conn.execute("UPDATE document SET due_date='2026-12-01' WHERE id>? AND id<=?", (ids[30],ids[-1]))
    conn.commit()
    params = {'queue':'OUT','q':'Leadneedle','lead_id':str(users[1]['id']),
              'due_from':'2026-11-01','due_to':'2026-11-30','status':'in_action',
              'verification':'verified','sort':'registered','dir':'asc'}
    first=grid.page(conn, users[4], params)
    second=grid.page(conn, users[4], {**params,'page':'2'})
    assert first['last_row']==31 and first['last_page']==2
    assert [r['id'] for r in first['data']+second['data']]==ids[:31]
    content,count=grid.export_csv(conn,users[4],{**params,'columns':'number,lead,due_date'})
    data=list(csv.reader(io.StringIO(content.removeprefix('\ufeff'))))
    assert count==31 and data[0]==['Number','Lead','Due date']
    assert [r[0] for r in data[1:]]==[f'REG-{i}' for i in ids[:31]]
    assert all(r[1]==users[1]['username'] for r in data[1:])
    assert not set(hidden)&{r['id'] for r in first['data']+second['data']}
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?",(ids[0],));conn.commit()
    refreshed=grid.page(conn,users[4],{**params,'page':'2'})
    assert refreshed['page']==1 and refreshed['last_row']==30
    assert grid.export_csv(conn,users[4],params)[1]==30
    assert grid.page(conn,users[4],{**params,'lead_id':str(users[0]['id'])})['last_row']==0
    assert grid.page(conn,users[4],{**params,'verification':'pending'})['last_row']==0


def test_inclusive_one_sided_dates_unknowns_inactive_and_unresolved_leads(registry,monkeypatch):
    conn,users,unit,_=registry
    monkeypatch.setattr(grid.tz,'today_local',lambda:date(2026,11,15))
    ids=seed_many(conn,users[0],unit,9)
    dates=['2026-10-31','2026-11-01','2026-11-30','2026-12-01',None,'','not-a-date','2026-02-30','20261115']
    for i,due in zip(ids,dates):
        conn.execute('UPDATE document SET due_date=? WHERE id=?',(due,i))
    conn.execute("UPDATE document SET status='closed' WHERE id=?",(ids[2],))
    conn.execute('UPDATE document SET lead_id=? WHERE id=?',(users[1]['id'],ids[1]));conn.commit()
    def found(**options): return {r['id'] for r in grid.page(conn,users[4],options)['data']}
    assert found(due_from='2026-11-01',due_to='2026-11-30')=={ids[1],ids[2],ids[8]}
    assert found(due_to='2026-11-01')=={ids[0],ids[1]}
    assert found(due_from='2026-11-30')=={ids[2],ids[3]}
    assert found(due_from='2026-11-01',due_to='2026-11-01')=={ids[1]}
    assert found(lead_id='unresolved',due_from='2026-11-01',due_to='2026-11-30')=={ids[2],ids[8]}
    assert found(deadline='unknown',due_to='2026-12-31')==set()
    assert found(deadline='overdue',due_from='2026-11-01',due_to='2026-11-30')=={ids[1]}


@pytest.mark.parametrize('options',[
    {'lead_id':'0'},{'lead_id':'01'},{'lead_id':'-1'},{'lead_id':'1.0'},{'lead_id':'1 OR 1=1'},
    {'lead_id':'9223372036854775808'},{'lead_id':True},{'lead_id':[]},{'lead_id':'١'},
    {'due_from':'2026-02-29'},{'due_to':'2026-13-01'},{'due_from':'20261101'},
    {'due_from':'2026-11-01T00:00:00'},{'due_to':None},{'due_from':True},
    {'due_from':'2026-12-01','due_to':'2026-11-01'}])
def test_bad_filters_rejected_for_grid_export_and_preferences(registry,options):
    conn,users,_,_=registry
    for run in (lambda:grid.page(conn,users[0],options),lambda:grid.export_csv(conn,users[0],options),
                lambda:grid.view_state(state(**options))):
        with pytest.raises(ValueError):run()


def test_private_views_round_trip_old_defaults_and_stale_lead_keeps_narrowing(registry):
    conn,users,unit,_=registry
    old=state(deadline='overdue')
    conn.execute('INSERT INTO document_registry_view(user_id,name,state_json,created_at,updated_at) VALUES (?,?,?,?,?)',
                 (users[0]['id'],'Old view',json.dumps(old),'2026-10-24','2026-10-24'));conn.commit()
    restored=grid.views(conn,users[0])[0]['state']
    assert all(restored[field]=='' for field in grid.LEAD_DATE_FIELDS)
    assert restored['deadline']=='overdue'
    ids=seed_many(conn,users[0],unit,1)
    conn.execute("UPDATE document SET lead_id=?,due_date='2026-11-15' WHERE id=?",(users[1]['id'],ids[0]));conn.commit()
    saved=create(conn,users[0],'November lead',lead_id=str(users[1]['id']),due_from='2026-11-01',due_to='2026-11-30')
    assert grid.page(conn,users[0],saved['state'])['last_row']==1
    conn.execute('UPDATE document SET lead_id=NULL WHERE id=?',(ids[0],));conn.commit()
    reopened=next(v for v in grid.views(conn,users[0]) if v['id']==saved['id'])
    assert reopened['state']['lead_id']==str(users[1]['id'])
    assert grid.page(conn,users[0],reopened['state'])['last_row']==0
    assert grid.export_csv(conn,users[0],{**reopened['state'],'columns':'number'})[1]==0
    assert grid.views(conn,users[1])==[]


def test_lead_choices_use_authorized_queue_search_and_keep_inactive_leads(registry):
    conn,users,unit,_=registry
    visible=seed_many(conn,users[0],unit,1,subject='Visiblelead')
    hidden=seed_many(conn,users[0],unit,1,subject='Hiddenlead',visibility='restricted')
    conn.execute('UPDATE document SET lead_id=? WHERE id=?',(users[1]['id'],visible[0]))
    conn.execute('UPDATE document SET lead_id=? WHERE id=?',(users[3]['id'],hidden[0]))
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[1]['id'],));conn.commit()
    assert grid.lead_choices(conn,users[4],{'queue':'OUT'})==[{'id':users[1]['id'],'name':users[1]['username']}]
    assert grid.lead_choices(conn,users[4],{'q':'Hiddenlead'})==[]
    assert grid.lead_choices(conn,users[4],{'queue':'IN'})==[]


def test_http_filters_validation_and_export_cache_headers(app_mod,viewer):
    conn=st.connect(app_mod.DB);st.set_setting(conn,'documents.enabled','1')
    user=st.get_admin_user(conn,'viewer@test.local')
    unit=conn.execute('SELECT id FROM org_unit LIMIT 1').fetchone()[0]
    ids=seed_many(conn,user,unit,2)
    conn.execute("UPDATE document SET lead_id=?,due_date='2026-11-15' WHERE id=?",(user['id'],ids[0]));conn.commit()
    params={'lead_id':str(user['id']),'due_from':'2026-11-01','due_to':'2026-11-30'}
    response=viewer.get('/documents/grid-data',params=params)
    assert response.status_code==200 and response.json()['last_row']==1
    assert response.headers['cache-control']=='no-store'
    response=viewer.get('/documents/grid-export.csv',params=params)
    assert response.status_code==200 and response.headers['x-export-rows']=='1'
    assert response.headers['cache-control']=='no-store'
    for path in ('/documents/grid-data','/documents/grid-export.csv'):
        bad=viewer.get(path,params={'due_from':'2026-12-01','due_to':'2026-11-01'})
        assert bad.status_code==400 and bad.headers['cache-control']=='no-store'
    conn.close()
