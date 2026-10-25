"""Type 3 discovery visibility and annual source scorecard comparison."""
import json
import pytest
import storage as st
import dashboard_insights as di
import survey_reports as reports
import documents_permissions as permissions
from documents_registry import snapshot


def form(conn, pid, token, year, *, count=10, high=False, na=False):
    fid=conn.execute("INSERT INTO form_instance(survey_type,form,qr_token,event_date,rp_id) VALUES (3,'F3',?,?,?)",(token,f'{year}-03-31',pid)).lastrowid
    for _ in range(count):
        rid=conn.execute("INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,'2042-01-01','PRIVATE')",(fid,)).lastrowid
        # Person-dashboard index excludes A and is distinct from consolidated means.
        items=[('A',1),('C',4 if high else 3),*[(f'B{i}',7 if high else {6:4,7:2,8:7,9:5}.get(i,6)) for i in range(1,10)]]
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)',[(rid,k,v,int(na)) for k,v in items])
    return fid


def seed(conn,count=10,na=False):
    pid=conn.execute("INSERT INTO resource_person(name,is_internal) VALUES ('Trend person',1)").lastrowid
    before=form(conn,pid,'person-trend-before',2039,count=count,na=na)
    after=form(conn,pid,'person-trend-after',2040,high=True)
    conn.commit()
    return pid,before,after


def test_person_discovery_filters_before_paging_and_rechecks_visibility(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);viewer=st.get_admin_user(conn,'viewer@test.local');admin=st.get_admin_user(conn,'admin@test.local')
    pid,_,_=seed(conn)
    hidden=conn.execute("INSERT INTO resource_person(name,is_internal,hidden_public) VALUES ('AAA HIDDEN trend',1,1)").lastrowid
    director=conn.execute("INSERT INTO resource_person(name,is_internal,position) VALUES ('BBB trend',1,'Director')").lastrowid
    archived=conn.execute("INSERT INTO resource_person(name,is_internal,archived_at) VALUES ('Archived trend',1,'2039-12-31')").lastrowid
    conn.commit()
    assert reports.find_survey_resource_persons(conn,viewer,'')=={'availability':'not_available'}
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED','1')
    before=conn.total_changes
    with snapshot(conn):
        page=reports.find_survey_resource_persons(conn,viewer,'https://office.example','TREND',1)
        assert page['data'][0]['resource_person_id']==str(archived) and page['data'][0]['archived'] is True
        assert set(page['data'][0])=={'resource_person_id','name','name_truncated','archived','web_url'}
        assert page['next_offset']==1
        following=reports.find_survey_resource_persons(conn,viewer,'','trend',1,page['next_offset'])
        assert following['data'][0]['resource_person_id']==str(pid) and following['next_offset'] is None
        assert reports.find_survey_resource_persons(conn,viewer,'','HIDDEN')['data']==[]
        assert len(reports.find_survey_resource_persons(conn,admin,'','trend')['data'])==4
    assert conn.total_changes==before
    conn.execute('UPDATE resource_person SET hidden_public=1 WHERE id=?',(pid,));conn.commit()
    assert reports.find_survey_resource_persons(conn,viewer,'','Trend person')['data']==[]
    for selected in (pid,hidden,director,9223372036854775807):
        with pytest.raises(permissions.Denied,match='not found or unavailable'):
            reports.compare_resource_person_surveys(conn,viewer,'',selected,2040)
    assert reports.compare_resource_person_surveys(conn,admin,'',pid,2040)['comparison_state']=='comparable'
    conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?",(admin['id'],));conn.commit()
    assert reports.find_survey_resource_persons(conn,admin,'','HIDDEN')['data']==[]
    with pytest.raises(permissions.Denied):reports.compare_resource_person_surveys(conn,admin,'',pid,2040)
    conn.close()


