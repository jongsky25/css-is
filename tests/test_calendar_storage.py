"""Office calendar storage (increment A1): entries, people, tags, sequence rules,
revisions, cancel/restore and the date-range query. Throwaway DB, no HTTP."""
from __future__ import annotations
from datetime import timedelta

import pytest

import storage as st
import tzutil as tz


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "cal.db"))
    st.init_db(c)
    return c


@pytest.fixture()
def users(conn):
    return [st.create_admin_user(conn, f"cal{i}@test.local", "x", "y", "viewer")
            for i in range(3)]


def _make(conn, **kw):
    kw.setdefault("title", "Section 1 Mtg")
    kw.setdefault("start_date", "2026-10-06")
    title, start = kw.pop("title"), kw.pop("start_date")
    return st.cal_create(conn, title, start, **kw)


def test_create_and_get_defaults(conn):
    eid = _make(conn, by="alice")
    e = st.cal_get(conn, eid)
    assert e["title"] == "Section 1 Mtg"
    assert (e["kind"], e["status"], e["audience"], e["source"]) == (
        "meeting", "confirmed", "unit", "app")
    assert e["sequence"] == 0 and e["end_date"] is None
    assert len(e["uid"]) == 32 and "@" not in e["uid"]
    assert e["created_by"] == "alice" and e["people"] == [] and e["tags"] == []
    assert [r["action"] for r in st.cal_revisions(conn, eid)] == ["create"]


def test_uids_are_unique_and_opaque(conn):
    assert st.cal_get(conn, _make(conn))["uid"] != st.cal_get(conn, _make(conn))["uid"]


def test_same_day_range_is_stored_as_single_day(conn):
    eid = _make(conn, end_date="2026-10-06")
    assert st.cal_get(conn, eid)["end_date"] is None


@pytest.mark.parametrize("kw", [
    {"title": "  "}, {"start_date": "2026-13-01"}, {"start_date": "tomorrow"},
    {"end_date": "2026-10-01"}, {"kind": "party"}, {"status": "maybe"},
    {"audience": "world"}, {"modality": "carrier-pigeon"}, {"start_time": "25:00"},
    {"source": "robot"},
])
def test_create_validation(conn, kw):
    with pytest.raises(ValueError):
        _make(conn, **kw)


def test_people_and_tags_are_normalised(conn, users):
    a, b, _ = users
    eid = _make(conn, people=[a, (b, "lead"), (a, "travel")], tags=["PK", " pk ", "BHW", ""])
    e = st.cal_get(conn, eid)
    assert [(p["user_id"], p["role"]) for p in e["people"]] == [(a, "attending"), (b, "lead")]
    assert e["tags"] == ["BHW", "PK"]                    # case-insensitive dedupe, blanks dropped
    with pytest.raises(ValueError):
        _make(conn, people=[(a, "boss")])


def test_sequence_rises_only_for_schedule_fields(conn):
    eid = _make(conn)
    st.cal_update(conn, eid, title="Renamed", venue="Room 2", by="x")
    assert st.cal_get(conn, eid)["sequence"] == 0
    st.cal_update(conn, eid, start_date="2026-10-07", by="x")
    assert st.cal_get(conn, eid)["sequence"] == 1
    st.cal_update(conn, eid, start_time="09:00", end_time="10:30", by="x")
    assert st.cal_get(conn, eid)["sequence"] == 2
    st.cal_update(conn, eid, status="postponed", by="x")
    assert st.cal_get(conn, eid)["sequence"] == 3
    st.cal_update(conn, eid, title="Renamed", by="x")          # no change at all
    assert st.cal_get(conn, eid)["sequence"] == 3
    assert len(st.cal_revisions(conn, eid)) == 5               # create + 4 real edits


def test_people_edit_keeps_seen_seq_and_does_not_bump_sequence(conn, users):
    a, b, c = users
    eid = _make(conn, people=[a, b])
    conn.execute("UPDATE calendar_entry_person SET seen_seq=0 WHERE user_id=?", (a,))
    st.cal_update(conn, eid, people=[a, c], by="x")
    e = st.cal_get(conn, eid)
    by_user = {p["user_id"]: p for p in e["people"]}
    assert set(by_user) == {a, c} and by_user[a]["seen_seq"] == 0
    assert by_user[c]["seen_seq"] is None and e["sequence"] == 0
    assert "people" in st.cal_revisions(conn, eid)[0]["diff"]


def test_updating_to_a_range_and_back(conn):
    eid = _make(conn)
    st.cal_update(conn, eid, end_date="2026-10-09")
    assert st.cal_get(conn, eid)["end_date"] == "2026-10-09"
    st.cal_update(conn, eid, end_date="")
    assert st.cal_get(conn, eid)["end_date"] is None
    with pytest.raises(ValueError):
        st.cal_update(conn, eid, end_date="2026-10-01")
    # moving the start onto the end collapses it to a single day
    st.cal_update(conn, eid, end_date="2026-10-09")
    st.cal_update(conn, eid, start_date="2026-10-09")
    assert st.cal_get(conn, eid)["end_date"] is None


