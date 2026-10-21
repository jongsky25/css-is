"""Durable, bounded Drive discovery and receipt-preserving filing retries."""
import asyncio
import json
from datetime import timedelta
import uuid

import documents as d
import documents_permissions as p
from documents_storage import rows, transaction, event
from documents_workspace import Unconfigured, WorkspaceError, BudgetAdapter
import tzutil as tz

LEASE_SECONDS = 600
CHECK_SECONDS = 180
TICK_SECONDS = 30
MAX_ATTEMPTS = 6
FATAL_CODES = {'unauthorized','unknown_action','not_configured','bad_folder',
               'invalid_endpoint','receipt_mismatch','operation_conflict','version_changed',
               'unsupported_format','bad_request'}


def now():
    return tz.now_iso()


def later(seconds):
    return (tz.now_local()+timedelta(seconds=seconds)).isoformat(timespec='seconds')


def state(conn):
    return rows(conn,'SELECT * FROM document_intake_sync WHERE id=1')[0]


def active(value):
    return bool(value['lease_owner'] and (value['lease_until'] or '') > now())


def owned(conn, token):
    current=state(conn)
    if current['lease_owner'] != token:
        raise d.Conflict('Another worker owns this Drive check. Refresh its current status.')
    return current


def due_file(conn, *, manual=False):
    sql="SELECT * FROM document_intake WHERE filing_state IN ('pending','running','error')"
    if not manual:
        sql+=' AND filing_blocked=0 AND (filing_next_at IS NULL OR filing_next_at<=?)'
    return next(iter(rows(conn,sql+(' ORDER BY id LIMIT 1' if manual else ' ORDER BY COALESCE(filing_next_at,updated_at),id LIMIT 1'),() if manual else (now(),))),None)


def claim(conn, *, manual=False, filing_only=False):
    with transaction(conn):
        current=state(conn)
        if active(current):return None
        listing_due=not current['next_check_at'] or current['next_check_at']<=now()
        if not manual and (current['blocked'] or (not listing_due and not due_file(conn) and current['state']!='running')):
            return None
        if filing_only and not due_file(conn,manual=manual):return None
        token=str(uuid.uuid4())
        conn.execute("UPDATE document_intake_sync SET lease_owner=?,lease_until=?,state='running',last_started_at=? WHERE id=1",
                     (token,later(LEASE_SECONDS),now()))
        return token,current


def fatal(exc):
    return isinstance(exc,(Unconfigured,p.Denied)) or (isinstance(exc,WorkspaceError) and exc.code in FATAL_CODES)


def request_check(conn,user):
    import documents_intake as intake
    with transaction(conn):
        intake.reviewer(conn,user);intake._active(conn)
        if active(state(conn)):return 'running'
        conn.execute("UPDATE document_intake_sync SET lease_owner=NULL,lease_until=NULL,state='pending',next_check_at=?,blocked=0,failures=0 WHERE id=1",(now(),))
        return 'pending'


def retry_file(conn,user,item_id):
    import documents_intake as intake
    with transaction(conn):
        user=intake.reviewer(conn,user);intake._active(conn)
        if active(state(conn)):
            raise d.Conflict('A Drive check is running. Wait for it to finish before requesting a retry.')
        found=rows(conn,'SELECT * FROM document_intake WHERE id=?',(item_id,))
        d.require(found and found[0]['document_id'])
        item=found[0];d.get(conn,user,item['document_id'])
        if item['filing_state'] not in ('pending','running','error'):
            raise ValueError('This file does not need another filing check.')
        conn.execute("UPDATE document_intake SET filing_state='pending',filing_attempts=0,filing_blocked=0,filing_next_at=? WHERE id=?",(now(),item_id))
        conn.execute("UPDATE document_intake_sync SET lease_owner=NULL,lease_until=NULL,state='pending',next_check_at=?,blocked=0,failures=0 WHERE id=1",(now(),))
        event(conn,item['document_id'],user,'drive_filing_retry_requested',{'intake_id':item_id})


def file_one(conn,adapter,token, *, manual=False):
    import documents_intake as intake
    item=None
    try:
        with transaction(conn):
            owned(conn,token)
            config=intake._active(conn)
            actor=intake.reviewer(conn,{'id':int(config['actor_id'])})
            item=due_file(conn,manual=manual)
            if not item:return
            if item['filing_attempts']>=MAX_ATTEMPTS and not manual:
                conn.execute("UPDATE document_intake SET filing_state='error',filing_blocked=1,filing_next_at=NULL,error=? WHERE id=?",
                    ('Drive filing needs review after repeated interruptions. The document is registered.',item['id']))
                return
            payload=json.loads(item['filing_payload'])
            original=intake.reviewer(conn,{'id':payload['actor_id']})
            d.get(conn,original,item['document_id'])
            if (payload['inbox'],payload['filed'])!=(config['inbox'],config['filed']):
                raise ValueError('The filing folders changed.')
            conn.execute("UPDATE document_intake SET filing_state='running',filing_attempts=filing_attempts+1,filing_last_at=?,filing_next_at=? WHERE id=?",
                         (now(),later(LEASE_SECONDS),item['id']))
        # Existing relay atomically writes the move/rename and operation marker.
        # Reusing this ID and payload checks that marker after a lost response.
        result=adapter.call('intake_file',payload,item['filing_operation'])
        if result.get('state')!='confirmed' or result.get('file_id')!=item['file_id'] or not result.get('fingerprint'):
            raise ValueError('Filing not confirmed.')
        with transaction(conn):
            owned(conn,token);intake._active(conn)
            intake.reviewer(conn,actor)
            intake.reviewer(conn,original);d.get(conn,original,item['document_id'])
            conn.execute("UPDATE document_intake SET filing_state='complete',filing_next_at=NULL,filing_blocked=0,error='',updated_at=? WHERE id=?",
                         (now(),item['id']))
            conn.execute("UPDATE document_file_version SET fingerprint=? WHERE document_id=? AND file_id=? AND role='reference' AND fingerprint=''",
                         (str(result['fingerprint'])[:500],item['document_id'],item['file_id']))
            event(conn,item['document_id'],actor,'drive_filed',{'intake_id':item['id'],'file_id':item['file_id']})
    except Exception as exc:
        if item is None:raise
        with transaction(conn):
            owned(conn,token)
            current=rows(conn,'SELECT filing_attempts FROM document_intake WHERE id=?',(item['id'],))[0]
            blocked=fatal(exc) or current['filing_attempts']>=MAX_ATTEMPTS or isinstance(exc,(ValueError,KeyError)) and not isinstance(exc,WorkspaceError)
            delay=min(CHECK_SECONDS*2**min(5,max(0,current['filing_attempts']-1)),3600)
            conn.execute("UPDATE document_intake SET filing_state='error',filing_blocked=?,filing_next_at=?,error=?,updated_at=? WHERE id=?",
                         (int(blocked),None if blocked else later(delay),
                          'Drive filing needs attention; the registered record is saved. Check relay permissions and source changes.',now(),item['id']))


