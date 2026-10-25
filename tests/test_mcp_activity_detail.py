"""Merged activity discovery, current member resolution and source scorecard parity."""
import json
import pytest
import storage as st
import dashboard_insights as di
import documents_permissions as permissions
import survey_reports as reports
from documents_registry import snapshot


def seed(conn, title, token, venue='Detail fixture room', day='2040-03-31', count=10, survey_type=2):
    fid = conn.execute('INSERT INTO form_instance(survey_type,form,qr_token,event_date,venue,topic,created_at) VALUES (?,?,?,?,?,?,?)',
                       (survey_type, f'F{survey_type}', token, day, venue, title, '2040-01-01')).lastrowid
    for _ in range(count):
        rid = conn.execute('INSERT INTO response(form_instance_id,submitted_at,remarks) VALUES (?,?,?)',
                           (fid, '2041-01-01', 'Private survey comment')).lastrowid
        conn.executemany('INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,0)',
                         [(rid, item, value) for item,value in [('A',7), *[(f'B{i}', 4 if i==6 else 2 if i==7 else 6) for i in range(1,10)], ('C',3)]])
    conn.commit()
    return fid


def test_discovery_and_merged_detail_match_report(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    first = seed(conn, 'Alpha detail', 'detail-one', count=5)
    member = seed(conn, 'Member title', 'detail-two', count=5)
    speaker = seed(conn, 'Speaker private title', 'detail-three', survey_type=3)
    second = seed(conn, 'Beta detail', 'detail-other', venue='Other room')
    seed(conn, 'No answer activity', 'detail-empty', venue='Empty room', count=0)
    assert reports.find_survey_activities(conn, user, '', 2040, 1)['availability'] == 'not_available'
    monkeypatch.setenv('CSS_MCP_ACTIVITY_DETAILS_ENABLED', '1')
    baseline = conn.total_changes
    with snapshot(conn):
        page = reports.find_survey_activities(conn, user, '', 2040, 1, limit=1)
        next_page = reports.find_survey_activities(conn, user, '', 2040, 1, limit=1, offset=page['next_offset'])
        assert {page['data'][0]['activity_id'], next_page['data'][0]['activity_id']} == {str(first), str(second)}
        assert all('overall_mean' not in i and 'respondents' not in i for i in page['data'])
        assert reports.find_survey_activities(conn, user, '', 2040, 1, query='aLpHa')['data'][0]['activity_id'] == str(first)
        detail = reports.activity_detail(conn, user, 'https://office.example', member)
        via_speaker_member = reports.activity_detail(conn, user, 'https://office.example', speaker)
        assert detail['activity_id'] == via_speaker_member['activity_id'] == str(first)
        assert detail['submissions'] == detail['rated_respondents'] == 10
        atoms = st.load_atoms(conn, instance_ids=[first,member,speaker])
        source = di.activity_servqual(atoms, [first,member,speaker])
        assert detail['overall_mean'] == source['average']
        assert detail['gap'] == source['servqual']
        assert {d['dimension']:d['mean'] for d in detail['dimensions']} == {d['key']:d['value'] for d in source['dims']}
        event = next(e for e in di.build_events(atoms, st.list_activity_instances(conn)) if member in e['instance_ids'])
        assert int(detail['activity_id']) == event['id']
        assert detail['title'] == event['name']
        assert 'Private survey comment' not in json.dumps(detail)
        assert 'Speaker private title' not in json.dumps(detail)
        assert reports.find_survey_activities(conn, user, '', 2041, 1)['data'] == []
    assert conn.total_changes == baseline
    conn.execute('UPDATE form_instance SET archived=1 WHERE id=?', (member,)); conn.commit()
    with pytest.raises(permissions.Denied):
        reports.activity_detail(conn, user, '', member)
    remaining = reports.activity_detail(conn, user, '', first)
    assert remaining['state'] == 'insufficient_sample' and 'overall_mean' not in remaining
    conn.execute("UPDATE form_instance SET topic='Renamed activity',event_date='2040-04-01' WHERE id=?", (first,)); conn.commit()
    assert reports.find_survey_activities(conn, user, '', 2040, 1, query='Alpha')['data'] == []
    assert reports.find_survey_activities(conn, user, '', 2040, 2, query='Renamed')['data']
    with pytest.raises(permissions.Denied):
        reports.activity_detail(conn, user, '', 9223372036854775807)
    monkeypatch.setattr(reports, 'MAX_ACTIVITY_QUERY_STEPS', 0)
    assert reports.find_survey_activities(conn, user, '', 2040, 1)['reason'] == 'capacity_limit'
    assert conn.execute('SELECT 1').fetchone()[0] == 1
    conn.close()


def test_detail_unrated_and_input_bounds(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    fid = seed(conn, 'Unrated', 'detail-na')
    conn.execute('UPDATE answer SET is_na=1 WHERE response_id IN (SELECT id FROM response WHERE form_instance_id=?)', (fid,)); conn.commit()
    monkeypatch.setenv('CSS_MCP_ACTIVITY_DETAILS_ENABLED', '1')
    result = reports.activity_detail(conn, user, '', fid)
    assert result['state'] == 'no_valid_ratings' and 'overall_mean' not in result
    for args in ((2040,0,'',10,0), (2040,1,'x'*121,10,0), (2040,1,'',26,0), (2040,1,'',10,-1)):
        with pytest.raises(ValueError):
            reports.find_survey_activities(conn, user, '', *args)
    conn.execute("UPDATE answer SET is_na=CASE WHEN item_id IN ('B6','B7') THEN 0 ELSE 1 END WHERE response_id IN (SELECT id FROM response WHERE form_instance_id=?)", (fid,))
    conn.commit()
    people_only = reports.activity_detail(conn, user, '', fid)
    assert people_only['reason'] == 'source_report_unavailable' and 'overall_mean' not in people_only
    monkeypatch.setattr(reports, 'MAX_RESPONSES', 1)
    assert reports.activity_detail(conn, user, '', fid)['reason'] == 'capacity_limit'
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (user['id'],)); conn.commit()
    with pytest.raises(permissions.Denied):
        reports.find_survey_activities(conn, user, '', 2040, 1)
    conn.close()


def test_large_archive_search_pagination_and_targeted_detail(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    speaker = seed(conn, 'Not the activity name', 'large-speaker', venue='  ÜBER Hall ', survey_type=3)
    target = seed(conn, 'Regional BHW Summit Straße %_ Forum', 'large-target', venue='über hall')
    conn.executemany('INSERT INTO form_instance(survey_type,form,qr_token,event_date,venue,topic,created_at) VALUES (2,?,?,?,?,?,?)',
                     [('F2', f'large-{i}', '2040-03-31', f'Other room {i}', f'Other activity {i}', '2040-01-01') for i in range(2105)])
    conn.execute("INSERT INTO response(form_instance_id,submitted_at) SELECT id,'2040-04-01' FROM form_instance WHERE qr_token LIKE 'large-%' AND qr_token NOT IN ('large-target','large-speaker')")
    conn.execute("INSERT INTO answer(response_id,item_id,value,is_na) SELECT r.id,'B1',6,0 FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id WHERE fi.qr_token LIKE 'large-%' AND fi.qr_token NOT IN ('large-target','large-speaker')")
    # The rest of the archive must not affect an empty quarter or target lookup.
    conn.executemany('INSERT INTO form_instance(survey_type,form,qr_token,event_date,venue,topic,created_at) VALUES (3,?,?,?,?,?,?)',
                     [('F3', f'historical-{i}', '2030-01-01', f'Old room {i}', 'Old session', '2030-01-01') for i in range(2105)])
    conn.commit()
    monkeypatch.setenv('CSS_MCP_ACTIVITY_DETAILS_ENABLED', '1')
    monkeypatch.setattr(st, 'list_activity_instances', lambda *a: pytest.fail('Must not load the full archive'))
    changes = conn.total_changes
    found = reports.find_survey_activities(conn, user, '', 2040, 1, query='STRASSE %_')
    assert found['availability'] == 'available' and found['next_offset'] is None
    assert len(found['data']) == 1 and found['data'][0]['activity_id'] == str(speaker)
    assert reports.find_survey_activities(conn, user, '', 2040, 1, query='Not the activity name')['data'] == []
    page = reports.find_survey_activities(conn, user, '', 2040, 1, limit=25, offset=2001)
    assert len(page['data']) == 25 and page['next_offset'] == 2026
    tail = reports.find_survey_activities(conn, user, '', 2040, 1, limit=25, offset=2100)
    assert len(tail['data']) == 6 and tail['next_offset'] is None
    assert reports.find_survey_activities(conn, user, '', 2041, 1)['data'] == []
    for member in (speaker, target):
        detail = reports.activity_detail(conn, user, '', member)
        assert detail['state'] == 'rated' and detail['activity_id'] == str(speaker)
        assert detail['submissions'] == 10
        assert detail['title'] == found['data'][0]['title']
    assert conn.total_changes == changes
    monkeypatch.setattr(reports, 'MAX_ACTIVITY_GROUP_FORMS', 1)
    bounded = reports.activity_detail(conn, user, '', target)
    assert bounded['reason'] == 'capacity_limit' and 'overall_mean' not in bounded
    monkeypatch.setattr(reports, 'MAX_ACTIVITY_GROUP_FORMS', 2000)
    monkeypatch.setattr(reports, 'MAX_ACTIVITY_QUERY_STEPS', 0)
    assert reports.activity_detail(conn, user, '', target)['reason'] == 'capacity_limit'
    assert conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0] > 4000
    conn.close()


def test_discovery_keeps_source_grouping_titles_and_eligibility(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    speaker = seed(conn, 'Speaker title', 'parity-speaker', venue='\u2003Straße ROOM\u2003', survey_type=3)
    first = seed(conn, 'First %_ title', 'parity-first', venue='straße room')
    later = seed(conn, 'Secondary title must not match', 'parity-later', venue='STRAẞE ROOM')
    unit = st.add_org_unit(conn, 'Separate organizer', 'division', 'PARITY')
    separate = seed(conn, 'Separate organizer title', 'parity-separate', venue='straße room')
    conn.execute('UPDATE form_instance SET lead_org_id=? WHERE id=?', (unit,separate))
    conn.execute("UPDATE form_instance SET created_at='2039-01-01',end_date='2040-04-02' WHERE id=?", (first,))
    for title, token, kind in [('Empty','parity-empty','empty'), ('Archived','parity-archived','archived'),
                                ('Pooled','parity-pooled','pooled'), ('Archived answers','parity-answers','answers')]:
        fid = seed(conn,title,token,venue=token,count=0 if kind=='empty' else 10)
        if kind in ('archived','pooled'):
            conn.execute(f'UPDATE form_instance SET {"archived" if kind=="archived" else "pooled"}=1 WHERE id=?', (fid,))
        if kind=='answers':
            conn.execute("UPDATE response SET archived_at='2040-04-01' WHERE form_instance_id=?", (fid,))
    conn.commit()
    monkeypatch.setenv('CSS_MCP_ACTIVITY_DETAILS_ENABLED', '1')
    groups = di.group_activity_instances(st.list_activity_instances(conn)).values()
    expected = [reports._activity_identity(g,'') for g in groups if any(f['id'] in (first,later,separate) for f in g)]
    expected.sort(key=lambda i: (i['start_date'],int(i['activity_id'])), reverse=True)
    assert reports.find_survey_activities(conn,user,'',2040,1)['data'] == expected
    found = reports.find_survey_activities(conn,user,'',2040,1,query='%_')['data']
    assert len(found)==1 and found[0]['activity_id']==str(speaker) and found[0]['end_date']=='2040-04-02'
    assert reports.find_survey_activities(conn,user,'',2040,1,query='Secondary')['data']==[]
    assert reports.activity_detail(conn,user,'',later)['activity_id']==str(speaker)
    conn.close()
