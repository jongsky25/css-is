"""
Temporary OIC / acting approver for a section's wellness break + AWA requests
(storage.section_oic) — the toggle an admin flips when a section chief is on
leave: pick someone from the section, and the approvals routed to the chief
start routing to that person too, until the toggle is turned back off.

The load-bearing assertions: only one delegate at a time per section (the
table's PRIMARY KEY enforces it), the delegate is ADDED to the chain rather
than swapped in for the substantive chief, and a delegate with no chief seat
of their own still gets an approvals queue.
"""
from __future__ import annotations

import pytest

import auth
import storage as st


@pytest.fixture
def org(app_mod):
    """One section with a chief and two staff, a division chief above it and
    a director above that — enough to exercise the whole escalation chain —
    plus an outsider sitting in a wholly unrelated section, for testing that
    a tampered POST naming someone genuinely unconnected is refused."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)

    def _wipe():
        # section_oic rows reference admin_user (and org_unit) by foreign
        # key, so they have to go before the accounts/units they point at.
        # Run both before AND after: the fixture now mints a "Director"-rank
        # account, and rank-3 lookups are GLOBAL (no org_path filter), so a
        # leftover row here would leak into other test files' escalation
        # assertions if it weren't cleaned up as soon as each test is done.
        conn.execute("DELETE FROM section_oic WHERE org_unit_id IN "
                     "(SELECT id FROM org_unit WHERE path LIKE 'OICD%') "
                     "OR admin_user_id IN "
                     "(SELECT id FROM admin_user WHERE username LIKE 'oic-%@test.local')")
        conn.execute("DELETE FROM wellness_claim WHERE user_id IN "
                     "(SELECT id FROM admin_user WHERE username LIKE 'oic-%@test.local')")
        conn.execute("DELETE FROM admin_user WHERE username LIKE 'oic-%@test.local'")
        conn.execute("DELETE FROM resource_person WHERE name LIKE 'OIC-%'")
        conn.execute("DELETE FROM org_unit WHERE path LIKE 'OICD%'")
        conn.commit()
    _wipe()

    office_id = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Office", "Off", "office", "OICD")).lastrowid
    division_id = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Division", "Div", "division", "OICD/Div")).lastrowid
    section_id = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Section One", "S1", "section", "OICD/Div/S1")).lastrowid
    outsider_unit_id = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Elsewhere", "Else", "section", "OICD-ELSEWHERE/Else")).lastrowid

    def account(name, org_unit_id, designation=None, position=None):
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation, "
            "position) VALUES (?,1,?,?,?)", (name, org_unit_id, designation, position)).lastrowid
        return st.create_admin_user(conn, f"oic-{name.lower()}@test.local",
                                    "x", "y", "viewer", rp_id=rp)

    out = {
        "conn": conn, "section_id": section_id, "division_id": division_id,
        "office_id": office_id,
        "director": account("OIC-Director", office_id, None, "Director"),
        "chief": account("OIC-Chief", section_id, "Section Head"),
        "staff": account("OIC-Staff", section_id),
        "deputy": account("OIC-Deputy", section_id),         # eligible delegate, no seat
        "div_chief": account("OIC-DivChief", division_id, "Division Chief"),
        "outsider": account("OIC-Outsider", outsider_unit_id),   # unrelated section
    }
    conn.commit()
    yield out
    _wipe()
    conn.close()


def _u(conn, uid):
    r = st.get_admin_user_by_id(conn, uid)
    return {"id": r["id"], "username": r["username"], "role": r["role"]}


def _client(app_mod, conn, uid):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(_u(conn, uid)))
    return c


# --- the storage-level behaviour --------------------------------------------

def test_no_delegate_by_default(org):
    conn = org["conn"]
    assert st.get_section_oic(conn, org["section_id"]) is None
    assert st.get_approvers_for(conn, org["staff"]) == [org["chief"]]


def test_setting_a_delegate_adds_them_alongside_the_chief(org):
    """An acting OIC is a second route in, not a replacement — the chief keeps
    deciding their own section's requests if they come back early."""
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    approvers = st.get_approvers_for(conn, org["staff"])
    assert set(approvers) == {org["chief"], org["deputy"]}


