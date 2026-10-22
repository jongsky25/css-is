"""A17 calendar guidance agrees with real lifecycle, visibility and subscription rules."""
from datetime import timedelta

import pytest

import calendar_guidance as guidance
import storage as st
import tzutil as tz
from tests.test_calendar_entry_pages import conn, post, create
from tests.test_calendar_linked_edit import linked


def test_restore_display_matches_existing_service_boundary(conn):
    eid = st.cal_create(conn, 'CALEP Boundary', '2026-10-25', audience='bureau')
    st.cal_cancel(conn, eid)
    for age, allowed in [(timedelta(days=30), True), (timedelta(days=30,seconds=1), False)]:
        stamp = (tz.now_local()-age).isoformat()
        conn.execute('UPDATE calendar_entry SET cancelled_at=? WHERE id=?',(stamp,eid));conn.commit()
        e=st.cal_get(conn,eid)
        assert guidance.entry(e, now=tz.now_local(), restore_days=st.CAL_RESTORE_DAYS)['can_restore'] is allowed
        if allowed:
            assert st.cal_restore(conn,eid)['status']=='confirmed'
            st.cal_cancel(conn,eid)
        else:
            with pytest.raises(ValueError, match='30 days'):st.cal_restore(conn,eid)


@pytest.mark.parametrize('status,heading', [('confirmed','Confirmed on'),('tentative','Tentative'),
    ('postponed','Postponed'),('cancelled','Cancelled on')])
def test_current_status_has_an_actor_and_next_step_without_business_effects(viewer,conn,status,heading):
    eid=create(viewer,title='CALEP Guidance',start_date='2026-10-25',status='tentative' if status=='cancelled' else status)
    if status=='cancelled':st.cal_cancel(conn,eid)
    before=st.cal_get(conn,eid); revisions=st.cal_revisions(conn,eid)
    r=viewer.get(f'/calendar/entries/{eid}')
    assert r.status_code==200 and heading in r.text
    assert 'Who handles it' in r.text and 'Next step' in r.text
    assert 'does not confirm delivery' in r.text
    assert st.cal_get(conn,eid)==before and st.cal_revisions(conn,eid)==revisions


def test_expired_restore_has_explanation_instead_of_unusable_button(viewer,conn):
    eid=create(viewer,title='CALEP Expired')
    st.cal_cancel(conn,eid)
    conn.execute("UPDATE calendar_entry SET cancelled_at='2020-01-01T00:00:00' WHERE id=?",(eid,));conn.commit()
    r=viewer.get(f'/calendar/entries/{eid}')
    assert '30-day restore period has ended' in r.text
    assert f'action="/calendar/entries/{eid}/restore"' not in r.text
    assert st.cal_get(conn,eid)['status']=='cancelled'


def test_cancellation_review_is_read_only_and_visibility_scoped(viewer,client,conn):
    eid=create(viewer,title='CALEP Review',start_date='2026-10-25',repeat='weekly',until='2026-11-25')
    path=f'/calendar/entries/{eid}/cancel'
    revisions=st.cal_revisions(conn,eid)
    n=conn.execute('SELECT count(*) FROM calendar_outbox').fetchone()[0]
    r=viewer.get(path)
    assert r.status_code==200 and 'Cancel whole series' in r.text and 'Nothing changes until' in r.text
    assert 'does not withdraw a reservation or travel claim' in r.text
    assert st.cal_revisions(conn,eid)==revisions
    assert conn.execute('SELECT count(*) FROM calendar_outbox').fetchone()[0]==n
    assert client.get(path,follow_redirects=False).status_code in (302,303,401)
    hidden=st.cal_create(conn,'CALEP Hidden','2026-10-25',audience='people')
    assert viewer.get(f'/calendar/entries/{hidden}/cancel').status_code==404
    viewer.post(path)
    assert st.cal_get(conn,eid)['status']=='cancelled'
    assert 'already cancelled' in viewer.get(path).text
    html=viewer.get(f'/calendar/entries/{eid}?date=2026-11-01').text
    assert 'Skip this date' not in html and 'Change just this one' not in html


