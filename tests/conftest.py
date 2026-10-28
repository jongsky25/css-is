"""
Shared fixtures for the Office Connect HTTP test suite.

Strategy
--------
* Build a synthetic reference database once; give each test a private copy.
* Point app.DB at that test copy, with one ACTIVE account per role and a known
  password, plus one PENDING (invited, no-password) account for token tests.
* Provide a FastAPI TestClient and per-role authenticated clients. We log a
  role in through the same registered-session issuer the app uses,
  which is exactly what a real browser carries after /login.
"""
from __future__ import annotations
import contextlib, os, tempfile, sqlite3
import time
from datetime import datetime, timedelta
import tzutil as tz
import pytest

# Set before collection so module-level date constants use the same clock.
_TEST_NOW = datetime.fromisoformat(os.environ.get("CSS_TEST_NOW", "2026-10-20T06:00:00"))
_REAL_TIME = time.time
_TEST_EPOCH = _TEST_NOW.replace(tzinfo=tz.LOCAL_TZ).timestamp()
_REAL_NOW_LOCAL = tz.now_local
_REAL_TODAY_LOCAL = tz.today_local
def pytest_configure(config):
    started = time.monotonic()
    time.time = lambda: _TEST_EPOCH + time.monotonic() - started
    tz.now_local = lambda: _TEST_NOW
    tz.today_local = lambda: tz.now_local().date()


def pytest_unconfigure(config):
    time.time = _REAL_TIME
    tz.now_local = _REAL_NOW_LOCAL
    tz.today_local = _REAL_TODAY_LOCAL


def pytest_addoption(parser):
    parser.addoption("--application-suite", action="store_true", default=False,
                     help="Run application tests; leave explicitly disabled avatar experiment modules uncollected")
    parser.addoption("--shuffle-seed", type=int, default=None,
                     help="Deterministically shuffle test cases with this seed")


def pytest_ignore_collect(collection_path, config):
    if not config.getoption("--application-suite"):
        return None
    from tests.avatar_opt_in_suites import AVATAR_OPT_IN_SUITES
    opt_in = AVATAR_OPT_IN_SUITES.get(collection_path.name)
    return bool(opt_in and os.getenv(opt_in[0]) != opt_in[1])


def pytest_collection_modifyitems(config, items):
    seed = config.getoption("--shuffle-seed")
    if seed is not None:
        import hashlib
        items.sort(key=lambda item: hashlib.sha256(f"{seed}:{item.nodeid}".encode()).digest())


def pytest_report_header(config):
    return f"Application clock: {_TEST_NOW.isoformat()}; shuffle seed: {config.getoption('--shuffle-seed')}"


@pytest.fixture(autouse=True)
def application_clock(monkeypatch):
    # Epoch-based tokens and local dates share one reference. Monotonic time and
    # short elapsed intervals keep advancing, so worker timeouts still work.
    started = time.monotonic()
    monkeypatch.setattr(time, "time", lambda: _TEST_EPOCH + time.monotonic() - started)
    monkeypatch.setattr(tz, "now_local", lambda: _TEST_NOW)
    monkeypatch.setattr(tz, "today_local", lambda: tz.now_local().date())


@pytest.fixture
def real_application_clock(monkeypatch):
    """Opt into the real timezone adapter when testing that adapter itself."""
    monkeypatch.setattr(tz, "now_local", _REAL_NOW_LOCAL)


PW = "Test1234!"
ROLE_USERS = {
    "viewer":          "viewer@test.local",
    "encoder":         "encoder@test.local",
    "section_manager": "manager@test.local",
    "admin":           "admin@test.local",
}


