"""
Two approval-chain refinements on top of the shared escalation machinery
(storage._org_rank / get_approvers_for, STAFF_ONBOARDING_AVATAR_PLAN.md §7a.2):

* The Director sits at the top of the chain with nobody to route their own
  wellness break or work arrangement to — rather than sit pending on the
  admin fallback, filing one auto-approves it on the spot.
* An acting OIC's (storage.set_section_oic) OWN requests are redirected a
  rung above the seat they're covering, instead of following their
  substantive rank — the same escalation a genuine holder of that seat would
  follow, and never routed back to the (likely absent) substantive chief
  they're standing in for.
"""
from __future__ import annotations

import pytest

import storage as st


@pytest.fixture()
def chain(app_mod):
    """RD Office (Director) -> RD Division (Division Chief) -> RD Section
    (Section Chief + one staff) -- enough to exercise both refinements."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)

    def _wipe():
        conn.execute("DELETE FROM section_oic WHERE org_unit_id IN "
                     "(SELECT id FROM org_unit WHERE path LIKE 'RD%')")
        conn.execute("DELETE FROM wellness_claim WHERE user_id IN "
                     "(SELECT id FROM admin_user WHERE username LIKE 'rd-%@test.local')")
        conn.execute("DELETE FROM work_arrangement WHERE user_id IN "
                     "(SELECT id FROM admin_user WHERE username LIKE 'rd-%@test.local')")
        conn.execute("DELETE FROM admin_user WHERE username LIKE 'rd-%@test.local'")
        conn.execute("DELETE FROM resource_person WHERE name LIKE 'RD-%'")
        conn.execute("DELETE FROM org_unit WHERE path LIKE 'RD%'")
        conn.commit()
    _wipe()

    def unit(name, short, level, path):
        return conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (name, short, level, path)).lastrowid

    def person(name, org, desig=None, pos=None):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation, "
            "position) VALUES (?,1,?,?,?)", (name, org, desig, pos)).lastrowid

    def account(uname, rp, role="section_manager"):
        return st.create_admin_user(conn, uname, "x", "y", role, rp_id=rp)

    office = unit("RD Office", "RD", "office", "RD")
    div = unit("RD Division", "RDDiv", "division", "RD/Div")
    sec = unit("RD Section", "RDSec", "section", "RD/Div/Sec")

    director = account("rd-director@test.local", person("RD-Director", office, None, "Director"))
    divchief = account("rd-divchief@test.local", person("RD-DivChief", div, "Division Chief"))
    chief = account("rd-chief@test.local", person("RD-Chief", sec, "Section Chief"))
    staff = account("rd-staff@test.local", person("RD-Staff", sec), role="viewer")

    conn.commit()
    yield {"conn": conn, "office": office, "div": div, "sec": sec,
           "director": director, "divchief": divchief, "chief": chief, "staff": staff}
    _wipe()
    conn.close()


# --- the Director's own requests auto-approve --------------------------------

def test_directors_wellness_claim_is_auto_approved(chain, future_weekday):
    conn = chain["conn"]
    claim_id = st.create_wellness_claim(conn, chain["director"], future_weekday,
                                        "13:00", "exercise")
    claim = st.get_wellness_claim(conn, claim_id)
    assert claim["status"] == "approved"
    assert claim["decided_by"] == chain["director"]
    assert claim["decide_note"]


def test_a_non_directors_wellness_claim_still_needs_approval(chain, future_weekday):
    conn = chain["conn"]
    claim_id = st.create_wellness_claim(conn, chain["staff"], future_weekday,
                                        "13:00", "exercise")
    assert st.get_wellness_claim(conn, claim_id)["status"] == "pending"


def test_directors_work_arrangement_filing_is_auto_approved(chain):
    conn = chain["conn"]
    ps = st.work_arrangement_open_periods()[0]
    wa_id = st.create_work_arrangement(conn, chain["director"], ps, "REG")
    row = st.get_work_arrangement(conn, wa_id)
    assert row["status"] == "approved"
    assert row["decided_by"] == chain["director"]


def test_a_non_directors_work_arrangement_filing_still_needs_approval(chain):
    conn = chain["conn"]
    ps = st.work_arrangement_open_periods()[0]
    wa_id = st.create_work_arrangement(conn, chain["staff"], ps, "REG")
    assert st.get_work_arrangement(conn, wa_id)["status"] == "pending"


def test_directors_work_arrangement_change_is_auto_approved_and_supersedes(chain):
    conn = chain["conn"]
    ps = st.work_arrangement_open_periods()[0]
    wa_id = st.create_work_arrangement(conn, chain["director"], ps, "REG")
    assert st.get_work_arrangement(conn, wa_id)["status"] == "approved"

    new_id = st.request_work_arrangement_change(conn, wa_id, chain["director"], "WFH", weekday=1)
    new_row = st.get_work_arrangement(conn, new_id)
    assert new_row["status"] == "approved"
    assert new_row["decided_by"] == chain["director"]
    # the same supersede step a manual approval would apply
    assert st.get_work_arrangement(conn, wa_id)["status"] == "superseded"


# --- an acting OIC's own requests redirect up a rung --------------------------

def test_a_section_level_oic_own_request_redirects_to_the_division_chief(chain):
    conn = chain["conn"]
    st.set_section_oic(conn, chain["sec"], chain["staff"], set_by=chain["chief"])
    assert st.get_approvers_for(conn, chain["staff"]) == [chain["divchief"]]
    assert st.approver_name_for(conn, chain["staff"]) == "RD-DivChief"
    assert st.approver_title_for(conn, chain["staff"]) == "your division chief"


def test_a_division_level_oic_own_request_redirects_to_the_director(chain):
    conn = chain["conn"]
    st.set_section_oic(conn, chain["div"], chain["chief"], set_by=chain["divchief"])
    assert st.get_approvers_for(conn, chain["chief"]) == [chain["director"]]
    assert st.approver_name_for(conn, chain["chief"]) == "RD-Director"
    assert st.approver_title_for(conn, chain["chief"]) == "the Director"


def test_the_oic_redirect_never_names_the_oic_themselves(chain):
    """Even standing in for their own section's chief seat, an OIC can never
    be their own approver (mirrors test_section_oic's self-exclusion rule)."""
    conn = chain["conn"]
    st.set_section_oic(conn, chain["sec"], chain["staff"], set_by=chain["chief"])
    assert chain["staff"] not in st.get_approvers_for(conn, chain["staff"])


def test_clearing_the_oic_restores_the_normal_chain(chain):
    conn = chain["conn"]
    st.set_section_oic(conn, chain["sec"], chain["staff"], set_by=chain["chief"])
    assert st.get_approvers_for(conn, chain["staff"]) == [chain["divchief"]]
    st.clear_section_oic(conn, chain["sec"])
    assert st.get_approvers_for(conn, chain["staff"]) == [chain["chief"]]
