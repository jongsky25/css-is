"""HTTP query reduction, display parity and current-request access boundaries."""
import sqlite3
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

import storage as st
from tests.conftest import session_token
from starlette.testclient import TestClient
import auth
from request_reads import RequestReads


@pytest.fixture
def home_world(app_mod):
    conn = app_mod.get_conn()
    units = {}
    users = {}
    for suffix, path in [('one', 'READ/D1/S1'), ('other', 'READ/D2/S2'), ('admin', 'READ/ADMIN')]:
        units[suffix] = conn.execute(
            'INSERT INTO org_unit(name,short_name,level,path) VALUES (?,?,?,?)',
            (suffix, suffix, 'section', path)).lastrowid
    for name, section, designation, role in [
        ('chief', 'one', 'Section Head', 'section_manager'),
        ('staff', 'one', '', 'viewer'),
        ('other', 'other', '', 'viewer'),
        ('rooms', 'admin', '', 'viewer'),
        ('unlinked', None, '', 'admin'),
    ]:
        rp = conn.execute(
            'INSERT INTO resource_person(name,is_internal,org_unit_id,designation) VALUES (?,1,?,?)',
            (f'Read {name}', units[section], designation)).lastrowid if section else None
        uid = st.create_admin_user(conn, f'read-{name}@test.local', 'x', 'y', role, rp_id=rp)
        st.mark_onboarded(conn, uid)
        users[name] = st.get_admin_user_by_id(conn, uid)
    claim = st.create_wellness_claim(conn, users['staff']['id'], '2026-10-22', '10:00', 'exercise')
    st.create_wellness_claim(conn, users['other']['id'], '2026-10-22', '10:00', 'exercise')
    st.set_setting(conn, 'documents.enabled', '1')
    import documents
    doc = documents.register(conn, users['staff'], {'subject': 'Read private review', 'type': 'memo'})
    conn.execute("UPDATE document SET reviewer_id=?,status='in_review' WHERE id=?", (users['chief']['id'], doc['id']))
    conn.execute('INSERT INTO document_access(document_id,user_id,source) VALUES (?,?,?)',
                 (doc['id'], users['chief']['id'], 'read-test'))
    conn.commit()
    clients = {}
    for name, user in users.items():
        client = TestClient(app_mod.app)
        client.cookies.set(auth.COOKIE_NAME, session_token(user))
        clients[name] = client
    yield {'conn': conn, 'users': users, 'clients': clients, 'units': units, 'doc': doc, 'claim': claim}
    for client in clients.values():
        client.close()
    conn.close()


def test_home_reads_are_shared(app_mod, home_world, monkeypatch):
    import documents
    import rooms
    import work_inbox
    counts = dict(approvals=0, reviews=0, room_admin=0, work_preview=0)
    for module, name, key in [(st, 'pending_approval_counts', 'approvals'),
                              (documents, 'count_visible', 'reviews'),
                              (rooms, 'is_room_admin', 'room_admin'),
                              (work_inbox, 'page', 'work_preview')]:
        original = getattr(module, name)

        def counted(*args, _original=original, _key=key, **kwargs):
            counts[_key] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, counted)
    statements = []
    connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, 'connect', traced_connect)
    response = home_world['clients']['chief'].get('/')
    assert response.status_code == 200
    assert '1 wellness break waiting on your decision' in response.text
    assert '1 document review' in response.text
    selects = sum(s.lstrip().upper().startswith(('SELECT', 'WITH')) for s in statements)
    print({'display_builds': counts, 'http_selects': selects})
    assert counts == dict(approvals=1, reviews=1, room_admin=1, work_preview=1)


def _payload(response):
    assert response.status_code == 200
    ctx = response.context
    state = ctx['request'].state
    calendar = dict(ctx['cal_page']) if ctx['cal_page'] else None
    if calendar:
        # Compare the link builder's output rather than two closure identities.
        calendar['qs'] = [calendar['qs'](), calendar['qs'](scope='mine')]
    return deepcopy({
        'data': ctx['d'], 'tasks': ctx['tasks'], 'week': ctx['cal_week'],
        'calendar': calendar, 'team_linked': ctx['team_linked'],
        'notifications': state.notifications, 'notif_count': state.notif_count,
        'is_chief': state.is_chief, 'room_approver': state.user['room_approver'],
        'bureau_access': state.user['bureau_access'],
    })


