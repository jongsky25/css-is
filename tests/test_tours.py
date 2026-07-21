"""
Guided page tours (Track B / UI-plan Phase 4).

The tour itself is client-side (tour.js + localStorage), so these are render +
data assertions: the engine is wired into the dashboard chrome, the source data
(tours.py) is well-formed, and the /help manual renders the role-filtered guide.
"""

import tours


def test_tour_for_returns_steps_and_empties():
    home = tours.tour_for("home")
    assert len(home) >= 3
    # every step is a well-formed dict the JS can render
    for s in home:
        assert s.get("target") and s.get("title") and s.get("body")
    # unknown / public pages have no tour
    assert tours.tour_for("nope") == []
    assert tours.tour_for("") == []


def test_tour_engine_wired_into_dashboard(admin):
    r = admin.get("/dashboard")
    assert r.status_code == 200
    # per-page payload + the engine script
    assert 'window.PAGE_KEY="pulse"' in r.text
    assert "window.PAGE_TOUR" in r.text
    assert "/static/js/tour.js" in r.text
    # the nav "?" affordance: replay this page + open the guide
    assert "data-tour-replay" in r.text
    assert 'href="/help"' in r.text


def test_tour_absent_on_login(client):
    # /login is public chrome with no tour wiring.
    r = client.get("/login")
    assert r.status_code == 200
    assert "window.PAGE_TOUR" not in r.text
    assert "/static/js/tour.js" not in r.text


def test_help_manual_renders(admin):
    r = admin.get("/help")
    assert r.status_code == 200
    assert "Guide" in r.text
    # the Home tour section + its replay-in-context link (the hub moved to /css
    # in the onboarding fork — the tour markup lives there now)
    assert ">Home<" in r.text
    assert "/css?tour=1" in r.text
    # the searchable section markers the filter JS keys on
    assert "data-help-sec" in r.text