def test_cancel_while_editing_keeps_draft_without_restoring_or_saving(viewer,conn):
    eid=create(viewer,title='CALEP Race',start_date='2026-10-25')
    stamp=st.cal_get(conn,eid)['updated_at']
    st.cal_cancel(conn,eid)
    revisions=st.cal_revisions(conn,eid)
    r=post(viewer,f'/calendar/entries/{eid}/edit',title='CALEP My draft',venue='Draft venue',
           note='Draft notes',start_date='2026-10-26',updated_at=stamp)
    assert r.status_code==409
    assert 'cancelled while you were editing' in r.text and 'CALEP My draft' in r.text
    assert 'Draft venue' in r.text and 'Draft notes' in r.text
    assert 'Review cancelled item in a new tab' in r.text
    assert 'cf-save' not in r.text
    assert st.cal_revisions(conn,eid)==revisions and st.cal_get(conn,eid)['title']=='CALEP Race'


def test_conflict_replacement_is_explicit_and_another_edit_is_checked_again(viewer,conn):
    eid=create(viewer,title='CALEP Conflict')
    stamp=st.cal_get(conn,eid)['updated_at']
    conn.execute("UPDATE calendar_entry SET venue='Current',updated_at='2099-01-01T00:00:00' WHERE id=?",(eid,));conn.commit()
    r=post(viewer,f'/calendar/entries/{eid}/edit',venue='My draft',updated_at=stamp)
    assert r.status_code==409 and 'Replace with my changes' in r.text and 'View current item in a new tab' in r.text
    assert 'value="My draft"' in r.text
    conn.execute("UPDATE calendar_entry SET updated_at='2099-01-02T00:00:00' WHERE id=?",(eid,));conn.commit()
    r=post(viewer,f'/calendar/entries/{eid}/edit',venue='My draft',updated_at='2099-01-01T00:00:00')
    assert r.status_code==409 and st.cal_get(conn,eid)['venue']=='Current'


def test_linked_activity_cancellation_and_series_download_have_honest_scope(admin,conn):
    eid,event_id,_=linked(conn)
    r=admin.get(f'/calendar/entries/{eid}/cancel')
    assert 'calendar item only' in r.text
    event=st.get_event_by_id(conn,event_id)
    admin.post(f'/calendar/entries/{eid}/cancel')
    assert st.get_event_by_id(conn,event_id)==event
    assert 'does not cancel that activity' in admin.get(f'/calendar/entries/{eid}').text
    other=create(admin,title='CALEP Repeats',repeat='weekly',until='2026-11-30')
    html=admin.get(f'/calendar/entries/{other}?date=2026-10-19').text
    assert 'whole series' in html and 'one-time copy' in html
    assert html.count('event.ics')==1 and f'/calendar/entries/{other}/detach?date=2026-10-19' in html


def test_subscription_help_and_page_filters_do_not_change_token_or_settings(viewer,client,conn):
    uid=st.get_admin_user(conn,'viewer@test.local')['id']
    token=st.feed_reset(conn,uid); before=st.feed_get(conn,uid)
    for url in ['/calendar?scope=bureau&status=tentative','/?view=calendar&kind=travel','/me']:
        html=viewer.get(url).text
        assert '/me#calendar-feed' in html or 'Subscription link active' in html
        assert st.feed_get(conn,uid)==before
    html=viewer.get('/me').text
    assert 'read-only copy' in html and 'one-time copy' in html
    assert 'Neither action erases copies already downloaded' in html
    assert client.get(f'/calendar/feed/{token}.ics').status_code==200
    viewer.post('/me/calendar-feed/off')
    assert 'No active subscription link' in viewer.get('/me').text
    assert client.get(f'/calendar/feed/{token}.ics').status_code==404


def test_legacy_or_unknown_display_fails_without_granting_restore():
    args={'now':tz.now_local(),'restore_days':30}
    assert guidance.entry({'status':'other'},**args)['can_restore'] is False
    g=guidance.entry({'status':'cancelled','cancelled_at':'unparseable'},**args)
    assert not g['can_restore'] and 'could not be checked' in g['step']