@pytest.fixture(scope="session", autouse=True)
def _browser_request_origins():
    """HTTP clients model a browser's Origin; security tests can clear it.

    This exercises the production origin check, not an authentication bypass.
    TestClient does not synthesize browser security headers itself. Explicit
    per-request headers still override the default, including hostile origins.
    """
    from starlette.testclient import TestClient
    from urllib.parse import urlsplit
    original = TestClient.__init__

    def browser_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        url = urlsplit(str(self.base_url))
        self.headers.setdefault('Origin', f'{url.scheme}://{url.netloc}')

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(TestClient, '__init__', browser_init)
        yield

def join_admin_section(conn, user_id, path="BLHSD/ADMIN"):
    """Make this account a member of the Administrative Section (the only room approvers)."""
    row = conn.execute("SELECT id FROM org_unit WHERE path=?", (path,)).fetchone()
    unit = row[0] if row else conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Administrative Section", "ADMIN", "section", path)).lastrowid
    rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES (?,1,?)",
                      (f"ADMIN-{user_id}", unit)).lastrowid
    conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp, user_id))
    conn.commit()
    return user_id


@pytest.fixture(scope="session")
def reference_database(tmp_path_factory):
    """No production input: a documented, nonempty example for all three surveys."""
    import storage as st, auth
    path = str(tmp_path_factory.mktemp("reference") / "reference.db")
    conn = st.connect(path)
    st.init_db(conn)
    h, salt = auth.hash_password(PW)
    for role, username in ROLE_USERS.items():
        uid = st.create_admin_user(conn, username, h, salt, role, created_by="test", active=True)
        st.mark_onboarded(conn, uid)
    st.create_admin_user(conn, "pending@test.local", "", "", "viewer", created_by="test", active=False)
    st.get_or_create_blhsd(conn)
    section = st.add_org_unit(conn, "Reference Section", "section", "BLHSD/REFERENCE")
    people = []
    for name in ("Test Internal One", "Test Internal Two", "Test Internal Three"):
        people.append(conn.execute("INSERT INTO resource_person(name,is_internal,org_unit_id) VALUES (?,1,?)",
                                  (name, section)).lastrowid)
    conn.commit()
    for days in (7, 42):
        day = (_TEST_NOW.date() - timedelta(days=days)).isoformat()
        for kind in (1, 2, 3):
            fid = st.create_form_instance(conn, kind, f"F{kind}", day,
                topic=f"Reference Learning {days}", venue=f"Reference Hall {days}",
                lead_org_id=section if kind == 2 else None,
                serving_staff_org_id=section if kind == 1 else None,
                rp_id=people[0] if kind == 3 else None)
            answers = ([(f"SQD{i}", 5) for i in range(9)] if kind == 1 else
                       [("A", 6), *[(f"B{i}", 6) for i in range(1, 10)], ("C", 4)])
            for n in range(12):
                st.record_response(conn, fid, answers, submitted_at=day+"T09:00:00",
                    remarks="Reference feedback: clear explanations",
                    served_by_rp_id=people[0] if kind == 1 else None)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return path


@pytest.fixture
def app_mod(reference_database, monkeypatch):
    import app as app_mod
    import storage as st, monitoring
    with tempfile.TemporaryDirectory(prefix="office-test-") as directory:
        test_db = os.path.join(directory, "test.db")
        with sqlite3.connect(reference_database) as src, sqlite3.connect(test_db) as dst:
            src.backup(dst)
        # The travel admin review (spot feedback #174) is required in production; the many tests that walk a claim to
        # ready start with it off and the review tests switch it on.
        _c = st.connect(test_db)
        st.set_setting(_c, "travel.review_required", "0")
        _c.commit(); _c.close()
        monkeypatch.setattr(app_mod, "DB", test_db)
        # Lifespan tests close the application reader. Keep that lifecycle local
        # to this test, just like its database, instead of poisoning later clients.
        from sqlite_reader import SQLiteReader
        reader = SQLiteReader()
        monkeypatch.setattr(app_mod, "_read_worker", reader)
        monkeypatch.setattr(monitoring, "LOG_PATH", os.path.join(directory, "requests.log"))
        # Test-local snapshots prevent direct cache mutation leaking into later cases.
        monkeypatch.setattr(app_mod, "_atoms_state", dict(
            key=None, df=None, built=0.0, answer_maxid=0, force_full=True,
            rebuilding=False, rebuild_started=0.0, stale_since=0.0, bg_full=False, epoch=0))
        monkeypatch.setattr(app_mod, "_view_memo", {})
        monkeypatch.setattr(app_mod, "_view_prev", {})
        monkeypatch.setattr(app_mod, "_views_warming", False)
        monkeypatch.setattr(app_mod, "_views_warming_since", 0.0)
        # Restore even the few legacy tests that directly assign these wrappers.
        monkeypatch.setattr(app_mod, "_today_local", lambda: tz.today_local())
        monkeypatch.setattr(app_mod, "_now_local", lambda: tz.now_local())
        st.basic_status_clear_cache()
        try:
            yield app_mod
        finally:
            # Startup may replace the fixture reader; close both owners.
            app_mod._read_worker.close()
            reader.close()
            st.basic_status_clear_cache()

