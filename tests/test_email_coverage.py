"""Guards that keep every email the system sends under the admin email console
(docs/ADMIN_EMAIL_FEATURES_PLAN.md): a new send path or catalog entry that skips
the switches, the pause or the send log fails here instead of shipping."""
import ast
import glob
import os
import re

import mailer
import storage as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = [f for f in sorted(glob.glob(os.path.join(ROOT, "*.py")))]

# Every function allowed to call mailer.send() directly. The gateable ones check
# st.email_feature_enabled themselves (or are only reached through a gated caller);
# the rest are account/recovery mail, which is never switchable.
DIRECT_SEND_ALLOWED = {
    ("room_approval_delivery.py", "_transport"),  # gated, single-attempt requester approval notice

    ("activity_creation_delivery.py", "_transport"),  # gated, durably claimed/logged creation notices
    ("work_arrangement_delivery.py", "_transport"),  # gated, durably claimed/logged MCP filing notices
    ("app.py", "_notify_account"), ("app.py", "_notify_email"), ("app.py", "_send_and_log"),
    ("app.py", "_provision_account"), ("app.py", "forgot_submit"), ("app.py", "admin_users_reset_default"),
    ("app.py", "monitor_resend_link"), ("app.py", "admin_email_test"),
    ("send_reminders.py", "_send"),
    ("room_request_delivery.py", "_transport"),  # gated, claimed MCP room-notice worker
    ("travel_decision_delivery.py", "_transport"),  # current-policy, single-attempt travel reviewer result
    ("travel_review_delivery.py", "_transport"),  # claimed worker gates feature/pause and logs each outcome
}


def _direct_sends():
    found = set()
    for path in SOURCES:
        tree = ast.parse(open(path, encoding="utf-8").read())

        class V(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, n):
                self.stack.append(n.name); self.generic_visit(n); self.stack.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                if (isinstance(f, ast.Attribute) and f.attr == "send"
                        and isinstance(f.value, ast.Name) and f.value.id == "mailer"):
                    found.add((os.path.basename(path), self.stack[-1] if self.stack else "<module>"))
                self.generic_visit(n)
        V().visit(tree)
    return found


def test_no_new_unreviewed_direct_mailer_send():
    new = _direct_sends() - DIRECT_SEND_ALLOWED
    assert not new, (f"{sorted(new)} call mailer.send() directly. Send through _notify_email/_notify_account/"
                     "_mail_after_response/send_reminders._send (which log and honour the switches and the "
                     "pause), or add the function to DIRECT_SEND_ALLOWED after deciding whether it is account mail.")


def _non_catalog_source():
    # ai_core.py has its own feature switchboard (the AI console), unrelated to email
    return "\n".join(open(p, encoding="utf-8").read() for p in SOURCES
                     if os.path.basename(p) not in ("mailer.py", "ai_core.py"))


def test_every_feature_literal_in_code_is_in_the_catalog():
    src = _non_catalog_source()
    used = set(re.findall(r'feature="(\w+)"', src))
    used |= set(re.findall(r'email_feature_enabled\(\s*\w+,\s*["\'](\w+)["\']', src))
    used |= set(re.findall(r'_send\(\s*\w+,\s*["\'](\w+)["\']', src))
    for line in re.findall(r'JOB_FEATURE = \{(.*?)\n\}', src, re.S):
        used |= set(re.findall(r'": "(job_\w+)"', line))
    used -= {"assistant_action", "nl_answer", "nl_help", "travel_scan", "nl_answer_grounded"}   # AI call sites in app.py
    unknown = {k for k in used if k not in mailer.FEATURES and k not in mailer.ALWAYS_ON
               and k not in mailer.EXTERNAL}
    assert not unknown, f"features used in code but missing from mailer.FEATURES: {sorted(unknown)}"


def test_every_catalog_feature_is_actually_used_in_code():
    src = _non_catalog_source()
    unused = [k for k in mailer.FEATURES if f'"{k}"' not in src and f"'{k}'" not in src]
    assert not unused, f"in mailer.FEATURES but nothing sends or checks them: {unused}"


def test_every_composer_is_previewable_or_used():
    """A *_message composer nobody calls and no catalog entry previews is dead or unmanaged."""
    src = _non_catalog_source()
    composers = re.findall(r"^def (\w+_message)\(", open(os.path.join(ROOT, "mailer.py"), encoding="utf-8").read(), re.M)
    orphans = [c for c in composers if f"mailer.{c}" not in src and f"{c}(" not in
               open(os.path.join(ROOT, "mailer.py"), encoding="utf-8").read().split("_PREVIEWS = {")[1]]
    assert not orphans, f"composers with no caller and no preview: {orphans}"


# ---- the funnels honour switch and pause, and log what they skip ------------

def test_funnels_skip_and_log_when_off_or_paused(app_mod, db_path, monkeypatch):
    sent = []
    monkeypatch.setattr(app_mod.mailer, "send", lambda *a, **k: sent.append(a) or {"sent": True, "detail": "ok"})
    conn = st.connect(db_path)
    try:
        conn.execute("DELETE FROM email_log"); conn.commit()
        app_mod._notify_email(conn, "a@x.test", "S", "B", feature="event_created")
        assert len(sent) == 1
        st.set_email_feature(conn, "event_created", False)
        app_mod._notify_email(conn, "a@x.test", "S", "B", feature="event_created")
        st.set_email_feature(conn, "event_created", True)
        st.set_email_paused(conn, True)
        app_mod._notify_email(conn, "b@x.test", "S", "B", feature="event_created")
        assert len(sent) == 1
        statuses = [r["status"] for r in st.recent_email_sends(conn, 5)]
        assert statuses.count("skipped_off") == 2
        assert app_mod._mail_after_response(conn, "c@x.test", "S", "B", feature="event_created") is None
    finally:
        conn.execute("DELETE FROM app_setting WHERE key IN ('email_paused','email_feature.event_created')")
        conn.commit(); conn.close()


def test_scheduled_jobs_do_not_run_while_paused(db_path, monkeypatch):
    import send_reminders
    ran = []
    monkeypatch.setattr(send_reminders, "remind_tomorrows_events", lambda *a, **k: ran.append(1) or 0)
    monkeypatch.setenv("CSS_BASE_URL", "https://x.example")
    conn = st.connect(db_path); st.init_db(conn)
    try:
        st.set_email_paused(conn, True)
        report = send_reminders.run(db_path, jobs={"events"})
        assert ran == [] and "events" not in report
    finally:
        conn.execute("DELETE FROM app_setting WHERE key='email_paused'"); conn.commit(); conn.close()
