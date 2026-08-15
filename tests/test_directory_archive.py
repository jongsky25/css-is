"""
Archiving a directory person — the admin's answer to "this one resigned".

The rule the whole feature rests on: an archive is NOT a delete. The row stays,
so everything already written about that person keeps resolving (get_rp, their
ratings, the certificates they signed); what it removes is their presence on the
CURRENT roster — every picker, the org chain of command, and the headcounts.

So the tests come in pairs: for each surface, assert the archived person is gone
from the "pick someone now" list AND still resolvable from the "who was this"
list. A change that satisfies only the first half deletes history in slow motion.
"""
from __future__ import annotations

import pytest

import storage as st


@pytest.fixture
def dirfix(app_mod):
    """One section holding a section head and a staff member, both with accounts,
    plus one external RP — enough to exercise the pickers, the chain of command
    and the account coupling."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _wipe(conn)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Arch Section", "AS", "section", "ARCHTEST/D1/S1")).lastrowid
    div = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Arch Division", "AD", "division", "ARCHTEST/D1")).lastrowid

    def person(name, unit_id, designation="", position=""):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id,"
            " designation, position) VALUES (?,1,?,?,?)",
            (name, unit_id, designation or None, position or None)).lastrowid

    head = person("ARCH-Head", unit, "Section Head", "Chief Health Program Officer")
    staff = person("ARCH-Staff", unit, "", "Health Program Officer II")
    chief = person("ARCH-DivChief", div, "Division Chief")
    ext = conn.execute(
        "INSERT INTO resource_person(name, is_internal, agency) VALUES (?,0,?)",
        ("ARCH-Guest", "Some Agency")).lastrowid
    mk = lambda u, rp: st.create_admin_user(conn, u, "x", "y", "viewer", rp_id=rp)
    out = {"conn": conn, "unit": unit, "head_rp": head, "staff_rp": staff,
           "chief_rp": chief, "ext_rp": ext,
           "head_u": mk("arch-head@test.local", head),
           "staff_u": mk("arch-staff@test.local", staff),
           "chief_u": mk("arch-chief@test.local", chief)}
    conn.commit()
    yield out
    # The DB is session-scoped: this fixture seats a section head and a division
    # chief, and the escalation chain finds seats by rank. Leaving them behind
    # would show up as a failure in someone else's file.
    _wipe(conn)
    conn.commit()
    conn.close()


def _wipe(conn):
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'arch-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'ARCH-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'ARCHTEST%'")


def _names(people):
    return {p["name"] for p in people}


# ---------------------------------------------------------------- the basics

def test_archiving_takes_someone_off_the_current_roster(dirfix):
    conn = dirfix["conn"]
    assert "ARCH-Staff" in _names(st.list_resource_persons(conn))

    res = st.set_rp_archived(conn, dirfix["staff_rp"], True, reason="Resigned 31 Jul 2026")
    assert res["ok"]

    assert "ARCH-Staff" not in _names(st.list_resource_persons(conn))
    assert "ARCH-Staff" in _names(st.list_resource_persons(conn, include_archived=True))


def test_the_archive_is_not_a_delete(dirfix):
    """get_rp has to keep resolving an archived person: certificates, ratings and
    the approval trail all name people by id long after they leave."""
    conn = dirfix["conn"]
    st.set_rp_archived(conn, dirfix["staff_rp"], True)

    rp = st.get_rp(conn, dirfix["staff_rp"])
    assert rp is not None
    assert rp["name"] == "ARCH-Staff"
    assert rp["archived"] is True


def test_the_reason_and_the_date_are_kept(dirfix):
    conn = dirfix["conn"]
    st.set_rp_archived(conn, dirfix["staff_rp"], True, reason="  Resigned 31 Jul 2026  ")
    rp = st.get_rp(conn, dirfix["staff_rp"])
    assert rp["archived_reason"] == "Resigned 31 Jul 2026"       # trimmed
    assert rp["archived_at"]


def test_restore_puts_them_back(dirfix):
    conn = dirfix["conn"]
    st.set_rp_archived(conn, dirfix["staff_rp"], True, reason="Resigned")
    assert st.set_rp_archived(conn, dirfix["staff_rp"], False)["ok"]

    rp = st.get_rp(conn, dirfix["staff_rp"])
    assert rp["archived"] is False
    assert rp["archived_at"] is None and rp["archived_reason"] is None
    assert "ARCH-Staff" in _names(st.list_resource_persons(conn))


def test_archiving_twice_is_not_an_error(dirfix):
    conn = dirfix["conn"]
    st.set_rp_archived(conn, dirfix["staff_rp"], True)
    again = st.set_rp_archived(conn, dirfix["staff_rp"], True)
    assert again["ok"] and "already archived" in again["msg"]


def test_archiving_someone_who_is_gone_fails_cleanly(dirfix):
    res = st.set_rp_archived(dirfix["conn"], 10 ** 7, True)
    assert res["ok"] is False


# -------------------------------------------------------------- the account

def test_archiving_deactivates_their_sign_in(dirfix):
    """Someone who has left the bureau should not still be able to sign in, and
    leaving that to a second trip through Admin -> Users is how it gets missed."""
    conn = dirfix["conn"]
    res = st.set_rp_archived(conn, dirfix["staff_rp"], True)

    assert res["account"] == "arch-staff@test.local"
    assert st.get_admin_user_by_id(conn, dirfix["staff_u"])["active"] == 0


def test_restore_does_not_hand_the_sign_in_back(dirfix):
    """Re-granting access is a decision about permissions, not about a directory
    row, so it stays an explicit act on the accounts page."""
    conn = dirfix["conn"]
    st.set_rp_archived(conn, dirfix["staff_rp"], True)
    res = st.set_rp_archived(conn, dirfix["staff_rp"], False)

    assert st.get_admin_user_by_id(conn, dirfix["staff_u"])["active"] == 0
    # ...and the copy says so, so nobody assumes the sign-in came back with them
    assert "Admin" in res["msg"] and "Users" in res["msg"]


# ------------------------------------------------ pickers & chain of command

def test_an_archived_person_cannot_be_picked_as_a_signatory(dirfix):
    conn = dirfix["conn"]
    assert "ARCH-Head" in _names(st.list_signatories(conn))
    st.set_rp_archived(conn, dirfix["head_rp"], True)
    assert "ARCH-Head" not in _names(st.list_signatories(conn))


def test_a_resigned_chief_stops_being_the_approver(dirfix):
    """The sharp end of the feature: a section head who has left must not still
    be routed this week's wellness break."""
    conn = dirfix["conn"]
    assert dirfix["head_u"] in st.get_approvers_for(conn, dirfix["staff_u"])
    assert st._org_role_filled(conn, 1, org_path="ARCHTEST/D1/S1") is True
    assert st._org_seat_name(conn, 1, org_path="ARCHTEST/D1/S1") == "ARCH-Head"

    st.set_rp_archived(conn, dirfix["head_rp"], True)

    assert st.get_approvers_for(conn, dirfix["staff_u"]) == []
    assert st._org_role_filled(conn, 1, org_path="ARCHTEST/D1/S1") is False
    assert st._org_seat_name(conn, 1, org_path="ARCHTEST/D1/S1") is None