def sync(conn,adapter=None, *, manual=True,filing_only=False):
    import documents_intake as intake
    claimed=claim(conn,manual=manual,filing_only=filing_only)
    if not claimed:return False
    token,previous=claimed
    phase='settings';listed=False
    try:
        config=intake._active(conn)
        phase='account'
        actor=intake.reviewer(conn,{'id':int(config['actor_id'])})
        adapter=BudgetAdapter(adapter or intake.ops.get_adapter())
        listing_due=manual or not previous['next_check_at'] or previous['next_check_at']<=now()
        if listing_due and not filing_only:
            phase='relay'
            result=adapter.call('intake_list',{'inbox':config['inbox'],'cursor':config['cursor'],
                                'actor_id':actor['id']},str(uuid.uuid4()))
            phase='listing'
            intake.discover(conn,config,result,owner=token)
            listed=True
        phase='filing'
        # Leave filing due for a fresh turn if discovery used the whole budget.
        if adapter.available():
            file_one(conn,adapter,token,manual=manual)
        with transaction(conn):
            owned(conn,token)
            # Only a successful listing clears its diagnostic/backoff history.
            conn.execute('''UPDATE document_intake_sync SET lease_owner=NULL,lease_until=NULL,
                state=?,last_finished_at=?,failures=?,blocked=?,next_check_at=? WHERE id=1''',
                ('idle' if listed or not previous['failures'] else ('blocked' if previous['blocked'] else 'error'),now(),
                 0 if listed else previous['failures'],0 if listed else previous['blocked'],
                 later(CHECK_SECONDS) if listed else previous['next_check_at']))
        return True
    except Exception as exc:
        if conn.in_transaction:conn.rollback()
        with transaction(conn):
            # Superseded workers may not change cursors, errors or retry state.
            owned(conn,token)
            failures=previous['failures']+1
            blocked=fatal(exc) or failures>=MAX_ATTEMPTS or phase in ('settings','account','listing')
            intake._setting(conn,'cursor','')
            intake._setting(conn,'sync_error',intake.sync_failure(exc,phase))
            conn.execute('''UPDATE document_intake_sync SET lease_owner=NULL,lease_until=NULL,
                state=?,last_finished_at=?,failures=?,blocked=?,next_check_at=? WHERE id=1''',
                ('blocked' if blocked else 'error',now(),failures,int(blocked),
                 None if blocked else later(min(CHECK_SECONDS*2**min(failures-1,5),3600))))
        return True  # This turn was used, even though its listing failed.


def progress(conn):
    current=state(conn)
    status='running' if active(current) else ('needs_review' if current['blocked'] else
           'pending' if current['state']=='pending' else 'interrupted' if current['state']=='running' else
           'retrying' if current['failures'] else 'idle')
    labels={'running':'Drive check running','pending':'Drive check queued','needs_review':'Drive check needs attention',
            'interrupted':'Interrupted Drive check awaiting recovery','retrying':'Waiting to retry Drive check','idle':'Drive checks ready'}
    return {'status':status,'label':labels[status],'next_check_at':current['next_check_at'],
            'last_finished_at':current['last_finished_at'],'running':active(current)}


async def worker(get_conn):
    import documents_external as external
    import documents_intake as intake
    import documents_jobs as jobs
    turn=0
    def intake_tick():
        conn=get_conn()
        try:
            if d.enabled(conn) and intake.settings(conn)['intake_enabled']=='1':
                return sync(conn,manual=False)
            return False
        finally:conn.close()
    def tick():
        nonlocal turn
        turn+=1
        # Alternate priority after each admitted turn. If one side has no work,
        # the other can use this turn. Timeouts retain the actual worker slot.
        if turn%2:
            if jobs.recover_one(get_conn) is None:intake_tick()
        elif not intake_tick():
            jobs.recover_one(get_conn)
    while True:
        try:await external.run_background(tick)
        except (external.Busy,external.Unconfirmed):pass
        except Exception:pass  # Safe per-operation diagnostics remain in SQLite.
        await asyncio.sleep(TICK_SECONDS)
