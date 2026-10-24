"""Type 2 source-report parity, scale, privacy and event-date selection."""
import json
import pytest
import storage as st
import css_is_engine as eng
import documents_permissions as permissions
import survey_reports as reports
from documents_registry import snapshot


def seed(conn, count=10, na=False):
    fid = conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date,topic) VALUES (2,'F2','type2-pilot','2040-01-31','Survey fixture')").lastrowid
    for i in range(count):
        rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)',
                           (fid, '2041-12-20', 'Private respondent text')).lastrowid
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)',
                         [(rid, item, value, int(na)) for item, value in
                          [('A', 7), *[(f'B{n}', 4 if n == 6 else 2 if n == 7 else 6) for n in range(1, 10)], ('C', 3)]])
    conn.commit()
    return fid


def test_type2_source_parity_and_privacy(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    fid = seed(conn)
    # A genuine receipt without answers is absent from the historical atom
    # report count; expose that distinction instead of calling both 'people'.
    conn.execute('INSERT INTO response(form_instance_id,submitted_at) VALUES (?,?)', (fid, '2041-12-20'))
    third = conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date) VALUES (3,'F3','type3-separate','2040-01-31')").lastrowid
    rid3 = conn.execute('INSERT INTO response(form_instance_id,submitted_at) VALUES (?,?)', (third, '2040-01-31')).lastrowid
    conn.execute("INSERT INTO answer(response_id,item_id,value) VALUES (?,'B1',1)", (rid3,))
    conn.commit()
    assert reports.activity_summary(conn, user, '', 2040, 1)['availability'] == 'not_available'
    monkeypatch.setenv('CSS_MCP_ACTIVITY_SURVEYS_ENABLED', '1')
    before = conn.total_changes
    with snapshot(conn):
        result = reports.activity_summary(conn, user, 'https://office.example', 2040, 1)
        atoms = st.load_atoms(conn, instance_ids=[fid])
        source = app_mod._servqual_official(atoms, eng.DIM_MAP_FORM2, list(atoms['response_id'].unique()), conn)
        assert result['state'] == 'rated'
        assert result['overall_mean'] == source['overall']['value'] == 4.8
        assert result['expectation_mean'] == source['expectation']['value'] == 7
        assert result['osq_mean'] == source['osq']['value'] == 3
        assert result['gap'] == pytest.approx(-2.2)
        assert result['rated_respondents'] == source['overall']['n'] == 10
        assert result['report_submissions'] == source['respondents'] == 10
        assert result['submissions'] == 11
        assert len(result['dimensions']) == 5
        assert {d['dimension']: d['mean'] for d in result['dimensions']} == {d['dim']: d['value'] for d in source['dimensions']}
        assert next(d['mean'] for d in result['dimensions'] if d['dimension'] == 'Assurance') == 4
        assert next(d['mean'] for d in result['dimensions'] if d['dimension'] == 'Empathy') == 2
        assert 'Private respondent' not in json.dumps(result)
        assert 'quarter%3A2040-Q1' in result['web_url']
        assert reports.activity_summary(conn, user, '', 2041, 4)['state'] == 'no_matching_responses'
    assert conn.total_changes == before
    # A sparse OSQ cell must suppress the perception headline too.
    conn.execute('DELETE FROM answer WHERE id=(SELECT MIN(id) FROM answer WHERE item_id=\'C\' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?))', (fid,))
    conn.commit()
    suppressed = reports.activity_summary(conn, user, '', 2040, 1)
    assert suppressed['state'] == 'insufficient_sample'
    assert 'overall_mean' not in suppressed and 'osq_mean' not in suppressed
    monkeypatch.setattr(reports, 'MAX_ACTIVITY_ANSWERS', 1)
    assert reports.activity_summary(conn, user, '', 2040, 1)['reason'] == 'capacity_limit'
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (user['id'],)); conn.commit()
    with pytest.raises(permissions.Denied):
        reports.activity_summary(conn, user, '', 2040, 1)
    conn.close()


@pytest.mark.parametrize('count,na,state', [(0, False, 'no_matching_responses'), (1, False, 'insufficient_sample'), (10, True, 'no_valid_ratings')])
def test_type2_missing_and_small_samples(app_mod, monkeypatch, count, na, state):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    fid = seed(conn, count, na)
    monkeypatch.setenv('CSS_MCP_ACTIVITY_SURVEYS_ENABLED', '1')
    result = reports.activity_summary(conn, user, '', 2040, 1)
    assert result['state'] == state and 'overall_mean' not in result
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?', (fid,)); conn.commit()
    assert reports.activity_summary(conn, user, '', 2040, 1)['state'] == 'no_matching_responses'
    for year, quarter in ((2040, 0), (2040, 5), (True, 1), (0, 1)):
        with pytest.raises(ValueError):
            reports.activity_summary(conn, user, '', year, quarter)
    conn.close()
