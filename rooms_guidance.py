"""Read-only room reservation guidance; action services remain authoritative.

Callers first establish ownership. Related records must belong to that same
requester; public tracking pages never receive newly minted tracking links.
"""
from datetime import date

import tzutil as tz


def _same_requester(res, other):
    uid = res.get('requester_user_id')
    if uid is not None:
        return other.get('requester_user_id') == uid
    return (other.get('requester_user_id') is None and
            all(other.get(k) == res.get(k) for k in ('ext_name', 'ext_org', 'ext_email', 'ext_phone')))


def guest_relations(conn, res):
    """Only immediate same-contact relatives of a validated guest tracking record."""
    keys = ('id', 'ref_code', 'day', 'status', 'source', 'moves_reservation_id')
    rows = conn.execute(
        'SELECT id,ref_code,day,status,source,moves_reservation_id FROM room_reservation '
        'WHERE requester_user_id IS NULL AND ext_name IS ? AND ext_org IS ? '
        'AND ext_email IS ? AND ext_phone IS ? AND (id=? OR moves_reservation_id=?)',
        tuple(res.get(k) for k in ('ext_name', 'ext_org', 'ext_email', 'ext_phone')) +
        (res.get('moves_reservation_id'), res['id'])).fetchall()
    contact = {k: res.get(k) for k in ('requester_user_id', 'ext_name', 'ext_org', 'ext_email', 'ext_phone')}
    return [{**dict(zip(keys, row)), **contact} for row in rows]


def relationship_index(records):
    by_id, children = {}, {}
    for record in records:
        by_id[record['id']] = record
        children.setdefault(record.get('moves_reservation_id'), []).append(record)
    return by_id, children


def reservation(res, *, peers=(), relationships=None, offers=(), today=None):
    """Explain persisted state without changing it, checking email, or holding slots."""
    today = today or tz.today_local()
    status = res.get('status')
    by_id, by_parent = relationships if relationships is not None else relationship_index(peers)
    candidates = list(by_parent.get(res['id'], ()))
    if res.get('moves_reservation_id') in by_id:
        candidates.append(by_id[res['moves_reservation_id']])
    owned = [p for p in candidates if p['id'] != res['id'] and _same_requester(res, p)]
    parent = next((p for p in owned if p['id'] == res.get('moves_reservation_id')), None)
    children = [p for p in owned if p.get('moves_reservation_id') == res['id']
                and p['status'] in ('requested', 'approved')]
    replacement = max(children, key=lambda p: (p['status'] == 'approved', p['id']), default=None)
    try:
        past = date.fromisoformat(res['day']) < today
    except (ValueError, TypeError, KeyError):
        past = True

    def result(state, title, holding, actor, step, related=None):
        return {'state': state, 'title': title, 'holding': holding, 'actor': actor, 'step': step,
                'related': ({'label': related['ref_code'],
                             'href': '#room-' + str(related['id']) if res.get('requester_user_id') is not None else None}
                            if related else None)}

    if replacement and status in ('declined', 'cancelled', 'withdrawn'):
        return result('replaced', 'A newer reservation replaces this one',
                      'These original hours are not reserved by this record.',
                      'Administrative Section' if replacement['status'] == 'requested' else 'You',
                      'Check the newer reservation: ' + ('it is waiting for approval.' if replacement['status'] == 'requested'
                                                        else 'it is approved for its own listed hours.'), replacement)
    if past and status not in ('expired', 'withdrawn'):
        return result('past', 'This date has passed', 'This is a record of an earlier date.',
                      'No action needed here', 'Check the current availability board if you need a new reservation.')
    if status == 'requested':
        if res.get('source') == 'move':
            hold = ('The new hours are not reserved. The previous approved booking remains in place.'
                    if parent and parent['status'] == 'approved'
                    else 'The new hours are not reserved. Check the earlier reservation for its current status.')
            return result('waiting', 'Move awaiting approval', hold, 'Administrative Section',
                          'Wait for the decision on the new time. Check this page for updates.', parent)
        return result('waiting', 'Standby request awaiting confirmation' if res.get('standby') else 'Waiting for approval',
                      'No hours are reserved by this request.', 'Administrative Section',
                      ('The Section must confirm the standby request before you can rely on the room. Check this page for updates.'
                       if res.get('standby') else 'The Section must approve the request before the room is reserved. Check this page for updates.'))
    if status == 'approved':
        move = next((p for p in children if p.get('source') == 'move' and p['status'] == 'requested'), None)
        if move:
            return result('waiting', 'A move is awaiting approval', 'These original approved hours remain reserved.',
                          'Administrative Section', 'The original booking stays until the new time is approved.', move)
        return result('ready', 'Approved for the listed date and hours', 'The room is reserved for these hours.',
                      'You, if plans change', 'Use the room as booked. Withdraw if you no longer need it so others can request the hours.')
    if status in ('declined', 'cancelled'):
        bumped = status == 'cancelled' and res.get('bumped_by_reservation_id') is not None
        step = (('Choose an alternative below. If it is still free, it is booked immediately with approval.'
                 if bumped else 'Choose an alternative below to send a new request for approval.') if offers else
                'No alternative is currently listed. Check availability or contact the Administrative Section with your reference.')
        return result('attention', 'Booking cancelled' if status == 'cancelled' else 'Request declined',
                      'These hours are not reserved by this record.', 'You, if you still need the room', step)
    if status == 'withdrawn':
        return result('closed', 'Reservation withdrawn', 'This record no longer holds any hours.',
                      'No action needed here', 'Check availability before requesting these hours again.')
    if status == 'expired':
        return result('closed', 'Request expired without approval', 'No hours were reserved by this request.',
                      'You, if you still need the room', 'Choose a new date and send a new request.')
    return result('attention', 'Check this reservation with the Administrative Section',
                  'A confirmed booking cannot be established from this status.', 'Administrative Section',
                  'Give the Section your reference before relying on the room.')
