"""CSM screen parity, privacy, dates, capacity and current authority."""
import json
import pytest
import storage as st
import survey_reports as reports
import documents_permissions as permissions
from documents_registry import snapshot


def seed(conn, count=10, *, na=False):
    fid = conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date) VALUES (1,'F1','mcp-csm','1999-01-01')").lastrowid
    for i in range(count):
        rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)',
                           (fid, '2040-10-31 23:59:59.999', 'Private respondent remark')).lastrowid
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)',
                         [(rid, f'SQD{n}', 5 if i % 2 else 2, int(na)) for n in range(9)])
        conn.execute("INSERT INTO item_remark(response_id,item_id,text) VALUES (?,'EMAIL','private@example.invalid')", (rid,))
    conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)',
                 (fid, '2040-11-01T00:00:00', 'Outside month'))
    conn.execute('INSERT INTO response(form_instance_id,submitted_at,archived_at) VALUES (?,?,?)',
                 (fid, '2040-10-20', '2040-10-21'))
    conn.commit()
    return fid


def test_csm_summary_matches_existing_report_and_excludes_private_data(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    seed(conn)
    assert reports.csm_summary(conn, user, '', 2040, 10)['availability'] == 'not_available'
    monkeypatch.setenv('CSS_MCP_CSM_ENABLED', '1')
    initial = conn.total_changes
    with snapshot(conn):
        summary = reports.csm_summary(conn, user, 'https://office.example', 2040, 10)
        ui = app_mod._arta_official_report(app_mod._csm_blhsd_rows(conn, '2040-10-01', '2040-10-31'))
        assert summary['submissions'] == ui['respondents'] == 10
        assert summary['overall_percent'] == ui['overall'] == 50.0
        assert summary['valid_item_answers'] == ui['overall_n'] == 80
        assert summary['items'][1]['percent'] == ui['sqd'][1]['score']
        assert summary['date_basis'] == 'submission_date'
        assert 'Private' not in json.dumps(summary)
        assert 'private@example.invalid' not in json.dumps(summary)
        assert 'date_from=2040-10-01' in summary['web_url']
        assert reports.csm_summary(conn, user, '', 2040, 9)['state'] == 'no_matching_responses'
        assert reports.csm_summary(conn, user, '', 2040, 11)['state'] == 'no_valid_ratings'
    assert initial == conn.total_changes
    conn.execute("DELETE FROM answer WHERE id=(SELECT MIN(id) FROM answer WHERE item_id='SQD1' AND response_id IN (SELECT id FROM response WHERE submitted_at='2040-10-31 23:59:59.999'))")
    conn.commit()
    sparse = reports.csm_summary(conn, user, '', 2040, 10)
    assert sparse['state'] == 'insufficient_sample' and 'overall_percent' not in sparse
    monkeypatch.setattr(reports, 'MAX_RESPONSES', 9)
    capped = reports.csm_summary(conn, user, '', 2040, 10)
    assert capped['reason'] == 'capacity_limit' and 'overall_percent' not in capped
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (user['id'],)); conn.commit()
    with pytest.raises(permissions.Denied):
        reports.csm_summary(conn, user, '', 2040, 10)
    conn.close()


@pytest.mark.parametrize('count,na,state', [(1, False, 'insufficient_sample'), (10, True, 'no_valid_ratings')])
def test_csm_no_score_is_never_zero(app_mod, monkeypatch, count, na, state):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    seed(conn, count, na=na)
    monkeypatch.setenv('CSS_MCP_CSM_ENABLED', '1')
    result = reports.csm_summary(conn, user, '', 2040, 10)
    assert result['state'] == state
    assert 'overall_percent' not in result and 'items' not in result
    for year, month in ((2040, 0), (2040, 13), (True, 1), (0, 1)):
        with pytest.raises(ValueError):
            reports.csm_summary(conn, user, '', year, month)
    conn.close()
