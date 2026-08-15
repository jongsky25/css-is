"""
The one-shot ANNEX C backfill for August 16-31, 2026.

Two things are under test and they are different in kind. First, the TRANSCRIPTION:
the sheet is the record and the constant in work_arrangement_backfill.ROWS is a
copy of it, so these tests re-derive the Remarks wording from the stored fields
and check it against what the sheet actually says. A typo in the copy is the most
likely defect here and the only one no amount of careful code prevents.

Second, the APPLY: that it matches people the way the sheet writes their names,
that it never overwrites someone's own filing, and that the two "No AWA" tags land
on this period rather than reaching back over a first half already submitted.
"""
from __future__ import annotations

import pytest

import storage as st
import tzutil as tz
import work_arrangement_backfill as wabf


# ------------------------------------------------------ the sheet itself -----

def test_the_sheet_is_transcribed_whole():
    assert len(wabf.ROWS) == 45
    assert [r[0] for r in wabf.ROWS] == list(range(1, 46))


def test_the_arrangement_mix_matches_the_submitted_sheet():
    """4 regular, 5 compressed, 33 work-from-home, 3 with none — the counts a
    human can check against the paper in about ten seconds."""
    kinds = [r[4] for r in wabf.ROWS]
    assert kinds.count("REG") == 4
    assert kinds.count("CWW") == 5
    assert kinds.count("WFH") == 33
    assert kinds.count(None) == 3


def test_every_row_is_a_shape_the_app_accepts():
    for no, name, _pos, _unit, arrangement, weekday, remark in wabf.ROWS:
        if arrangement is None:
            assert weekday is None, f"row {no}: no arrangement but a weekday"
            continue
        assert arrangement in st.WORK_ARRANGEMENT_LABELS, f"row {no}: {arrangement}"
        assert remark is None, f"row {no}: an arrangement AND a No-AWA remark"
        if arrangement == "REG":
            assert weekday is None, f"row {no}: REG applies to the whole week"
        else:
            assert weekday in wabf._DAY_INDEX, f"row {no}: {weekday!r}"


@pytest.mark.parametrize("no,expected", [
    (2, "Friday Day off"),        # CWW
    (8, "Monday WFH"),            # the day that moved from the first-half sheet
    (21, "Friday Day off"),       # Naranjo, Monday on the first half
    (14, "Thursday WFH"),
    (45, "Wednesday WFH"),
])
def test_remarks_come_back_out_worded_the_way_the_sheet_words_them(no, expected):
    """The Remarks column is DERIVED, never stored (see storage._wa_remarks), so
    the only way the printed annex can match the sheet is if the arrangement and
    weekday we stored regenerate its exact wording."""
    _no, _name, _pos, _unit, arrangement, weekday, _remark = wabf.ROWS[no - 1]
    assert st._wa_remarks(arrangement, wabf._DAY_INDEX[weekday]) == expected


def test_the_two_stated_reasons_are_copied_verbatim():
    """Including 'requst'. This is what was submitted, and a form that quietly
    corrects its source is a form nobody can reconcile against the original."""
    by_name = {r[1]: r for r in wabf.ROWS}
    assert by_name["Sales, Miriam Cecilia"][6] == (
        "With requst WFH due to medical condition, for approval from OSEC")
    assert by_name["Bagos, Jesel"][6] == "Leave"
    # Orpilla is the third blank and has NO reason — that gap is the information.
    assert by_name["Orpilla, Maejorie"][4] is None
    assert by_name["Orpilla, Maejorie"][6] is None


# ------------------------------------------------------------- matching -----

@pytest.mark.parametrize("sheet,directory", [
    ("Delmendo, Eric", "Eric Delmendo"),                 # surname-first, comma
    ("Medel Alexander R.", "Alexander R. Medel"),        # surname-first, no comma
    ("Ventura, Ray Justin", "Ray Justine Ventura"),      # the spelling that differs
    ("De Guzman, Sophia Abigael D.", "Sophia Abigael De Guzman"),
    ("Flores, Kathrine Joyce D", "Kathrine Joyce Flores"),
])
def test_the_matcher_reads_the_sheet_the_way_a_person_does(sheet, directory):
    assert wabf._score(sheet, directory) >= wabf._THRESHOLD


