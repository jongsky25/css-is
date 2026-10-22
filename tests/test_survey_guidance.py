"""A18 survey confirmation and draft scopes use actual HTTP and saved responses."""
import re

import pytest

import app
import storage as st
from tests.test_pwa import offline_form, _response_count


def test_device_scope_preserves_legacy_anonymous_keys_and_separates_attendees():
    a=app._survey_draft_key('/r/public',att='signed-one')
    b=app._survey_draft_key('/r/public',att='signed-two')
    assert app._survey_draft_key('/r/public')=='css_draft_v2_/r/public'
    assert a!=b and 'signed-one' not in a
    assert app._survey_draft_key('/seq',tokens='b,a')==app._survey_draft_key('/seq',tokens='a,b')


@pytest.mark.parametrize('combined',[False,True])
def test_queue_receipt_is_bound_to_id_and_preserves_existing_replay_dedup(client,offline_form,combined):
    db,token=offline_form
    sid='SURVEY-ACK-1'
    data={'submission_id':sid,'tokens':token,f'{token}::A':'5'} if combined else {'submission_id':sid,'A':'5'}
    url='/seq' if combined else f'/r/{token}'
    before=_response_count(db,token)
    response=client.post(url,data=data,headers={'Accept':'application/json'})
    assert response.json()['ok'] is True and response.json()['submission_id']==sid
    assert _response_count(db,token)==before+1
    replay=client.post(url,data=data,headers={'Accept':'application/json'})
    assert replay.json()=={'ok':True,'deduped':True,'submission_id':sid}
    assert _response_count(db,token)==before+1


def test_confirmation_only_clears_the_matching_device_revision(client,offline_form):
    db,token=offline_form
    response=client.post(f'/r/{token}',data={'A':'4','draft_saved_at':'revision-one'})
    assert 'data-confirmed-draft="css_draft_v2_/r/'+token+'"' in response.text
    assert 'data-draft-revision="revision-one"' in response.text


def test_skip_flag_is_honoured_without_javascript_even_if_ratings_were_posted(client,offline_form):
    db,token=offline_form
    before=_response_count(db,token)
    response=client.post('/seq',data={'tokens':token,f'{token}::A':'5',f'skip::{token}':'1'})
    assert 'No feedback recorded' in response.text and 'data-confirmed-draft=' not in response.text
    assert _response_count(db,token)==before


def test_partial_combined_confirmation_reports_unavailable_forms_and_keeps_draft(client,offline_form):
    db,token=offline_form
    data={'tokens':token+',missing-form',f'{token}::A':'5','draft_saved_at':'keep-me'}
    response=client.post('/seq',data=data)
    assert response.status_code==200 and 'form(s) were unavailable and were not recorded' in response.text
    assert 'data-confirmed-draft=' not in response.text
    assert _response_count(db,token)==1
    data['submission_id']='JSON-PARTIAL'
    receipt=client.post('/seq',data=data,headers={'Accept':'application/json'}).json()
    assert receipt=={'ok':True,'submission_id':'JSON-PARTIAL','recorded':1,'unavailable':1}


def test_registered_draft_scopes_follow_verified_attendee_identity(client,offline_form):
    db,token=offline_form
    conn=st.connect(db)
    fid=conn.execute('SELECT id FROM form_instance WHERE qr_token=?',(token,)).fetchone()[0]
    ev=st.create_event(conn,'A18 scope test','2026-10-20',form_instance_ids=[fid])
    first,_=st.register_attendee(conn,ev['id'],name='First',email='first@survey.test',consent_text='test')
    second,_=st.register_attendee(conn,ev['id'],name='Second',email='second@survey.test',consent_text='test')
    conn.close()
    keys=[]
    for attendee in (first,second):
        credential=app._att_token(attendee)
        html=client.get(f'/r/{token}',params={'att':credential}).text
        key=re.search(r'data-survey-draft-key="([^"]+)"',html)[1]
        assert key==app._survey_draft_key(f'/r/{token}',att=credential)
        keys.append(key)
    assert keys[0]!=keys[1]
    html=client.get(f'/r/{token}',params={'att':str(first)}).text
    assert f'data-survey-draft-key="css_draft_v2_/r/{token}"' in html


def test_registered_completion_message_waits_for_all_activity_forms(client,offline_form):
    import i18n
    db,token=offline_form
    conn=st.connect(db)
    fid=conn.execute('SELECT id FROM form_instance WHERE qr_token=?',(token,)).fetchone()[0]
    other=st.create_form_instance(conn,2,'F2','2026-10-20',topic='Other feedback')
    ev=st.create_event(conn,'Complete all forms','2026-10-20',form_instance_ids=[fid,other])
    attendee,_=st.register_attendee(conn,ev['id'],name='Rater',email='rater@survey.test',consent_text='test')
    other_token=conn.execute('SELECT qr_token FROM form_instance WHERE id=?',(other,)).fetchone()[0]
    credential=app._att_token(attendee)
    response=client.post(f'/r/{token}',data={'A':'5','att':credential})
    assert 'Open the activity page to check the remaining feedback' in response.text
    assert str(i18n.t('thanks_all_done_event','en')) not in response.text
    st.set_response_window(conn,other,'2026-10-19T00:00','2026-10-21T23:59')
    response=client.post(f'/r/{other_token}',data={'A':'5','att':credential})
    assert str(i18n.t('thanks_all_done_event','en')) in response.text
    conn.close()
