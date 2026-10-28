"""Supplies email: durable outbox, current-authority recheck, admin switches and at-most-once delivery."""
import pytest

import mailer
import storage as st
import supplies_mail as mail
import supplies_requests as requests
from tests.test_supplies import supplies_db, key
from tests.test_supplies_requests import request_db, draft, submit, get
from tests.test_supplies_approvals import approval_db, decide

BASE = 'https://oc.example.test'


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, 'email_configured', lambda: True)

    def send(to, subject, body, html=None, attachments=None):
        sent.append({'to': to, 'subject': subject, 'body': body, 'html': html})
        return {'sent': True, 'detail': 'Email sent.'}
    return sent, send


def deliver(c, send, **kw):
    return mail.run(c, BASE, send=send, **kw)


def states(c):
    return [tuple(r) for r in c.execute('SELECT kind,recipient_id,state FROM supply_mail ORDER BY id')]


def log(c):
    return [tuple(r) for r in c.execute('SELECT feature,recipient,status FROM email_log ORDER BY id')]


def test_submit_queues_only_for_eligible_approvers_and_sends_once(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = draft(c, u, item); submit(c, u, r)
    assert states(c) == [('supplies_request_pending', u[3]['id'], 'queued'), ('supplies_request_pending', u[4]['id'], 'queued')]
    assert deliver(c, send) == 2
    assert sorted(m['to'] for m in sent) == ['supply3@example.test', 'supply4@example.test']
    assert 'SUP-2026-00001' in sent[0]['subject'] and f'{BASE}/supplies/requests/{r}' in sent[0]['body']
    assert deliver(c, send) == 0 and len(sent) == 2
    assert {x[2] for x in states(c)} == {'sent'}
    assert [x[2] for x in log(c)] == ['sent', 'sent']


def test_replayed_submission_does_not_queue_twice(approval_db):
    c, u, _, _, item = approval_db
    r = draft(c, u, item); op = key(); submit(c, u, r, operation_key=op)
    submit(c, u, r, expected_revision=1, operation_key=op)
    assert len(states(c)) == 2


def test_decision_emails_requester_with_reason_and_resubmission_emails_again(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = draft(c, u, item); submit(c, u, r); deliver(c, send); sent.clear()
    decide(c, u, r, fields={'decision': 'returned', 'reason': 'Lower the quantity.', 'lines': []})
    assert deliver(c, send) == 1
    assert sent[0]['to'] == 'supply2@example.test' and 'returned for correction' in sent[0]['subject']
    assert 'Lower the quantity.' in sent[0]['body'] and 'Lower the quantity.' in sent[0]['html']
    sent.clear()
    submit(c, u, r)
    assert deliver(c, send) == 2 and all('SUP-2026-00001' in m['subject'] for m in sent)


def test_feature_switch_and_pause_log_skipped_and_never_send(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    st.set_email_feature(c, 'supplies_request_pending', False); c.commit()
    r = draft(c, u, item); submit(c, u, r)
    deliver(c, send)
    assert not sent and {x[2] for x in states(c)} == {'skipped_off'}
    assert {x[2] for x in log(c)} == {'skipped_off'}


def test_global_pause_skips(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    st.set_email_paused(c, True); c.commit()
    r = draft(c, u, item); submit(c, u, r)
    deliver(c, send)
    assert not sent and {x[2] for x in states(c)} == {'skipped_off'}


def test_unconfigured_mailer_is_logged_terminal(approval_db, monkeypatch):
    c, u, _, _, item = approval_db
    monkeypatch.setattr(mailer, 'email_configured', lambda: False)
    r = draft(c, u, item); submit(c, u, r)
    assert deliver(c, lambda *a, **k: pytest.fail('must not send')) == 0
    assert {x[2] for x in states(c)} == {'not_configured'} and {x[2] for x in log(c)} == {'not_configured'}


def test_missing_base_url_or_disabled_module_waits(approval_db, outbox, monkeypatch):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = draft(c, u, item); submit(c, u, r)
    assert mail.run(c, '', send=send) == 0
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'"); c.commit()
    assert deliver(c, send) == 0 and not sent
    assert {x[2] for x in states(c)} == {'queued'}


def test_revoked_approver_inactive_user_and_changed_request_are_cancelled(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = draft(c, u, item); submit(c, u, r)
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='request_approver'",
              (u[0]['id'], u[3]['id']))
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (u[4]['id'],)); c.commit()
    assert deliver(c, send) == 0 and not sent
    assert {x[2] for x in states(c)} == {'cancelled'}
    r2 = draft(c, u, item); submit(c, u, r2)
    requests.withdraw(c, u[2], r2, reason='No longer needed', expected_revision=get(c, u, r2)['revision'], operation_key=key())
    assert deliver(c, send) == 0 and not sent


def test_definite_failure_is_retried_up_to_the_limit_then_fails(approval_db, monkeypatch):
    c, u, _, _, item = approval_db
    monkeypatch.setattr(mailer, 'email_configured', lambda: True)
    c.execute("DELETE FROM supply_role_grant WHERE user_id=? AND role='request_approver'", (u[4]['id'],)); c.commit()
    r = draft(c, u, item); submit(c, u, r)
    calls = []
    def failing(to, subject, body, html=None, attachments=None):
        calls.append(to); return {'sent': False, 'detail': 'relay down'}
    st.set_setting(c, 'email_param.send_retry_attempts', '2'); c.commit()
    deliver(c, failing); assert states(c)[0][2] == 'queued'
    deliver(c, failing); assert states(c)[0][2] == 'failed'
    deliver(c, failing); assert len(calls) == 2
    assert [x[2] for x in log(c)] == ['failed']


def test_exception_during_send_is_uncertain_and_never_resent(approval_db, monkeypatch):
    c, u, _, _, item = approval_db
    monkeypatch.setattr(mailer, 'email_configured', lambda: True)
    r = draft(c, u, item); submit(c, u, r)
    def boom(*a, **k): raise OSError('connection dropped')
    deliver(c, boom)
    assert {x[2] for x in states(c)} == {'uncertain'}
    deliver(c, lambda *a, **k: pytest.fail('must not resend'))


def test_stale_attempting_rows_become_uncertain_and_old_queue_cancels(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = draft(c, u, item); submit(c, u, r)
    c.execute("UPDATE supply_mail SET created_at=created_at-?", (mail.STALE_SECONDS + 5,)); c.commit()
    assert deliver(c, send) == 0 and not sent
    assert {x[2] for x in states(c)} == {'cancelled'}


def test_mail_failure_cannot_undo_the_business_operation(approval_db, outbox, monkeypatch):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = draft(c, u, item); submit(c, u, r)
    def broken(*a, **k): raise RuntimeError('composer bug')
    monkeypatch.setitem(mail.KINDS, 'supplies_request_pending', broken)
    assert deliver(c, send) == 0
    assert get(c, u, r)['approval_status'] == 'submitted'


def test_previews_render_for_every_supplies_message():
    for key_ in ('supplies_request_pending', 'supplies_request_decided'):
        subject, body, html = mailer.sample_message(key_)
        assert subject and body and html and 'Office Connect' in html