@pytest.fixture(autouse=True)
def _reset_shared_state(request):
    """Reset cross-test global state before each test:

    * The rate limiter keeps a process-global hit log (ratelimit._HITS) keyed by
      (bucket, IP). Tests run from a single constant IP, so without a reset the
      register/check buckets accumulate across the whole session and later HTTP
      tests intermittently fail with 429 depending on wall-clock timing.
    * A client cookie jar can retain authentication, so a
      single successful login (e.g. test_login_success_sets_cookie) would
      silently authenticate every later "anonymous" request and make order-
      dependent assertions flap. Clear its jar so each test starts logged out.
    """
    import ratelimit
    ratelimit.reset()
    # Avoid creating an HTTP client for pure logic/storage tests.
    if "client" in getattr(request, "fixturenames", ()):
        request.getfixturevalue("client").cookies.clear()
    yield


@pytest.fixture
def client(app_mod):
    from starlette.testclient import TestClient
    # raise_server_exceptions=True surfaces 500s as test failures with tracebacks
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    yield c
    c.close()

def session_token(user):
    """Use the application's registered-session path for authenticated fixtures."""
    import app
    token = app._issue_session(user)
    assert token is not None, "Fixture account must be active and eligible to sign in"
    return token


def _auth_client(app_mod, role):
    from starlette.testclient import TestClient
    import auth, storage as st
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user(conn, ROLE_USERS[role]); conn.close()
    user = {"id": u["id"], "username": u["username"], "role": u["role"]}
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, session_token(user))
    return c

@contextlib.contextmanager
def in_the_directory(app_mod, *usernames, path="LFTEAM/D1/S1"):
    """Place these accounts in one directory unit for the duration of a test.

    The seeded role accounts carry no rp_id, and the DIRECTORY — not the app
    role — is what decides whose filings a page shows (storage.team_scope_for_user),
    so without this they have no team and the landing page renders the personal
    view. Everything is undone on the way out so callers can compare the
    linked and unlinked states in the same test."""
    import storage as st
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("LF Section", "LF-S1", "section", path)).lastrowid
    before, made = {}, []
    try:
        for username in usernames:
            u = st.get_admin_user(conn, username)
            before[u["id"]] = conn.execute(
                "SELECT rp_id FROM admin_user WHERE id=?", (u["id"],)).fetchone()[0]
            rp = conn.execute(
                "INSERT INTO resource_person(name, is_internal, org_unit_id)"
                " VALUES (?,1,?)", (f"LF-{username.split('@')[0]}", unit)).lastrowid
            made.append(rp)
            conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp, u["id"]))
        conn.commit()
        yield
    finally:
        for uid, rp_id in before.items():
            conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp_id, uid))
        for rp in made:
            conn.execute("DELETE FROM resource_person WHERE id=?", (rp,))
        conn.execute("DELETE FROM org_unit WHERE id=?", (unit,))
        conn.commit()
        conn.close()


