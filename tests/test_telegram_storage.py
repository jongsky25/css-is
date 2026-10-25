"""Synthetic storage/restart/restore checks; no bot credentials or provider I/O."""
import sqlite3

import pytest

import backups
import storage as st
import telegram_storage as telegram
import work_channels
from tests.test_work import workspace

STAMP = '2026-10-25T00:00:00Z'


def connection(c, user, sender=101):
    return c.execute('''INSERT INTO telegram_connection
        (account_id,telegram_user_id,private_chat_id,state,created_at,updated_at)
        VALUES (?,?,?,'active',?,?) RETURNING id,generation''',
        (user['id'], sender, sender, STAMP, STAMP)).fetchone()


def seed(c, user):
    cid, generation = connection(c, user)
    for update_id, state in enumerate(('queued', 'processing', 'processed', 'ignored')):
        c.execute('''INSERT INTO telegram_update
            (bot_identity,update_id,sender_id,chat_id,connection_id,generation,payload_json,
             payload_hash,received_at,state,claim_token,lease_until)
            VALUES (1,?,101,101,?,?,'{"text":"synthetic"}','hash',?,?, 'old-claim',?)''',
            (update_id, cid, generation, STAMP, state, STAMP))
    for state in ('pending', 'committed', 'partial', 'failed'):
        c.execute('''INSERT INTO telegram_operation
            (operation_id,actor_id,connection_id,generation,action,client_key,input_hash,
             state,result_code,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,'original',?,?)''',
            (state, user['id'], cid, generation, 'calendar.create', state, 'hash', state, STAMP, STAMP))
    for state in ('queued', 'claimed', 'sending', 'retry_wait', 'accepted', 'failed', 'uncertain', 'cancelled'):
        c.execute('''INSERT INTO telegram_delivery
            (dedupe_key,operation_id,connection_id,generation,chat_id,projection_json,state,
             claim_token,lease_until,retry_at,expires_at,created_at,updated_at,provider_message_id)
            VALUES (?,'committed',?,?,101,'{}',?,'old-claim',?,?,?,?,?,77)''',
            (state, cid, generation, state, STAMP, STAMP, STAMP, STAMP, STAMP))
    c.commit()
    return cid, generation


def test_empty_upgrade_and_repeated_init_preserve_existing_digest(workspace):
    c, users, _, _ = workspace
    work_channels.save(c, users[0], 0, 'daily')
    before = work_channels.preferences(c, users[0])
    # A pre-T1.1 snapshot has all existing schema but none of the new tables.
    for table in ('telegram_delivery', 'telegram_operation', 'telegram_update', 'telegram_connection'):
        c.execute('DROP TABLE ' + table)
    c.commit()
    st.init_db(c)
    assert all(c.execute('SELECT count(*) FROM telegram_' + name).fetchone()[0] == 0
               for name in ('connection', 'update', 'operation', 'delivery'))
    seed(c, users[0])
    dump = sorted(c.iterdump())
    st.init_db(c)
    assert sorted(c.iterdump()) == dump
    assert work_channels.preferences(c, users[0]) == before
    assert c.execute('PRAGMA foreign_key_check').fetchall() == []


def test_constraints_deduplicate_without_replacing_receipts(workspace):
    c, users, _, _ = workspace
    seed(c, users[0])
    with pytest.raises(sqlite3.IntegrityError):
        connection(c, users[0], 202)
    with pytest.raises(sqlite3.IntegrityError):
        connection(c, users[1], 101)
    for table, columns, values in (
        ('telegram_update', 'bot_identity,update_id,payload_hash,received_at', (1, 0, 'other', STAMP)),
        ('telegram_operation', 'operation_id,actor_id,connection_id,generation,action,client_key,input_hash,created_at,updated_at',
         ('another-id', users[0]['id'], 1, 'g', 'rooms.request', 'committed', 'other', STAMP, STAMP)),
        ('telegram_delivery', 'dedupe_key,chat_id,expires_at,created_at,updated_at', ('accepted', 101, STAMP, STAMP, STAMP)),
        ('telegram_connection', 'account_id,telegram_user_id,private_chat_id,created_at,updated_at',
         (999999, 303, 303, STAMP, STAMP)),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in values)})', values)
    c.rollback()
    assert c.execute("SELECT result_code FROM telegram_operation WHERE operation_id='committed'").fetchone() == ('original',)
    # Provider identity scopes update IDs; sequential IDs are not assumed globally unique.
    c.execute("INSERT INTO telegram_update(bot_identity,update_id,payload_hash,received_at) VALUES (2,0,'hash',?)", (STAMP,))
    c.execute("UPDATE telegram_connection SET state='revoked',revoked_at=? WHERE id=1", (STAMP,))
    connection(c, users[0])  # Explicitly revoked binding permits future relink.
    c.commit()


def test_restart_preserves_receipts_claims_and_switches(workspace):
    c, users, _, path = workspace
    cid, generation = seed(c, users[0])
    other = st.connect(path)
    try:
        st.init_db(other)
        assert other.execute('SELECT generation FROM telegram_connection WHERE id=?', (cid,)).fetchone() == (generation,)
        assert other.execute("SELECT state,claim_token FROM telegram_delivery WHERE dedupe_key='sending'").fetchone() == ('sending', 'old-claim')
        assert other.execute("SELECT result_code FROM telegram_operation WHERE operation_id='committed'").fetchone() == ('original',)
    finally:
        other.close()


