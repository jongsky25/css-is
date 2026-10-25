"""One-person/one-activity isolation, source-page parity and independent consent."""
import json

import pytest
import dashboard_insights as di
import documents_permissions as permissions
from documents_registry import snapshot
import storage as st
import survey_reports as reports


def form(conn, pid, token, *, count=10, value=6, day='2040-07-23', venue='Activity room', survey_type=3):
    fid = st.create_form_instance(conn,survey_type=survey_type,form=f'F{survey_type}',event_date=day,
                                  venue=venue,rp_id=pid,topic='Private session title')
    for _ in range(count):
        rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)',
                           (fid,'2041-01-01','Never return this comment')).lastrowid
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,0)',
                         [(rid,k,v) for k,v in [('A',7),*[(f'B{i}',value) for i in range(1,10)],('C',3)]])
    conn.commit()
    return fid


def person(conn,name):
    return conn.execute('INSERT INTO resource_person(name,is_internal) VALUES (?,1)',(name,)).lastrowid


def test_person_activity_matches_source_and_excludes_annual_other_person_and_type2(app_mod, viewer, monkeypatch):
    conn=st.connect(app_mod.DB)
    user=st.get_admin_user(conn,'viewer@test.local')
    pid=person(conn,'Selected resource person');other=person(conn,'Other resource person')
    representative=form(conn,pid,'f2',survey_type=2,value=1)
    first=form(conn,pid,'first',count=5,venue='  ÄCTIVITY room ')
    second=form(conn,pid,'second',count=5,venue='äctivity room')
    removed_receipt=conn.execute("INSERT INTO response(form_instance_id,submitted_at,archived_at,remarks) VALUES (?,'2040-07-23','2040-07-24','Archived private comment')",(first,)).lastrowid
    conn.execute("INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,'B1',1,0)",(removed_receipt,))
    # Match the representative's normalized venue to this source group.
    conn.execute("UPDATE form_instance SET venue='ÄCTIVITY ROOM' WHERE id=?",(representative,))
    other_form=form(conn,other,'other',value=1,venue='äctivity room')
    form(conn,pid,'different-date',value=1,day='2040-07-24')
    archived=form(conn,pid,'archived',value=1,venue='äctivity room')
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?',(archived,))
    pooled=form(conn,pid,'pooled',value=1,venue='äctivity room')
    conn.execute('UPDATE form_instance SET pooled=1 WHERE id=?',(pooled,));conn.commit()
    disabled=reports.resource_person_activity_survey(conn,user,'',first,pid)
    assert disabled['reason']=='disabled' and 'name' not in disabled and 'activity_id' not in disabled
    monkeypatch.setenv('CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED','1')
    monkeypatch.delenv('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED',raising=False)
    monkeypatch.delenv('CSS_MCP_ACTIVITY_DETAILS_ENABLED',raising=False)
    changes=conn.total_changes
    with snapshot(conn):
        result=reports.resource_person_activity_survey(conn,user,'https://office.example',second,pid)
        via_representative=reports.resource_person_activity_survey(conn,user,'https://office.example',representative,pid)
        assert result['scope']=='one_resource_person_one_activity' and result['state']=='rated'
        assert result['activity_id']==via_representative['activity_id']==str(representative)
        assert result['submissions']==result['rated_respondents']==10
        atoms=st.load_atoms(conn,instance_ids=[representative,first,second,other_form])
        scoped=atoms[(atoms['survey_type']==3)&(atoms['rp_id']==pid)]
        source=di.person_card(scoped,st.get_rp(conn,pid))
        assert result['quality_index']==source['quality']['index']
        assert result['osq_mean']==source['quality']['osq']
        assert {d['dimension']:d['mean'] for d in result['dimensions']}=={d['raw']:d['value'] for d in di.person_dimensions(scoped,st.get_rp(conn,pid))}
        assert result['web_url']==f'https://office.example/dashboard/people/{pid}/activity/{representative}'
        assert result['activity_report_url']==f'https://office.example/reports?type=3&activity={representative}'
        assert 'Never return' not in json.dumps(result) and 'Private session title' not in json.dumps(result)
        assert 'Other resource person' not in json.dumps(result)
    assert conn.total_changes==changes
    assert viewer.get(f'/dashboard/people/{pid}/activity/{representative}').status_code==200
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED','1')
    annual=reports.resource_person_summary(conn,user,'',pid,2040)
    assert annual['submissions']>result['submissions'] and annual['quality_index']!=result['quality_index']
    conn.execute("UPDATE form_instance SET venue='Moved room' WHERE id=?",(second,));conn.commit()
    moved=reports.resource_person_activity_survey(conn,user,'',second,pid)
    assert moved['state']=='insufficient_sample' and 'quality_index' not in moved
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?',(second,));conn.commit()
    with pytest.raises(permissions.Denied): reports.resource_person_activity_survey(conn,user,'',second,pid)
    conn.close()


