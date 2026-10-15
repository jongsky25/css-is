"""Travel admin data (T7): ceilings and routes, the justification library, retention, the holiday
notice, and a sweep of the rules every travel route must keep."""
from __future__ import annotations
import ast
import json
import pathlib
import subprocess
import sys
from datetime import date, datetime, timedelta

import pytest

import retention
import rooms_notify
import storage as st
import travel
import travel_docs as td
import tzutil as tz
from conftest import join_admin_section
from test_travel_generate import dicts, flags, items, jpost, mk, post, relay, ride            # noqa: F401

MEMBER, OTHER = "encoder@test.local", "manager@test.local"      # Administrative Section members
ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    snap = {t: dicts(c, f"SELECT * FROM {t}") for t in ("travel_ceiling", "travel_route_type", "travel_justification")}
    settings = {k: st.get_setting(c, k) for k in ("travel.enabled", "travel.template_admins")}
    yield c
    for t in ("travel_flag", "travel_item", "travel_filing"):
        c.execute(f"DELETE FROM {t}")
    for t, rows in snap.items():
        c.execute(f"DELETE FROM {t}")
        for r in rows:
            c.execute(f"INSERT INTO {t}({','.join(r)}) VALUES ({','.join('?' * len(r))})", tuple(r.values()))
    for k, v in settings.items():
        st.set_setting(c, k, v or "")
    c.execute("DELETE FROM holiday WHERE name LIKE 'TRAVELTEST%'")
    c.commit(); c.close()


@pytest.fixture()
def unit(conn):
    ids = [conn.execute("SELECT id FROM admin_user WHERE username=?", (u,)).fetchone()[0] for u in (MEMBER, OTHER)]
    for i in ids:
        join_admin_section(conn, i)
    yield ids
    for i in ids:
        conn.execute("UPDATE admin_user SET rp_id=NULL WHERE id=?", (i,))
    conn.commit()


def ceil(conn):
    return travel.ceilings(conn)


# ----------------------------------------------------------- ceilings and routes ---

def test_the_screen_is_for_the_admin_unit_only(encoder, viewer, admin, conn, unit):
    page = encoder.get("/travel/admin")
    assert page.status_code == 200 and "Residence" in page.text and "550" in page.text
    assert viewer.get("/travel/admin").status_code == 403 and admin.get("/travel/admin").status_code == 403
    assert post(viewer, "/travel/admin/ceilings", tnvs="1").status_code == 403
    assert post(admin, "/travel/admin/route", label="X", rer="100").status_code == 403
    assert ceil(conn)[("tnvs", "*")] == 700


def test_changed_ceilings_apply_to_the_next_ride_check(encoder, viewer, conn, relay, unit):         # noqa: F811
    ref = mk(viewer)
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-01", 560)]})
    assert [f["kind"] for f in flags(conn, ref)] == ["over_ceiling"]
    r = post(encoder, "/travel/admin/ceilings", rer__residence_airport="600", rer__residence_venue="450",
             tnvs="700", taxi="700", cenrr="300", active__residence_airport="1", active__residence_venue="1")
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert ceil(conn)[("rer", "residence_airport")] == 600
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-01", 560)]})
    assert flags(conn, ref) == []
    row = dicts(conn, "SELECT * FROM travel_ceiling WHERE mode='rer' AND route_type='residence_airport'")[0]
    assert row["updated_by"] == MEMBER and row["updated_at"]
    assert dicts(conn, "SELECT * FROM audit_log WHERE action='travel_ceiling_save'")


def test_bad_amounts_change_nothing(encoder, conn, unit):
    for bad in ("0", "-5", "abc", "", "100001"):
        r = post(encoder, "/travel/admin/ceilings", rer__residence_airport="900", rer__residence_venue="450",
                 tnvs=bad, taxi="700", cenrr="300", active__residence_airport="1", active__residence_venue="1")
        assert "err=" in r.headers["location"], bad
        assert ceil(conn)[("rer", "residence_airport")] == 550 and ceil(conn)[("tnvs", "*")] == 700


def test_switching_a_route_off_makes_rides_on_it_unlisted(encoder, viewer, conn, relay, unit):      # noqa: F811
    post(encoder, "/travel/admin/ceilings", rer__residence_airport="550", rer__residence_venue="450", tnvs="700",
         taxi="700", cenrr="300", active__residence_venue="1")                                         # airport left unticked = off
    assert ("rer", "residence_airport") not in ceil(conn)
    ref = mk(viewer)
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-01", 400)]})
    assert [f["kind"] for f in flags(conn, ref)] == ["unlisted_route"]


