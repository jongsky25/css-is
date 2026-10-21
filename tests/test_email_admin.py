"""
Admin email control center (docs/ADMIN_EMAIL_FEATURES_PLAN.md).
Phase 1: the per-feature on/off setting and the mailer.py catalog it reads
against. Phase 4: the /admin/email console built on top of it. Phase 5:
preview + test-send. Phase 6: the send log.
"""
from datetime import timedelta

import mailer
import retention
import storage as st
import tzutil as tz


def _reset(conn):
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'email_feature.%'")
    conn.commit()


def _reset_log(conn):
    conn.execute("DELETE FROM email_log")
    conn.commit()


# ---- storage.email_feature_enabled / set_email_feature ---------------------

def test_feature_defaults_enabled_with_no_row(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        assert st.email_feature_enabled(conn, "event_created") is True
    finally:
        conn.close()


def test_set_feature_off_then_on(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_email_feature(conn, "event_created", False)
        assert st.email_feature_enabled(conn, "event_created") is False
        st.set_email_feature(conn, "event_created", True)
        assert st.email_feature_enabled(conn, "event_created") is True
    finally:
        conn.close()


def test_unknown_key_reads_enabled(db_path):
    """A typo'd or not-yet-cataloged key must never silently swallow a send."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        assert st.email_feature_enabled(conn, "not_a_real_feature") is True
    finally:
        conn.close()


def test_features_are_independent(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_email_feature(conn, "wellness_approval", False)
        assert st.email_feature_enabled(conn, "wellness_approval") is False
        assert st.email_feature_enabled(conn, "wellness_decided") is True
    finally:
        _reset(conn)
        conn.close()


# ---- mailer.FEATURES / ALWAYS_ON catalog ------------------------------------

def test_features_and_always_on_keys_are_disjoint():
    assert set(mailer.FEATURES) & set(mailer.ALWAYS_ON) == set()


def test_every_feature_has_label_hint_and_valid_group():
    for key, (label, hint, group) in mailer.FEATURES.items():
        assert label and isinstance(label, str), key
        assert hint and isinstance(hint, str), key
        assert group in ("transactional", "scheduled"), key


def test_every_always_on_has_label_and_why():
    for key, (label, why) in mailer.ALWAYS_ON.items():
        assert label and isinstance(label, str), key
        assert why and isinstance(why, str), key


def test_scheduled_features_match_reminder_jobs():
    """Every job_* key in FEATURES lines up 1:1 with an actual scheduled job
    (send_reminders._ALL_JOBS) — a stale or misspelled key here would gate
    nothing real."""
    import send_reminders as sr
    scheduled_keys = {k for k, v in mailer.FEATURES.items() if v[2] == "scheduled"}
    assert scheduled_keys == {f"job_{j}" for j in sr._ALL_JOBS}


# ---- /admin/email console (Phase 4) -----------------------------------------

def test_admin_email_lists_every_row(admin):
    body = admin.get("/admin/email").text
    for label, _hint, _group in mailer.FEATURES.values():
        assert label in body
    for label, _why in mailer.ALWAYS_ON.values():
        assert label in body


def test_admin_email_shows_recent_sends(admin, db_path):
    conn = st.connect(db_path)
    try:
        _reset_log(conn)
        st.log_email_send(conn, "event_created", "row@test.local", "A subject", "sent")
        st.log_email_send(conn, "wellness_approval", "row2@test.local", "B subject",
                          "skipped_off")
        body = admin.get("/admin/email").text
        assert "row@test.local" in body
        assert "row2@test.local" in body
        assert "A subject" in body
        assert "skipped off" in body       # status word, underscore replaced with space
    finally:
        _reset_log(conn)
        conn.close()


def test_admin_email_requires_manage_users(viewer):
    assert viewer.get("/admin/email").status_code == 403
    assert viewer.post("/admin/email/toggle", data={"key": "event_created", "on": "0"}).status_code == 403


def test_admin_email_toggle_flips_setting_and_audits(admin, db_path):
    conn = st.connect(db_path)
    try:
        _reset(conn)
        before = len(st.list_audit(conn, action="email_feature_toggle"))
        r = admin.post("/admin/email/toggle", data={"key": "event_created", "on": "0"},
                       follow_redirects=False)
        assert r.status_code == 303
        assert st.email_feature_enabled(conn, "event_created") is False
        after = st.list_audit(conn, action="email_feature_toggle")
        assert len(after) == before + 1

        admin.post("/admin/email/toggle", data={"key": "event_created", "on": "1"})
        assert st.email_feature_enabled(conn, "event_created") is True
    finally:
        _reset(conn)
        conn.close()


def test_admin_email_toggle_rejects_unknown_key(admin, db_path):
    conn = st.connect(db_path)
    try:
        _reset(conn)
        r = admin.post("/admin/email/toggle", data={"key": "not_a_real_feature", "on": "0"},
                       follow_redirects=False)
        assert r.status_code == 303
        assert "err=" in r.headers["location"]
        assert conn.execute(
            "SELECT 1 FROM app_setting WHERE key LIKE 'email_feature.%'").fetchone() is None
    finally:
        conn.close()


# ---- mailer.sample_message / preview (Phase 5) ------------------------------

def test_every_feature_and_always_on_key_has_a_working_sample():
    """The one test that stops a future composer from being added to the
    catalog without a preview sample."""
    for key in list(mailer.FEATURES) + list(mailer.ALWAYS_ON):
        result = mailer.preview(key)
        assert result is not None, key
        subject, html = result
        assert subject and isinstance(subject, str), key
        assert html and mailer._SAMPLE_LINK in html, key


def test_sample_message_matches_preview_subject():
    for key in list(mailer.FEATURES) + list(mailer.ALWAYS_ON):
        subject, _body, _html = mailer.sample_message(key)
        assert subject == mailer.preview(key)[0], key


def test_preview_none_on_unknown_key():
    assert mailer.preview("not_a_real_feature") is None
    assert mailer.sample_message("not_a_real_feature") is None


# ---- /admin/email/preview + /admin/email/test (Phase 5) ---------------------

def test_admin_email_preview_renders_sample_html(admin):
    r = admin.get("/admin/email/preview/event_created")
    assert r.status_code == 200
    assert mailer._SAMPLE_LINK in r.text


def test_admin_email_preview_404s_on_unknown_key(admin):
    assert admin.get("/admin/email/preview/not_a_real_feature").status_code == 404


def test_admin_email_preview_requires_manage_users(viewer):
    assert viewer.get("/admin/email/preview/event_created").status_code == 403


def test_admin_email_test_sends_only_to_the_requesting_admin(admin, monkeypatch):
    """A `to`/`email` field posted alongside `key` must never be honored —
    test-send only ever goes to the signed-in admin's own address, so this
    route can never be turned into an open relay."""
    calls = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send",
                        lambda *a, **kw: calls.append(a) or {"sent": True, "detail": "ok"})
    r = admin.post("/admin/email/test",
                   data={"key": "event_created", "to": "attacker@evil.example"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]
    assert len(calls) == 1
    assert calls[0][0] == "admin@test.local"


def test_admin_email_test_not_configured_says_so(admin, monkeypatch):
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    r = admin.post("/admin/email/test", data={"key": "event_created"}, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]


def test_admin_email_test_rejects_unknown_key(admin, monkeypatch):
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    r = admin.post("/admin/email/test", data={"key": "not_a_real_feature"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]


def test_admin_email_test_requires_manage_users(viewer):
    assert viewer.post("/admin/email/test", data={"key": "event_created"}).status_code == 403


# ---- mailer.send_status (Phase 6) -------------------------------------------

def test_send_status_sent(monkeypatch):
    assert mailer.send_status({"sent": True, "detail": "Email sent."}) == "sent"


def test_send_status_not_configured(monkeypatch):
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    assert mailer.send_status({"sent": False, "detail": "x"}) == "not_configured"


def test_send_status_failed(monkeypatch):
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    assert mailer.send_status({"sent": False, "detail": "x"}) == "failed"


# ---- storage.log_email_send / recent_email_sends / purge (Phase 6) ---------

def test_log_email_send_and_recent_email_sends(db_path):
    conn = st.connect(db_path)
    try:
        _reset_log(conn)
        st.log_email_send(conn, "event_created", "a@test.local", "Subj", "sent")
        st.log_email_send(conn, "wellness_approval", "b@test.local", "Subj2", "skipped_off")
        rows = st.recent_email_sends(conn, limit=10)
        assert len(rows) == 2
        assert rows[0]["feature"] == "wellness_approval"      # newest first
        assert rows[0]["status"] == "skipped_off"
        assert rows[1]["status"] == "sent"
    finally:
        _reset_log(conn)
        conn.close()


def test_recent_email_sends_respects_limit(db_path):
    conn = st.connect(db_path)
    try:
        _reset_log(conn)
        for i in range(5):
            st.log_email_send(conn, "event_created", f"a{i}@test.local", "S", "sent")
        assert len(st.recent_email_sends(conn, limit=3)) == 3
    finally:
        _reset_log(conn)
        conn.close()


def test_purge_stale_email_log_removes_old_keeps_new(db_path):
    conn = st.connect(db_path)
    try:
        _reset_log(conn)
        old_ts = (tz.now_local() - timedelta(days=200)).isoformat()
        conn.execute(
            "INSERT INTO email_log(created_at, feature, recipient, subject, status) "
            "VALUES (?,?,?,?,?)", (old_ts, "event_created", "old@test.local", "Old", "sent"))
        conn.commit()
        st.log_email_send(conn, "event_created", "new@test.local", "New", "sent")
        cutoff = (tz.now_local() - timedelta(days=90)).isoformat()
        n = st.purge_stale_email_log(conn, cutoff)
        assert n == 1
        remaining = {r["recipient"] for r in st.recent_email_sends(conn, limit=10)}
        assert remaining == {"new@test.local"}
    finally:
        _reset_log(conn)
        conn.close()


def test_retention_purge_stale_email_log_dry_run_changes_nothing(db_path):
    conn = st.connect(db_path)
    try:
        _reset_log(conn)
        old_ts = (tz.now_local() - timedelta(days=200)).isoformat()
        conn.execute(
            "INSERT INTO email_log(created_at, feature, recipient, subject, status) "
            "VALUES (?,?,?,?,?)", (old_ts, "event_created", "old@test.local", "Old", "sent"))
        conn.commit()
        n = retention.purge_stale_email_log(db_path=db_path, days=90, dry_run=True)
        assert n == 1
        assert len(st.recent_email_sends(conn, limit=10)) == 1   # untouched
    finally:
        _reset_log(conn)
        conn.close()


# ---- global pause ----------------------------------------------------------

def test_pause_holds_every_feature_but_not_account_mail(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_email_paused(conn, True)
        for key in list(mailer.FEATURES) + ["not_a_real_feature"]:
            assert st.email_feature_enabled(conn, key) is False, key
        for key in mailer.ALWAYS_ON:
            assert st.email_feature_enabled(conn, key) is True, key
        st.set_email_paused(conn, False)
        assert st.email_feature_enabled(conn, "event_created") is True
    finally:
        conn.execute("DELETE FROM app_setting WHERE key='email_paused'"); conn.commit()
        conn.close()


def test_always_on_constant_matches_mailer_catalog():
    assert set(st.EMAIL_ACCOUNT_KEYS) == set(mailer.ALWAYS_ON)


def test_admin_email_pause_route_audits_and_toggles(admin, db_path):
    conn = st.connect(db_path)
    try:
        r = admin.post("/admin/email/pause", data={"paused": "1"}, follow_redirects=False)
        assert r.status_code == 303 and "msg=" in r.headers["location"]
        assert st.email_paused(conn) is True
        assert "PAUSED" in admin.get("/admin/email").text
        admin.post("/admin/email/pause", data={"paused": "0"}, follow_redirects=False)
        assert st.email_paused(conn) is False
    finally:
        conn.execute("DELETE FROM app_setting WHERE key='email_paused'"); conn.commit()
        conn.close()


def test_admin_email_pause_requires_manage_users(viewer):
    assert viewer.post("/admin/email/pause", data={"paused": "1"}).status_code == 403


def test_paused_room_and_calendar_queues_wait(db_path):
    import rooms_notify, office_calendar
    conn = st.connect(db_path); st.init_db(conn)
    try:
        st.set_email_paused(conn, True)
        sent = []
        assert rooms_notify.flush(conn, "https://x.example", send=lambda *a, **k: sent.append(a)) == {}
        assert office_calendar.flush_outbox(conn, "https://x.example", send=lambda *a, **k: sent.append(a)) == 0
        assert sent == []
    finally:
        conn.execute("DELETE FROM app_setting WHERE key='email_paused'"); conn.commit()
        conn.close()


# ---- room meal alerts split + attachment options ---------------------------

def test_room_meal_alerts_has_own_switch_and_preview():
    import rooms_notify
    assert "room_meal_alerts" in mailer.FEATURES
    assert {rooms_notify.FEATURE[k] for k in rooms_notify.MEAL_KINDS} == {"room_meal_alerts"}
    assert mailer.sample_message("room_meal_alerts")[0]


def test_room_meal_alerts_follow_the_old_switch_until_set(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_email_feature(conn, "room_admin_alerts", False)
        assert st.email_feature_enabled(conn, "room_meal_alerts") is False   # was off before the split
        st.set_email_feature(conn, "room_meal_alerts", True)
        assert st.email_feature_enabled(conn, "room_meal_alerts") is True
        st.set_email_feature(conn, "room_admin_alerts", True)
        st.set_email_feature(conn, "room_meal_alerts", False)
        assert st.email_feature_enabled(conn, "room_admin_alerts") is True
    finally:
        _reset(conn); conn.close()


def test_email_option_defaults_on_and_route_toggles(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    try:
        assert st.email_option_enabled(conn, "calendar_ics") is True
        r = admin.post("/admin/email/option", data={"key": "calendar_ics", "on": "0"}, follow_redirects=False)
        assert r.status_code == 303 and "msg=" in r.headers["location"]
        assert st.email_option_enabled(conn, "calendar_ics") is False
        bad = admin.post("/admin/email/option", data={"key": "nope", "on": "0"}, follow_redirects=False)
        assert "err=" in bad.headers["location"]
    finally:
        conn.execute("DELETE FROM app_setting WHERE key LIKE 'email_option.%'"); conn.commit(); conn.close()


def test_email_option_requires_manage_users(viewer):
    assert viewer.post("/admin/email/option", data={"key": "calendar_ics", "on": "0"}).status_code == 403
