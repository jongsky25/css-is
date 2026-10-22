"""Travel display meaning and mutations share current checklist/flag facts."""
import pytest

import travel
import travel_guidance as guidance
import travel_rules as rules
import storage as st
from tests.conftest import join_admin_section
from tests.test_travel_generate import conn, mk, post
from tests.test_travel_relay import fake, env

LINK='https://docs.google.com/document/d/example/edit'


def complete(c,f):
    for it in travel.view_items(c,f):
        if it['requirement']=='required' and it['handling']!='fmis' and it['state']!='na':
            travel.save_item(c,travel.get_filing(c,f['id']),it['code'],drive_url=LINK)
    return travel.get_filing(c,f['id'])


def facts(c,f,**kw):
    return guidance.filing(f,travel.view_items(c,f),travel.flags_of(c,f['id']),owner=kw.pop('owner',True),**kw)


@pytest.mark.parametrize('status,heading', [('open','Add the missing documents'),('ready','Ready to print and sign'),
    ('submitted','Paper submission recorded'),('withdrawn','Filing withdrawn')])
def test_lifecycle_guidance_matches_actual_saved_state(viewer,conn,status,heading):
    ref=mk(viewer);f=travel.get_by_ref(conn,ref)
    if status in ('ready','submitted'):
        f=travel.mark_ready(conn,complete(conn,f))
        if status=='submitted':f=travel.mark_submitted(conn,f)
    elif status=='withdrawn':f=travel.withdraw(conn,f)
    page=viewer.get(f'/travel/f/{ref}')
    assert page.status_code==200 and heading in page.text
    assert 'Who acts next' in page.text and 'What to do' in page.text
    assert travel.get_by_ref(conn,ref)['status']==status
    if status=='submitted':assert 'does not confirm receipt, approval or payment' in page.text


def test_ready_and_submit_recheck_current_generation_even_with_a_stale_object(viewer,conn):
    f=complete(conn,travel.get_by_ref(conn,mk(viewer)))
    ready=travel.mark_ready(conn,f)
    travel.start_generation(conn,ready,['appendix_a'])
    for fn in (travel.mark_ready,travel.mark_submitted):
        with pytest.raises(travel.TravelError,match='still being made'):fn(conn,ready)
    current=travel.get_filing(conn,f['id'])
    g=facts(conn,current)
    assert g['state']=='waiting' and not g['can_submit']
    assert g['blockers']==rules.readiness(current,travel.view_items(conn,current),travel.flags_of(conn,current['id']))
    assert current['status']=='ready' and current['submitted_at'] is None
    page=viewer.get(f"/travel/f/{f['ref_code']}/ready").text
    assert 'Mark submitted' not in page and 'still being made' in page
    assert viewer.get(f"/travel/f/{f['ref_code']}/status").headers['cache-control']=='no-store'


def test_submit_rechecks_new_flags_and_no_handover_is_recorded(viewer,conn):
    f=travel.mark_ready(conn,complete(conn,travel.get_by_ref(conn,mk(viewer))))
    travel.sync_flags(conn,f,[rules.FlagSpec('over_ceiling','changed','Fare changed after marking ready')])
    with pytest.raises(travel.TravelError,match='Admin Unit'):travel.mark_submitted(conn,f)
    current=travel.get_filing(conn,f['id']);g=facts(conn,current)
    assert g['state']=='waiting' and g['actor']=='Administrative Section' and not g['can_submit']
    assert current['submitted_at'] is None
    flag=travel.flags_of(conn,f['id'])[0]
    travel.decide_flag(conn,flag,'reviewer','verified')
    assert travel.mark_submitted(conn,current)['status']=='submitted'


def test_submit_does_not_trust_a_ready_object_after_a_checklist_edit(viewer,conn):
    f=travel.mark_ready(conn,complete(conn,travel.get_by_ref(conn,mk(viewer))))
    travel.save_item(conn,f,'dpo',drive_url='')
    with pytest.raises(travel.TravelError,match='Mark the filing ready'):travel.mark_submitted(conn,f)
    assert travel.get_filing(conn,f['id'])['status']=='open'


