"""Durable stock-warning snapshots, alert episodes and recipient-scoped in-app notices."""
import json

import supplies as s
import supplies_permissions as permissions
import supplies_stock as stock
from supplies_storage import Invalid, Missing, operation, record, rows, transaction
import tzutil as tz


LABELS = {'unrecorded':'Stock not recorded', 'inactive':'Inactive', 'out_of_stock':'Out of stock',
          'critical':'Critical', 'normal':'Normal', 'fully_reserved':'Fully reserved',
          'low_available':'Low available', 'available':'Available'}


def classify(on_hand, reserved, critical_level, *, recorded=True, active=True):
    available = on_hand - reserved
    if not active:
        physical = available_state = 'inactive'
    elif not recorded:
        physical = available_state = 'unrecorded'
    elif on_hand == 0:
        physical = available_state = 'out_of_stock'
    else:
        physical = 'critical' if on_hand < critical_level else 'normal'
        available_state = 'fully_reserved' if available == 0 else 'low_available' if available < critical_level else 'available'
    severity = {'out_of_stock':3, 'fully_reserved':2, 'low_available':1}.get(available_state,0)
    return {'on_hand':on_hand,'reserved':reserved,'available':available,'critical_level':critical_level,
            'recorded':bool(recorded),'active':bool(active),'physical_state':physical,'availability_state':available_state,
            'physical_label':LABELS[physical],'availability_label':LABELS[available_state],'severity':severity}


def _snapshot(conn, item_id):
    item = s._item(conn,item_id)
    totals = stock._totals(conn,item_id)
    reserved = sum(r[0] for r in conn.execute('SELECT reserved_quantity FROM supply_reservation WHERE item_id=?',(item_id,)))
    return {'item_id':item_id,'code':item['code'],'description':item['description'],'unit':item['unit'],
            **classify(totals['on_hand'],reserved,item['critical_level'],recorded=totals['recorded'],active=item['active'])}


def status(conn, user, item_id):
    with stock._snapshot(conn):
        s.get_item(conn,user,item_id)
        return _snapshot(conn,item_id)


def enqueue(conn, item_ids, operation_key, *, force=False):
    """Caller owns the business transaction; snapshots capture its final allocation."""
    if not conn.in_transaction:
        raise RuntimeError('Warning snapshots require the caller write transaction.')
    for item_id in sorted(set(item_ids)):
        snapshot = json.dumps(_snapshot(conn,item_id),sort_keys=True)
        latest = conn.execute('SELECT snapshot_json FROM supply_alert_event WHERE item_id=? ORDER BY id DESC LIMIT 1',(item_id,)).fetchone()
        if not force and latest and latest[0] == snapshot:
            continue
        conn.execute('''INSERT INTO supply_alert_event(item_id,operation_key,snapshot_json,created_at)
          VALUES (?,?,?,?) ON CONFLICT(item_id,operation_key) DO NOTHING''',(item_id,operation_key,snapshot,tz.now_iso()))


def _deliver(conn, episode, event_id, snapshot, now):
    # Reload recipients for each delivery; old role grants confer no ongoing notice access.
    recipients = conn.execute('''SELECT DISTINCT u.id FROM admin_user u JOIN supply_role_grant g ON g.user_id=u.id
      WHERE u.active=1 AND g.role='custodian' AND g.revoked_at IS NULL''').fetchall()
    for recipient in recipients:
        conn.execute('''INSERT INTO supply_notice(episode_id,version,event_id,item_id,recipient_id,snapshot_json,created_at)
          VALUES (?,?,?,?,?,?,?) ON CONFLICT(episode_id,version,recipient_id) DO NOTHING''',
          (episode['id'],episode['version'],event_id,snapshot['item_id'],recipient[0],json.dumps(snapshot,sort_keys=True),now))


