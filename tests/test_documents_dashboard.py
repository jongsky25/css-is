"""Dashboard aggregates and every drill-down share the registry's current authority."""
from datetime import date
from urllib.parse import urlsplit, parse_qs

import pytest

import documents_dashboard as dashboard
import documents_grid as grid
import documents_permissions as permissions
from tests.test_documents import registry
from tests.test_document_registry_pagination import mixed, legacy_visible, seed_many


def link_params(href):
    return {key:values[0] for key,values in parse_qs(urlsplit(href).query,keep_blank_values=True).items()}


@pytest.mark.parametrize('queue',sorted(grid.QUEUES))
def test_dashboard_queue_authority_matches_independent_registry_reference(mixed,queue):
    c,users,_,_,_=mixed
    for user in users:
        if queue=='instruction' and not permissions.director(c,user):
            with pytest.raises(permissions.Denied):dashboard.report(c,user,{'queue':queue})
            continue
        report=dashboard.report(c,user,{'queue':queue,'q':'Needle' if queue!='instruction' else ''})
        expected=legacy_visible(c,user,'Needle' if queue!='instruction' else '',queue)
        assert report['total']==len(expected)
        for dimension in ('workflow','deadlines','leads'):
            assert sum(row['count'] for row in report[dimension])==report['total']
            for row in report[dimension]:
                if row['count'] and row['href']:
                    assert grid.page(c,user,link_params(row['href']))['last_row']==row['count']


def test_dashboard_deadlines_working_days_invalid_dates_leads_and_access_changes(registry,monkeypatch):
    c,u,unit,_=registry
    monkeypatch.setattr(grid.tz,'today_local',lambda:date(2026,10,23)) # Friday; next 3 weekdays through Wednesday
    ids=seed_many(c,u[0],unit,65,subject='Dashboardneedle')
    hidden=seed_many(c,u[0],unit,3,subject='Private details must not enter chart data',visibility='restricted')
    c.execute("UPDATE document SET status='in_action',due_date='2026-10-23',lead_id=?",(u[1]['id'],))
    for identifier,due in zip(ids[:7],['2026-10-22','2026-10-24','2026-10-28','2026-10-29',None,'invalid-date','20261023']):
        c.execute('UPDATE document SET due_date=? WHERE id=?',(due,identifier))
    c.execute("UPDATE document SET status='closed' WHERE id=?",(ids[7],))
    c.execute("UPDATE document SET status='cancelled',due_date=NULL,lead_id=NULL WHERE id=?",(ids[8],))
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[1]['id'],));c.commit()
    scope={'queue':'OUT','q':'Dashboardneedle'}
    result=dashboard.report(c,u[4],scope)
    assert result['total']==65 and result['soon']=='2026-10-28'
    counts={r['key']:r['count'] for r in result['deadlines']}
    assert counts=={'overdue':1,'due_soon':59,'scheduled':1,'unknown':2,'inactive':2}
    assert {r['key']:r['count'] for r in result['leads']}=={str(u[1]['id']):64,'0':1}
    assert 'Private details' not in str(result) and 'subject' not in result
    for dimension in ('workflow','deadlines','leads'):
        for row in result[dimension]:
            if row['count'] and row['href']:
                params=link_params(row['href'])
                assert params['q']=='Dashboardneedle' and params['queue']=='OUT'
                assert grid.page(c,u[4],params)['last_row']==row['count']
                assert grid.export_csv(c,u[4],params)[1]==row['count']
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(ids[-1],));c.commit()
    assert dashboard.report(c,u[4],scope)['total']==64
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[4]['id'],));c.commit()
    with pytest.raises(permissions.Denied):dashboard.report(c,u[4],scope)


def test_empty_scope_invalid_options_and_no_calendar_data_writes(registry):
    c,u,_,_=registry
    before=c.total_changes
    result=dashboard.report(c,u[4],{'q':'No matching records'})
    assert result['total']==0 and result['leads']==[]
    assert c.total_changes==before
    with pytest.raises(ValueError):dashboard.report(c,u[4],{'queue':'DROP TABLE document'})
    with pytest.raises(ValueError):dashboard.report(c,u[4],{'q':'x'*121})
    with pytest.raises(permissions.Denied):dashboard.report(c,u[4],{'queue':'instruction'})


def test_all_leads_remain_in_counts_beyond_chart_limit_and_hidden_leads_stay_private(registry):
    import storage as st
    c,u,unit,_=registry
    ids=seed_many(c,u[0],unit,22,subject='Lead chart')
    for index,identifier in enumerate(ids):
        uid=st.create_admin_user(c,f'chart-lead-{index:02}@example.test','unused','unused','viewer',active=False)
        c.execute('UPDATE document SET lead_id=? WHERE id=?',(uid,identifier))
    hidden=seed_many(c,u[0],unit,1,subject='Lead chart private',visibility='restricted')
    secret=st.create_admin_user(c,'hidden-lead-only@example.test','unused','unused','viewer',active=True)
    c.execute('UPDATE document SET lead_id=? WHERE id=?',(secret,hidden[0]));c.commit()
    result=dashboard.report(c,u[4],{'q':'Lead chart'})
    assert result['total']==22 and len(result['leads'])==22 and result['chart_lead_limit']==20
    assert 'hidden-lead-only' not in str(result)
