"""Acknowledgments bind exact history; no exception applies to later damage."""
import pytest
import storage as st
from tests.test_audit_chain_writes import fresh


def acknowledge(conn, monkeypatch):
    rows = conn.execute('SELECT id,ts,actor,action,target_type,target_id,summary,'
                        'before_text,after_text,ip,prev_hash,row_hash '
                        'FROM audit_log ORDER BY id').fetchall()
    monkeypatch.setattr(st, '_AUDIT_INCIDENT', {
        'through_id': rows[-1][0], 'row_count': len(rows),
        'prefix_sha256': st._audit_prefix_digest(rows), 'bad_ids': [rows[0][0]],
    })


def historical(conn, monkeypatch):
    st.audit(conn, 'synthetic', 'first')
    conn.execute("UPDATE audit_log SET summary='old mismatch' WHERE id=1")
    conn.commit()
    st.audit(conn, 'synthetic', 'second')
    acknowledge(conn, monkeypatch)


def test_preserves_raw_failure_and_exact_rows(tmp_path, monkeypatch):
    conn = fresh(tmp_path / 'audit.db')
    historical(conn, monkeypatch)
    before = conn.execute('SELECT * FROM audit_log ORDER BY id').fetchall()
    health = st.audit_health(conn)
    assert health['ok'] and health['acknowledged'] and not health['raw_ok']
    assert health['historical_bad_ids'] == [1]
    assert st.verify_audit_chain(conn) == (False, 1)
    assert conn.execute('SELECT * FROM audit_log ORDER BY id').fetchall() == before
    st.audit(conn, 'synthetic', 'later', target_id=0)
    assert st.audit_health(conn)['ok']
    conn.close()


@pytest.mark.parametrize('field', ['ts', 'actor', 'action', 'target_type',
    'target_id', 'summary', 'before_text', 'after_text', 'ip', 'prev_hash', 'row_hash'])
def test_any_reviewed_field_change_reopens_warning(tmp_path, monkeypatch, field):
    conn = fresh(tmp_path / 'audit.db')
    historical(conn, monkeypatch)
    conn.execute(f'UPDATE audit_log SET {field}=? WHERE id=1', ('changed',))
    conn.commit()
    assert not st.audit_health(conn)['ok']
    assert not st.audit_health(conn)['acknowledged']
    conn.close()


def test_rehashing_history_cannot_clear_checkpoint_warning(tmp_path, monkeypatch):
    conn = fresh(tmp_path / 'audit.db')
    historical(conn, monkeypatch)
    conn.execute('DELETE FROM audit_log')
    conn.commit()
    st.audit(conn, 'synthetic', 'replacement first')
    st.audit(conn, 'synthetic', 'replacement second')
    assert st.verify_audit_chain(conn) == (True, None)
    assert not st.audit_health(conn)['ok']
    assert st.audit_health(conn)['checkpoint_changed']
    conn.close()


@pytest.mark.parametrize('damage', ['edit', 'delete', 'fork'])
def test_new_failure_is_never_acknowledged(tmp_path, monkeypatch, damage):
    conn = fresh(tmp_path / 'audit.db')
    historical(conn, monkeypatch)
    st.audit(conn, 'synthetic', 'later')
    st.audit(conn, 'synthetic', 'last')
    if damage == 'edit':
        conn.execute("UPDATE audit_log SET summary='new corruption' WHERE id=3")
    elif damage == 'delete':
        conn.execute('DELETE FROM audit_log WHERE id=3')
    else:
        parent = conn.execute('SELECT row_hash FROM audit_log WHERE id=2').fetchone()[0]
        row = conn.execute('SELECT ts,actor,action,target_type,target_id,summary,'
                           'before_text,after_text FROM audit_log WHERE id=4').fetchone()
        conn.execute('UPDATE audit_log SET prev_hash=?,row_hash=? WHERE id=4',
                     (parent, st._audit_hash(parent, *row)))
    conn.commit()
    health = st.audit_health(conn)
    assert health['acknowledged'] and not health['ok']
    assert health['bad_id'] > 2
    conn.close()


def test_clean_database_needs_no_acknowledgment(tmp_path):
    conn = fresh(tmp_path / 'audit.db')
    assert st.audit_health(conn)['ok']
    st.audit(conn, 'synthetic', 'first')
    health = st.audit_health(conn)
    assert health['ok'] and health['raw_ok'] and not health['acknowledged']
    conn.close()


def test_pages_distinguish_acknowledged_history_and_new_failure(admin, db_path, monkeypatch):
    conn = st.connect(db_path)
    st.audit(conn, 'synthetic', 'first')
    conn.execute("UPDATE audit_log SET summary='reviewed synthetic mismatch' "
                 'WHERE id=(SELECT MIN(id) FROM audit_log)')
    conn.commit()
    acknowledge(conn, monkeypatch)
    body = admin.get('/admin/audit').text
    assert 'No new audit failures detected' in body
    assert 'Original records and hashes are preserved' in body
    assert 'Chain intact' not in body
    assert 'Historical audit incident acknowledged' in admin.get('/ops').text
    st.audit(conn, 'synthetic', 'new')
    conn.execute("UPDATE audit_log SET summary='new damage' "
                 'WHERE id=(SELECT MAX(id) FROM audit_log)')
    conn.commit()
    assert 'Audit review needed' in admin.get('/admin/audit').text
    assert 'Audit record needs review' in admin.get('/ops').text
    conn.close()
