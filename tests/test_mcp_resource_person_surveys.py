"""Named Type 3 scope, person visibility, index/dimension parity and privacy."""
import json
import pytest
import storage as st
import dashboard_insights as di
import documents_permissions as permissions
import survey_reports as reports
from documents_registry import snapshot


def seed(conn, count=10, na=False, only_osq=False):
    pid = conn.execute("INSERT INTO resource_person(name,is_internal) VALUES ('Type 3 fixture',1)").lastrowid
    fid = conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date,rp_id) VALUES (3,'F3','type3-pilot','2040-03-31',?)", (pid,)).lastrowid
    items = [('C', 3)] if only_osq else [('A', 7), *[(f'B{i}', {6:4, 7:2, 8:7, 9:5}.get(i, 6)) for i in range(1,10)], ('C', 3)]
    for i in range(count):
        rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)', (fid, '2041-12-20', 'Secret respondent comment')).lastrowid
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)', [(rid, item, v, int(na)) for item,v in items])
    conn.commit()
    return pid, fid


def test_type3_person_dashboard_parity_and_current_visibility(app_mod, viewer, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    admin = st.get_admin_user(conn, 'admin@test.local')
    pid, fid = seed(conn)
    other = conn.execute("INSERT INTO resource_person(name,is_internal) VALUES ('Other person',1)").lastrowid
    for survey_type, selected_person in ((3, other), (2, pid)):
        extra_fid = conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date,rp_id) VALUES (?,?,?,?,?)",
                                 (survey_type, f'F{survey_type}', f'extra-{survey_type}', '2040-03-31', selected_person)).lastrowid
        rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at) VALUES (?,?)', (extra_fid, '2040-03-31')).lastrowid
        conn.execute("INSERT INTO answer(response_id,item_id,value) VALUES (?,'B1',1)", (rid,))
    conn.commit()
    assert reports.resource_person_summary(conn, user, '', pid, 2040)['availability'] == 'not_available'
    assert 'name' not in reports.resource_person_summary(conn, user, '', pid, 2040)
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED', '1')
    assert viewer.get(f'/dashboard/people/{pid}?period=year:2040', follow_redirects=False).status_code == 200
    initial = conn.total_changes
    with snapshot(conn):
        result = reports.resource_person_summary(conn, user, 'https://office.example', pid, 2040)
        atoms = st.load_atoms(conn, instance_ids=[fid])
        person = st.get_rp(conn, pid)
        source = di.person_card(atoms, person)
        assert result['state'] == 'rated'
        assert result['quality_index'] == source['quality']['index']
        assert result['osq_mean'] == source['quality']['osq'] == 3
        source_dims = {d['raw']: d['value'] for d in di.person_dimensions(atoms, person)}
        assert {d['dimension']: d['mean'] for d in result['dimensions']} == source_dims
        assert source_dims['Assurance'] == 3 and source_dims['Empathy'] == 7
        assert result['rated_respondents'] == result['quality_respondents'] == 10
        assert 'Secret respondent' not in json.dumps(result)
        assert 'rank' not in result and 'contact' not in result
        assert f'/dashboard/people/{pid}?' in result['web_url']
        assert reports.resource_person_summary(conn, user, '', pid, 2041)['state'] == 'no_matching_responses'
    assert conn.total_changes == initial
    for column, value in (('hidden_public', 1), ('position', 'Director')):
        conn.execute('UPDATE resource_person SET hidden_public=0,position=NULL WHERE id=?', (pid,))
        conn.execute(f'UPDATE resource_person SET {column}=? WHERE id=?', (value, pid)); conn.commit()
        with pytest.raises(permissions.Denied, match='not found or unavailable'):
            reports.resource_person_summary(conn, user, '', pid, 2040)
        assert reports.resource_person_summary(conn, admin, '', pid, 2040)['state'] == 'rated'
        assert not reports.can_view_resource_person(user, st.get_rp(conn, pid))
        assert viewer.get(f'/dashboard/people/{pid}?period=year:2040', follow_redirects=False).status_code == 303
    with pytest.raises(permissions.Denied, match='not found or unavailable'):
        reports.resource_person_summary(conn, user, '', 9223372036854775807, 2040)
    conn.execute("DELETE FROM answer WHERE id=(SELECT MIN(id) FROM answer WHERE item_id='C' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?))", (fid,))
    conn.commit()
    suppressed = reports.resource_person_summary(conn, admin, '', pid, 2040)
    assert suppressed['state'] == 'insufficient_sample' and 'quality_index' not in suppressed
    monkeypatch.setattr(reports, 'MAX_ACTIVITY_ANSWERS', 1)
    assert reports.resource_person_summary(conn, admin, '', pid, 2040)['reason'] == 'capacity_limit'
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (admin['id'],)); conn.commit()
    with pytest.raises(permissions.Denied):
        reports.resource_person_summary(conn, admin, '', pid, 2040)
    conn.close()


@pytest.mark.parametrize('count,na,only_osq,state', [(0,False,False,'no_matching_responses'), (1,False,False,'insufficient_sample'), (10,True,False,'no_valid_ratings'), (10,False,True,'no_valid_ratings')])
def test_type3_unrated_small_and_archived(app_mod, monkeypatch, count, na, only_osq, state):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    pid, fid = seed(conn, count, na, only_osq)
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED', '1')
    result = reports.resource_person_summary(conn, user, '', pid, 2040)
    assert result['state'] == state and 'quality_index' not in result
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?', (fid,)); conn.commit()
    assert reports.resource_person_summary(conn, user, '', pid, 2040)['state'] == 'no_matching_responses'
    with pytest.raises(ValueError):
        reports.resource_person_summary(conn, user, '', 0, 2040)
    conn.close()