def test_earlier_copy_is_distinguished_from_a_failed_replacement(viewer,conn):
    f=complete(conn,travel.get_by_ref(conn,mk(viewer)))
    rev=travel.start_generation(conn,f,['appendix_a'])['appendix_a']
    travel.finish_item(conn,f['id'],'appendix_a',rev,error='Example form service failure <script>unsafe()</script>')
    travel.finish_generation(conn,f['id'])
    f=travel.get_filing(conn,f['id']);g=facts(conn,f)
    assert g['state']=='attention' and 'earlier linked copy' in g['step']
    page=viewer.get(f"/travel/f/{f['ref_code']}").text
    item=page.split('id="item-appendix_a"',1)[1].split('</li>',1)[0]
    assert 'Latest attempt failed' in item and 'Open the earlier form' in item
    assert 'Example form service failure' in item and '<script>unsafe()' not in item
    # An earlier valid link remains a checklist fact; the failed attempt is not called a new completed copy.
    assert next(i for i in travel.view_items(conn,f) if i['code']=='appendix_a')['doc_url']==LINK


def test_flag_reason_and_actor_change_after_rejection_and_verification(viewer,encoder,conn):
    f=complete(conn,travel.get_by_ref(conn,mk(viewer)))
    travel.sync_flags(conn,f,[rules.FlagSpec('participant_only','role','Participant travel')])
    flag=travel.flags_of(conn,f['id'])[0]
    waiting=facts(conn,f)
    assert waiting['actor']=='Administrative Section'
    travel.decide_flag(conn,flag,'reviewer','rejected','Please correct the route')
    g=facts(conn,travel.get_filing(conn,f['id']))
    assert g['state']=='attention' and g['actor']=='The traveller'
    assert any('Please correct the route' in x for x in g['blockers'])
    travel.decide_flag(conn,flag,'reviewer','verified',supervisor_confirmed=True)
    g=facts(conn,travel.get_filing(conn,f['id']))
    assert g['state']=='ready' and not g['blockers']


def test_owner_and_admin_read_boundaries_and_fresh_membership(viewer,encoder,admin,conn):
    ref=mk(viewer);f=complete(conn,travel.get_by_ref(conn,ref))
    travel.sync_flags(conn,f,[rules.FlagSpec('over_ceiling','fare','Review fare')])
    assert encoder.get(f'/travel/f/{ref}').status_code==404
    assert admin.get(f'/travel/f/{ref}').status_code==404
    join_admin_section(conn,st.get_admin_user(conn,'encoder@test.local')['id'])
    page=encoder.get(f'/travel/f/{ref}').text
    assert 'Open flag review queue' in page and 'Save link' not in page and 'Save answers' not in page
    assert post(encoder,f'/travel/f/{ref}/answers',dpo_no='Other').status_code==403
    conn.execute("UPDATE admin_user SET rp_id=NULL WHERE username='encoder@test.local'");conn.commit()
    flag=travel.flags_of(conn,f['id'])[0]
    assert post(encoder,f"/travel/verify/{flag['id']}",outcome='verified').status_code==403
    assert travel.flags_of(conn,f['id'])[0]['state']=='open'


def test_answer_error_preserves_values_and_saved_record(viewer,conn):
    ref=mk(viewer);before=travel.get_by_ref(conn,ref)
    r=post(viewer,f'/travel/f/{ref}/answers',role='participant',dpo_no='Changed DPO',
        advance_amount='not a number',flew='1',dpo_date='2026-10-01',mc114_format='separate')
    assert r.status_code==400 and 'Not saved.' in r.text
    assert 'value="not a number"' in r.text and 'value="Changed DPO"' in r.text
    assert 'value="2026-10-01"' in r.text and 'id="travel-answers" open' in r.text
    assert travel.get_by_ref(conn,ref)['dpo_no']==before['dpo_no']
    assert travel.get_by_ref(conn,ref)['answers_json']==before['answers_json']


