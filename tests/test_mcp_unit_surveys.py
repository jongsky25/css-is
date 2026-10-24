"""Unit report parity and current lead-unit selection; no business writes."""
import json
import pytest
import storage as st
import css_is_engine as eng
import survey_reports as reports
import documents_permissions as permissions
from documents_registry import snapshot


def activity(conn, unit, token, count=10, value=6, na=False):
    fid = conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date,lead_org_id) VALUES (2,'F2',?,'2040-01-31',?)", (token, unit)).lastrowid
    for _ in range(count):
        rid = conn.execute("INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,'2041-12-20','PRIVATE')", (fid,)).lastrowid
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)',
                         [(rid, item, score, na) for item, score in [('A',7),('C',3), *[(f'B{i}',value) for i in range(1,10)]]])
    return fid


def test_unit_selection_matches_report_and_current_reassignment(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    parent = st.add_org_unit(conn, 'Literal unit', 'division', 'Pilot%_')
    child = st.add_org_unit(conn, 'Child', 'section', 'Pilot%_/Child')
    sibling = st.add_org_unit(conn, 'Prefix collision', 'division', 'Pilot%_Other')
    f1 = activity(conn, parent, 'unit-p1')
    f2 = activity(conn, child, 'unit-p2', value=4)
    f3 = activity(conn, sibling, 'unit-p3', value=1)
    conn.commit()
    assert reports.unit_activity_summary(conn, user, '', parent, 2040, 1) == {'availability':'not_available'}
    monkeypatch.setenv('CSS_MCP_UNIT_SURVEYS_ENABLED', '1')
    before = conn.total_changes
    with snapshot(conn):
        result = reports.unit_activity_summary(conn, user, 'https://office.example', parent, 2040, 1)
        atoms = st.load_atoms(conn, instance_ids=[f1,f2,f3])
        selected = app_mod._report_scope_atoms(atoms, 'Pilot%_', 'quarter:2040-Q1', 2)
        source = reports.servqual_block(selected, eng.DIM_MAP_FORM2)
        assert result['state'] == 'rated'
        assert result['submissions'] == result['report_submissions'] == 20
        assert result['overall_mean'] == source['overall']['value'] == 5
        assert result['expectation_mean'] == source['expectation']['value']
        assert result['osq_mean'] == source['osq']['value']
        assert result['gap'] == -2
        assert result['dimensions'] == [{'dimension':d['dim'],'mean':d['value'],'valid_item_answers':d['n']} for d in source['dimensions']]
        assert 'org=Pilot%25_' in result['web_url'] and 'PRIVATE' not in json.dumps(result)
        page = reports.find_survey_units(conn, user, 'pilot%_', 1)
        assert len(page['data']) == 1 and page['next_offset'] == 1
        assert reports.find_survey_units(conn, user, 'CHILD')['data'][0]['unit_id'] == str(child)
    assert conn.total_changes == before
    conn.execute('UPDATE form_instance SET lead_org_id=? WHERE id=?', (sibling,f2)); conn.commit()
    assert reports.unit_activity_summary(conn,user,'',parent,2040,1)['submissions'] == 10
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?',(f1,));conn.commit()
    assert reports.unit_activity_summary(conn,user,'',parent,2040,1)['state'] == 'no_matching_responses'
    for invalid in (True,0,-1,2**64):
        with pytest.raises(ValueError): reports.unit_activity_summary(conn,user,'',invalid,2040,1)
    with pytest.raises(permissions.Denied): reports.unit_activity_summary(conn,user,'',9999999,2040,1)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));conn.commit()
    with pytest.raises(permissions.Denied): reports.find_survey_units(conn,user)
    conn.close()


@pytest.mark.parametrize('count,na,state', [(0,False,'no_matching_responses'),(1,False,'insufficient_sample'),(10,True,'no_valid_ratings')])
def test_unit_small_empty_and_capacity(app_mod, monkeypatch, count, na, state):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    uid=st.add_org_unit(conn,'Pilot','division','UnitPilot')
    activity(conn,uid,'unit-sparse',count=count,na=na);conn.commit()
    monkeypatch.setenv('CSS_MCP_UNIT_SURVEYS_ENABLED','1')
    result=reports.unit_activity_summary(conn,user,'',uid,2040,1)
    assert result['state']==state and 'overall_mean' not in result
    monkeypatch.setattr(reports,'MAX_RESPONSES',0)
    if count: assert reports.unit_activity_summary(conn,user,'',uid,2040,1)['reason']=='capacity_limit'
    for query,limit,offset in (('x'*121,10,0),('',True,0),('',10,-1)):
        with pytest.raises(ValueError):reports.find_survey_units(conn,user,query,limit,offset)
    conn.close()
