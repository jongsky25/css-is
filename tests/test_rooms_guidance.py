"""A17 reservation guidance agrees with real room lifecycle and access checks."""
from datetime import timedelta

import pytest

import auth
import rooms
import rooms_guidance as guidance
import storage as st
import tzutil as tz
from tests.test_rooms_pages import conn, bookable_day, slot_id, form
from tests.conftest import in_the_directory


def ask(conn, who='viewer@test.local', *, title='Guidance meeting', day=None, standby=False):
    return rooms.request(conn, title=title, day=day or bookable_day(conn), slot_ids=[slot_id(conn, 9)],
                         requester_user_id=st.get_admin_user(conn, who)['id'], standby=standby)


def rendered(viewer, rid):
    response = viewer.get('/rooms/mine')
    assert response.status_code == 200
    return next(r for k in ('upcoming', 'attention', 'earlier') for r in response.context[k] if r['id'] == rid)


def test_pending_approved_and_withdrawn_guidance_follows_writes(viewer, conn):
    res = ask(conn)
    row = rendered(viewer, res['id'])
    assert row['guidance']['state'] == 'waiting'
    assert row['guidance']['actor'] == 'Administrative Section'
    assert 'No hours are reserved' in row['guidance']['holding']
    rooms.approve(conn, res['id'], 'approver')
    assert rendered(viewer, res['id'])['guidance']['state'] == 'ready'
    response = viewer.post(f"/rooms/{res['id']}/withdraw", data={'reason': 'Plans changed'})
    assert response.status_code == 200
    row = rendered(viewer, res['id'])
    assert row['status'] == 'withdrawn' and row['guidance']['state'] == 'closed'
    assert 'no longer holds' in row['guidance']['holding']
    assert not conn.execute('SELECT 1 FROM room_reservation_slot WHERE is_approved=1').fetchone()


def test_standby_never_claims_a_booking_on_another_persons_hours(viewer, conn):
    held = ask(conn, 'encoder@test.local', title='Already reserved')
    rooms.approve(conn, held['id'], 'approver')
    pending = ask(conn, standby=True)
    row = rendered(viewer, pending['id'])
    assert 'Standby' in row['guidance']['title']
    assert 'No hours are reserved' in row['guidance']['holding']
    day = next(d for d in rooms.board(conn, bookable_day(conn), pending['requester_user_id'])['days']
               if d['iso'] == pending['day'])
    cell = next(c for c in day['cells'] if c['slot']['id'] == slot_id(conn, 9))
    assert cell['mine_requested'] and not cell['mine_approved']
    html = viewer.get('/rooms?week=' + pending['day']).text
    assert 'your request is still waiting' in html
    assert rooms.get_reservation(conn, held['id'])['status'] == 'approved'


def test_move_guidance_keeps_original_booking_until_decision(viewer, conn):
    original = ask(conn)
    rooms.approve(conn, original['id'], 'approver')
    user = st.get_admin_user(conn, 'viewer@test.local')
    moved = rooms.request_move(conn, original['id'], rooms.add_working_days(conn, bookable_day(conn), 1), user)
    old = rendered(viewer, original['id'])['guidance']
    new = rendered(viewer, moved['id'])['guidance']
    assert 'remain reserved' in old['holding']
    assert 'previous approved booking remains' in new['holding']
    assert old['related']['href'] == f"#room-{moved['id']}"
    rooms.approve(conn, moved['id'], 'approver')
    assert rendered(viewer, original['id'])['guidance']['state'] == 'replaced'
    assert rendered(viewer, moved['id'])['guidance']['state'] == 'ready'
    assert not conn.execute('SELECT 1 FROM room_reservation_slot WHERE reservation_id=? AND is_approved=1', (original['id'],)).fetchone()


@pytest.mark.parametrize('bumped', [False, True])
def test_alternatives_explain_request_vs_immediate_booking_and_replacement(viewer, conn, bumped):
    res = ask(conn)
    if bumped:
        rooms.approve(conn, res['id'], 'approver')
        rooms.encode(conn, by='approver', title='Priority use', day=res['day'], slot_ids=res['slot_ids'],
                     ext={'name': 'Office'}, bump_reason='Priority briefing')
    else:
        rooms.decline(conn, res['id'], 'approver', 'Use another time')
    row = rendered(viewer, res['id'])
    assert row['guidance']['state'] == 'attention'
    assert ('booked immediately' if bumped else 'new request for approval') in row['guidance']['step']
    offer = row['offers'][0]
    response = viewer.post(f"/rooms/{res['id']}/take", data={'day': offer['day'], 'slots': ','.join(map(str, offer['slot_ids']))})
    assert response.status_code == 200
    old = rendered(viewer, res['id'])
    assert old['guidance']['state'] == 'replaced' and not old['offers']
    replacement = conn.execute('SELECT id,status FROM room_reservation WHERE moves_reservation_id=?', (res['id'],)).fetchone()
    assert replacement[1] == ('approved' if bumped else 'requested')
    assert old['guidance']['related']['href'] == '#room-' + str(replacement[0])


def test_stale_alternative_keeps_original_state_and_refreshes_guidance(viewer, conn):
    res = ask(conn)
    rooms.decline(conn, res['id'], 'approver', 'Other time needed')
    offer = rendered(viewer, res['id'])['offers'][0]
    held = rooms.request(conn, title='Taken meanwhile', day=offer['day'], slot_ids=offer['slot_ids'],
                         requester_user_id=st.get_admin_user(conn, 'encoder@test.local')['id'])
    rooms.approve(conn, held['id'], 'approver')
    before = conn.execute('SELECT count(*) FROM room_reservation').fetchone()[0]
    response = viewer.post(f"/rooms/{res['id']}/take", data={'day': offer['day'], 'slots': ','.join(map(str, offer['slot_ids']))})
    assert 'no longer free' in response.text
    assert conn.execute('SELECT count(*) FROM room_reservation').fetchone()[0] == before
    assert rendered(viewer, res['id'])['guidance']['state'] == 'attention'