def test_closed_during_edit_retains_unsaved_details_without_controls(viewer,conn):
    ref=mk(viewer);f=complete(conn,travel.get_by_ref(conn,ref))
    travel.mark_submitted(conn,travel.mark_ready(conn,f))
    r=post(viewer,f'/travel/f/{ref}/answers',role='secretariat',dpo_no='Unsaved DPO',advance_amount='7000')
    assert r.status_code==409 and 'Unsaved DPO' in r.text and 'Your unsaved details' in r.text
    assert 'Save answers' not in r.text and travel.get_by_ref(conn,ref)['status']=='submitted'


def test_verify_error_preserves_note_and_requires_existing_supervisor_confirmation(viewer,encoder,conn):
    ref=mk(viewer);f=travel.get_by_ref(conn,ref)
    travel.sync_flags(conn,f,[rules.FlagSpec('participant_only','role','Participant-only travel')])
    flag=travel.flags_of(conn,f['id'])[0]
    join_admin_section(conn,st.get_admin_user(conn,'encoder@test.local')['id'])
    r=post(encoder,f"/travel/verify/{flag['id']}",outcome='verified',note='Draft note <unsafe>')
    assert r.status_code==400 and 'value="Draft note &lt;unsafe&gt;"' in r.text
    assert travel.flags_of(conn,f['id'])[0]['state']=='open'
    r=post(encoder,f"/travel/verify/{flag['id']}",outcome='verified',note='Draft note',supervisor_confirmed='1')
    assert r.status_code==303 and travel.flags_of(conn,f['id'])[0]['state']=='verified'


def test_display_ignores_optional_fmis_and_not_applicable_items_without_writing(viewer,conn):
    f=complete(conn,travel.get_by_ref(conn,mk(viewer)))
    items=travel.view_items(conn,f)+[{'code':'optional','label':'Optional','handling':'upload','requirement':'optional','state':'missing'}]
    before=conn.total_changes
    g=guidance.filing(f,items,[],owner=True)
    assert not g['blockers'] and g['state']=='ready' and conn.total_changes==before


@pytest.mark.parametrize('closed',[False,True])
def test_invalid_or_closed_replacement_does_not_trash_existing_uploaded_files(viewer,conn,fake,env,closed):
    from tests.test_travel_relay import up
    st.set_setting(conn,'travel.relay_version','2')
    ref=mk(viewer)
    assert up(viewer,ref).status_code==200
    f=travel.get_by_ref(conn,ref)
    if closed:
        for it in travel.view_items(conn,f):
            if it['code']!='dpo' and it['requirement']=='required' and it['handling']!='fmis':
                travel.save_item(conn,travel.get_filing(conn,f['id']),it['code'],drive_url=LINK)
        travel.mark_submitted(conn,travel.mark_ready(conn,travel.get_filing(conn,f['id'])))
    response=post(viewer,f'/travel/f/{ref}/item/dpo',drive_url=LINK if closed else 'https://example.test/not-drive')
    assert response.status_code==(409 if closed else 400)
    assert fake.trashed==[]
    row=next(i for i in travel.view_items(conn,travel.get_by_ref(conn,ref)) if i['code']=='dpo')
    assert row['drive_source']=='upload' and 'FOLDER1234567890123456' in row['drive_url']


def test_removed_checklist_row_and_missing_flag_keep_the_users_unsaved_note(viewer,encoder,conn):
    ref=mk(viewer)
    r=post(viewer,f'/travel/f/{ref}/item/removed_row',note='Retained old row note')
    assert r.status_code==400 and 'Your unsaved details' in r.text and 'Retained old row note' in r.text
    join_admin_section(conn,st.get_admin_user(conn,'encoder@test.local')['id'])
    r=post(encoder,'/travel/verify/999999',outcome='verified',note='Retained review note')
    assert r.status_code==404 and 'Retained review note' in r.text
