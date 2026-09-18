"""
Admin email control center (docs/ADMIN_EMAIL_FEATURES_PLAN.md).
Phase 1: the per-feature on/off setting and the mailer.py catalog it reads
against. Phase 4: the /admin/email console built on top of it.
"""
import mailer
import storage as st


def _reset(conn):
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'email_feature.%'")
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