def test_a_new_route_gets_its_rer_ceiling_and_counts_as_approved(encoder, viewer, conn, relay, unit):   # noqa: F811
    r = post(encoder, "/travel/admin/route", label="Residence ⇄ Terminal 3", rer="500")
    assert "ok=" in r.headers["location"]
    code = "residence_terminal_3"
    assert ceil(conn)[("rer", code)] == 500 and code in {x["code"] for x in travel.route_types(conn) if x["active"]}
    ref = mk(viewer)
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-01", 480, route=code)]})
    assert flags(conn, ref) == []
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-01", 520, route=code)]})
    assert [f["kind"] for f in flags(conn, ref)] == ["over_ceiling"]
    assert "Terminal 3" in viewer.get(f"/travel/f/{ref}/prepare").text


def test_route_names_must_be_new_and_the_ceiling_valid(encoder, conn, unit):
    for label, rer in (("", "100"), ("!!!", "100"), ("Residence ⇄ Airport", "100"), ("Brand new", "0"), ("Brand new", "x")):
        assert "err=" in post(encoder, "/travel/admin/route", label=label, rer=rer).headers["location"], (label, rer)
    assert len(travel.route_types(conn)) == 2


def test_admin_screens_check_origin_and_the_switch(encoder, admin, conn, unit):
    r = encoder.post("/travel/admin/ceilings", content="tnvs=1", follow_redirects=False,
                     headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://evil.example"})
    assert r.status_code == 403 and ceil(conn)[("tnvs", "*")] == 700
    post(admin, "/admin/travel")                                                                      # switch off
    assert "not switched on" in encoder.get("/travel/admin").text and "not switched on" in encoder.get("/travel/library").text


# ------------------------------------------------------------------- the library ---

def test_template_administrators_edit_other_members_only_read(encoder, manager, conn, unit):
    st.set_setting(conn, "travel.template_admins", MEMBER); conn.commit()
    jid = travel.justifications(conn)[0]["id"]
    assert "Save" in encoder.get("/travel/library").text and "readonly" not in encoder.get("/travel/library").text
    assert "readonly" in manager.get("/travel/library").text
    ok = post(encoder, "/travel/library", id=str(jid), title="Edited", format="separate", body="Hello {{traveler_name}}", active="1")
    assert "ok=" in ok.headers["location"] and dicts(conn, "SELECT title, updated_by FROM travel_justification WHERE id=?", (jid,))[0] == {"title": "Edited", "updated_by": MEMBER}
    assert post(manager, "/travel/library", id=str(jid), title="Hacked", format="separate", body="x").status_code == 403
    assert dicts(conn, "SELECT title FROM travel_justification WHERE id=?", (jid,))[0]["title"] == "Edited"
    assert dicts(conn, "SELECT * FROM audit_log WHERE action='travel_library_save'")


def test_library_text_is_validated(encoder, conn, unit):
    st.set_setting(conn, "travel.template_admins", MEMBER); conn.commit()
    n = len(travel.justifications(conn))
    for body in ("Dear {{boss_name}}", "", "x" * 6001):
        r = post(encoder, "/travel/library", title="T", format="separate", body=body, active="1")
        assert "err=" in r.headers["location"]
    assert "err=" in post(encoder, "/travel/library", title="", format="separate", body="ok").headers["location"]
    assert "err=" in post(encoder, "/travel/library", title="T", format="nope", body="ok").headers["location"]
    assert len(travel.justifications(conn)) == n


def test_a_new_text_is_used_by_the_prepare_defaults_and_inactive_ones_are_not(encoder, conn, unit):
    st.set_setting(conn, "travel.template_admins", MEMBER); conn.commit()
    conn.execute("UPDATE travel_justification SET active=0 WHERE format='separate'"); conn.commit()
    f = {"id": 1, "ref_code": "TF-2610-0001", "kind": "liquidation", "act_title": "Workshop", "act_start": "2026-10-01",
         "act_end": "2026-10-02", "act_venue": "Cebu", "mc114_format": "separate"}
    profile = {"person_name": "Ana", "username": "a@doh.gov.ph"}
    assert td.defaults(conn, f, profile, {})["mc114_text"] == ""
    post(encoder, "/travel/library", title="Fresh", format="separate", body="{{traveler_name}} went to {{venue}}.", active="1")
    assert td.defaults(conn, f, profile, {})["mc114_text"] == "Ana went to Cebu."


# --------------------------------------------------------------------- retention ---

def filing(conn, uid, status, when, **kw):
    f = dict(user_id=uid, kind="liquidation", source_kind="blank", act_title="T", act_start="2025-01-01", act_end="2025-01-02",
             status=status, answers_json='{"flew": 1}', dpo_no="2025-9")
    f["ref_code"] = f"TF-X-{conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] + 1:04d}"
    f.update(kw)
    if status == "submitted":
        f["submitted_at"] = when
    if status == "withdrawn":
        f["withdrawn_at"] = when
    fid = conn.execute(f"INSERT INTO travel_filing({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values())).lastrowid
    conn.execute("INSERT INTO travel_item(filing_id, item_code, handling, state, drive_url, drive_file_id, doc_url, fmis_ref, note) "
                 "VALUES (?, 'dpo', 'upload', 'present', 'https://drive.google.com/a', 'fid', 'https://docs.google.com/b', 'FM-1', 'private')", (fid,))
    conn.execute("INSERT INTO travel_flag(filing_id, kind, sig, detail, state, note) VALUES (?, 'over_ceiling', ?, 'Fare 560', 'verified', 'secret note')",
                 (fid, f"s{fid}"))
    conn.commit()
    return fid


TODAY = date(2026, 10, 15)


def old(months=14):
    return (datetime(2026, 10, 15) - timedelta(days=30 * months)).isoformat()


def test_purge_blanks_personal_data_after_twelve_months_and_keeps_the_row(conn):
    uid = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    a = filing(conn, uid, "submitted", old(14))
    b = filing(conn, uid, "withdrawn", old(14))
    keep = [filing(conn, uid, "submitted", old(2)), filing(conn, uid, "open", old(30))]
    assert travel.purge_filings(conn, today=TODAY, dry_run=True) == 2
    assert dicts(conn, "SELECT drive_url FROM travel_item WHERE filing_id=?", (a,))[0]["drive_url"]       # dry run changed nothing
    assert travel.purge_filings(conn, today=TODAY) == 2
    for fid in (a, b):
        it = dicts(conn, "SELECT * FROM travel_item WHERE filing_id=?", (fid,))[0]
        assert not any(it[k] for k in ("drive_url", "drive_file_id", "doc_url", "fmis_ref", "note")) and it["state"] == "present"
        fl = dicts(conn, "SELECT * FROM travel_flag WHERE filing_id=?", (fid,))[0]
        assert fl["detail"] is None and fl["note"] is None and fl["state"] == "verified"
        f = dicts(conn, "SELECT * FROM travel_filing WHERE id=?", (fid,))[0]
        assert f["answers_json"] == "{}" and f["purged_at"] and f["status"] in ("submitted", "withdrawn") and f["act_title"] == "T"
    for fid in keep:
        assert dicts(conn, "SELECT drive_url FROM travel_item WHERE filing_id=?", (fid,))[0]["drive_url"]
        assert dicts(conn, "SELECT purged_at FROM travel_filing WHERE id=?", (fid,))[0]["purged_at"] is None
    assert travel.purge_filings(conn, today=TODAY) == 0                                                   # idempotent
    assert dicts(conn, "SELECT * FROM audit_log WHERE action='travel_purge'")


def test_the_window_comes_from_the_setting(conn):
    uid = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    filing(conn, uid, "submitted", old(4))
    assert travel.purge_filings(conn, today=TODAY, dry_run=True) == 0
    st.set_setting(conn, "travel.retention_months", "3"); conn.commit()
    assert travel.purge_filings(conn, today=TODAY, dry_run=True) == 1
    st.set_setting(conn, "travel.retention_months", "12"); conn.commit()


def test_retention_wrapper_and_command_line(app_mod, conn):
    uid = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    filing(conn, uid, "submitted", old(14))
    assert retention.purge_travel_filings(conn, dry_run=True, today=TODAY) == 1
    out = subprocess.run([sys.executable, "retention.py", "--db", app_mod.DB, "--travel-filings", "--dry-run"],
                         capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert out.returncode == 0 and "[dry-run]" in out.stdout and "would be purged" in out.stdout


def test_the_daily_tick_purges_once_a_day(tmp_path, monkeypatch):
    c = st.connect(str(tmp_path / "t.db")); st.init_db(c)
    calls = []
    monkeypatch.setattr(travel, "purge_filings", lambda conn, **kw: calls.append(kw))
    now = datetime(2026, 10, 15, 9, 0, tzinfo=tz.now_local().tzinfo)
    rooms_notify.tick(c, "https://x.test", now=now, send=lambda *a, **k: {"sent": True})
    rooms_notify.tick(c, "https://x.test", now=now, send=lambda *a, **k: {"sent": True})
    assert len(calls) == 1
    monkeypatch.setattr(travel, "purge_filings", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rooms_notify.tick(c, "https://x.test", now=now + timedelta(days=1), send=lambda *a, **k: {"sent": True})   # must not raise


# ----------------------------------------------------------------- holiday notice ---

def test_the_notice_shows_until_next_years_holidays_are_loaded(admin, encoder, conn, unit):
    year = tz.today_local().year + 1
    conn.execute("DELETE FROM holiday WHERE day BETWEEN ? AND ?", (f"{year}-01-01", f"{year}-12-31")); conn.commit()
    assert f"No holidays are loaded for {year}" in admin.get("/admin/travel").text
    assert f"No holidays are loaded for {year}" in encoder.get("/travel/admin").text
    conn.execute("INSERT INTO holiday(day, name, kind, created_by) VALUES (?, 'TRAVELTEST day', 'regular', 'test')", (f"{year}-01-01",)); conn.commit()
    assert "No holidays are loaded" not in admin.get("/admin/travel").text
    assert "No holidays are loaded" not in encoder.get("/travel/admin").text


# ------------------------------------------------------------------- final sweep ---

EXPECTED_COLUMNS = {
    "travel_filing": {"id", "ref_code", "user_id", "kind", "source_kind", "entry_id", "event_id", "act_title", "act_start",
                      "act_end", "act_venue", "dpo_no", "dpo_date", "answers_json", "advance_amount", "ca_filing_id",
                      "mc114_format", "deadline_date", "deadline_rule", "status", "gen_state", "opened_at", "ready_at",
                      "submitted_at", "withdrawn_at", "created_by", "updated_at", "purged_at"},
    "travel_item": {"filing_id", "item_code", "handling", "state", "drive_url", "drive_file_id", "doc_url", "doc_state", "drive_source",
                    "fmis_ref", "note", "updated_at"},
    "travel_flag": {"id", "filing_id", "kind", "sig", "detail", "state", "supervisor_confirmed", "note", "decided_by",
                    "decided_at", "created_at"},
}


def test_no_table_can_quietly_start_storing_form_contents(conn):
    """Form contents are never saved (plan section 1). A new column on these tables must be a conscious change."""
    for table, cols in EXPECTED_COLUMNS.items():
        assert {r[1] for r in conn.execute(f"PRAGMA table_info({table})")} == cols, table


NOT_AUDITED = {"travel_answers", "travel_item", "travel_link_check", "admin_travel_ping",
               "travel_rates_calc", "travel_scan_document"}      # drafts and read-only checks (the calculator and the ticket reader store nothing)


def test_every_travel_post_is_audited_unless_it_is_a_draft_edit():
    tree = ast.parse((ROOT / "travel_routes.py").read_text())
    posts = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            routes = [d for d in node.decorator_list if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "post"]
            if routes:
                has_audit = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "audit" for n in ast.walk(node))
                posts.append((node.name, has_audit))
    assert len(posts) >= 10
    unaudited = {n for n, a in posts if not a}
    # the ready / submit / withdraw handlers are built by _transition(), which audits for all three
    assert unaudited - {"handler"} <= NOT_AUDITED, unaudited


def test_every_travel_page_needs_a_login(client, app_mod):
    paths = set()
    for top in app_mod.app.routes:                       # newer FastAPI keeps included routers behind a wrapper
        for r in getattr(getattr(top, "original_router", None), "routes", None) or [top]:
            p = getattr(r, "path", "")
            if p.startswith("/travel") or p.startswith("/admin/travel"):
                paths.add((p, tuple(sorted(getattr(r, "methods", set()) - {"HEAD"}))))
    assert len(paths) >= 20
    for p, methods in paths:
        url = p.replace("{ref}", "TF-2610-0001").replace("{code}", "dpo").replace("{flag_id}", "1")
        for m in methods:
            resp = client.request(m, url, content="{}", follow_redirects=False)
            assert resp.status_code in (302, 303, 401, 403), (m, p, resp.status_code)


def test_travel_never_appears_in_a_public_prefix_list():
    src = (ROOT / "app.py").read_text()
    for marker in ("_PUBLIC_PREFIXES", "PUBLIC_PREFIXES", "_PUBLIC_PATHS"):
        for line in src.splitlines():
            if marker in line and "=" in line:
                assert "/travel" not in line