@pytest.mark.parametrize("sheet,directory", [
    ("Santiago, Marifel", "Maria Teresa Santiago"),      # two Santiagos on the sheet
    ("Dela Cruz, Ronnel John", "Ronnel Manaloto"),       # two Ronnels
    ("Sepe, Demi Arantxa", "Demi Sese"),
])
def test_a_shared_surname_or_given_name_is_not_a_match(sheet, directory):
    assert wabf._score(sheet, directory) < wabf._THRESHOLD


# ---------------------------------------------------------------- apply -----

@pytest.fixture()
def bf_org(app_mod):
    """Accounts for a slice of the sheet, named the way the DIRECTORY would hold
    them (given-name first) rather than the way the sheet writes them."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM work_arrangement_noawa")
    conn.execute("DELETE FROM work_arrangement")
    conn.execute("DELETE FROM app_setting WHERE key = ?", (wabf.MARKER,))
    # Accounts first, then the people they point at, then the unit: every one of
    # those references the next.
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'bf-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE org_unit_id IN "
                 "(SELECT id FROM org_unit WHERE path = 'TEST/BF')")
    conn.execute("DELETE FROM org_unit WHERE path = 'TEST/BF'")
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('BF Test Unit','BFU','section','TEST/BF')").lastrowid

    def person(label, full_name, position):
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, position) "
            "VALUES (?, 1, ?, ?)", (full_name, unit, position)).lastrowid
        return st.create_admin_user(conn, f"bf-{label}@test.local", "x", "y",
                                    "viewer", rp_id=rp)

    ids = {
        "delmendo": person("delmendo", "Eric Delmendo", "Admin Asst. III"),
        "medel": person("medel", "Alexander R. Medel", "Admin Officer IV"),
        "naranjo": person("naranjo", "John Vincent Naranjo", "CP III"),
        "dimaano": person("dimaano", "Catherine Dimaano", "Nurse III"),
        "sales": person("sales", "Miriam Cecilia Sales", "Medical Officer IV"),
        "bagos": person("bagos", "Jesel Bagos", "Sr HPO"),
        "orpilla": person("orpilla", "Maejorie Orpilla", "HPO II"),
    }
    conn.commit()
    yield {"conn": conn, "ids": ids}
    conn.close()


def _live(conn, uid):
    return conn.execute(
        "SELECT arrangement, weekday, status FROM work_arrangement "
        "WHERE user_id = ? AND period_start = ?", (uid, wabf.PERIOD)).fetchone()


def test_it_files_the_sheet_as_already_approved(bf_org):
    """Approved, not pending: the paper form was approved and signed before the
    app ever saw it, and only approved rows print on the annex."""
    conn, ids = bf_org["conn"], bf_org["ids"]
    wabf.apply(conn)
    assert _live(conn, ids["delmendo"]) == ("CWW", 4, "approved")   # Friday off
    assert _live(conn, ids["medel"]) == ("REG", None, "approved")
    assert _live(conn, ids["naranjo"]) == ("CWW", 4, "approved")
    assert _live(conn, ids["dimaano"]) == ("WFH", 3, "approved")    # Thursday WFH


def test_the_backfilled_rows_say_where_they_came_from(bf_org):
    conn, ids = bf_org["conn"], bf_org["ids"]
    wabf.apply(conn)
    note = conn.execute(
        "SELECT decide_note FROM work_arrangement WHERE user_id = ?",
        (ids["medel"],)).fetchone()[0]
    assert wabf.SOURCE in note


def test_the_annex_prints_what_the_sheet_said(bf_org):
    conn, ids = bf_org["conn"], bf_org["ids"]
    wabf.apply(conn)
    rows = {r["name"]: r for r in st.work_arrangement_export_rows(conn, wabf.PERIOD)}
    assert rows["Eric Delmendo"]["arrangement"] == "CWW"
    assert rows["Eric Delmendo"]["remarks"] == "Friday Day off"
    assert rows["Catherine Dimaano"]["remarks"] == "Thursday WFH"
    assert rows["Alexander R. Medel"]["remarks"] == ""


def test_a_stated_reason_becomes_a_no_awa_tag_on_this_period_only(bf_org):
    """effective_from is the PERIOD, not whatever period today falls in. Tagging
    from 'today' would reach back over August 1-15, whose annex has already gone
    out, and silently change a form somebody already signed."""
    conn, ids = bf_org["conn"], bf_org["ids"]
    wabf.apply(conn)
    row = conn.execute(
        "SELECT remark, effective_from, effective_to FROM work_arrangement_noawa "
        "WHERE user_id = ?", (ids["sales"],)).fetchone()
    assert row[1] == wabf.PERIOD
    assert row[2] is None
    assert row[0].startswith("With requst WFH")
    assert conn.execute(
        "SELECT remark FROM work_arrangement_noawa WHERE user_id = ?",
        (ids["bagos"],)).fetchone()[0] == "Leave"
    # ...and it reads through to the printed form.
    rows = {r["name"]: r for r in st.work_arrangement_export_rows(conn, wabf.PERIOD)}
    assert rows["Jesel Bagos"]["arrangement"] == st.WORK_ARRANGEMENT_NOAWA
    assert rows["Jesel Bagos"]["remarks"] == "Leave"


def test_a_blank_nobody_explained_stays_blank(bf_org):
    conn, ids = bf_org["conn"], bf_org["ids"]
    summary = wabf.apply(conn)
    assert summary["blank"] == 1
    assert _live(conn, ids["orpilla"]) is None
    assert conn.execute("SELECT 1 FROM work_arrangement_noawa WHERE user_id = ?",
                        (ids["orpilla"],)).fetchone() is None
    rows = {r["name"]: r for r in st.work_arrangement_export_rows(conn, wabf.PERIOD)}
    assert rows["Maejorie Orpilla"]["arrangement"] == ""
    assert rows["Maejorie Orpilla"]["remarks"] == ""


def test_it_never_overwrites_what_a_person_already_holds(bf_org):
    """A real filing, or an admin's correction, outranks the transcription — in
    either order. The sheet says Friday off for Naranjo; the DB already says
    Wednesday, and the DB wins."""
    conn, ids = bf_org["conn"], bf_org["ids"]
    conn.execute(
        "INSERT INTO work_arrangement(user_id, period_start, arrangement, weekday, "
        "status, created_at) VALUES (?,?,'CWW',2,'approved',?)",
        (ids["naranjo"], wabf.PERIOD, tz.now_iso()))
    conn.commit()
    summary = wabf.apply(conn)
    assert _live(conn, ids["naranjo"]) == ("CWW", 2, "approved")
    assert summary["already"] >= 1


def test_a_pending_change_in_flight_is_left_alone(bf_org):
    conn, ids = bf_org["conn"], bf_org["ids"]
    conn.execute(
        "INSERT INTO work_arrangement(user_id, period_start, arrangement, weekday, "
        "status, created_at) VALUES (?,?,'WFH',0,'pending',?)",
        (ids["dimaano"], wabf.PERIOD, tz.now_iso()))
    conn.commit()
    wabf.apply(conn)
    rows = conn.execute(
        "SELECT arrangement, weekday, status FROM work_arrangement "
        "WHERE user_id = ? AND period_start = ?",
        (ids["dimaano"], wabf.PERIOD)).fetchall()
    assert rows == [("WFH", 0, "pending")]


def test_running_it_twice_changes_nothing(bf_org):
    conn = bf_org["conn"]
    first = wabf.apply(conn)
    again = wabf.apply(conn)
    assert again["skipped_marker"] is True
    forced = wabf.apply(conn, force=True)
    assert forced["applied"] == 0            # every row is now 'already'
    assert forced["already"] == first["applied"] + first["noawa"]
    assert conn.execute(
        "SELECT COUNT(*) FROM work_arrangement WHERE period_start = ?",
        (wabf.PERIOD,)).fetchone()[0] == first["applied"]


def test_the_marker_is_only_set_once_it_has_run(bf_org):
    conn = bf_org["conn"]
    assert st.get_setting(conn, wabf.MARKER) is None
    wabf.apply(conn)
    assert st.get_setting(conn, wabf.MARKER)


def test_a_dry_run_writes_nothing(bf_org):
    conn = bf_org["conn"]
    summary = wabf.apply(conn, dry_run=True)
    assert summary["applied"] > 0
    assert conn.execute(
        "SELECT COUNT(*) FROM work_arrangement WHERE period_start = ?",
        (wabf.PERIOD,)).fetchone()[0] == 0
    assert st.get_setting(conn, wabf.MARKER) is None


def test_people_with_no_account_are_reported_not_guessed(bf_org):
    """Most of the 45 have no account in this fixture. None of them may be
    attached to somebody else — a wrong schedule on the annex is worse than a
    missing one, because only the missing one is visible."""
    conn, ids = bf_org["conn"], bf_org["ids"]
    summary = wabf.apply(conn)
    assert len(summary["unmatched"]) == len(wabf.ROWS) - len(ids)
    placed = conn.execute(
        "SELECT user_id FROM work_arrangement WHERE period_start = ?",
        (wabf.PERIOD,)).fetchall()
    assert {u for (u,) in placed} <= set(ids.values())


def test_two_accounts_with_one_name_leave_the_row_for_a_human(bf_org):
    """A duplicate account is a directory problem. Picking one of the two and
    filing a schedule against it hides the problem AND may put the wrong person
    on the annex, so the row is reported instead."""
    conn = bf_org["conn"]
    unit = conn.execute("SELECT id FROM org_unit WHERE path = 'TEST/BF'").fetchone()[0]
    rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, position) "
        "VALUES ('Eric Delmendo', 1, ?, 'Admin Asst. III')", (unit,)).lastrowid
    st.create_admin_user(conn, "bf-delmendo2@test.local", "x", "y", "viewer", rp_id=rp)
    conn.commit()
    rec = next(r for r in wabf.resolve(conn) if r["name"] == "Delmendo, Eric")
    assert rec["user_id"] is None
    assert "ambiguous" in rec["why"]


def test_an_archived_person_neither_matches_nor_blocks_the_one_who_replaced_them(bf_org):
    """Someone who has left does not print on the annex (the roster excludes
    them), so matching one would file a row nobody sees — and would take the name
    from whoever holds the seat now."""
    conn, ids = bf_org["conn"], bf_org["ids"]
    unit = conn.execute("SELECT id FROM org_unit WHERE path = 'TEST/BF'").fetchone()[0]
    old = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, position, "
        "archived_at) VALUES ('Catherine Dimaano', 1, ?, 'Nurse III', ?)",
        (unit, tz.now_iso())).lastrowid
    st.create_admin_user(conn, "bf-dimaano-old@test.local", "x", "y", "viewer",
                         rp_id=old)
    conn.commit()
    rec = next(r for r in wabf.resolve(conn) if r["name"] == "Dimaano, Catherine")
    assert rec["user_id"] == ids["dimaano"]     # not ambiguous, and not the leaver
    wabf.apply(conn)
    assert _live(conn, ids["dimaano"]) == ("WFH", 3, "approved")


def test_the_boot_hook_survives_a_broken_backfill(bf_org, monkeypatch):
    """An annex row missing is a bug; an app that will not start is an outage."""
    conn = bf_org["conn"]
    monkeypatch.setattr(wabf, "resolve",
                        lambda _c: (_ for _ in ()).throw(RuntimeError("boom")))
    assert wabf.run_once(conn) is None
    assert st.get_setting(conn, wabf.MARKER) is None


def test_the_boot_hook_applies_once_then_costs_a_lookup(bf_org):
    conn = bf_org["conn"]
    assert wabf.run_once(conn)["applied"] > 0
    assert wabf.run_once(conn) is None
