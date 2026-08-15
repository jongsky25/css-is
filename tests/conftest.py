"""
Shared fixtures for the Office Connect HTTP test suite.

Strategy
--------
* Copy the real css_is.db into a temp file (never touch the delivered DB).
* Point app.DB at the copy, seed one ACTIVE account per role with a known
  password, plus one PENDING (invited, no-password) account for token tests.
* Provide a FastAPI TestClient and per-role authenticated clients. We log a
  role in by minting the same signed cookie the app issues (auth.make_token),
  which is exactly what a real browser carries after /login.
"""
from __future__ import annotations
import os, shutil, tempfile, importlib
import pytest

PW = "Test1234!"
ROLE_USERS = {
    "viewer":          "viewer@test.local",
    "encoder":         "encoder@test.local",
    "section_manager": "manager@test.local",
    "admin":           "admin@test.local",
}

@pytest.fixture(scope="session")
def app_mod(tmp_path_factory):
    import app as app_mod
    import storage as st, auth
    src = os.path.join(os.path.dirname(app_mod.__file__), "css_is.db")
    tmpdir = tmp_path_factory.mktemp("db")
    test_db = str(tmpdir / "test.db")
    shutil.copy(src, test_db)
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
    conn.commit(); conn.close()
    # reset the in-process atoms cache so it binds to the test DB
    app_mod._atoms_state.update({"key": None, "df": None, "built": 0.0})
    app_mod._view_memo.clear()
    return app_mod

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

def _auth_client(app_mod, role):
    from starlette.testclient import TestClient
    import auth, storage as st
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user(conn, ROLE_USERS[role]); conn.close()
    user = {"id": u["id"], "username": u["username"], "role": u["role"]}
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(user))
    return c

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
