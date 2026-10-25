"""Linked Type 3 person selectors keep current visibility and annual scope clear."""
import json

import pytest
import storage as st
import survey_reports as reports
import documents_permissions as permissions


def linked(conn, name, *, hidden=0, position=None, archived=False, form_archived=0, survey_type=3):
    person = conn.execute('INSERT INTO resource_person(name,is_internal,hidden_public,position,archived_at) VALUES (?,1,?,?,?)',
                          (name,hidden,position,'2026-01-01' if archived else None)).lastrowid
    form = st.create_form_instance(conn,survey_type=survey_type,form=f'F{survey_type}',event_date='2026-07-23',rp_id=person)
    conn.execute('UPDATE form_instance SET archived=? WHERE id=?',(form_archived,form))
    return person,form


def test_links_visibility_dedup_boundaries_and_no_scores(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn,'viewer@test.local')
    admin = st.get_admin_user(conn,'admin@test.local')
    visible, form = linked(conn,'Visible speaker')
    _, hidden = linked(conn,'Hidden speaker',hidden=1)
    _, director = linked(conn,'Director speaker',position='Deputy DIRECTOR')
    old_person, old_form = linked(conn,'Historical speaker',archived=True)
    _, removed = linked(conn,'Archived form speaker',form_archived=1)
    _, type2 = linked(conn,'Activity-only person',survey_type=2)
    extra = st.create_form_instance(conn,survey_type=3,form='F3',event_date='2026-07-23',rp_id=visible)
    event = st.create_event(conn,'Synthetic Summit','2026-07-23',event_kind='outside',
        form_instance_ids=[form,hidden,director,old_form,removed,type2,extra],created_by=user['username'])
    conn.commit()
    assert reports.activity_resource_person_links(conn,user,'',event['id'],'2026-07-23')=={'availability':'not_available','reason':'disabled'}
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED','1')
    before = conn.total_changes
    result = reports.activity_resource_person_links(conn,user,'https://office.example',event['id'],'2026-07-23')
    assert {p['resource_person_id'] for p in result['data']}=={str(visible),str(old_person)}
    assert len(result['data'])==2 and not result['truncated'] and result['annual_summary_year']==2026
    assert next(p for p in result['data'] if p['resource_person_id']==str(old_person))['archived']
    assert all(p['annual_report_url'].endswith('?period=year:2026') for p in result['data'])
    assert not {'quality_index','submissions','overall_mean','dimensions'} & result.keys()
    assert 'Annual results can include other activities' in result['note']
    assert 'Hidden speaker' not in json.dumps(result) and 'Director speaker' not in json.dumps(result)
    privileged = reports.activity_resource_person_links(conn,admin,'',event['id'],'2026-07-23')
    assert len(privileged['data'])==4
    assert conn.total_changes==before
    monkeypatch.setattr(reports,'MAX_ACTIVITY_LINKED_PERSONS',1)
    assert reports.activity_resource_person_links(conn,user,'',event['id'],'2026-07-23')=={'availability':'not_available','reason':'capacity_limit'}
    monkeypatch.setattr(reports,'MAX_ACTIVITY_LINKED_PERSONS',2000)
    assert reports.activity_resource_person_links(conn,user,'',event['id'],'bad')['reason']=='invalid_activity_date'
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],));conn.commit()
    with pytest.raises(permissions.Denied):
        reports.activity_resource_person_links(conn,user,'',event['id'],'2026-07-23')
    conn.close()


def test_hidden_people_filtered_before_output_limit(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn,'viewer@test.local')
    forms = [linked(conn,f'A hidden {i}',hidden=1)[1] for i in range(30)]
    forms += [linked(conn,f'Visible {i:02}')[1] for i in range(26)]
    event = st.create_event(conn,'Many speakers','2026-07-23',event_kind='outside',form_instance_ids=forms)
    conn.commit()
    monkeypatch.setenv('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED','1')
    result = reports.activity_resource_person_links(conn,user,'',event['id'],'2026-07-23')
    assert len(result['data'])==25 and result['truncated']
    assert [p['name'] for p in result['data']]==[f'Visible {i:02}' for i in range(25)]
    assert 'hidden' not in json.dumps(result)
    conn.close()