def test_stale_sequence_is_a_conflict(conn):
    eid = _make(conn)
    st.cal_update(conn, eid, start_date="2026-10-08", by="mae")      # seq 1
    with pytest.raises(st.CalendarConflict) as ei:
        st.cal_update(conn, eid, title="Mine", expected_sequence=0, by="riza")
    assert ei.value.entry["start_date"] == "2026-10-08"
    assert st.cal_get(conn, eid)["title"] == "Section 1 Mtg"          # nothing written
    st.cal_update(conn, eid, title="Mine", expected_sequence=1, by="riza")
    assert st.cal_get(conn, eid)["title"] == "Mine"


def test_unknown_field_is_rejected(conn):
    with pytest.raises(ValueError):
        st.cal_update(conn, _make(conn), uid="hijack")


def test_cancel_and_restore_returns_to_prior_status(conn):
    eid = _make(conn, status="tentative")
    st.cal_cancel(conn, eid, by="mae")
    e = st.cal_get(conn, eid)
    assert e["status"] == "cancelled" and e["cancelled_by"] == "mae" and e["cancelled_at"]
    assert e["sequence"] == 1
    st.cal_restore(conn, eid, by="riza")
    e = st.cal_get(conn, eid)
    assert e["status"] == "tentative" and e["cancelled_at"] is None
    assert [r["action"] for r in st.cal_revisions(conn, eid)] == ["restore", "cancel", "create"]


def test_restore_window(conn, monkeypatch):
    eid = _make(conn)
    st.cal_cancel(conn, eid)
    old = (tz.now_local() - timedelta(days=st.CAL_RESTORE_DAYS + 1)).isoformat(timespec="seconds")
    conn.execute("UPDATE calendar_entry SET cancelled_at=? WHERE id=?", (old, eid))
    with pytest.raises(ValueError):
        st.cal_restore(conn, eid)
    assert st.cal_restore(conn, eid, force=True)["status"] == "confirmed"


def test_cancelled_entries_are_hidden_from_lists_by_default(conn):
    eid = _make(conn)
    st.cal_cancel(conn, eid)
    assert st.cal_list_between(conn, "2026-10-01", "2026-10-31") == []
    assert len(st.cal_list_between(conn, "2026-10-01", "2026-10-31",
                                   include_cancelled=True)) == 1


def test_range_query_includes_multi_day_entries_crossing_the_window(conn):
    trip = _make(conn, title="TA Palawan", start_date="2026-09-29", end_date="2026-10-03",
                 kind="travel")
    _make(conn, title="Before", start_date="2026-09-20")
    _make(conn, title="After", start_date="2026-10-12")
    on_edge = _make(conn, title="Edge", start_date="2026-10-05", start_time="08:00")
    got = st.cal_list_between(conn, "2026-10-01", "2026-10-05")
    assert [e["id"] for e in got] == [trip, on_edge]
    assert st.cal_list_between(conn, "2026-10-04", "2026-10-04") == []


def test_list_orders_by_day_then_time(conn):
    late = _make(conn, title="Late", start_time="14:00")
    early = _make(conn, title="Early", start_time="09:00")
    allday = _make(conn, title="All day")
    assert [e["id"] for e in st.cal_list_between(conn, "2026-10-06", "2026-10-06")] == [
        allday, early, late]


def test_import_key_is_idempotent(conn):
    a = _make(conn, import_key="docx:2026-10-06:section 1 mtg", source="import")
    b = _make(conn, title="Changed", import_key="docx:2026-10-06:section 1 mtg",
              source="import")
    assert a == b and st.cal_get(conn, a)["title"] == "Section 1 Mtg"
    assert conn.execute("SELECT COUNT(*) FROM calendar_entry").fetchone()[0] == 1


def test_hard_delete_removes_children(conn, users):
    eid = _make(conn, people=[users[0]], tags=["PK"])
    assert st.cal_delete(conn, eid, by="admin") is True
    for t in ("calendar_entry", "calendar_entry_person", "calendar_entry_tag",
              "calendar_entry_revision"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
    assert st.cal_delete(conn, eid) is False


def test_writes_are_audited_when_the_actor_is_known(conn):
    eid = _make(conn, by="mae")
    st.cal_update(conn, eid, title="X", by="mae")
    st.cal_cancel(conn, eid, by="mae")
    acts = [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert acts[-3:] == ["calendar_create", "calendar_update", "calendar_update"]


def test_init_db_is_safe_to_rerun_on_a_populated_db(conn):
    eid = _make(conn, tags=["PK"])
    st.init_db(conn)
    assert st.cal_get(conn, eid)["tags"] == ["PK"]
