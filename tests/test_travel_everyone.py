"""'Apply to everyone on this DPO' (Spot Feedback #126/#128): one personnel order covers several travellers,
each with their own filing; marking a row not applicable can be copied to the others."""
from __future__ import annotations

import pytest

import storage as st
import travel


@pytest.fixture()
def w(tmp_path):
    c = st.connect(str(tmp_path / "t.db")); st.init_db(c)
    out = {"conn": c}

    def filing(label, **kw):
        uid = st.create_admin_user(c, f"{label}@test.local", "x", "y", "viewer")
        f = dict(user_id=uid, ref_code=f"TF-{label}", kind="ca", source_kind="entry", entry_id=7,
                 act_title="T", act_start="2026-10-12", act_end="2026-10-16", dpo_no="DPO-1", status="open")
        f.update(kw)
        fid = c.execute("INSERT INTO travel_filing(%s) VALUES (%s)" % (",".join(f), ",".join("?" * len(f))),
                        tuple(f.values())).lastrowid
        c.commit()
        out[label] = travel.get_filing(c, fid)
    filing("me"); filing("b"); filing("c")
    filing("other_dpo", dpo_no="DPO-2"); filing("other_act", entry_id=8)
    filing("done", status="submitted"); filing("lower", dpo_no=" dpo-1 ")
    return out


def state(w, who, code="dpo"):
    r = w["conn"].execute("SELECT state FROM travel_item WHERE filing_id=? AND item_code=?",
                          (w[who]["id"], code)).fetchone()
    return r[0] if r else None


def test_peers_share_activity_kind_and_dpo_and_are_still_open(w):
    ids = {p["id"] for p in travel.peers_of(w["conn"], w["me"])}
    assert ids == {w["b"]["id"], w["c"]["id"], w["lower"]["id"]}      # not the other DPO/activity/submitted one


def test_a_blank_activity_or_empty_dpo_links_nobody(w):
    c = w["conn"]
    c.execute("UPDATE travel_filing SET dpo_no='' WHERE id=?", (w["me"]["id"],)); c.commit()
    assert travel.peers_of(c, travel.get_filing(c, w["me"]["id"])) == []


def test_not_applicable_is_copied_but_never_over_a_filled_row(w):
    c = w["conn"]
    travel.sync_items(c, w["b"])
    c.execute("UPDATE travel_item SET state='present', drive_url='https://drive.google.com/x' "
              "WHERE filing_id=? AND item_code='dpo'", (w["b"]["id"],)); c.commit()
    travel.save_item(c, w["me"], "dpo", na=True)
    assert travel.apply_na_to_peers(c, w["me"], "dpo", True, by="me@test.local") == 2
    assert state(w, "me") == state(w, "c") == state(w, "lower") == "na"
    assert state(w, "b") == "present"                                 # someone's own upload is left alone
    assert state(w, "other_dpo") is None and state(w, "done") is None


def test_needed_after_all_only_reverses_rows_marked_not_applicable(w):
    c = w["conn"]
    travel.save_item(c, w["me"], "dpo", na=True)
    travel.apply_na_to_peers(c, w["me"], "dpo", True)
    travel.save_item(c, w["me"], "dpo", na=False)
    assert travel.apply_na_to_peers(c, w["me"], "dpo", False, by="me@test.local") == 3
    assert {state(w, x) for x in ("me", "b", "c", "lower")} == {"missing"}
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_item_everyone'").fetchone()[0] == 1


def test_an_audit_label_exists():
    assert "travel_item_everyone" in st._AUDIT_ACTIONS