def _apply(conn, event):
    snapshot = json.loads(event['snapshot_json'])
    now = tz.now_iso()
    current = rows(conn,'SELECT * FROM supply_alert_episode WHERE item_id=? AND resolved_at IS NULL',(event['item_id'],))
    episode = current[0] if current else None
    severity = snapshot['severity']
    if not severity:
        if episode:
            conn.execute('UPDATE supply_alert_episode SET resolved_at=?,updated_at=? WHERE id=?',(now,now,episode['id']))
            conn.execute('UPDATE supply_notice SET resolved_at=? WHERE episode_id=? AND resolved_at IS NULL',(now,episode['id']))
    else:
        if not episode:
            episode_id = conn.execute('''INSERT INTO supply_alert_episode
              (item_id,version,peak_severity,notified_available,last_event_id,started_at,updated_at)
              VALUES (?,1,?,?,?,?,?)''',(event['item_id'],severity,snapshot['available'],event['id'],now,now)).lastrowid
            episode = rows(conn,'SELECT * FROM supply_alert_episode WHERE id=?',(episode_id,))[0]
        else:
            # A new severity or a further halving of availability warrants another notice.
            # Partial recovery inside an episode does not reset the notification baseline.
            worsening = (severity > episode['peak_severity'] or
                         (snapshot['available'] > 0 and snapshot['available'] <= episode['notified_available']//2))
            if worsening:
                conn.execute('''UPDATE supply_alert_episode SET version=version+1,peak_severity=MAX(peak_severity,?),
                  notified_available=?,last_event_id=?,updated_at=? WHERE id=?''',
                  (severity,snapshot['available'],event['id'],now,episode['id']))
                episode = rows(conn,'SELECT * FROM supply_alert_episode WHERE id=?',(episode['id'],))[0]
        # Same version is harmless; a newly granted custodian gets the active warning once.
        _deliver(conn,episode,event['id'],snapshot,now)
    conn.execute('''INSERT INTO supply_item_alert(item_id,last_event_id,snapshot_json,updated_at) VALUES (?,?,?,?)
      ON CONFLICT(item_id) DO UPDATE SET last_event_id=excluded.last_event_id,snapshot_json=excluded.snapshot_json,updated_at=excluded.updated_at''',
      (event['item_id'],event['id'],event['snapshot_json'],now))
    conn.execute('UPDATE supply_alert_event SET processed_at=?,last_error=NULL WHERE id=?',(now,event['id']))


def process_pending(conn, *, limit=100):
    """Only projects committed snapshots. A failure cannot replay or undo stock work."""
    if conn.in_transaction:
        raise RuntimeError('Notice processing needs a clean connection.')
    limit = s.integer(limit,'Processing limit',1)
    if limit > 1000:
        raise Invalid('Process at most 1000 warning events per batch.')
    processed = 0
    for _ in range(limit):
        event = None
        try:
            conn.execute('BEGIN IMMEDIATE')
            pending = rows(conn,'SELECT * FROM supply_alert_event WHERE processed_at IS NULL ORDER BY id LIMIT 1')
            if not pending:
                conn.rollback()
                break
            event = pending[0]
            _apply(conn,event)
            conn.commit()
            processed += 1
        except Exception:
            conn.rollback()
            if event:
                # Keep a bounded, non-sensitive error; explicit reconciliation retries the event.
                conn.execute("UPDATE supply_alert_event SET attempts=attempts+1,last_error='Notice processing failed; retry reconciliation.' WHERE id=?",(event['id'],))
                conn.commit()
            raise
    return processed


def reconcile_alerts(conn, user, *, operation_key):
    """Explicit bookkeeping retry/backfill; allowed while stock mutations are disabled."""
    with transaction(conn):
        user = permissions.require_custodian(conn,user)
        key,digest,prior = operation(conn,user,operation_key,'alerts_reconcile',{})
        if prior is not None:
            return prior
        result = {'id':0}
        record(conn,user,key,digest,'alerts_reconcile','alert_queue',result,result)
        enqueue(conn,[r[0] for r in conn.execute('SELECT id FROM supply_item')],key)
        return result


def list_warnings(conn, user, *, page=1, query='', state=''):
    with stock._snapshot(conn):
        from supplies_dashboard import queue
        result = queue(conn,user,'warnings',page=page,query=query,state=state)
        result['pending_count'] = conn.execute('SELECT COUNT(*) FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0]
        return result


def _notice(conn, user, notice_id):
    user = permissions.require_custodian(conn,user)
    found = rows(conn,'SELECT * FROM supply_notice WHERE id=? AND recipient_id=?',
                 (s.integer(notice_id,'Notice',1),user['id']))
    if not found:
        raise Missing('Notice not found or unavailable to you.')
    notice = found[0]
    notice['snapshot'] = json.loads(notice.pop('snapshot_json'))
    return notice


def get_notice(conn, user, notice_id):
    with stock._snapshot(conn):
        return _notice(conn,user,notice_id)


def list_notices(conn, user, *, page=1, unread=False):
    with stock._snapshot(conn):
        user = permissions.require_custodian(conn,user)
        page = s.integer(page,'Page',1)
        predicate = ' AND read_at IS NULL AND resolved_at IS NULL' if unread else ''
        found = rows(conn,'SELECT id FROM supply_notice WHERE recipient_id=?'+predicate+' ORDER BY id DESC LIMIT 26 OFFSET ?',
                     (user['id'],(page-1)*25))
        unread_count = conn.execute('SELECT COUNT(*) FROM supply_notice WHERE recipient_id=? AND read_at IS NULL AND resolved_at IS NULL',(user['id'],)).fetchone()[0]
        return {'notices':[_notice(conn,user,r['id']) for r in found[:25]],'page':page,'has_next':len(found)>25,
                'unread_only':unread,'unread_count':unread_count}


def mark_read(conn, user, notice_id, *, operation_key):
    with transaction(conn):
        user = permissions.require_custodian(conn,user)
        notice = _notice(conn,user,notice_id)
        key,digest,prior = operation(conn,user,operation_key,'notice_read',{'id':notice['id']})
        if prior is not None:
            return prior
        result = {'id':notice['id']}
        record(conn,user,key,digest,'notice_read','notice',result,result)
        conn.execute('UPDATE supply_notice SET read_at=COALESCE(read_at,?) WHERE id=?',(tz.now_iso(),notice['id']))
        return result
