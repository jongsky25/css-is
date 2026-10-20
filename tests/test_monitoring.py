"""Performance monitoring (golden signals, /health, /ops) + new audit hooks."""
import time
import pytest
import monitoring as mon
import storage as st


@pytest.fixture(autouse=True)
def _log_to_tmp(tmp_path):
    """Keep the structured request log out of the repo for the direct-record tests."""
    orig = mon.LOG_PATH
    mon.LOG_PATH = str(tmp_path / "requests.log")
    yield
    mon.LOG_PATH = orig


# ---- pure monitoring helpers --------------------------------------------

def test_bucket_path_collapses_ids():
    assert mon.bucket_path("/r/0d74d95171f6") == "/r/{token}"
    assert mon.bucket_path("/e/abc123abc123") == "/e/{token}"
    assert mon.bucket_path("/photo/42") == "/photo/{id}"
    assert mon.bucket_path("/directory/person/7/edit") == "/directory/person/{id}/edit"
    assert mon.bucket_path("/dashboard/pulse") == "/dashboard/pulse"   # unchanged


def test_percentile_interpolates():
    vals = [10, 20, 30, 40, 50]
    assert mon._percentile(vals, 0.5) == 30
    assert mon._percentile([], 0.95) == 0.0
    assert mon._percentile([7], 0.99) == 7


def test_snapshot_signals(tmp_path):
    mon.reset()
    now = time.time()
    for i in range(10):
        mon.record("GET", f"/dashboard/people/{i}", 200, 100.0 + i, now=now)
    mon.record("POST", "/r/abc123abc123", 500, 1500.0, now=now)   # one error + slow
    snap = mon.snapshot(str(tmp_path / "none.db"), now=now)
    assert snap["total"] == 11
    assert snap["status"]["5xx"] == 1
    assert snap["err5_5m"] == 1
    assert snap["slow_total"] == 1
    assert snap["p50"] >= 100
    # people route collapsed to one bucket
    buckets = {r["path"] for r in snap["routes"]}
    assert "/dashboard/people/{name}" in buckets and "/r/{token}" in buckets


def test_health_payload(tmp_path):
    mon.reset()
    h = mon.health(str(tmp_path / "x.db"), db_ok=True)
    assert h["status"] == "ok" and h["db"] == "ok"
    bad = mon.health(str(tmp_path / "x.db"), db_ok=False)
    assert bad["status"] == "degraded" and bad["db"] == "error"


# ---- routes --------------------------------------------------------------

def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and "uptime_s" in body


def test_ops_admin_only(app_mod, viewer, admin):
    from starlette.testclient import TestClient
    anon = TestClient(app_mod.app, raise_server_exceptions=True)
    assert anon.get("/ops", follow_redirects=False).status_code in (303, 307)
    assert viewer.get("/ops").status_code == 403
    assert admin.get("/ops").status_code == 200


# ---- new audit hooks -----------------------------------------------------

def _last_actions(db_path, n=12):
    conn = st.connect(db_path)
    rows = [r["action"] for r in st.list_audit(conn, limit=n)]
    conn.close()
    return rows


def test_logout_is_audited(admin, db_path):
    admin.post("/logout", follow_redirects=False)
    assert "logout" in _last_actions(db_path)


def test_directory_changes_audited(admin, db_path):
    admin.post("/directory/division", data={"name": "Audit Test Division", "confirm": "1"},
               follow_redirects=False)
    actions = _last_actions(db_path)
    assert "directory_add" in actions
    conn = st.connect(db_path)
    row = st.list_audit(conn, action="directory_add", limit=1)[0]
    conn.close()
    assert "Audit Test Division" in row["summary"]
    assert st.verify_audit_chain(st.connect(db_path))[0]   # chain still intact


def test_directory_unit_rename(admin, db_path):
    admin.post("/directory/division", data={"name": "Rename Me Division",
               "short_name": "RMD", "confirm": "1"}, follow_redirects=False)
    conn = st.connect(db_path)
    unit = next(u for u in st.list_org_units(conn) if u["name"] == "Rename Me Division")
    conn.close()
    admin.post(f"/directory/unit/{unit['id']}/edit",
               data={"name": "Renamed Division", "short_name": "RND"},
               follow_redirects=False)
    conn = st.connect(db_path)
    row = conn.execute("SELECT name, short_name FROM org_unit WHERE id=?",
                       (unit["id"],)).fetchone()
    conn.close()
    assert row[0] == "Renamed Division"
    assert row[1] == "RND"
    assert "directory_edit" in _last_actions(db_path)


def test_failed_login_audited(client, db_path):
    client.post("/login", data={"username": "nobody@test.local", "password": "wrong"},
                follow_redirects=False)
    assert "login_failed" in _last_actions(db_path)