@pytest.fixture
def viewer(app_mod):
    c = _auth_client(app_mod, "viewer")
    yield c
    c.close()
@pytest.fixture
def encoder(app_mod):
    c = _auth_client(app_mod, "encoder")
    yield c
    c.close()
@pytest.fixture
def manager(app_mod):
    c = _auth_client(app_mod, "section_manager")
    yield c
    c.close()
@pytest.fixture
def admin(app_mod):
    c = _auth_client(app_mod, "admin")
    yield c
    c.close()

@pytest.fixture
def db_path(app_mod):
    return app_mod.DB


@pytest.fixture
def sample_ids(app_mod):
    """Real ids/tokens pulled from the test DB for path-param routes."""
    import storage as st
    conn = st.connect(app_mod.DB); st.init_db(conn)
    rp = conn.execute("SELECT id FROM resource_person ORDER BY id LIMIT 1").fetchone()
    unit = conn.execute("SELECT id FROM org_unit ORDER BY id LIMIT 1").fetchone()
    tok = conn.execute("SELECT qr_token FROM form_instance WHERE qr_token IS NOT NULL "
                       "ORDER BY id LIMIT 1").fetchone()
    inst = conn.execute("SELECT id FROM form_instance ORDER BY id LIMIT 1").fetchone()
    resp = conn.execute("SELECT id FROM response ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return {
        "rp_id": rp[0] if rp else 0,
        "unit_id": unit[0] if unit else 0,
        "qr_token": tok[0] if tok else "missing",
        "form_instance_id": inst[0] if inst else 0,
        "response_id": resp[0] if resp else 0,
    }


@pytest.fixture
def future_weekday(monkeypatch):
    """A workday (Wednesday) inside the CURRENT ISO week, with the wall clock
    pinned to that week's Monday morning.

    Wellness breaks can only be filed within the current work week
    (storage.WELLNESS_WINDOW_WEEKS == 1), so "a day safely in the future"
    only exists on some real calendar days — on a Thu/Fri/Sat/Sun test run
    there's no later weekday left in-window, and falling back to today would
    couple every caller to the real wall-clock's time-of-day against
    WELLNESS_MIN_LEAD_MINUTES. Freezing 'now' to a fixed Monday sidesteps
    both: any weekday that week is fair game, deterministically, regardless
    of which real day the suite happens to run on."""
    import tzutil as tz
    from datetime import datetime, time, timedelta
    today = tz.today_local()
    monday = today - timedelta(days=today.weekday())
    fixed = datetime.combine(monday, time(6, 0))
    monkeypatch.setattr(tz, "now_local", lambda: fixed)
    monkeypatch.setattr(tz, "today_local", lambda: fixed.date())
    return (monday + timedelta(days=2)).isoformat()   # Wednesday


@pytest.fixture
def reference_form(app_mod):
    """Create explicit survey examples and remove their rows after the test."""
    import storage as st
    created = []

    def make(survey_type, day, answers, *, submitted_at=None, **context):
        conn = st.connect(app_mod.DB)
        try:
            fid = st.create_form_instance(conn, survey_type, f"F{survey_type}", day, **context)
            created.append(fid)
            st.record_response(conn, fid, answers, submitted_at=submitted_at)
        finally:
            conn.close()
        app_mod.invalidate_atoms()
        return fid

    yield make
    conn = st.connect(app_mod.DB)
    try:
        for fid in created:
            for table in ("answer", "item_remark"):
                conn.execute(f"DELETE FROM {table} WHERE response_id IN "
                             "(SELECT id FROM response WHERE form_instance_id=?)", (fid,))
            conn.execute("DELETE FROM response WHERE form_instance_id=?", (fid,))
            conn.execute("DELETE FROM form_instance WHERE id=?", (fid,))
        conn.commit()
    finally:
        conn.close()
        app_mod.invalidate_atoms()