def _assign(world):
    conn = world['conn']
    conn.execute('''INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at)
                    VALUES (?,?,'contributor','Review','assigned','2026-10-20')''',
                 (world['doc']['id'], world['users']['chief']['id']))
    conn.commit()


class FreshReads(RequestReads):
    """Reference path: run the existing domain readers afresh for every caller."""
    def _read(self, key, user, build):
        assert user['id'] == self.user_id
        return deepcopy(build())


@pytest.mark.parametrize('who', ['chief', 'staff', 'other', 'rooms', 'unlinked'])
@pytest.mark.parametrize('view', ['', '?view=me', '?view=calendar'])
def test_shared_display_matches_fresh_domain_reads(app_mod, home_world, monkeypatch, who, view):
    _assign(home_world)
    client = home_world['clients'][who]
    shared = _payload(client.get('/' + view))
    monkeypatch.setattr(app_mod, 'RequestReads', FreshReads)
    fresh = _payload(client.get('/' + view))
    assert shared == fresh
    if who != 'chief':
        assert 'Read private review' not in str(shared)


def test_next_request_sees_new_approval_and_review_status(home_world):
    client = home_world['clients']['chief']
    before = _payload(client.get('/'))
    assert before['data']['approvals'] == {'wellness': 1, 'awa': 0, 'total': 1}
    conn = home_world['conn']
    conn.execute("UPDATE wellness_claim SET status='approved' WHERE id=?", (home_world['claim'],))
    conn.execute("UPDATE document SET status='approved' WHERE id=?", (home_world['doc']['id'],))
    conn.commit()
    after = _payload(client.get('/'))
    assert after['data']['approvals'] is None
    assert not [t for t in after['tasks'] if t['key'] == 'approvals']
    assert not [n for n in after['notifications'] if 'waiting on your decision' in n['text']
                or 'document reviews' in n['text']]


def test_document_access_revocation_removes_preview_and_reviews(home_world):
    _assign(home_world)
    client = home_world['clients']['chief']
    assert 'Read private review' in str(_payload(client.get('/')))
    conn = home_world['conn']
    conn.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?',
                 (home_world['doc']['id'], home_world['users']['chief']['id']))
    conn.commit()
    after = _payload(client.get('/'))
    assert 'Read private review' not in str(after)
    assert not [n for n in after['notifications'] if 'document reviews' in n['text']]
    assert client.get('/documents/' + str(home_world['doc']['id'])).status_code == 404


def test_oic_revocation_takes_effect_on_next_request(home_world):
    conn = home_world['conn']
    st.set_section_oic(conn, home_world['units']['one'], home_world['users']['other']['id'])
    client = home_world['clients']['other']
    before = _payload(client.get('/'))
    assert before['is_chief']
    assert before['data']['approvals']['wellness'] == 1
    st.clear_section_oic(conn, home_world['units']['one'])
    after = _payload(client.get('/'))
    assert not after['is_chief']
    assert after['data']['approvals'] is None


def test_room_membership_revocation_takes_effect_on_next_request(home_world):
    client = home_world['clients']['rooms']
    assert _payload(client.get('/'))['room_approver']
    conn = home_world['conn']
    conn.execute('UPDATE resource_person SET org_unit_id=? WHERE id=?',
                 (home_world['units']['one'], home_world['users']['rooms']['rp_id']))
    conn.commit()
    assert not _payload(client.get('/'))['room_approver']
    assert client.get('/travel/verify').status_code == 403


def test_bureau_grant_revocation_is_not_cached(home_world):
    conn = home_world['conn']
    client = home_world['clients']['staff']
    st.set_bureau_access(conn, home_world['users']['staff']['id'], 'all')
    assert _payload(client.get('/'))['data']['scope']['kind'] == 'bureau'
    st.set_bureau_access(conn, home_world['users']['staff']['id'], '')
    after = _payload(client.get('/'))
    assert after['data']['scope']['kind'] == 'unit'
    assert after['bureau_access'] == ''


