"""Official CSM report parity and two-month suppression/capacity boundaries."""
import json
import pytest
import storage as st
import survey_reports as reports
import documents_permissions as permissions
from documents_registry import snapshot


def seed_month(conn, token, submitted_at, count=20, *, current=False, na=False):
    fid=conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date) VALUES (1,'F1',?,'1999-01-01')",(token,)).lastrowid
    for i in range(count):
        rid=conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)',(fid,submitted_at,'PRIVATE respondent comment')).lastrowid
        # Unequal denominators distinguish pooled SQD1-8 from mean item percentages.
        values=[('SQD0',1),('SQD1',5 if current or i<10 else 2)]
        if i<10: values.append(('SQD2',2 if current else 5))
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)',[(rid,k,v,int(na)) for k,v in values])
        conn.execute("INSERT INTO item_remark(response_id,item_id,text) VALUES (?,'EMAIL','private@example.invalid')",(rid,))
    return fid


def test_report_parity_leap_month_and_independent_switch(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    seed_month(conn,'csm-prev','2040-01-31 23:59:59.999')
    seed_month(conn,'csm-current','2040-02-29T23:59:59.999',current=True)
    seed_month(conn,'csm-next','2040-03-01T00:00:00')
    archived=seed_month(conn,'csm-archived','2040-02-20',current=True)
    conn.execute('UPDATE response SET archived_at=? WHERE form_instance_id=?',('2040-02-21',archived));conn.commit()
    assert reports.compare_csm_months(conn,user,'',2040,2)=={'availability':'not_available'}
    monkeypatch.setenv('CSS_MCP_CSM_TRENDS_ENABLED','1')
    before=conn.total_changes
    with snapshot(conn):
        result=reports.compare_csm_months(conn,user,'https://office.example',2040,2)
        assert result['comparison_state']=='comparable'
        for period,start,end in (('previous','2040-01-01','2040-01-31'),('current','2040-02-01','2040-02-29')):
            source=app_mod._arta_official_report(app_mod._csm_blhsd_rows(conn,start,end))
            assert result[period]['overall_percent']==source['overall']==66.7
            assert result[period]['submissions']==source['respondents']==20
            assert result[period]['valid_item_answers']==source['overall_n']==30
            assert result[period]['items'][1]['percent']==source['sqd'][1]['score']
            assert 'date_from='+start in result[period]['web_url']
        assert result['changes']['overall_percentage_points']==0
        changes={i['item']:i['percentage_points'] for i in result['changes']['items']}
        assert changes['SQD1']==50 and changes['SQD2']==-100
        assert changes['SQD0']==0 and changes['SQD3'] is None
        assert 'PRIVATE' not in json.dumps(result) and 'private@example.invalid' not in json.dumps(result)
    assert conn.total_changes==before
    # One sparse cell suppresses both months, including SQD0/item details.
    conn.execute("DELETE FROM answer WHERE id=(SELECT MIN(id) FROM answer WHERE item_id='SQD2' AND response_id IN (SELECT id FROM response WHERE form_instance_id=(SELECT id FROM form_instance WHERE qr_token='csm-current')))")
    conn.commit()
    small=reports.compare_csm_months(conn,user,'',2040,2)
    assert small['current']['state']=='insufficient_sample'
    assert 'changes' not in small and 'overall_percent' not in small['previous'] and 'items' not in small['previous']
    conn.close()


@pytest.mark.parametrize('count,na,state',[(0,False,'no_matching_responses'),(1,False,'insufficient_sample'),(20,True,'no_valid_ratings')])
def test_prior_year_and_unusable_month(app_mod,monkeypatch,count,na,state):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    seed_month(conn,'csm-prior-year','2039-12-31',count=count,na=na)
    seed_month(conn,'csm-new-year','2040-01-01',current=True);conn.commit()
    monkeypatch.setenv('CSS_MCP_CSM_TRENDS_ENABLED','1')
    result=reports.compare_csm_months(conn,user,'',2040,1)
    assert result['previous']['start_date']=='2039-12-01'
    assert result['previous']['state']==state and result['comparison_state']=='not_comparable'
    assert 'changes' not in result
    for key in ('previous','current'):
        assert 'overall_percent' not in result[key] and 'items' not in result[key]
    conn.close()


def test_caps_validation_and_current_authority(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    seed_month(conn,'csm-cap-prior','2040-01-01');seed_month(conn,'csm-cap-current','2040-02-01',current=True);conn.commit()
    monkeypatch.setenv('CSS_MCP_CSM_TRENDS_ENABLED','1')
    with monkeypatch.context() as m:
        m.setattr(reports,'MAX_RESPONSES',19)
        capped=reports.compare_csm_months(conn,user,'',2040,2)
        assert capped['availability']=='not_available' and capped['current']['reason']=='capacity_limit'
        assert 'changes' not in capped
    with monkeypatch.context() as m:
        m.setattr(reports,'MAX_CSM_TREND_ANSWERS',1)
        capped=reports.compare_csm_months(conn,user,'',2040,2)
        assert capped['availability']=='not_available' and 'changes' not in capped
    for year,month in ((1900,1),(True,2),(2040,True),(2040,13),(9999,12)):
        with pytest.raises(ValueError):reports.compare_csm_months(conn,user,'',year,month)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));conn.commit()
    with pytest.raises(permissions.Denied):reports.compare_csm_months(conn,user,'',2040,2)
    conn.close()


def test_comparable_year_rollover_and_source_archive_rules(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    previous=seed_month(conn,'csm-rollover-before','2039-12-31T23:59:59.999')
    seed_month(conn,'csm-rollover-after','2040-01-01 00:00:00',current=True);conn.commit()
    monkeypatch.setenv('CSS_MCP_CSM_TRENDS_ENABLED','1')
    result=reports.compare_csm_months(conn,user,'',2040,1)
    assert result['comparison_state']=='comparable'
    assert result['previous']['end_date']=='2039-12-31' and result['current']['start_date']=='2040-01-01'
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?',(previous,));conn.commit()
    result=reports.compare_csm_months(conn,user,'',2040,1)
    # The earliest standing walk-in form stays included even if archived,
    # exactly as on the source CSM report; ordinary forms do not.
    assert result['comparison_state']=='comparable'
    conn.execute("UPDATE form_instance SET archived=1 WHERE qr_token='csm-rollover-after'");conn.commit()
    result=reports.compare_csm_months(conn,user,'',2040,1)
    assert result['current']['state']=='no_matching_responses'
    assert 'changes' not in result and 'overall_percent' not in result['previous']
    conn.close()


def test_percentage_points_use_published_values_and_missing_item_is_null(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    seed_month(conn,'csm-point-before','2040-01-01')
    after=seed_month(conn,'csm-point-after','2040-02-01',current=True)
    conn.execute("UPDATE answer SET value=5 WHERE item_id='SQD2' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?)",(after,));conn.commit()
    monkeypatch.setenv('CSS_MCP_CSM_TRENDS_ENABLED','1')
    result=reports.compare_csm_months(conn,user,'',2040,2)
    assert result['previous']['overall_percent']==66.7 and result['current']['overall_percent']==100
    assert result['changes']['overall_percentage_points']==33.3
    conn.execute("DELETE FROM answer WHERE item_id='SQD2' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?)",(after,));conn.commit()
    result=reports.compare_csm_months(conn,user,'',2040,2)
    assert result['comparison_state']=='comparable'
    assert next(i['percentage_points'] for i in result['changes']['items'] if i['item']=='SQD2') is None
    conn.close()
