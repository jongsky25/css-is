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


# ---- replenishment, release and stock-ready messages ---------------------------------------------------

from tests.test_supplies_replenishment_flow import flow_db, prepared, approve
import supplies_replenishment_flow as flow
from tests.test_supplies_backorders import ready, receipt
from tests.test_supplies_issues import issue


def test_replenishment_submit_goes_to_other_approvers_and_decision_to_preparer(flow_db, outbox):
    c, u, _, _, item = flow_db
    sent, send = outbox
    rid = prepared(c, u, item)
    flow.submit_replenishment(c, u[1], rid, expected_revision=1, operation_key=key())
    assert states(c) == [('supplies_replenishment_pending', u[4]['id'], 'queued')]
    assert deliver(c, send) == 1
    assert sent[0]['to'] == 'supply4@example.test' and 'REP-2026-00001' in sent[0]['subject']
    assert f'{BASE}/supplies/replenishments/{rid}' in sent[0]['body']
    sent.clear()
    approve(c, u, rid)
    assert deliver(c, send) == 1
    assert sent[0]['to'] == 'supply1@example.test' and 'approved' in sent[0]['subject']


def test_replenishment_pending_is_cancelled_once_decided_before_sending(flow_db, outbox):
    c, u, _, _, item = flow_db
    sent, send = outbox
    rid = prepared(c, u, item)
    flow.submit_replenishment(c, u[1], rid, expected_revision=1, operation_key=key())
    approve(c, u, rid)
    deliver(c, send)
    assert [m['to'] for m in sent] == ['supply1@example.test']
    assert ('supplies_replenishment_pending', u[4]['id'], 'cancelled') in states(c)