def test_only_one_delegate_at_a_time_per_section(org):
    """Assigning a second person replaces the first outright — never both."""
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    st.set_section_oic(conn, org["section_id"], org["staff"], set_by=org["chief"])
    current = st.get_section_oic(conn, org["section_id"])
    assert current["admin_user_id"] == org["staff"]
    # routing OIC-deputy's own request reaches the chief and the NEW delegate
    # (org["staff"]) only — if the old delegate (OIC-deputy) had lingered
    # alongside it, it would also appear here (self-exclusion aside).
    approvers = st.get_approvers_for(conn, org["deputy"])
    assert set(approvers) == {org["chief"], org["staff"]}


def test_clearing_the_delegate_restores_the_plain_chain(org):
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    st.clear_section_oic(conn, org["section_id"])
    assert st.get_section_oic(conn, org["section_id"]) is None
    assert st.get_approvers_for(conn, org["staff"]) == [org["chief"]]


def test_a_delegate_never_approves_their_own_request(org):
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    assert org["deputy"] not in st.get_approvers_for(conn, org["deputy"])


def test_a_delegate_with_no_chief_seat_still_sees_the_queue(org):
    """OIC-Deputy holds no rank of their own — without the delegate check
    user_is_approving_chief would shut the queue on them entirely."""
    conn = org["conn"]
    deputy = _u(conn, org["deputy"])
    assert st.user_is_approving_chief(conn, deputy) is False
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    assert st.user_is_approving_chief(conn, deputy) is True


def test_a_delegate_can_decide_the_sections_pending_claims(org, future_weekday):
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    deputy = _u(conn, org["deputy"])
    assert st.is_approver_for(conn, deputy, org["staff"]) is True
    claim_id = st.create_wellness_claim(conn, org["staff"], future_weekday, "13:00", "exercise")
    pending = st.list_wellness_approvals(conn, deputy)
    assert any(c["id"] == claim_id for c in pending)
    st.decide_wellness_claim(conn, claim_id, deputy, "approve")
    assert st.get_wellness_claim(conn, claim_id)["status"] == "approved"


def test_delegate_name_takes_the_apply_page_copy(org):
    """approver_name_for shows the delegate while they're standing in, but the
    chain still names the chief once the delegate is cleared."""
    conn = org["conn"]
    assert st.approver_name_for(conn, org["staff"]) == "OIC-Chief"
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["chief"])
    assert st.approver_name_for(conn, org["staff"]) == "OIC-Deputy"
    st.clear_section_oic(conn, org["section_id"])
    assert st.approver_name_for(conn, org["staff"]) == "OIC-Chief"


def test_a_delegate_can_stand_in_for_a_division_chief_too(org):
    """The same mechanism covers the rung above: a delegate set on the
    division stands in for whoever decides a section chief's own requests."""
    conn = org["conn"]
    st.set_section_oic(conn, org["division_id"], org["deputy"], set_by=org["div_chief"])
    approvers = st.get_approvers_for(conn, org["chief"])
    assert set(approvers) == {org["div_chief"], org["deputy"]}


# --- the division chief as a section's OIC ------------------------------------

def test_the_division_chief_may_cover_one_of_their_own_sections(org):
    """A section's parent division chief is a legitimate pick too -- not just
    someone from the section itself."""
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["div_chief"], set_by=org["div_chief"])
    approvers = st.get_approvers_for(conn, org["staff"])
    assert set(approvers) == {org["chief"], org["div_chief"]}


def test_the_division_chiefs_own_request_is_unaffected_by_covering_a_section(org):
    """Covering a section doesn't change how the division chief's OWN request
    is decided -- they already outrank the seat, so it keeps escalating
    through their real rank (division chief -> Director), exactly as if they
    held no OIC assignment at all.

    Rank-3 lookups are bureau-wide (see _org_accounts_at_rank), so in a
    full-suite run other files' fixtures may leave other Director-ranked
    accounts lying around — assert membership/substring rather than an exact
    match, the same way test_wellness.py's escalation tests do."""
    conn = org["conn"]
    assert org["director"] in st.get_approvers_for(conn, org["div_chief"])
    st.set_section_oic(conn, org["section_id"], org["div_chief"], set_by=org["div_chief"])
    assert org["director"] in st.get_approvers_for(conn, org["div_chief"])
    assert "OIC-Director" in (st.approver_name_for(conn, org["div_chief"]) or "")
    assert st.approver_title_for(conn, org["div_chief"]) == "the Director"


