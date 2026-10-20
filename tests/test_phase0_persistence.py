"""Real SQLite saves/restores plus deterministic stalled-worker injection."""
import asyncio
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import backups as bk
import storage as st


@pytest.fixture
def persistence(app_mod, tmp_path, monkeypatch):
    db = str(tmp_path / 'live.db')
    conn = st.connect(db); st.init_db(conn)
    conn.execute('CREATE TABLE persistence_probe (id INTEGER PRIMARY KEY, value TEXT)')
    conn.commit(); conn.close()
    monkeypatch.setattr(app_mod, 'DB', db)
    monkeypatch.setattr(app_mod, 'PERSIST_DIR', str(tmp_path / 'bucket'))
    monkeypatch.setattr(bk, 'SCHED_DIR', str(tmp_path / 'bucket'))
    monkeypatch.setattr(app_mod, '_PERSIST_TASK', None)
    monkeypatch.setattr(app_mod, '_PERSIST_HEALTH', dict(state='unknown', reason='test',
        last_ok=None, last_event=None, consecutive_bad=0, last_tick_mono=None, last_ok_mono=None))
    clock = {'now': datetime(2026, 10, 19, 12)}
    monkeypatch.setattr(bk, '_now', lambda: clock['now'])
    return app_mod, db, clock


def test_later_commits_and_updates_reach_snapshot_and_restored_database(persistence, tmp_path):
    app, db, clock = persistence
    async def exercise():
        for number in range(3):
            with sqlite3.connect(db) as conn:
                conn.execute('INSERT INTO persistence_probe(value) VALUES (?)', (str(number),))
                # In-place updates also count; max-ID/row-count heuristics miss them.
                conn.execute('UPDATE persistence_probe SET value=? WHERE id=1', ('latest-'+str(number),))
            assert await app._persist_once()
            snapshot = bk.newest_valid_snapshot()
            with sqlite3.connect(snapshot) as saved:
                assert saved.execute('SELECT count(*) FROM persistence_probe').fetchone()[0] == number+1
                assert saved.execute('SELECT value FROM persistence_probe WHERE id=1').fetchone()[0] == 'latest-'+str(number)
            clock['now'] += timedelta(seconds=61)
        return snapshot
    snapshot = asyncio.run(exercise())
    # Recover into a separate initialized DB through the actual restore service.
    restored = str(tmp_path / 'restored.db')
    conn = st.connect(restored); st.init_db(conn); conn.close()
    bk.restore_backup(Path(snapshot).name, restored)
    with sqlite3.connect(restored) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT value FROM persistence_probe ORDER BY id').fetchall() == [('latest-2',), ('1',), ('2',)]
    assert app._persist_health_view()['down'] is False


def test_failed_copy_marks_health_bad_and_next_attempt_recovers(persistence, monkeypatch):
    app, db, clock = persistence
    real = bk.make_backup
    def fail(*args, **kwargs):
        raise OSError('synthetic unavailable bucket')
    monkeypatch.setattr(bk, 'make_backup', fail)
    assert asyncio.run(app._persist_once()) is False
    assert app._PERSIST_HEALTH['last_ok'] is None
    assert app._persist_health_view()['down'] is True
    monkeypatch.setattr(bk, 'make_backup', real)
    assert asyncio.run(app._persist_once()) is True
    assert app._persist_health_view()['down'] is False


def test_timeout_reuses_one_worker_and_shutdown_waits_before_final_save(persistence, monkeypatch):
    app, db, clock = persistence
    started, release = threading.Event(), threading.Event()
    calls = []
    real = app._snapshot_to_bucket
    def delayed(reason):
        calls.append(reason); started.set()
        assert release.wait(5), 'test must release worker'
        return real(reason)
    monkeypatch.setattr(app, '_snapshot_to_bucket', delayed)
    monkeypatch.setattr(app, 'PERSIST_OP_TIMEOUT', .03)
    async def exercise():
        try:
            assert await app._persist_once() is False
            assert started.is_set()
            task = app._PERSIST_TASK
            assert not task.done()
            assert app._persist_health_view()['down'] is True
            assert await app._persist_once() is False
            assert app._PERSIST_TASK is task and len(calls) == 1
            # Shutdown must also reuse the stalled writer, not launch a second.
            await app._persist_on_shutdown()
            assert len(calls) == 1
        finally:
            release.set()
            if app._PERSIST_TASK:
                await asyncio.wait_for(app._PERSIST_TASK, 5)
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO persistence_probe(value) VALUES ('after-stall')")
        clock['now'] += timedelta(seconds=61)
        await app._persist_on_shutdown()
        assert calls == ['timer', 'shutdown']
    asyncio.run(exercise())
    with sqlite3.connect(bk.newest_valid_snapshot()) as saved:
        assert saved.execute('SELECT value FROM persistence_probe').fetchall() == [('after-stall',)]


def test_highwater_is_measured_from_saved_snapshot_not_newer_live_db(persistence, monkeypatch):
    app, db, clock = persistence
    real = bk.write_highwater
    captured = []
    def after_copy(path, name):
        # Simulate a live commit immediately after SQLite's backup completes.
        with sqlite3.connect(db) as live:
            live.execute("INSERT INTO admin_user(username,pw_hash,salt,role) VALUES ('new@test','x','x','viewer')")
        captured.append(str(path))
        return real(path, name)
    monkeypatch.setattr(bk, 'write_highwater', after_copy)
    meta = bk.make_backup(db)
    snapshot = str(Path(bk.SCHED_DIR) / meta['name'])
    assert captured == [snapshot]
    assert bk.read_highwater() == bk.db_marker(snapshot)
    assert bk.db_marker(db) != bk.read_highwater()
