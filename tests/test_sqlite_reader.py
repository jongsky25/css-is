"""Ownership, freshness, cleanup and bounded reuse of application reads."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

import pytest

from sqlite_reader import SQLiteReader
import storage as st


@pytest.fixture
def reader(tmp_path):
    path = tmp_path / 'read.db'
    conn = st.connect(path)
    conn.execute('CREATE TABLE value (n INTEGER)')
    conn.execute('INSERT INTO value VALUES (1)')
    conn.commit()
    conn.close()
    worker = SQLiteReader()
    yield worker, path
    worker.close()


def test_reuses_one_owned_connection_across_calling_threads(reader):
    worker, path = reader
    opens = []
    def connect():
        opens.append(threading.get_ident())
        return st.connect(path)
    def read(_):
        return worker.read(path, connect, lambda c: (
            threading.get_ident(), c.execute('SELECT n FROM value').fetchone()[0]))
    with ThreadPoolExecutor(max_workers=8) as callers:
        results = list(callers.map(read, range(60)))
    assert len(opens) == 1
    assert results == [(opens[0], 1)] * 60
    assert opens[0] != threading.get_ident()


def test_current_data_no_pinned_snapshot_and_write_rejected(reader):
    worker, path = reader
    def read(c):
        c.execute('BEGIN')
        return c.execute('SELECT n FROM value').fetchone()[0]
    run = lambda op: worker.read(path, lambda: st.connect(path), op)
    assert run(read) == 1
    with st.connect(path) as writer:
        writer.execute('UPDATE value SET n=2')
    assert run(read) == 2
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        run(lambda c: c.execute('UPDATE value SET n=3'))
    assert run(read) == 2


def test_exception_discards_connection_and_nested_call_fails(reader):
    worker, path = reader
    opens = []
    def connect():
        opens.append(1)
        return st.connect(path)
    def broken(c):
        c.execute('BEGIN')
        raise ValueError('callback failed')
    with pytest.raises(ValueError):
        worker.read(path, connect, broken)
    assert worker.read(path, connect, lambda c: c.in_transaction) is False
    assert len(opens) == 2
    with pytest.raises(RuntimeError, match='Nested'):
        worker.read(path, connect, lambda c: worker.read(path, connect, lambda c: 1))


def test_replacement_refresh_and_shutdown(reader, tmp_path):
    worker, path = reader
    run = lambda **kw: worker.read(path, lambda: st.connect(path),
                                  lambda c: c.execute('SELECT n FROM value').fetchone()[0], **kw)
    assert run() == 1
    # Move the complete old DB aside with its WAL files before replacing it.
    worker.read(path, lambda: st.connect(path), lambda c: c.execute('SELECT 1').fetchone())
    replacement = tmp_path / 'new.db'
    with sqlite3.connect(replacement) as conn:
        conn.execute('CREATE TABLE value (n INTEGER)')
        conn.execute('INSERT INTO value VALUES (7)')
    path.rename(tmp_path / 'old.db')
    for suffix in ('-wal', '-shm'):
        side = path.with_name(path.name + suffix)
        if side.exists():
            side.rename(tmp_path / ('old.db' + suffix))
    replacement.rename(path)
    assert run() == 7
    assert run(refresh=True) == 7
    worker.close()
    worker.close()
    with pytest.raises(RuntimeError, match='shutdown'):
        run()


def test_auth_revocation_is_visible_after_cached_read(app_mod, admin):
    # Existing endpoint checks must reject the SAME cookie after DB revocation.
    assert admin.get('/appearance/current').status_code == 200
    conn = app_mod.get_conn()
    conn.execute('DELETE FROM login_session')
    conn.commit()
    conn.close()
    assert admin.get('/appearance/current', follow_redirects=False).status_code in (303, 401)
