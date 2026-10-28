"""Increment 1.2: plain-language request stage for requesters."""
import pytest

import supplies_dashboard as dashboard
import supplies_requests as requests
from supplies_status import STEPS, requester_stage
from tests.test_supplies import supplies_db, key
from tests.test_supplies_requests import request_db, draft, submit, withdraw
from tests.test_supplies_approvals import approval_db, decide
from tests.test_supplies_backorders import ready
from tests.test_supplies_acknowledgments import released, respond
import supplies_issues as issues


def entry(state, **extra):
    base = {'approval_status': state, 'reserved_quantity': 0, 'outstanding_quantity': 0,
            'issue_count': 0, 'ack_pending': 0, 'ack_disputed': 0, 'approver_names': []}
    return {**base, **extra}


@pytest.mark.parametrize('data,step,label,tone,action', [
    (entry('draft'), 0, 'Not sent yet', 'neutral', 'Review and send'),
    (entry('returned'), 1, 'Needs your changes', 'warn', 'Fix and resend'),
    (entry('rejected'), 1, 'Not approved', 'bad', ''),
    (entry('cancelled'), 0, 'Withdrawn', 'muted', ''),
    (entry('submitted'), 1, 'Sent', 'info', ''),
    (entry('approved', outstanding_quantity=3), 2, 'Waiting for stock', 'warn', ''),
    (entry('approved', outstanding_quantity=3, reserved_quantity=3), 3, 'Ready for pickup', 'good', ''),
    (entry('approved', issue_count=1, ack_pending=1), 3, 'Please confirm receipt', 'warn', 'Confirm receipt'),
    (entry('approved', issue_count=1, ack_disputed=1), 3, 'Problem reported', 'bad', ''),
    (entry('approved', issue_count=2), 4, 'Received', 'good', ''),
    (entry('approved'), 2, 'Approved', 'good', ''),
])
def test_every_state(data, step, label, tone, action):
    stage = requester_stage(data)
    assert (stage['step'], stage['label'], stage['tone'], stage['action']) == (step, label, tone, action)
    assert stage['sentence'] and 0 <= stage['step'] <= len(STEPS)


def test_sentences_name_the_next_person_and_cover_partial_releases():
    named = requester_stage(entry('submitted', approver_names=['Maria Santos', 'Jose Reyes']))
    assert named['sentence'] == 'Waiting for Maria Santos, Jose Reyes to approve.'
    many = requester_stage(entry('submitted', approver_names=[f'P{i}' for i in range(6)]))
    assert 'and others' in many['sentence']
    assert 'administrator' in requester_stage(entry('submitted'))['sentence']
    partial = requester_stage(entry('approved', issue_count=1, ack_pending=1, outstanding_quantity=2))
    assert partial['label'] == 'Please confirm receipt' and 'still on the way' in partial['sentence']
    jargon = ('reserved', 'outstanding', 'revision', 'snapshot', 'issuance')
    for data in (entry('draft'), entry('approved', outstanding_quantity=1, reserved_quantity=1), entry('approved', ack_pending=1)):
        assert not any(w in requester_stage(data)['sentence'].lower() for w in jargon)


def stage_of(c, user, request_id):
    found = dashboard.queue(c, user, 'requests', limit=25)['requests']
    return next(e for e in found if e['id'] == request_id)['stage']


def test_queue_attaches_stage_for_draft_submitted_and_withdrawn(request_db):
    c, u, _, _, item = request_db
    r = draft(c, u, item)
    assert stage_of(c, u[2], r)['label'] == 'Not sent yet'
    submit(c, u, r)
    assert stage_of(c, u[2], r)['label'] == 'Sent'
    withdraw(c, u, r)
    assert stage_of(c, u[2], r)['label'] == 'Withdrawn'


def test_queue_stage_through_approval_release_and_receipt(released):
    c, u, _, _, _, r, first, second = released
    assert stage_of(c, u[2], r)['label'] == 'Please confirm receipt'
    respond(c, u, first)
    assert stage_of(c, u[2], r)['label'] == 'Please confirm receipt'
    respond(c, u, second, status='disputed', note='Short by one box')
    assert stage_of(c, u[2], r)['label'] == 'Problem reported'


def test_queue_stage_ready_and_received(approval_db):
    c, u, _, _, item = approval_db
    r = ready(c, u, item, 6)
    assert stage_of(c, u[2], r)['label'] == 'Ready for pickup'


def test_queue_stage_received_after_every_release_is_confirmed(released):
    c, u, _, _, _, r, first, second = released
    respond(c, u, first)
    respond(c, u, second)
    stage = stage_of(c, u[2], r)
    assert (stage['label'], stage['step']) == ('Received', 4)


def test_queue_submitted_sentence_names_the_approver(approval_db):
    c, u, _, _, item = approval_db
    r = draft(c, u, item)
    submit(c, u, r)
    found = next(e for e in dashboard.queue(c, u[2], 'requests')['requests'] if e['id'] == r)
    assert found['approver_names'] and found['stage']['sentence'] == 'Waiting for ' + ', '.join(found['approver_names']) + ' to approve.'
