"""M1.1 privacy, UI parity, pagination and no-domain-write checks."""
import json

import pytest
import storage as st
import rooms
import work_updates
from documents_registry import snapshot
from mcp_read import _notice_page, _room_availability


def test_personal_notices_hide_content_and_recheck_visibility(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    other = st.get_admin_user(conn, 'encoder@test.local')
    unit = conn.execute("INSERT INTO org_unit(name,level,path) VALUES ('M1','section','M1')").lastrowid
    for key in ('documents.enabled', 'work.enabled'):
        st.set_setting(conn, key, '1')
    case = conn.execute('''INSERT INTO work_case(title,outcome,unit_id,creator_id,created_at,updated_at)
        VALUES ('Hidden title','Private outcome',?,?,?,?)''',
        (unit, user['id'], '2026-10-20', '2026-10-20')).lastrowid
    for recipient in (user['id'], user['id'], other['id']):
        comment = conn.execute('INSERT INTO work_comment(case_id,author_id,created_at) VALUES (?,?,?)',
                               (case, other['id'], '2026-10-20')).lastrowid
        conn.execute('INSERT INTO work_comment_revision VALUES (?,1,?,?)', (comment, 'Secret message body', '2026-10-20'))
        conn.execute("INSERT INTO work_notice(comment_id,user_id,revision,reason,created_at) VALUES (?,?,1,'mention',?)",
                     (comment, recipient, '2026-10-20'))
    conn.commit()
    assert _notice_page(conn, user, 'https://office.example')['availability'] == 'not_available'
    monkeypatch.setenv('CSS_MCP_NOTIFICATIONS_ENABLED', '1')
    initial_changes = conn.total_changes
    with snapshot(conn):
        page = _notice_page(conn, user, 'https://office.example', limit=1)
        second = _notice_page(conn, user, 'https://office.example', limit=1, before=page['next_before'])
        ui, _ = work_updates.inbox(conn, user)
        assert {n['id'] for n in ui} == {int(page['data'][0]['id']), int(second['data'][0]['id'])}
        assert page['data'][0]['id'] != second['data'][0]['id']
        assert page['data'][0]['unread'] is True
        assert 'Secret message body' not in json.dumps(page)
        assert 'Hidden title' not in json.dumps(page)
        assert 'author' not in page['data'][0]
    assert conn.total_changes == initial_changes
    assert conn.execute('SELECT COUNT(*) FROM work_comment_read').fetchone()[0] == 0
    conn.execute('UPDATE work_case SET creator_id=? WHERE id=?', (other['id'], case))
    conn.commit()
    with snapshot(conn):
        assert _notice_page(conn, user, 'https://office.example')['data'] == []
    st.set_setting(conn, 'work.enabled', '0')
    assert _notice_page(conn, user, 'https://office.example')['availability'] == 'not_available'
    conn.close()


def test_room_availability_matches_picker_and_has_no_private_details(app_mod, monkeypatch):
    conn = st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    assert _room_availability(conn, user, '', '2026-10-27')['availability'] == 'not_available'
    rooms.ensure_slots(conn)
    slots = rooms.list_slots(conn)
    day = '2026-10-27'
    for state, slot in zip(('approved', 'requested'), slots):
        rid = conn.execute('INSERT INTO room_reservation(title,day,status,requester_user_id) VALUES (?,?,?,?)',
                           ('Private booking title', day, state, user['id'])).lastrowid
        conn.execute('INSERT INTO room_reservation_slot(reservation_id,day,slot_id,is_approved) VALUES (?,?,?,?)',
                     (rid, day, slot['id'], int(state == 'approved')))
    conn.execute('INSERT INTO room_block(day,slot_id,reason) VALUES (?,?,?)', (day, slots[2]['id'], 'Private block reason'))
    conn.commit()
    monkeypatch.setenv('CSS_MCP_AVAILABILITY_ENABLED', '1')
    initial_changes = conn.total_changes
    with snapshot(conn):
        page = _room_availability(conn, user, '', day, limit=2)
        second = _room_availability(conn, user, '', day, limit=2, offset=page['next_offset'])
        ui = rooms.day_view(conn, day)
        assert [n['state'] for n in page['data']] == [h['state'] for h in ui['hours'][:2]]
        assert page['data'][0]['available_for_request'] is False
        assert page['data'][1]['available_for_request'] is True  # Pending holds nothing.
        assert second['data'][0]['state'] == 'closed'
        assert 'Private' not in json.dumps(page) + json.dumps(second)
        assert not page['reservation_made']
        weekend = _room_availability(conn, user, '', '2026-10-25')
        assert all(not n['available_for_request'] for n in weekend['data'])
    assert conn.total_changes == initial_changes
    for invalid in ('2026-99-99', '2026-1-1', '', 'tomorrow'):
        with pytest.raises(ValueError):
            _room_availability(conn, user, '', invalid)
    with pytest.raises(ValueError):
        _room_availability(conn, user, '', day, limit=26)
    conn.close()
