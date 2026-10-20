"""
Shared fixtures for the Office Connect HTTP test suite.

Strategy
--------
* Copy the real css_is.db into a temp file (never touch the delivered DB).
* Point app.DB at the copy, seed one ACTIVE account per role with a known
  password, plus one PENDING (invited, no-password) account for token tests.
* Provide a FastAPI TestClient and per-role authenticated clients. We log a
  role in through the same registered-session issuer the app uses,
  which is exactly what a real browser carries after /login.
"""
from __future__ import annotations
import contextlib, os, shutil, tempfile, importlib
import pytest

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
def app_mod(tmp_path_factory):
    import app as app_mod
    import storage as st, auth
    src = os.path.join(os.path.dirname(app_mod.__file__), "css_is.db")
    tmpdir = tmp_path_factory.mktemp("db")
    test_db = str(tmpdir / "test.db")
    if os.path.isfile(src):
        shutil.copy(src, test_db)
    else:
        # Clean checkouts need no production snapshot to exercise HTTP routes.
        seed = st.connect(test_db)
        st.init_db(seed)
        seed.close()
    app_mod.DB = test_db                      # repoint the whole app at the copy
    import monitoring                         # keep the request log out of the repo
    monitoring.LOG_PATH = str(tmpdir / "requests.log")

    conn = st.connect(test_db); st.init_db(conn)
    # wipe any pre-existing accounts, seed deterministic ones
    conn.execute("DELETE FROM admin_user"); conn.commit()
    h, salt = auth.hash_password(PW)
    for role, username in ROLE_USERS.items():
        uid = st.create_admin_user(conn, username, h, salt, role, created_by="test", active=True)
        # The seeded role accounts represent ESTABLISHED users (post first-run):
        # stamp them onboarded so the landing (`/`) renders the hub instead of
        # diverting to the one-time /welcome flow. Tests that exercise onboarding
        # reset onboarded_at to NULL on the account they need fresh.
        st.mark_onboarded(conn, uid)
    # a pending invited account (no password) for invite/reset token tests
    st.create_admin_user(conn, "pending@test.local", "", "", "viewer",
                         created_by="test", active=False)
    # A clean checkout has no css_is.db snapshot, so the directory is empty and every test that
    # creates an activity from "the first internal person" has nobody to pick. Seed a few.
    if not conn.execute("SELECT 1 FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone():
        for name in ("Test Internal One", "Test Internal Two", "Test Internal Three"):
            conn.execute("INSERT INTO resource_person(name, is_internal) VALUES (?, 1)", (name,))
    conn.commit(); conn.close()
    # reset the in-process atoms cache so it binds to the test DB
    app_mod._atoms_state.update({"key": None, "df": None, "built": 0.0})
    app_mod._view_memo.clear()
    return app_mod

@pytest.fixture(autouse=True)
def _no_duplicate_gate(request, monkeypatch):
    """The Save-time duplicate-activity check (v7.23) asks for a second, explicit submission when an
    activity with the same title and date already exists. The session shares one database, so many
    tests that each create "the same" sample activity would be refused with a 409. Switch the check
    off everywhere except the module that tests it."""
    if request.module.__name__.endswith("test_create_duplicate_warning"):
        yield
        return
    import storage
    monkeypatch.setattr(storage, "find_similar_events", lambda *a, **k: [])
    yield


@pytest.fixture(autouse=True)
def _reset_shared_state(request):
    """Reset cross-test global state before each test:

    * The rate limiter keeps a process-global hit log (ratelimit._HITS) keyed by
      (bucket, IP). Tests run from a single constant IP, so without a reset the
      register/check buckets accumulate across the whole session and later HTTP
      tests intermittently fail with 429 depending on wall-clock timing.
    * The session-scoped `client` carries its cookie jar across tests, so a
      single successful login (e.g. test_login_success_sets_cookie) would
      silently authenticate every later "anonymous" request and make order-
      dependent assertions flap. Clear its jar so each test starts logged out.
    """
    import ratelimit
    ratelimit.reset()
    # Only touch the client if it has already been built this session — don't
    # force-create it for tests that never use HTTP.
    if "client" in getattr(request, "fixturenames", ()):
        request.getfixturevalue("client").cookies.clear()
    yield


@pytest.fixture(scope="session")
def client(app_mod):
    from starlette.testclient import TestClient
    # raise_server_exceptions=True surfaces 500s as test failures with tracebacks
    return TestClient(app_mod.app, raise_server_exceptions=True)

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
    view. Everything is undone on the way out: app_mod's database is session-
    scoped, and a stray directory link would silently change what every later
    test's admin can see."""
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
def viewer(app_mod):          return _auth_client(app_mod, "viewer")
@pytest.fixture
def encoder(app_mod):         return _auth_client(app_mod, "encoder")
@pytest.fixture
def manager(app_mod):         return _auth_client(app_mod, "section_manager")
@pytest.fixture
def admin(app_mod):           return _auth_client(app_mod, "admin")

@pytest.fixture(scope="session")
def db_path(app_mod):
    return app_mod.DB


@pytest.fixture(scope="session")
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