def test_get_section_oic_flags_by_right_for_the_division_chief(org):
    conn = org["conn"]
    st.set_section_oic(conn, org["section_id"], org["deputy"], set_by=org["div_chief"])
    assert st.get_section_oic(conn, org["section_id"])["by_right"] is False
    st.set_section_oic(conn, org["section_id"], org["div_chief"], set_by=org["div_chief"])
    assert st.get_section_oic(conn, org["section_id"])["by_right"] is True


# --- the admin routes --------------------------------------------------------

def test_an_admin_can_assign_and_it_is_audited(app_mod, org):
    conn = org["conn"]
    admin = st.create_admin_user(conn, "oic-admin@test.local", "x", "y", "admin")
    conn.commit()
    c = _client(app_mod, conn, admin)
    r = c.post(f"/admin/users/section-oic/{org['section_id']}/set",
               data={"admin_user_id": org["deputy"]}, follow_redirects=False)
    assert r.status_code == 303
    assert st.get_section_oic(conn, org["section_id"])["admin_user_id"] == org["deputy"]

    row = conn.execute(
        "SELECT summary FROM audit_log WHERE action='set_section_oic' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row and "oic-oic-deputy@test.local" in row[0]

    r = c.post(f"/admin/users/section-oic/{org['section_id']}/clear", follow_redirects=False)
    assert r.status_code == 303
    assert st.get_section_oic(conn, org["section_id"]) is None
    row = conn.execute(
        "SELECT summary FROM audit_log WHERE action='clear_section_oic' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row and "Section One" in row[0]


def test_only_user_managers_may_assign_a_delegate(app_mod, org):
    conn = org["conn"]
    r = _client(app_mod, conn, org["staff"]).post(
        f"/admin/users/section-oic/{org['section_id']}/set",
        data={"admin_user_id": org["deputy"]}, follow_redirects=False)
    assert r.status_code == 403
    assert st.get_section_oic(conn, org["section_id"]) is None


def test_the_picked_account_must_belong_to_the_section_or_chief_its_division(app_mod, org):
    """Defense in depth against a tampered POST: an account from an unrelated
    section (or no account at all) is refused, not silently accepted -- the
    section's OWN parent division chief is the one exception (see
    test_an_admin_can_assign_the_division_chief_over_http)."""
    conn = org["conn"]
    admin = st.create_admin_user(conn, "oic-admin2@test.local", "x", "y", "admin")
    conn.commit()
    c = _client(app_mod, conn, admin)
    r = c.post(f"/admin/users/section-oic/{org['section_id']}/set",
               data={"admin_user_id": org["outsider"]}, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]
    assert st.get_section_oic(conn, org["section_id"]) is None


def test_an_admin_can_assign_the_division_chief_over_http(app_mod, org):
    conn = org["conn"]
    admin = st.create_admin_user(conn, "oic-admin4@test.local", "x", "y", "admin")
    conn.commit()
    c = _client(app_mod, conn, admin)

    html = c.get("/admin/users").text
    assert f'<option value="{org["div_chief"]}">OIC-DivChief (Division Chief)</option>' in html

    r = c.post(f"/admin/users/section-oic/{org['section_id']}/set",
               data={"admin_user_id": org["div_chief"]}, follow_redirects=False)
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]
    current = st.get_section_oic(conn, org["section_id"])
    assert current["admin_user_id"] == org["div_chief"]
    assert current["by_right"] is True

    row = conn.execute(
        "SELECT summary FROM audit_log WHERE action='set_section_oic' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row and row[0].startswith("Division chief for Section One:")


def test_the_chief_is_not_offered_as_their_own_sections_delegate(app_mod, org):
    """The picker names a STAND-IN for the chief, so the chief themselves has
    no business appearing in their own section's picker — and a tampered POST
    naming them anyway is refused, the same as picking someone from another
    section."""
    conn = org["conn"]
    admin = st.create_admin_user(conn, "oic-admin3@test.local", "x", "y", "admin")
    conn.commit()
    c = _client(app_mod, conn, admin)

    # OIC-Chief still shows up elsewhere on the page (the staff accounts
    # table), so check the specific <option> the section's picker would
    # render for them, not a bare name search.
    html = c.get("/admin/users").text
    assert f'<option value="{org["chief"]}">OIC-Chief</option>' not in html
    assert f'<option value="{org["deputy"]}">OIC-Deputy</option>' in html

    r = c.post(f"/admin/users/section-oic/{org['section_id']}/set",
               data={"admin_user_id": org["chief"]}, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]
    assert st.get_section_oic(conn, org["section_id"]) is None

