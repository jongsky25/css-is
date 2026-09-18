"""
Admin email control center (docs/ADMIN_EMAIL_FEATURES_PLAN.md), Phase 1:
the per-feature on/off setting and the mailer.py catalog it reads against.
Nothing calls the gate yet (Phase 2) — this only covers the building block.
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
