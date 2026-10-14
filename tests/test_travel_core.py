"""Travel filing foundations: schema, seeds, employee number."""
from __future__ import annotations
import sqlite3

import pytest

import storage as st
import travel
import travel_rules as tr


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "travel.db")); st.init_db(c)
    return c


def test_tables_exist(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"travel_filing", "travel_item", "travel_flag", "travel_route_type", "travel_ceiling",
            "travel_justification"} <= names


def test_seeds_are_complete_and_idempotent(conn):
    travel.ensure_defaults(conn); travel.ensure_defaults(conn); st.init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM travel_route_type").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM travel_ceiling").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM travel_justification").fetchone()[0] == 2
    c = travel.ceilings(conn)
    assert c[("rer", "residence_airport")] == 550 and c[("tnvs", "*")] == 700 and c[("cenrr", "*")] == 300
    assert st.get_setting(conn, "travel.enabled") == "1"
    assert st.get_setting(conn, "travel.retention_months") == "12"


def test_admin_edits_are_not_put_back(conn):
    conn.execute("DELETE FROM travel_justification"); conn.execute("UPDATE travel_ceiling SET amount=600 "
                 "WHERE mode='rer' AND route_type='residence_airport'"); conn.commit()
    travel.ensure_defaults(conn)
    assert conn.execute("SELECT COUNT(*) FROM travel_justification").fetchone()[0] == 0
    assert travel.ceilings(conn)[("rer", "residence_airport")] == 600


def test_inactive_route_is_not_approved(conn):
    conn.execute("UPDATE travel_route_type SET active=0 WHERE code='residence_venue'"); conn.commit()
    assert ("rer", "residence_venue") not in travel.ceilings(conn)
    r = tr.ride_check("public_noreceipt", "residence_venue", 400, "none", travel.ceilings(conn))
    assert [f.kind for f in r.flags] == ["unlisted_route"]


def test_seeded_starter_justifications_carry_the_tokens(conn):
    bodies = " ".join(r[0] for r in conn.execute("SELECT body FROM travel_justification"))
    for tok in ("{{activity_title}}", "{{dates}}", "{{venue}}"):
        assert tok in bodies


def _filing(conn, uid, **kw):
    f = dict(user_id=uid, kind="ca", source_kind="blank", act_title="T", act_start="2026-10-12",
             act_end="2026-10-16")
    f.update(kw)
    cols = ",".join(f); q = ",".join("?" * len(f))
    return conn.execute(f"INSERT INTO travel_filing({cols}) VALUES ({q})", tuple(f.values())).lastrowid


def test_one_live_cash_advance_per_user_and_activity(conn):
    uid = st.create_admin_user(conn, "t@test.local", "x", "y", "viewer")
    a = _filing(conn, uid, source_kind="entry", entry_id=7)
    with pytest.raises(sqlite3.IntegrityError):
        _filing(conn, uid, source_kind="entry", entry_id=7)
    _filing(conn, uid, source_kind="entry", entry_id=8)                  # another activity
    _filing(conn, uid, kind="liquidation", source_kind="entry", entry_id=7)
    _filing(conn, uid, source_kind="blank"); _filing(conn, uid, source_kind="blank")   # blanks exempt
    conn.execute("UPDATE travel_filing SET status='withdrawn' WHERE id=?", (a,)); conn.commit()
    _filing(conn, uid, source_kind="entry", entry_id=7)                  # allowed after withdrawal


def test_item_and_flag_uniqueness(conn):
    uid = st.create_admin_user(conn, "t2@test.local", "x", "y", "viewer")
    fid = _filing(conn, uid)
    conn.execute("INSERT INTO travel_item(filing_id,item_code,handling) VALUES (?,?,?)", (fid, "dpo", "upload"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO travel_item(filing_id,item_code,handling) VALUES (?,?,?)", (fid, "dpo", "upload"))
    conn.execute("INSERT INTO travel_flag(filing_id,kind,sig) VALUES (?,?,?)", (fid, "over_ceiling", "s"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO travel_flag(filing_id,kind,sig) VALUES (?,?,?)", (fid, "over_ceiling", "s"))


def test_deleting_a_filing_removes_its_items(conn):
    conn.execute("PRAGMA foreign_keys=ON")
    uid = st.create_admin_user(conn, "t3@test.local", "x", "y", "viewer")
    fid = _filing(conn, uid)
    conn.execute("INSERT INTO travel_item(filing_id,item_code,handling) VALUES (?,?,?)", (fid, "dpo", "upload"))
    conn.execute("DELETE FROM travel_filing WHERE id=?", (fid,)); conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM travel_item").fetchone()[0] == 0


def test_employee_number_round_trip(conn):
    uid = st.create_admin_user(conn, "e@test.local", "x", "y", "viewer")
    assert st.get_user_profile(conn, uid)["employee_no"] == ""
    st.set_user_employee_no(conn, uid, "  12345  ")
    assert st.get_user_profile(conn, uid)["employee_no"] == "12345"
    assert st.get_admin_user_by_id(conn, uid)["employee_no"] == "12345"
    st.set_user_employee_no(conn, uid, "   ")
    assert st.get_user_profile(conn, uid)["employee_no"] == ""


def test_audit_labels_registered():
    for a in ("travel_open", "travel_generate", "travel_ready", "travel_submit", "travel_withdraw",
              "travel_flag_decide", "travel_ceiling_save", "travel_library_save",
              "travel_settings_save", "travel_purge"):
        assert a in st._AUDIT_ACTIONS


# ------------------------------------------------------------ /me page ---

def test_me_page_saves_the_employee_number(app_mod, viewer):
    from urllib.parse import urlencode
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    try:
        assert 'name="employee_no"' in viewer.get("/me").text
        base = {"avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "nickname": "", "designation": ""}
        hdr = {"Content-Type": "application/x-www-form-urlencoded"}
        r = viewer.post("/me", content=urlencode({**base, "employee_no": " 98765 "}), headers=hdr,
                        follow_redirects=False)
        assert r.status_code in (302, 303)
        assert st.get_user_profile(c, uid)["employee_no"] == "98765"
        # a form that does not carry the field leaves it alone
        viewer.post("/me", content=urlencode(base), headers=hdr, follow_redirects=False)
        assert st.get_user_profile(c, uid)["employee_no"] == "98765"
        viewer.post("/me", content=urlencode({**base, "employee_no": ""}), headers=hdr, follow_redirects=False)
        assert st.get_user_profile(c, uid)["employee_no"] == ""
    finally:
        st.set_user_employee_no(c, uid, ""); c.close()
