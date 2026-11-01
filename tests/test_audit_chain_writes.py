"""Audit rows must hash persisted values and serialize independent writers."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import storage as st


def fresh(path):
    conn = st.connect(str(path))
    conn.execute("""CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT,
        target_type TEXT, target_id TEXT, summary TEXT, before_text TEXT,
        after_text TEXT, ip TEXT, prev_hash TEXT, row_hash TEXT)""")
    conn.commit()
    return conn


@pytest.mark.parametrize('target_id', [0, 1, None, '', '0'])
def test_hash_uses_stored_target_id(tmp_path, target_id):
    with fresh(tmp_path / 'audit.db') as conn:
        st.audit(conn, 'synthetic', 'supply_enabled_set', target_id=target_id)
        assert st.verify_audit_chain(conn) == (True, None)


def test_concurrent_writers_keep_one_chain(tmp_path):
    path = tmp_path / 'audit.db'
    fresh(path).close()
    start = Barrier(6)

    def write(worker):
        conn = st.connect(str(path))
        try:
            start.wait(timeout=10)
            for n in range(20):
                st.audit(conn, f'synthetic-{worker}', 'integration_read', target_id=n)
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write, range(6)))
    with st.connect(str(path)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == 120
        assert st.verify_audit_chain(conn) == (True, None)


def test_uncommitted_audit_remains_in_callers_transaction(tmp_path):
    path = tmp_path / 'audit.db'
    conn = fresh(path)
    other = st.connect(str(path))
    try:
        conn.execute('BEGIN IMMEDIATE')
        st.audit(conn, 'synthetic', 'first', commit=False)
        st.audit(conn, 'synthetic', 'second', commit=False)
        assert st.verify_audit_chain(conn) == (True, None)
        assert other.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == 0
        conn.rollback()
        assert conn.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == 0
        st.audit(conn, 'synthetic', 'third', commit=False)
        conn.commit()
        assert st.verify_audit_chain(other) == (True, None)
    finally:
        other.close()
        conn.close()


def test_old_corruption_is_still_reported(tmp_path):
    with fresh(tmp_path / 'audit.db') as conn:
        st.audit(conn, 'synthetic', 'first')
        conn.execute("UPDATE audit_log SET summary='changed' WHERE id=1")
        conn.commit()
        st.audit(conn, 'synthetic', 'second')
        assert st.verify_audit_chain(conn) == (False, 1)
