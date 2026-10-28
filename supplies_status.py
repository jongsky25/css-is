"""Plain-language request stage for the requester views (pure; reads only the queue entry)."""

STEPS = ('Sent', 'Approved', 'Ready for pickup', 'Received')


def _stage(step, label, tone, sentence, action=''):
    return {'step': step, 'label': label, 'tone': tone, 'sentence': sentence, 'action': action}


def _names(entry):
    names = list(entry.get('approver_names') or ())
    if not names:
        return ''
    return ', '.join(names[:5]) + (' and others' if len(names) > 5 else '')


def requester_stage(entry):
    """Map a `requests` queue entry to {step, label, tone, sentence, action}.

    step is 0 before sending, else 1-4 along STEPS. Needs approval_status,
    reserved_quantity, outstanding_quantity, issue_count, ack_pending, ack_disputed
    and optionally approver_names (all provided by supplies_dashboard.queue).
    """
    state = entry['approval_status']
    if state == 'draft':
        return _stage(0, 'Not sent yet', 'neutral', 'Review your request and send it.', 'Review and send')
    if state == 'returned':
        return _stage(1, 'Needs your changes', 'warn', 'Your request was sent back. Fix it and send it again.', 'Fix and resend')
    if state == 'rejected':
        return _stage(1, 'Not approved', 'bad', 'Your request was not approved. See the reason.')
    if state == 'cancelled':
        return _stage(0, 'Withdrawn', 'muted', 'You withdrew this request.')
    if state == 'submitted':
        who = _names(entry)
        sentence = ('Waiting for ' + who + ' to approve.') if who else 'Waiting for an approver. None is assigned yet, so please tell your administrator.'
        return _stage(1, 'Sent', 'info', sentence)
    outstanding = entry.get('outstanding_quantity', 0) > 0
    more = ' More items are still on the way.' if outstanding else ''
    if entry.get('ack_disputed', 0) > 0:
        return _stage(3, 'Problem reported', 'bad', 'You reported a problem. The supply office will follow up.' + more)
    if entry.get('ack_pending', 0) > 0:
        return _stage(3, 'Please confirm receipt', 'warn', 'Supplies were handed over to you. Please confirm you received them.' + more, 'Confirm receipt')
    if outstanding:
        if entry.get('reserved_quantity', 0) > 0:
            return _stage(3, 'Ready for pickup', 'good', 'Your supplies are set aside. The supply office will hand them over.')
        return _stage(2, 'Waiting for stock', 'warn', 'Approved. The supply office is waiting for new stock to arrive.')
    if entry.get('issue_count', 0) > 0:
        return _stage(4, 'Received', 'good', 'You confirmed you received your supplies.')
    return _stage(2, 'Approved', 'good', 'Approved. Nothing is left to hand over.')
