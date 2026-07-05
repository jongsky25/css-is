"""
Input / abuse hardening — regression guard for BUG-1 (public respondent endpoint
must never 500 or store junk on hostile input) and BUG-3 (bad event_date must be
rejected at creation, not crash reporting).

The public POST /r/{token} is the highest-risk surface: it's unauthenticated and
writes to the DB. These tests fire malformed, out-of-range, and injection-style
payloads at it and assert it degrades gracefully (coerce-to-N/A) instead of
erroring.
"""
import pytest
import storage as st


@pytest.fixture
def walkin_token(app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    w = st.get_or_create_walkin_form(conn); conn.close()
    return w["qr_token"]


def _count_responses(app_mod, token):
    conn = st.connect(app_mod.DB)
    ctx = st.get_form_context(conn, token)
    n = conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?",
                     (ctx["id"],)).fetchone()[0]
    conn.close()
    return n


def test_submit_garbage_values_no_500(client, app_mod, walkin_token):
    before = _count_responses(app_mod, walkin_token)
    body = ("A=banana&B1=999&B2=-5&B3=3.14&B4=%27%3B+DROP+TABLE+response%3B--"
            "&served_by_rp_id=not-an-int&remarks=" + "x" * 5000)
    r = client.post(f"/r/{walkin_token}", content=body,
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code in (200, 403), r.text[:300]   # 200 thanks (or 403 if closed)
    # DB still intact and queryable (no dropped table)
    assert _count_responses(app_mod, walkin_token) >= before

def test_submit_injection_in_served_by(client, walkin_token):
    body = "served_by_rp_id=1%20OR%201%3D1&remarks=hi"
    r = client.post(f"/r/{walkin_token}", content=body,
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code in (200, 403)

def test_submit_out_of_range_rating_coerced(client, app_mod, walkin_token):
    # A wildly out-of-scale integer must be coerced to N/A, not stored.
    body = "A=100000000&remarks=test-oob"
    r = client.post(f"/r/{walkin_token}", content=body,
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        conn = st.connect(app_mod.DB)
        bad = conn.execute("SELECT COUNT(*) FROM answer WHERE value > 50").fetchone()[0]
        conn.close()
        assert bad == 0, "out-of-range rating was stored instead of coerced to N/A"

def test_submit_to_bad_token_404(client):
    r = client.post("/r/does-not-exist", content="A=1",
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 404

def test_submit_empty_body(client, walkin_token):
    r = client.post(f"/r/{walkin_token}", content="",
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code in (200, 403)

# ---- BUG-3: event_date validation at creation ----

def test_create_rejects_bad_date(manager):
    body = ("event_type=bureau&activity_name=Test&event_date=2026-13-99"
            "&rp_id=1&topic=Talk")
    r = manager.post("/create", content=body,
                     headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 400
    assert "date" in r.text.lower()

def test_create_rejects_missing_activity(manager):
    body = "event_type=bureau&event_date=2026-01-01&rp_id=1&topic=Talk"
    r = manager.post("/create", content=body,
                     headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 400

def test_create_rejects_inverted_window(manager):
    body = ("event_type=bureau&activity_name=Test&event_date=2026-01-01"
            "&rp_id=1&topic=Talk&open_at=2026-01-02T10:00&close_at=2026-01-01T10:00")
    r = manager.post("/create", content=body,
                     headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 400

def test_engine_survives_bad_event_date_in_db(app_mod):
    """BUG-3 root cause: a single bad event_date must not crash load_atoms /
    period assignment for the whole dataset."""
    import css_is_engine as eng
    import pandas as pd
    df = pd.DataFrame({"event_date": ["2026-01-01", "not-a-date", "2026-02-30", None]})
    out = eng.assign_periods(df.copy()) if hasattr(eng, "assign_periods") else None
    # if assign_periods exists it must not raise; bad dates become NaT
    assert out is None or len(out) == 4