def test_issue_asks_recipient_to_confirm_and_skips_when_already_acknowledged(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    r = ready(c, u, item, 3)
    deliver(c, send); sent.clear()
    issue(c, u, r, 1)
    issue(c, u, r, 1)
    assert [x[0] for x in states(c)].count('supplies_issue_recorded') == 2
    first, second = [x[0] for x in c.execute("SELECT ref_key FROM supply_mail WHERE kind='supplies_issue_recorded' ORDER BY id")]
    import supplies_acknowledgments as ack
    import supplies_issues as issues
    first_id = int(first.split(':')[1])
    ack.acknowledge_issue(c, u[2], first_id, {'status': 'acknowledged', 'note': ''},
                          expected_revision=issues.get_issue(c, u[1], first_id)['acknowledgment']['revision'], operation_key=key())
    assert deliver(c, send) == 1
    assert len(sent) == 1 and sent[0]['to'] == 'supply2@example.test' and 'ISS-2026-00002' in sent[0]['subject']


def test_issue_to_the_custodian_themselves_sends_nothing(approval_db, outbox):
    c, u, units, _, item = approval_db
    r = ready(c, u, item, 3)
    from tests.test_supplies_issues import data
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?', (st.add_rp(c, 'Synthetic custodian', True, units[1]), u[1]['id'])); c.commit()
    issue(c, u, r, 1, fields=data(c, u, r, 1, recipient_id=u[1]['id'], alternate_reason='Custodian collects'))
    assert not [x for x in states(c) if x[0] == 'supplies_issue_recorded']


@pytest.mark.usefixtures('unlimited_requests')
def test_delivery_that_fills_a_shortage_emails_only_the_requester_who_gained_stock(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    a = ready(c, u, item, 8); b = ready(c, u, item, 7)
    # Approval emails already say stock was set aside; the same operation adds no second message.
    assert [x[0] for x in states(c)].count('supplies_stock_ready') == 0
    deliver(c, send); sent.clear()
    receipt(c, u, item, 4)
    ready_rows = c.execute("SELECT ref_key FROM supply_mail WHERE kind='supplies_stock_ready'").fetchall()
    assert len(ready_rows) == 1 and ready_rows[0][0].startswith(f'request:{b}:')
    assert deliver(c, send) == 1
    assert 'Supplies ready' in sent[0]['subject'] and '6 of 7' in sent[0]['body']


@pytest.mark.usefixtures('unlimited_requests')
def test_stock_ready_waits_for_nothing_when_request_was_cancelled(approval_db, outbox):
    c, u, _, _, item = approval_db
    sent, send = outbox
    a = ready(c, u, item, 8); b = ready(c, u, item, 7)
    deliver(c, send); sent.clear()
    receipt(c, u, item, 4)
    from tests.test_supplies_backorders import cancel
    cancel(c, u, b)
    deliver(c, send)
    assert not sent


def test_new_previews_render():
    for key_ in ('supplies_replenishment_pending', 'supplies_replenishment_decided',
                 'supplies_issue_recorded', 'supplies_stock_ready'):
        subject, body, html = mailer.sample_message(key_)
        assert subject and body and html


# ---- weekly custodian digest ---------------------------------------------------------------------------

import send_reminders
import tzutil as tz
from datetime import date


def monday(monkeypatch, on=True):
    monkeypatch.setattr(tz, 'today_local', lambda: date(2026, 10, 26) if on else date(2026, 10, 27))


@pytest.fixture
def digest_sent(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, 'email_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send', lambda to, subject, body, html=None, attachments=None:
                        sent.append({'to': to, 'subject': subject, 'body': body, 'html': html}) or {'sent': True, 'detail': ''})
    return sent


@pytest.mark.usefixtures('unlimited_requests')
def test_digest_lists_warnings_and_requests_to_hand_over_for_each_custodian(approval_db, digest_sent, monkeypatch):
    c, u, _, _, item = approval_db
    monday(monkeypatch)
    ready(c, u, item, 10)                       # takes every unit: fully reserved warning + one request to hand over
    ready(c, u, item, 4)                        # waits for stock
    assert send_reminders.send_supplies_digest(c, BASE) == 1
    assert [m['to'] for m in digest_sent] == ['supply1@example.test']
    body = digest_sent[0]['body']
    assert 'week of October 26' in digest_sent[0]['subject']
    assert '1 approved request(s) ready to hand over' in body and '1 approved request(s) waiting for stock' in body
    assert 'fully reserved' in body and f'{BASE}/supplies/warnings' in body
    assert send_reminders.send_supplies_digest(c, BASE) == 0       # same week, same email: not repeated


def test_digest_only_on_its_weekday_and_never_when_nothing_to_chase(approval_db, digest_sent, monkeypatch):
    c, u, _, _, item = approval_db
    ready(c, u, item, 10)
    monday(monkeypatch, on=False)
    assert send_reminders.send_supplies_digest(c, BASE) == 0
    monday(monkeypatch)
    st.set_setting(c, 'email_param.supplies_digest_weekday', '1'); c.commit()
    assert send_reminders.send_supplies_digest(c, BASE) == 0
    st.set_setting(c, 'email_param.supplies_digest_weekday', '0'); c.commit()
    c.execute("UPDATE supply_alert_episode SET resolved_at='2026-10-20'")
    c.execute("UPDATE supply_reservation SET reserved_quantity=0, cancelled_quantity=(SELECT approved_quantity FROM supply_request_decision_line d WHERE d.revision_line_id=supply_reservation.revision_line_id)")
    c.commit()
    assert send_reminders.send_supplies_digest(c, BASE) == 0 and not digest_sent


def test_digest_job_switch_and_revoked_custodians(approval_db, digest_sent, monkeypatch):
    c, u, _, path, item = approval_db
    monday(monkeypatch)
    monkeypatch.setenv('CSS_BASE_URL', BASE)
    ready(c, u, item, 10)
    st.set_email_feature(c, 'job_supplies_digest', False); c.commit()
    assert 'supplies_digest' not in send_reminders.run(path, jobs={'supplies_digest'}) and not digest_sent
    st.set_email_feature(c, 'job_supplies_digest', True); c.commit()
    assert send_reminders.run(path, jobs={'supplies_digest'}) == {'supplies_digest': 1}
    digest_sent.clear()
    c.execute("DELETE FROM email_log"); c.commit()
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-20',revoked_by=? WHERE user_id=? AND role='custodian'", (u[0]['id'], u[1]['id']))
    c.commit()
    assert send_reminders.send_supplies_digest(c, BASE) == 0 and not digest_sent


def test_digest_is_off_with_the_module_and_preview_renders(approval_db, digest_sent, monkeypatch):
    c, u, _, _, item = approval_db
    monday(monkeypatch)
    ready(c, u, item, 10)
    c.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'"); c.commit()
    assert send_reminders.send_supplies_digest(c, BASE) == 0
    subject, body, html = mailer.sample_message('job_supplies_digest')
    assert 'Supplies summary' in subject and 'Open Supplies' in html
