"""The /activities/outside page — the stable home for non-bureau ("invited")
activities across every lifecycle.

The contract this locks: a CONCLUDED invited event still appears here, even though
it has dropped off the (lifecycle-filtered) Monitor — that is the whole point of the
page. It also stays scoped to outside events (bureau events never leak in).
"""
import storage as st


def _two_internal_rps(db_path):
    conn = st.connect(db_path)
    rows = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 ORDER BY id LIMIT 2").fetchall()
    conn.close()
    assert len(rows) >= 2, "need two internal resource persons in the test DB"
    return rows[0][0], rows[1][0]


def _make_outside(client, db_path, name, date):
    rp1, rp2 = _two_internal_rps(db_path)
    r = client.post("/create", data={
        "event_type": "outside", "activity_name": name,
        "event_date": date, "venue": "Partner Hall",
        "external_org": "DOH Regional Office", "qr_mode": "combined",
        "rp_id": [str(rp1), str(rp2)], "topic": ["Cold chain", "Surveillance"],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:500]


def test_concluded_invited_event_shows_here_but_not_on_monitor(admin, db_path):
    # A concluded invited event (well in the past) — the case that used to vanish.
    name = "Concluded Invited Forum XYZ"
    _make_outside(admin, db_path, name, "2025-01-15")

    page = admin.get("/activities/outside")
    assert page.status_code == 200
    assert name in page.text, "a concluded invited event must remain listed here"
    assert "concluded" in page.text  # its lifecycle badge

    # The same event is gone from the Monitor (lifecycle-filtered to upcoming/ongoing).
    mon = admin.get("/monitor")
    assert name not in mon.text, "concluded invited events should NOT be on the Monitor"


def test_upcoming_invited_event_shows(admin, db_path):
    name = "Upcoming Invited Forum XYZ"
    _make_outside(admin, db_path, name, "2027-12-01")
    page = admin.get("/activities/outside")
    assert page.status_code == 200
    assert name in page.text
    assert "upcoming" in page.text


def test_page_is_scoped_to_outside_only(admin, db_path):
    # A bureau (non-outside) activity must not appear on the invited-events page.
    rp1, _ = _two_internal_rps(db_path)
    r = admin.post("/create", data={
        "event_type": "bureau", "activity_name": "Bureau Only Activity ABC",
        "event_date": "2026-06-12", "venue": "HQ", "qr_mode": "combined",
        "rp_id": [str(rp1)], "topic": ["Internal"],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:400]
    page = admin.get("/activities/outside")
    assert "Bureau Only Activity ABC" not in page.text


def test_requires_manage_event_capability(client):
    # An unauthenticated / under-privileged client cannot reach the page.
    r = client.get("/activities/outside", follow_redirects=False)
    assert r.status_code in (302, 303, 403)


def test_your_recent_strip_badges_invited_events(manager, db_path, app_mod):
    # An invited event the manager just made carries an "Invited" badge in the home
    # "Your recent activities" strip, so it reads as distinct from bureau activities.
    from datetime import timedelta
    recent = (app_mod._today_local() - timedelta(days=2)).isoformat()
    _make_outside(manager, db_path, "Recent Invited Strip ABC", recent)
    home = manager.get("/css").text
    assert "Recent Invited Strip ABC" in home
    assert '<span class="badge amber">Invited</span>' in home
