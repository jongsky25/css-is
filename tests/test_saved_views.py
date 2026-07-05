"""
Saved views + deep-linkable filter state (UX #9).

The feature is client-side (localStorage), so these are render assertions: the
scope-bar control and its per-page context object appear on dashboard/report
pages (which set show_scope) and are absent on chrome-less pages like /login.
"""


def test_saved_views_control_on_scope_bar_page(admin):
    r = admin.get("/dashboard/trends")
    assert r.status_code == 200
    # The control group + its three actions render inside the scope bar.
    assert "data-savedviews" in r.text
    assert "data-sv-save" in r.text
    assert "data-sv-copy" in r.text
    assert "data-sv-toggle" in r.text
    # The per-page context the JS keys localStorage on, carrying the nav key.
    assert "window.SAVED_VIEW_CTX" in r.text
    assert 'key: "trends"' in r.text


def test_saved_views_absent_on_login(client):
    # /login has no scope bar (show_scope is False), so no control is emitted.
    r = client.get("/login")
    assert r.status_code == 200
    assert "data-savedviews" not in r.text
    assert "window.SAVED_VIEW_CTX" not in r.text