@pytest.mark.parametrize('count,na,only_c,state',[(9,False,False,'insufficient_sample'),(10,True,False,'no_valid_ratings'),(10,False,True,'no_valid_ratings')])
def test_activity_small_and_unrated_do_not_publish_scores(app_mod,monkeypatch,count,na,only_c,state):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    pid=person(conn,'Sample speaker');fid=form(conn,pid,'sample',count=count)
    if na: conn.execute('UPDATE answer SET is_na=1')
    if only_c: conn.execute("DELETE FROM answer WHERE item_id!='C'")
    conn.commit();monkeypatch.setenv('CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED','1')
    result=reports.resource_person_activity_survey(conn,user,'',fid,pid)
    assert result['state']==state and not {'quality_index','osq_mean','dimensions'}&result.keys()
    conn.close()


def test_visibility_cutoff_unknown_members_and_capacity(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local');admin=st.get_admin_user(conn,'admin@test.local')
    pid=person(conn,'Guarded speaker');fid=form(conn,pid,'guard')
    unrelated=person(conn,'Unrelated speaker');conn.commit()
    monkeypatch.setenv('CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED','1')
    for args in ((fid,unrelated),(9223372036854775807,pid),(fid,9223372036854775807)):
        with pytest.raises(permissions.Denied): reports.resource_person_activity_survey(conn,user,'',*args)
    for column,value in (('hidden_public',1),('position','Deputy director')):
        conn.execute('UPDATE resource_person SET hidden_public=0,position=NULL WHERE id=?',(pid,))
        conn.execute(f'UPDATE resource_person SET {column}=? WHERE id=?',(value,pid));conn.commit()
        with pytest.raises(permissions.Denied): reports.resource_person_activity_survey(conn,user,'',fid,pid)
        assert reports.resource_person_activity_survey(conn,admin,'',fid,pid)['state']=='rated'
    conn.execute('UPDATE resource_person SET hidden_public=0,position=NULL WHERE id=?',(pid,));conn.commit()
    cutoff=form(conn,pid,'cutoff',day='2026-06-15')
    assert reports.resource_person_activity_survey(conn,user,'',cutoff,pid)['state']=='rated'
    old=form(conn,pid,'old',day='2026-06-14')
    with pytest.raises(permissions.Denied): reports.resource_person_activity_survey(conn,user,'',old,pid)
    for field,value in [('MAX_RESPONSES',1),('MAX_ACTIVITY_ANSWERS',1),('MAX_ACTIVITY_GROUP_FORMS',0)]:
        with monkeypatch.context() as limit:
            limit.setattr(reports,field,value)
            result=reports.resource_person_activity_survey(conn,user,'',fid,pid)
            assert result['reason']=='capacity_limit' and 'quality_index' not in result
        assert conn.execute('SELECT 1').fetchone()[0]==1
    # A rare populated C cell cannot borrow the other person's answers.
    conn.execute("DELETE FROM answer WHERE id=(SELECT MIN(a.id) FROM answer a JOIN response r ON r.id=a.response_id WHERE r.form_instance_id=? AND a.item_id='C')",(fid,));conn.commit()
    result=reports.resource_person_activity_survey(conn,user,'',fid,pid)
    assert result['state']=='insufficient_sample' and 'dimensions' not in result
    for aid,rid in ((0,pid),(True,pid),(fid,-1),(fid,'1')):
        with pytest.raises(ValueError): reports.resource_person_activity_survey(conn,user,'',aid,rid)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));conn.commit()
    with pytest.raises(permissions.Denied): reports.resource_person_activity_survey(conn,user,'',fid,pid)
    conn.close()


def test_oversized_person_form_set_refuses_before_partial_scoring(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    pid=person(conn,'Many sessions');fid=form(conn,pid,'scored')
    conn.executemany("INSERT INTO form_instance(survey_type,form,qr_token,event_date,venue,rp_id,created_at) VALUES (3,'F3',?,'2040-07-23','Activity room',?,'2040-01-01')",
                     [(f'many-session-{i}',pid) for i in range(500)])
    conn.commit();monkeypatch.setenv('CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED','1')
    result=reports.resource_person_activity_survey(conn,user,'',fid,pid)
    assert result['reason']=='capacity_limit' and not {'quality_index','dimensions','submissions'}&result.keys()
    monkeypatch.setattr(reports,'MAX_ACTIVITY_QUERY_STEPS',0)
    assert reports.resource_person_activity_survey(conn,user,'',fid,pid)['reason']=='capacity_limit'
    assert conn.execute('SELECT 1').fetchone()[0]==1
    conn.close()