def test_closed_slots_and_no_offers_do_not_claim_alternative_held(viewer, conn, monkeypatch):
    res = ask(conn)
    rooms.decline(conn, res['id'], 'approver', '<script>private reason</script>')
    monkeypatch.setattr(rooms, 'suggestions_for', lambda *a, **k: [])
    page = viewer.get('/rooms/mine')
    assert 'No alternative is currently listed' in page.text and 'Check availability' in page.text
    assert '&lt;script&gt;private reason&lt;/script&gt;' in page.text
    assert '<script>private reason</script>' not in page.text


def test_owned_related_records_only_and_unknown_states_fail_closed():
    base = {'id': 1, 'requester_user_id': 4, 'status': 'cancelled', 'day': '2030-01-01'}
    private = {'id': 2, 'requester_user_id': 8, 'status': 'approved', 'ref_code': 'PRIVATE',
               'day': '2030-01-02', 'moves_reservation_id': 1}
    assert guidance.reservation(base, peers=[private])['related'] is None
    base['status'] = 'unexpected'
    assert guidance.reservation(base)['state'] == 'attention'
    assert 'cannot be established' in guidance.reservation(base)['holding']


def test_no_private_requests_or_new_actions_escape_the_owner_boundary(viewer, encoder, conn):
    mine = ask(conn)
    other = ask(conn, 'encoder@test.local', title='PRIVATE SUBJECT')
    page = viewer.get('/rooms/mine')
    assert 'PRIVATE SUBJECT' not in page.text
    assert f'id="room-{other["id"]}"' not in page.text
    assert encoder.post(f"/rooms/{mine['id']}/withdraw", data={}).status_code == 200
    assert rooms.get_reservation(conn, mine['id'])['status'] == 'requested'
    # A UI hint cannot grant approval; the POST checks current directory membership.
    assert viewer.post(f"/rooms/{mine['id']}/decide", data={'action': 'approve'}).status_code == 403


def test_approver_guidance_and_stale_membership_are_checked_again(app_mod, viewer, conn):
    res = ask(conn, 'encoder@test.local')
    with in_the_directory(app_mod, 'viewer@test.local', path='A17/ADMIN'):
        page = viewer.get('/approvals')
        assert 'Next: Administrative Section' in page.text
        assert 'Approve to reserve these hours' in page.text
        assert f'aria-label="Note or reason for {res["ref_code"]}"' in page.text
    assert viewer.post(f"/rooms/{res['id']}/decide", data={'action': 'approve'}).status_code == 403
    assert rooms.get_reservation(conn, res['id'])['status'] == 'requested'


def test_past_undecided_records_are_not_presented_as_approvable(conn):
    res = ask(conn)
    conn.execute('UPDATE room_reservation SET day=? WHERE id=?', ((tz.today_local() - timedelta(days=1)).isoformat(), res['id']))
    conn.commit()
    row = next(r for r in rooms.queue(conn) if r['id'] == res['id'])
    assert row['past'] and not row['can_approve'] and not row['can_confirm_standby']
    assert guidance.reservation(row)['state'] == 'past'


def test_guest_guidance_does_not_mint_tokens_or_disclose_foreign_relations(client, conn):
    res = rooms.request_external(conn, name='Guest', org='Example', email='guest@example.test', phone='',
                                 consent=True, title='Guest meeting', day=bookable_day(conn), slot_ids=[slot_id(conn, 9)])
    token = auth.make_room_track_token(res['id'])
    page = client.get('/room/t/' + token + '?new=1')
    assert page.status_code == 200 and 'No hours are reserved' in page.text
    assert 'We emailed a link' not in page.text
    foreign = ask(conn, title='PRIVATE RELATIVE')
    conn.execute('UPDATE room_reservation SET moves_reservation_id=? WHERE id=?', (res['id'], foreign['id']))
    conn.commit()
    assert guidance.guest_relations(conn, res) == []
    assert 'PRIVATE RELATIVE' not in client.get('/room/t/' + token).text


def test_reading_guidance_and_availability_never_requests_or_reserves(viewer, conn, monkeypatch):
    res = ask(conn)
    before = conn.execute('SELECT id,status,updated_at FROM room_reservation ORDER BY id').fetchall()
    monkeypatch.setattr(rooms, 'request', lambda *a, **k: pytest.fail('Read must not request'))
    monkeypatch.setattr(rooms, 'approve', lambda *a, **k: pytest.fail('Read must not approve'))
    assert viewer.get('/rooms/mine').status_code == 200
    response = viewer.get('/rooms/api/day?date=' + res['day'])
    assert response.status_code == 200
    assert 'Guidance meeting' not in response.text
    assert conn.execute('SELECT id,status,updated_at FROM room_reservation ORDER BY id').fetchall() == before


def test_expiry_is_explained_without_claiming_a_booking(viewer, conn):
    import rooms_notify
    res = ask(conn)
    old_day = (tz.today_local() - timedelta(days=1)).isoformat()
    conn.execute('UPDATE room_reservation SET day=? WHERE id=?', (old_day,res['id']))
    conn.execute('UPDATE room_reservation_slot SET day=? WHERE reservation_id=?', (old_day,res['id']))
    conn.commit()
    rooms_notify.expire_past_requests(conn,tz.today_local())
    row = rendered(viewer,res['id'])
    assert row['status'] == 'expired'
    assert row['guidance']['title'] == 'Request expired without approval'
    assert 'No hours were reserved' in row['guidance']['holding']
