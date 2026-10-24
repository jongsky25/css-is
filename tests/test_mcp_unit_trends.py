"""Two-period source parity, all-or-nothing scores and current authority."""
import json
import pytest
import storage as st
import survey_reports as reports
import documents_permissions as permissions
from documents_registry import snapshot
from test_mcp_unit_surveys import activity


def seed_periods(conn, previous_count=10, previous_na=False):
    uid = st.add_org_unit(conn, 'Trend pilot', 'division', 'TrendPilot')
    previous = activity(conn, uid, 'trend-previous', count=previous_count, value=4, na=previous_na)
    conn.execute("UPDATE form_instance SET event_date='2039-12-31' WHERE id=?", (previous,))
    current = activity(conn, uid, 'trend-current', value=6)
    conn.commit()
    return uid, previous, current


def test_year_rollover_source_parity_independent_flag_and_no_writes(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB); user = st.get_admin_user(conn, 'viewer@test.local')
    uid, previous, current = seed_periods(conn)
    assert reports.compare_unit_activity_surveys(conn,user,'',uid,2040,1) == {'availability':'not_available'}
    monkeypatch.setenv('CSS_MCP_UNIT_SURVEYS_ENABLED','1')
    p = reports.unit_activity_summary(conn,user,'https://office.example',uid,2039,4)
    c = reports.unit_activity_summary(conn,user,'https://office.example',uid,2040,1)
    monkeypatch.delenv('CSS_MCP_UNIT_SURVEYS_ENABLED')
    monkeypatch.setenv('CSS_MCP_UNIT_TRENDS_ENABLED','1')
    before = conn.total_changes
    with snapshot(conn):
        result = reports.compare_unit_activity_surveys(conn,user,'https://office.example',uid,2040,1)
    assert conn.total_changes == before
    assert result['comparison_state'] == 'comparable'
    assert result['previous']['start_date'] == '2039-10-01'
    assert result['current']['end_date'] == '2040-03-31'
    assert result['previous']['web_url'] == p['web_url']
    assert result['current']['web_url'] == c['web_url']
    for field in ('overall_mean','expectation_mean','osq_mean','gap'):
        assert result['previous'][field] == p[field]
        assert result['current'][field] == c[field]
        assert result['changes'][field] == pytest.approx(c[field]-p[field])
    assert result['changes']['overall_mean'] == 2
    assert all(d['mean_change']==2 for d in result['changes']['dimensions'])
    assert 'PRIVATE' not in json.dumps(result)
    # A missing OSQ or dimension is unknown, not a fabricated zero delta.
    conn.execute("DELETE FROM answer WHERE item_id IN ('A','C','B7') AND response_id IN (SELECT id FROM response WHERE form_instance_id=?)", (previous,));conn.commit()
    sparse = reports.compare_unit_activity_surveys(conn,user,'',uid,2040,1)
    assert sparse['comparison_state']=='comparable'
    assert sparse['changes']['osq_mean'] is None
    assert sparse['changes']['expectation_mean'] is None and sparse['changes']['gap'] is None
    assert next(d['mean_change'] for d in sparse['changes']['dimensions'] if d['dimension']=='Empathy') is None
    # Current reassignment applies to both quarters, not historical ownership.
    conn.execute('UPDATE form_instance SET lead_org_id=NULL WHERE id=?',(previous,));conn.commit()
    missing=reports.compare_unit_activity_surveys(conn,user,'',uid,2040,1)
    assert missing['comparison_state']=='not_comparable' and 'changes' not in missing
    assert 'overall_mean' not in missing['current']
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));conn.commit()
    with pytest.raises(permissions.Denied):reports.compare_unit_activity_surveys(conn,user,'',uid,2040,1)
    conn.close()


@pytest.mark.parametrize('count,na,state',[(0,False,'no_matching_responses'),(1,False,'insufficient_sample'),(10,True,'no_valid_ratings')])
def test_unusable_period_withholds_both_scorecards(app_mod,monkeypatch,count,na,state):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    uid,_,_=seed_periods(conn,count,na)
    monkeypatch.setenv('CSS_MCP_UNIT_TRENDS_ENABLED','1')
    result=reports.compare_unit_activity_surveys(conn,user,'',uid,2040,1)
    assert result['previous']['state']==state
    assert result['comparison_state']=='not_comparable' and 'changes' not in result
    for period in ('previous','current'):
        assert not {'overall_mean','expectation_mean','osq_mean','gap','dimensions'} & result[period].keys()
    conn.close()


def test_capacity_and_invalid_selections(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    uid,_,_=seed_periods(conn)
    monkeypatch.setenv('CSS_MCP_UNIT_TRENDS_ENABLED','1')
    monkeypatch.setattr(reports,'MAX_ACTIVITY_ANSWERS',1)
    result=reports.compare_unit_activity_surveys(conn,user,'',uid,2040,1)
    assert result['availability']=='not_available' and 'changes' not in result
    assert result['previous']['reason']=='capacity_limit'
    for year,quarter in ((1900,1),(True,2),(2040,True),(2040,5),(9999,4)):
        with pytest.raises(ValueError):reports.compare_unit_activity_surveys(conn,user,'',uid,year,quarter)
    with pytest.raises(permissions.Denied):reports.compare_unit_activity_surveys(conn,user,'',999999,2040,1)
    conn.close()


def test_within_year_and_small_current_period(app_mod, monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    uid,previous,current=seed_periods(conn)
    conn.execute("UPDATE form_instance SET event_date='2040-04-01' WHERE id=?",(current,));conn.commit()
    monkeypatch.setenv('CSS_MCP_UNIT_TRENDS_ENABLED','1')
    result=reports.compare_unit_activity_surveys(conn,user,'',uid,2040,2)
    assert result['previous']['start_date']=='2040-01-01'
    assert result['current']['start_date']=='2040-04-01'
    assert result['previous']['state']=='no_matching_responses'
    conn.execute("UPDATE form_instance SET event_date='2040-03-31' WHERE id=?",(previous,))
    conn.execute('DELETE FROM answer WHERE response_id IN (SELECT id FROM response WHERE form_instance_id=? ORDER BY id LIMIT 9)',(current,))
    conn.commit()
    result=reports.compare_unit_activity_surveys(conn,user,'',uid,2040,2)
    assert result['current']['state']=='insufficient_sample'
    assert 'changes' not in result and 'overall_mean' not in result['previous']
    conn.close()
