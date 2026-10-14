"""Travel filing reminders and bell rows (T3)."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import mailer
import send_reminders as sr
import storage as st
import travel
import travel_notify
import tzutil as tz

BASE = "https://x.test"
TODAY = date(2026, 10, 14)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    c = st.connect(str(tmp_path / "t.db")); st.init_db(c)
    monkeypatch.setattr(tz, "today_local", lambda: TODAY)
    return c


@pytest.fixture()
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subj, body, html=None, attachments=None: out.append((to, subj, body)) or
                        {"sent": True, "detail": "ok"})
    return out


_n = [0]


def filing(conn, uid, **kw):
    _n[0] += 1
    f = dict(user_id=uid, kind="reimbursement", source_kind="blank", act_title="Workshop", act_start="2026-10-05",
             act_end="2026-10-09", status="open", deadline_date=(TODAY + timedelta(days=1)).isoformat(),
             ref_code=f"TRV-{_n[0]}")
    f.update(kw)
    conn.execute(f"INSERT INTO travel_filing({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    conn.commit()
    return f["ref_code"]


@pytest.fixture()
def uid(conn):
    return st.create_admin_user(conn, "juan@x.test", "x", "y", "viewer")


def iso(n):
    return (TODAY + timedelta(days=n)).isoformat()


# ------------------------------------------------------------------ job ---

def test_a_due_filing_is_emailed_once_with_a_link(conn, uid, sent):
    ref = filing(conn, uid, deadline_date=iso(1))
    assert sr.send_travel_filing_due(conn, BASE) == 1
    assert len(sent) == 1 and sent[0][0] == "juan@x.test"
    assert f"{BASE}/travel/f/{ref}" in sent[0][2] and "reimbursement, due in 1 day" in sent[0][2]
    assert sr.send_travel_filing_due(conn, BASE) == 0 and len(sent) == 1          # idempotent


def test_overdue_is_included_and_dry_run_counts_without_sending(conn, uid, sent, capsys):
    filing(conn, uid, deadline_date=iso(-3))
    assert sr.send_travel_filing_due(conn, BASE, dry_run=True) == 1
    assert sent == [] and "[dry-run]" in capsys.readouterr().out
    assert sr.send_travel_filing_due(conn, BASE) == 1                            # dry run logged nothing


def test_withdrawn_submitted_and_far_off_filings_are_skipped(conn, uid, sent):
    filing(conn, uid, status="withdrawn", deadline_date=iso(0))
    filing(conn, uid, status="submitted", deadline_date=iso(0))
    filing(conn, uid, deadline_date=iso(3))                                       # lead is 2
    filing(conn, uid, deadline_date=None)
    assert sr.send_travel_filing_due(conn, BASE) == 0 and sent == []


def test_the_lead_days_setting_widens_the_window(conn, uid, sent):
    filing(conn, uid, deadline_date=iso(5))
    st.set_setting(conn, "email_param.travel_filing_lead_days", "5")
    assert sr.send_travel_filing_due(conn, BASE) == 1


def test_an_unliquidated_cash_advance_is_listed_and_a_liquidation_clears_it(conn, uid, sent):
    ca = filing(conn, uid, kind="ca", status="submitted", deadline_date=None, act_end=iso(-2), act_title="Planning")
    assert sr.send_travel_filing_due(conn, BASE) == 1
    assert "Planning" in sent[0][2] and "liquidation" in sent[0][2]
    sent.clear()
    cid = conn.execute("SELECT id FROM travel_filing WHERE ref_code=?", (ca,)).fetchone()[0]
    filing(conn, uid, kind="liquidation", ca_filing_id=cid, deadline_date=None, status="open")
    assert sr.send_travel_filing_due(conn, BASE) == 0


def test_one_email_per_person_and_it_goes_to_the_directory_email(conn, sent):
    rp = conn.execute("INSERT INTO resource_person(name, email, is_internal) VALUES ('Ana','ana@dir.test',1)").lastrowid
    u = st.create_admin_user(conn, "ana@login.test", "x", "y", "viewer")
    conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp, u)); conn.commit()
    filing(conn, u, deadline_date=iso(0)); filing(conn, u, deadline_date=iso(1))
    assert sr.send_travel_filing_due(conn, BASE) == 1
    assert sent[0][0] == "ana@dir.test" and sent[0][2].count("/travel/f/") == 2


def test_nothing_is_sent_when_travel_is_switched_off(conn, uid, sent):
    filing(conn, uid, deadline_date=iso(0))
    st.set_setting(conn, "travel.enabled", "0")
    assert sr.send_travel_filing_due(conn, BASE) == 0


def test_registered_everywhere_and_run_dispatches():
    j = "travel_filing_due"
    assert j in sr._ALL_JOBS and sr.JOB_FEATURE[j] == "job_travel_filing_due"
    assert sr.JOB_FEATURE[j] in mailer.FEATURES and mailer.FEATURES[sr.JOB_FEATURE[j]][2] == "scheduled"
    subj, body, html = mailer._PREVIEWS[sr.JOB_FEATURE[j]]()
    assert subj and "/" in body and html
    assert "travel_filing_lead_days" in sr.PARAMS


def test_run_reports_the_job(tmp_path, monkeypatch, sent):
    db = str(tmp_path / "r.db"); c = st.connect(db); st.init_db(c)
    monkeypatch.setattr(sr, "_base_url", lambda: BASE); monkeypatch.setattr(tz, "today_local", lambda: TODAY)
    u = st.create_admin_user(c, "r@x.test", "x", "y", "viewer"); filing(c, u, deadline_date=iso(0)); c.close()
    assert sr.run(db_path=db, jobs={"travel_filing_due"}) == {"travel_filing_due": 1}


# ----------------------------------------------------------------- bell ---

def test_bell_rows_appear_and_disappear(conn, uid):
    assert travel_notify.bell_rows(conn, uid, TODAY) == []
    filing(conn, uid, deadline_date=iso(2)); filing(conn, uid, deadline_date=iso(-1))
    filing(conn, uid, kind="ca", status="submitted", deadline_date=None, act_end=iso(-1))
    rows = {r["text"]: r for r in travel_notify.bell_rows(conn, uid, TODAY)}
    assert rows["1 travel claim is overdue"]["url"] == "/travel"
    assert rows["1 travel claim due soon"]["count"] == 1
    assert "A cash advance still needs a liquidation" in rows
    conn.execute("UPDATE travel_filing SET status='submitted'"); conn.commit()
    assert [r["text"] for r in travel_notify.bell_rows(conn, uid, TODAY)] == ["A cash advance still needs a liquidation"]
    conn.execute("UPDATE travel_filing SET status='withdrawn'"); conn.commit()
    assert travel_notify.bell_rows(conn, uid, TODAY) == []


def test_bell_is_per_user_and_empty_when_the_switch_is_off(conn, uid):
    other = st.create_admin_user(conn, "o@x.test", "x", "y", "viewer")
    filing(conn, uid, deadline_date=iso(0))
    assert travel_notify.bell_rows(conn, other, TODAY) == []
    assert travel_notify.bell_rows(conn, uid, TODAY)
    st.set_setting(conn, "travel.enabled", "0")
    assert travel_notify.bell_rows(conn, uid, TODAY) == []


def test_flag_line_only_for_admin_unit_and_only_with_open_flags(conn, uid, monkeypatch):
    f = filing(conn, uid, deadline_date=None)
    fid = conn.execute("SELECT id FROM travel_filing WHERE ref_code=?", (f,)).fetchone()[0]
    import rooms
    monkeypatch.setattr(rooms, "is_room_admin", lambda c, u: u["id"] == uid)
    assert travel_notify.bell_rows(conn, uid, TODAY) == []
    conn.execute("INSERT INTO travel_flag(filing_id, kind, sig) VALUES (?, 'over_ceiling', 'a')", (fid,)); conn.commit()
    assert [r["text"] for r in travel_notify.bell_rows(conn, uid, TODAY)] == ["1 travel flag to verify"]
    other = st.create_admin_user(conn, "o@x.test", "x", "y", "viewer")
    assert travel_notify.bell_rows(conn, other, TODAY) == []