def test_an_archived_person_has_no_team_and_is_off_the_roster(dirfix):
    conn = dirfix["conn"]
    user = {"id": dirfix["staff_u"], "username": "arch-staff@test.local", "role": "viewer"}
    assert st.team_scope_for_user(conn, user) == ("ARCHTEST/D1/S1", "unit")

    st.set_rp_archived(conn, dirfix["staff_rp"], True)

    assert st.team_scope_for_user(conn, user) == (None, "none")
    week = st.wellness_week_start()
    chief = {"id": dirfix["head_u"], "username": "arch-head@test.local", "role": "viewer"}
    roll = st.wellness_week_rollup(conn, week, chief)
    assert "ARCH-Staff" not in {r["name"] for r in roll["rows"]}
    assert "ARCH-Head" in {r["name"] for r in roll["rows"]}


def test_the_headcount_drops_them(dirfix):
    conn = dirfix["conn"]
    before = st.system_inventory(conn)["staff"]
    st.set_rp_archived(conn, dirfix["staff_rp"], True)
    assert st.system_inventory(conn)["staff"] == before - 1


def test_external_resource_persons_archive_too(dirfix):
    """A guest speaker who has retired is the same problem in a different table
    half — the split is is_internal, and the archive is orthogonal to it."""
    conn = dirfix["conn"]
    st.set_rp_archived(conn, dirfix["ext_rp"], True)
    assert "ARCH-Guest" not in _names(st.list_resource_persons(conn))
    assert st.get_rp(conn, dirfix["ext_rp"])["name"] == "ARCH-Guest"


# ----------------------------------------------------------------- over HTTP

def test_archive_and_restore_over_http(admin, app_mod, dirfix):
    conn = dirfix["conn"]
    r = admin.post(f"/directory/person/{dirfix['staff_rp']}/archive",
                   data={"reason": "Resigned"}, follow_redirects=False)
    assert r.status_code == 303
    assert st.get_rp(conn, dirfix["staff_rp"])["archived"] is True

    page = admin.get("/directory")
    assert page.status_code == 200
    assert "Archived" in page.text

    r = admin.post(f"/directory/person/{dirfix['staff_rp']}/archive",
                   data={"restore": "1"}, follow_redirects=False)
    assert r.status_code == 303
    assert st.get_rp(conn, dirfix["staff_rp"])["archived"] is False


def test_archiving_is_admin_only(viewer, dirfix):
    """/directory maps to the `directory` capability at the auth gate, which only
    admins hold — so a viewer can't archive a colleague."""
    r = viewer.post(f"/directory/person/{dirfix['staff_rp']}/archive",
                    data={"reason": "nope"}, follow_redirects=False)
    assert r.status_code == 403
    assert st.get_rp(dirfix["conn"], dirfix["staff_rp"])["archived"] is False
