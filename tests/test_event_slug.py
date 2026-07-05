"""Custom activity link (vanity slug) — Option B.

A manager may set an optional, human-readable slug as an alias for an event's
random token. The token never changes (printed QR codes keep working); the slug
is just a prettier way to reach the SAME activity. Covers the storage validation
rules, token-first resolution, and the manage-page HTTP round-trip.
"""
import re
import storage as st


def _make_event(manager, db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Slug Test Forum",
        "event_date": "2026-06-11", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    tok = re.search(r"/e/([0-9a-f]{12})", r.text)
    assert tok
    return tok.group(1)


# ---- storage layer -------------------------------------------------------

def test_set_and_resolve_slug(db_path):
    conn = st.connect(db_path)
    ev = st.create_event(conn, "Slugged", "2026-06-11")
    ok, err = st.set_event_slug(conn, ev["id"], "les-quezon-june")
    assert ok and err is None
    # resolvable by BOTH the slug and the original token, same activity
    by_slug = st.get_event(conn, "les-quezon-june")
    by_token = st.get_event(conn, ev["event_token"])
    assert by_slug and by_token and by_slug["id"] == by_token["id"] == ev["id"]
    assert by_slug["slug"] == "les-quezon-june"
    conn.close()


def test_slug_validation_rules(db_path):
    conn = st.connect(db_path)
    ev = st.create_event(conn, "Rules", "2026-06-11")
    # too short / illegal chars / spaces / leading-trailing/doubled hyphens rejected
    for bad in ("ab", "has space", "under_score", "-lead", "trail-", "a--b", "slash/y"):
        ok, err = st.set_event_slug(conn, ev["id"], bad)
        assert not ok and err, f"{bad!r} should be rejected"
    # input is normalised to lowercase, so mixed case is accepted (becomes valid)
    assert st.set_event_slug(conn, ev["id"], "Mixed-CASE")[0]
    # reserved route words rejected
    ok, _ = st.set_event_slug(conn, ev["id"], "reports")
    assert not ok
    # a good one sticks, and is normalised to lowercase + trimmed
    ok, err = st.set_event_slug(conn, ev["id"], "  Good-Slug-1  ")
    assert ok and st.get_event(conn, "good-slug-1")["id"] == ev["id"]
    conn.close()


def test_slug_uniqueness_and_clear(db_path):
    conn = st.connect(db_path)
    a = st.create_event(conn, "A", "2026-06-11")
    b = st.create_event(conn, "B", "2026-06-11")
    assert st.set_event_slug(conn, a["id"], "shared-link")[0]
    # b cannot steal a's slug
    ok, err = st.set_event_slug(conn, b["id"], "shared-link")
    assert not ok and err
    # b cannot use a's random token as a slug either (keys stay 1:1)
    ok, _ = st.set_event_slug(conn, b["id"], a["event_token"])
    assert not ok
    # clearing frees it up for b
    assert st.set_event_slug(conn, a["id"], "")[0]
    assert st.get_event(conn, a["event_token"])["slug"] is None
    assert st.set_event_slug(conn, b["id"], "shared-link")[0]
    conn.close()


# ---- HTTP round-trip on the manage page ----------------------------------

def test_manage_page_slug_roundtrip(manager, db_path):
    tok = _make_event(manager, db_path)
    # set a custom link via the manage form
    r = manager.post(f"/activities/{tok}/slug", data={"slug": "manage-rt-demo"},
                     follow_redirects=True)
    assert r.status_code == 200
    assert "Custom link saved." in r.text
    assert "/e/manage-rt-demo" in r.text          # displayed link now uses the slug
    # the manage page is reachable THROUGH the slug too (token-or-slug routing)
    r2 = manager.get(f"/activities/manage-rt-demo/manage")
    assert r2.status_code == 200 and "Slug Test Forum" in r2.text
    # the public link tree resolves by slug as well
    assert manager.get("/e/manage-rt-demo").status_code == 200
    # a bad slug is rejected with a friendly message, original link unchanged
    r3 = manager.post(f"/activities/{tok}/slug", data={"slug": "no good"},
                      follow_redirects=True)
    assert "lowercase letters" in r3.text