def test_annual_comparison_matches_person_dashboard_and_excludes_other_records(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    pid,prior,current=seed(conn)
    other=conn.execute("INSERT INTO resource_person(name,is_internal) VALUES ('Other person',1)").lastrowid
    form(conn,other,'person-trend-other',2040)
    wrong_type=form(conn,pid,'person-trend-type2',2040)
    conn.execute('UPDATE form_instance SET survey_type=2 WHERE id=?',(wrong_type,));conn.commit()
    assert reports.compare_resource_person_surveys(conn,user,'',pid,2040)=={'availability':'not_available'}
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED','1')
    before=conn.total_changes
    with snapshot(conn):
        result=reports.compare_resource_person_surveys(conn,user,'https://office.example',pid,2040)
        assert result['comparison_state']=='comparable'
        person=st.get_rp(conn,pid)
        cards=[]
        for key,fid,year in (('previous',prior,2039),('current',current,2040)):
            atoms=st.load_atoms(conn,instance_ids=[fid]);card=di.person_card(atoms,person);cards.append(card)
            assert result[key]['quality_index']==card['quality']['index']
            assert result[key]['osq_mean']==card['quality']['osq']
            dims={d['raw']:d['value'] for d in di.person_dimensions(atoms,person)}
            assert {d['dimension']:d['mean'] for d in result[key]['dimensions']}==dims
            assert result[key]['submissions']==10
            assert f'period=year%3A{year}' in result[key]['web_url']
        assert result['changes']['quality_index_points']==pytest.approx(cards[1]['quality']['index']-cards[0]['quality']['index'])
        assert result['changes']['osq_mean']==1
        assert 'PRIVATE' not in json.dumps(result) and 'rank' not in result['changes']
    assert conn.total_changes==before
    # Missing optional OSQ produces null, not zero change.
    conn.execute("DELETE FROM answer WHERE item_id='C' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?)",(prior,));conn.commit()
    assert reports.compare_resource_person_surveys(conn,user,'',pid,2040)['changes']['osq_mean'] is None
    conn.execute("DELETE FROM answer WHERE item_id='B8' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?)",(current,));conn.commit()
    optional=reports.compare_resource_person_surveys(conn,user,'',pid,2040)
    assert next(d['mean_change'] for d in optional['changes']['dimensions'] if d['dimension']=='Empathy') is None
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?',(prior,));conn.commit()
    result=reports.compare_resource_person_surveys(conn,user,'',pid,2040)
    assert result['previous']['state']=='no_matching_responses'
    assert 'changes' not in result and 'quality_index' not in result['current']
    conn.close()


@pytest.mark.parametrize('count,na,state',[(0,False,'no_matching_responses'),(1,False,'insufficient_sample'),(10,True,'no_valid_ratings')])
def test_unusable_prior_withholds_both_scorecards(app_mod,monkeypatch,count,na,state):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    pid,_,_=seed(conn,count,na)
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED','1')
    result=reports.compare_resource_person_surveys(conn,user,'',pid,2040)
    assert result['comparison_state']=='not_comparable' and result['previous']['state']==state
    assert 'changes' not in result
    for key in ('previous','current'):
        assert not {'quality_index','osq_mean','dimensions'} & result[key].keys()
    conn.close()


def test_small_current_caps_search_bounds_and_account_denial(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    pid,_,current=seed(conn)
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED','1')
    conn.execute("DELETE FROM answer WHERE id=(SELECT MIN(id) FROM answer WHERE item_id='C' AND response_id IN (SELECT id FROM response WHERE form_instance_id=?))",(current,));conn.commit()
    result=reports.compare_resource_person_surveys(conn,user,'',pid,2040)
    assert result['current']['state']=='insufficient_sample' and 'quality_index' not in result['previous']
    for cap in ('MAX_ACTIVITY_ANSWERS','MAX_RESPONSES'):
        with monkeypatch.context() as m:
            m.setattr(reports,cap,1)
            result=reports.compare_resource_person_surveys(conn,user,'',pid,2040)
            assert result['availability']=='not_available' and 'changes' not in result
    for query,limit,offset in (('x'*121,10,0),('',True,0),('',10,-1)):
        with pytest.raises(ValueError):reports.find_survey_resource_persons(conn,user,'',query,limit,offset)
    for year in (True,1900,9999):
        with pytest.raises(ValueError):reports.compare_resource_person_surveys(conn,user,'',pid,year)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));conn.commit()
    with pytest.raises(permissions.Denied):reports.find_survey_resource_persons(conn,user,'')
    with pytest.raises(permissions.Denied):reports.compare_resource_person_surveys(conn,user,'',pid,2040)
    conn.close()


def test_discovery_full_name_search_and_inventory_cap(app_mod,monkeypatch):
    conn=st.connect(app_mod.DB);user=st.get_admin_user(conn,'viewer@test.local')
    name='A'*260+' UNIQUE %_ suffix'
    conn.execute('INSERT INTO resource_person(name,is_internal) VALUES (?,1)',(name,));conn.commit()
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED','1')
    result=reports.find_survey_resource_persons(conn,user,'','%_ suffix')['data'][0]
    assert len(result['name'])==250 and result['name_truncated'] is True
    conn.executemany('INSERT INTO resource_person(name,is_internal) VALUES (?,1)',[(f'Cap {i}',) for i in range(2001)]);conn.commit()
    assert reports.find_survey_resource_persons(conn,user,'','no-match')['reason']=='capacity_limit'
    conn.close()