def test_disabled_account_cannot_reuse_a_previous_home_summary(home_world):
    client = home_world['clients']['chief']
    assert client.get('/').status_code == 200
    conn = home_world['conn']
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (home_world['users']['chief']['id'],))
    conn.commit()
    denied = client.get('/', follow_redirects=False)
    assert denied.status_code == 303 and denied.headers['location'].startswith('/login?next=')


def test_document_feature_switch_is_fresh_on_next_request(home_world):
    _assign(home_world)
    client = home_world['clients']['chief']
    assert 'Read private review' in str(_payload(client.get('/')))
    st.set_setting(home_world['conn'], 'documents.enabled', '0')
    after = _payload(client.get('/'))
    assert 'Read private review' not in str(after)
    assert not [n for n in after['notifications'] if 'document reviews' in n['text']]


def test_failed_preview_is_retried_by_home(app_mod, home_world, monkeypatch):
    import work_inbox
    _assign(home_world)
    original = work_inbox.page
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise sqlite3.OperationalError('synthetic transient failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(work_inbox, 'page', fail_once)
    result = _payload(home_world['clients']['chief'].get('/'))
    assert len(calls) == 2
    assert 'Read private review' in str(result['tasks'])


def test_display_results_do_not_authorize_a_write_after_revocation(home_world):
    conn = home_world['conn']
    user = home_world['users']['chief']
    reads = RequestReads(user['id'])
    assert reads.approvals(conn, user)['wellness'] == 1
    conn.execute("UPDATE resource_person SET designation='' WHERE id=?", (user['rp_id'],))
    conn.commit()
    with pytest.raises(PermissionError):
        st.decide_wellness_claim(conn, home_world['claim'], user, 'approve')
    assert st.get_wellness_claim(conn, home_world['claim'])['status'] == 'pending'


def test_display_results_are_copied_and_bound_to_one_account(home_world):
    conn = home_world['conn']
    user = home_world['users']['chief']
    reads = RequestReads(user['id'])
    counts = reads.approvals(conn, user)
    counts['wellness'] = 999
    assert reads.approvals(conn, user)['wellness'] == 1
    _assign(home_world)
    import tzutil
    preview, cursor = reads.work_preview(conn, user, tzutil.today_local())
    original_title = preview[0]['title']
    preview[0]['title'] = 'Changed by one display consumer'
    assert reads.work_preview(conn, user, tzutil.today_local())[0][0]['title'] == original_title
    with pytest.raises(ValueError, match='another account'):
        reads.approvals(conn, home_world['users']['staff'])


def test_simultaneous_users_have_separate_display_results(home_world):
    _assign(home_world)
    names = ['chief', 'staff', 'other']
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda name: _payload(home_world['clients'][name].get('/')), names))
    assert 'Read private review' in str(results[0])
    assert results[0]['data']['approvals']['wellness'] == 1
    assert results[1]['data']['approvals'] is None
    assert results[2]['data']['approvals'] is None
    assert 'Read private review' not in str(results[2])


@pytest.mark.parametrize('who', ['rooms', 'chief', 'unlinked'])
def test_travel_flags_reuse_room_display_check_without_role_bypass(home_world, monkeypatch, who):
    import rooms
    import travel_notify
    import tzutil
    conn = home_world['conn']
    user = home_world['users'][who]
    fid = conn.execute('''INSERT INTO travel_filing(ref_code,user_id,kind,source_kind,act_title,act_start,act_end)
        VALUES ('read-travel',?,'reimbursement','blank','Synthetic travel','2026-10-22','2026-10-23')''',
        (home_world['users']['staff']['id'],)).lastrowid
    conn.execute("INSERT INTO travel_flag(filing_id,kind,sig) VALUES (?,'over_ceiling','read-flag')", (fid,))
    conn.commit()
    fresh = travel_notify.bell_rows(conn, user['id'], tzutil.today_local())
    reads = RequestReads(user['id'])
    assert reads.room_admin(conn, user) == (who == 'rooms')

    def repeated(*args, **kwargs):
        raise AssertionError('The room display check was already read for this request.')

    monkeypatch.setattr(rooms, 'is_room_admin', repeated)
    shared = travel_notify.bell_rows(conn, user['id'], tzutil.today_local(), reads=reads)
    assert shared == fresh
    assert bool([r for r in shared if 'to verify' in r['text']]) == (who == 'rooms')
