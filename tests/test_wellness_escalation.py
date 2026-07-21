"""
Wellness approval escalation — Phase 6b (STAFF_ONBOARDING_AVATAR_PLAN.md §7a.2).

Approvals climb the chain of command by directory rank:
  staff -> section chief -> division chief -> Director -> (admin fallback).
Builds a two-section division under a directorate and checks each link, the
queue routing (a division chief sees their section chiefs' claims, not staff's),
cross-branch isolation, and the rank-aware "who approves you" label.
"""
from __future__ import annotations

import pytest

import auth
import storage as st


def _wipe_chain(conn):
    """FK-safe, SCOPED cleanup of just this fixture's rows (never other tests'
    data): reflections -> claims -> badges -> accounts -> people -> units, all
    keyed to the esc-/'ESC ' namespace."""
    esc = "SELECT id FROM admin_user WHERE username LIKE 'esc-%@test.local'"
    conn.execute(f"DELETE FROM wellness_reflection WHERE claim_id IN "
                 f"(SELECT id FROM wellness_claim WHERE user_id IN ({esc}))")
    conn.execute(f"DELETE FROM wellness_claim WHERE user_id IN ({esc})")
    conn.execute(f"DELETE FROM wellness_badge WHERE user_id IN ({esc})")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'esc-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'ESC %'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'ESC%'")
    conn.commit()


@pytest.fixture()
def chain_org(app_mod):
    """Directorate 'ESC' with a Director; division 'ESC/DivA' with a Division
    Chief; two sections 'ESC/DivA/SecX' (chief X + staff x) and 'ESC/DivA/SecY'
    (chief Y). Accounts are minted per person; all rows cleaned up after."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _wipe_chain(conn)

    def unit(name, short, level, path):
        return conn.execute("INSERT INTO org_unit(name, short_name, level, path) "
                            "VALUES (?,?,?,?)", (name, short, level, path)).lastrowid

    def person(name, unit_id, desig=None):
        return conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, "
                            "designation) VALUES (?,1,?,?)", (name, unit_id, desig)).lastrowid

    def account(uname, rp, role="viewer"):
        return st.create_admin_user(conn, uname, "x", "y", role, rp_id=rp)

    office = unit("ESC Directorate", "ESC", "office", "ESC")
    divA = unit("ESC Division A", "DivA", "division", "ESC/DivA")
    secX = unit("ESC Section X", "SecX", "section", "ESC/DivA/SecX")
    secY = unit("ESC Section Y", "SecY", "section", "ESC/DivA/SecY")

    director = account("esc-dir@test.local", person("ESC Director", office, "Director"), "admin")
    divchief = account("esc-divchief@test.local",
                       person("ESC DivChief", divA, "Division Chief"), "section_manager")
    chiefX = account("esc-chiefx@test.local",
                     person("ESC ChiefX", secX, "Section Chief"), "section_manager")
    chiefY = account("esc-chiefy@test.local",
                     person("ESC ChiefY", secY, "Section Chief"), "section_manager")
    staffx = account("esc-staffx@test.local", person("ESC Staffx", secX), "viewer")
    conn.commit()
    yield {"conn": conn, "director": director, "divchief": divchief,
           "chiefX": chiefX, "chiefY": chiefY, "staffx": staffx}
    _wipe_chain(conn)
    conn.close()


# --- each link of the chain --------------------------------------------------

def test_staff_escalates_to_their_section_chief(chain_org):
    conn = chain_org["conn"]
    assert st.get_wellness_approvers(conn, chain_org["staffx"]) == [chain_org["chiefX"]]


def test_section_chief_escalates_to_division_chief(chain_org):
    conn = chain_org["conn"]
    assert st.get_wellness_approvers(conn, chain_org["chiefX"]) == [chain_org["divchief"]]


def test_division_chief_escalates_to_director(chain_org):
    conn = chain_org["conn"]
    assert st.get_wellness_approvers(conn, chain_org["divchief"]) == [chain_org["director"]]


def test_director_has_no_chain_approver_only_admin(chain_org):
    conn = chain_org["conn"]
    assert st.get_wellness_approvers(conn, chain_org["director"]) == []
    # the admin fallback still covers the Director's own claim
    u_admin = {"id": 999999, "role": "admin"}
    assert st.is_wellness_approver(conn, u_admin, chain_org["director"])


# --- cross-branch isolation --------------------------------------------------

def test_section_chief_only_approves_their_own_section(chain_org):
    conn = chain_org["conn"]
    # ChiefY must NOT be an approver for Section X's staff
    assert chain_org["chiefY"] not in st.get_wellness_approvers(conn, chain_org["staffx"])


def test_division_chief_queue_holds_section_chiefs_not_staff(chain_org):
    """A division chief's queue = their division's SECTION CHIEFS' claims — not
    the staff under those sections (those route to the section chief)."""
    conn = chain_org["conn"]
    d = "2026-01-05"                      # a Monday; inserted directly
    staff_claim = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time, hours, "
        "activity, status, created_at) VALUES (?,?,?,?,1,'exercise','pending',?)",
        (chain_org["staffx"], d, d, "09:00", st.tz.now_iso())).lastrowid
    chief_claim = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time, hours, "
        "activity, status, created_at) VALUES (?,?,?,?,1,'exercise','pending',?)",
        (chain_org["chiefX"], d, d, "10:00", st.tz.now_iso())).lastrowid
    conn.commit()
    u_div = {"id": chain_org["divchief"], "role": "section_manager"}
    q = [c["id"] for c in st.list_wellness_approvals(conn, u_div)]
    assert chief_claim in q            # the section chief's own break -> division chief
    assert staff_claim not in q        # the staff's break -> their section chief

    u_chiefx = {"id": chain_org["chiefX"], "role": "section_manager"}
    qx = [c["id"] for c in st.list_wellness_approvals(conn, u_chiefx)]
    assert staff_claim in qx           # the staff's break IS in their section chief's queue
    assert chief_claim not in qx       # a chief never sees their own claim


# --- who-approves-you label --------------------------------------------------

def test_approver_title_is_rank_aware(chain_org):
    conn = chain_org["conn"]
    assert st.wellness_approver_title(conn, chain_org["staffx"]) == "your section chief"
    assert st.wellness_approver_title(conn, chain_org["chiefX"]) == "your division chief"
    assert st.wellness_approver_title(conn, chain_org["divchief"]) == "the Director"
    assert st.wellness_approver_title(conn, chain_org["director"]) == "an administrator"


def test_director_sees_the_approvals_queue(chain_org):
    """The Director must be recognised as an approver by DESIGNATION so the queue
    /nav shows even without the admin role. Pass a non-admin role so the check
    can't pass via the admin short-circuit."""
    conn = chain_org["conn"]
    assert st.user_is_wellness_chief(conn, {"id": chain_org["director"], "role": "viewer"})
    # a division chief too
    assert st.user_is_wellness_chief(conn, {"id": chain_org["divchief"], "role": "section_manager"})
    # a plain staff member does NOT
    assert not st.user_is_wellness_chief(conn, {"id": chain_org["staffx"], "role": "viewer"})