@pytest.mark.parametrize('deliberate', [False, True])
def test_snapshot_restore_pauses_and_fences_but_keeps_receipts(workspace, tmp_path, deliberate):
    c, users, _, _ = workspace
    cid, old_generation = seed(c, users[0])
    restored_path = str(tmp_path / 'restored.db')
    snapshot = sqlite3.connect(restored_path)
    c.backup(snapshot)
    snapshot.close()
    backups.clear_restored_sessions(restored_path, revoke_integrations=deliberate)
    restored = st.connect(restored_path)
    try:
        st.init_db(restored)
        state, generation = restored.execute('SELECT state,generation FROM telegram_connection WHERE id=?', (cid,)).fetchone()
        assert state == 'paused' and generation != old_generation
        assert restored.execute("SELECT state FROM telegram_update ORDER BY update_id").fetchall() == [('cancelled',), ('cancelled',), ('processed',), ('ignored',)]
        assert restored.execute('SELECT count(*) FROM telegram_update WHERE payload_json IS NOT NULL OR claim_token IS NOT NULL OR lease_until IS NOT NULL').fetchone()[0] == 0
        assert dict(restored.execute('SELECT operation_id,state FROM telegram_operation')) == {
            'pending': 'cancelled', 'committed': 'committed', 'partial': 'partial', 'failed': 'failed'}
        states = dict(restored.execute('SELECT dedupe_key,state FROM telegram_delivery'))
        assert states == {'queued': 'cancelled', 'claimed': 'cancelled', 'sending': 'uncertain',
                          'retry_wait': 'cancelled', 'accepted': 'accepted', 'failed': 'failed',
                          'uncertain': 'uncertain', 'cancelled': 'cancelled'}
        assert restored.execute("SELECT provider_message_id FROM telegram_delivery WHERE dedupe_key='accepted'").fetchone() == (77,)
        assert restored.execute("UPDATE telegram_delivery SET state='accepted' WHERE dedupe_key='sending' AND claim_token='old-claim' AND state='sending'").rowcount == 0
        assert restored.execute("UPDATE telegram_connection SET state='active' WHERE id=? AND generation=?", (cid, old_generation)).rowcount == 0
        restored.commit()
        backups.clear_restored_sessions(restored_path, revoke_integrations=deliberate)
        assert restored.execute('SELECT generation FROM telegram_connection WHERE id=?', (cid,)).fetchone()[0] != generation
        assert restored.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        restored.close()


def test_restore_hook_handles_older_snapshot_and_rolls_back(workspace, tmp_path):
    old = str(tmp_path / 'legacy.db')
    sqlite3.connect(old).close()
    backups.clear_restored_sessions(old)
    c, users, _, _ = workspace
    cid, generation = seed(c, users[0])
    c.execute('BEGIN')
    telegram.reset_after_restore(c)
    c.rollback()
    assert c.execute('SELECT generation FROM telegram_connection WHERE id=?', (cid,)).fetchone() == (generation,)


@pytest.mark.parametrize('capability', telegram.SWITCHES)
def test_switches_default_off_exact_and_independent(monkeypatch, capability):
    for switch in telegram.SWITCHES:
        monkeypatch.delenv('CSS_TELEGRAM_' + switch.upper() + '_ENABLED', raising=False)
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_ENABLED', '1')
    assert not any(telegram.enabled(s) for s in telegram.SWITCHES)
    key = 'CSS_TELEGRAM_' + capability.upper() + '_ENABLED'
    for value in ('true', 'yes', 'on', ' 1', '1 ', '2', ''):
        monkeypatch.setenv(key, value)
        assert not telegram.enabled(capability)
    monkeypatch.setenv(key, '1')
    assert telegram.enabled(capability)
    assert all(not telegram.enabled(s) for s in telegram.SWITCHES if s != capability)
    with pytest.raises(ValueError):
        telegram.enabled('unknown')


def test_deliberate_backup_restore_runs_fence(workspace, tmp_path, monkeypatch):
    c, users, _, path = workspace
    cid, generation = seed(c, users[0])
    work_channels.save(c, users[0], 0, 'daily')
    monkeypatch.setattr(backups, 'SCHED_DIR', str(tmp_path / 'snapshots'))
    saved = backups.make_backup(path, kind='manual')
    c.execute("UPDATE telegram_operation SET result_code='after-snapshot' WHERE operation_id='committed'")
    c.commit()
    backups.restore_backup(saved['name'], path)
    assert c.execute('SELECT state FROM telegram_connection WHERE id=?', (cid,)).fetchone() == ('paused',)
    assert c.execute('SELECT generation FROM telegram_connection WHERE id=?', (cid,)).fetchone()[0] != generation
    assert c.execute("SELECT result_code FROM telegram_operation WHERE operation_id='committed'").fetchone() == ('original',)
    assert c.execute("SELECT state FROM telegram_delivery WHERE dedupe_key='sending'").fetchone() == ('uncertain',)
    # Existing deliberate-restore digest behavior stays separate and unchanged.
    assert work_channels.preferences(c, users[0])['cadence'] == 'off'


def test_invalid_states_and_destinations_are_rejected(workspace):
    c, users, _, _ = workspace
    cid, _ = connection(c, users[0])
    c.commit()
    for sql in (
        "UPDATE telegram_connection SET state='unexpected' WHERE id=1",
        "UPDATE telegram_connection SET private_chat_id=-101 WHERE id=1",
        "UPDATE telegram_connection SET state='revoked' WHERE id=1",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(sql)
        c.rollback()
    assert c.execute('SELECT state FROM telegram_connection WHERE id=?', (cid,)).fetchone() == ('active',)
