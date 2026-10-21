"""Run actual registry statements through the OS SQLite as well as pinned Python.

Only the child interpreter's standard library is used. This catches parser limits
hidden by a newer SQLite bundled into a standalone Python distribution.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import documents_registry
from tests.test_documents import registry, register


def test_registry_statements_work_with_system_sqlite(registry, tmp_path):
    conn, users, unit, _ = registry
    doc = register(conn, users[0], unit, 'OUT', subject='Needle record')
    conn.execute("UPDATE document SET visibility='bureau',verification='verified',status='approved' WHERE id=?", (doc['id'],))
    conn.execute('''INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at)
        VALUES(?,?,'contributor','Review','assigned','2026-10-21')''', (doc['id'], users[3]['id']))
    conn.commit()
    cases = []
    for index, user in enumerate(users):
        for queue in ('all', 'mine', 'release'):
            for query in ('', 'Needle'):
                selection = documents_registry.Selection(conn, user, query, queue)
                page_sql, params = selection.page_statement(before=0, limit=3)
                count_sql = selection.read_ctes() + ' SELECT COUNT(*) FROM registry_selected'
                for operation, sql in (('page', page_sql), ('count', count_sql)):
                    cases.append({'label': f'{index}/{queue}/{query}/{operation}', 'sql': sql,
                                  'params': params, 'expected': conn.execute(sql, params).fetchall()})
                captured = []
                conn.set_trace_callback(lambda sql: captured.append(sql) if 'AVG(days) AS average_calendar_days' in sql else None)
                try:
                    selection.totals(conn)
                finally:
                    conn.set_trace_callback(None)
                assert len(captured) == 1
                cases.append({'label': f'{index}/{queue}/{query}/totals', 'sql': captured[0],
                              'params': {}, 'expected': conn.execute(captured[0]).fetchall()})
    database = tmp_path / 'registry-cross-sqlite.db'
    with sqlite3.connect(database) as destination:
        conn.backup(destination)
    corpus = tmp_path / 'registry-statements.json'
    corpus.write_text(json.dumps(cases))
    runner = r'''
import json, sqlite3, sys, unicodedata
from datetime import date, datetime
from pathlib import Path
conn = sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)
conn.create_function('registry_normalize', 1,
    lambda text: ' '.join(unicodedata.normalize('NFKC',str(text)).casefold().split()), deterministic=True)
conn.create_function('registry_due_day', 1,
    lambda value: date.fromisoformat(value).isoformat() if value else None, deterministic=True)
conn.create_function('registry_elapsed_days', 2,
    lambda created, closed: (datetime.fromisoformat(closed)-datetime.fromisoformat(created)).total_seconds()/86400
        if closed is not None else None, deterministic=True)
cases = json.loads(Path(sys.argv[2]).read_text())
for case in cases:
    try:
        actual = [list(row) for row in conn.execute(case['sql'],case['params']).fetchall()]
    except sqlite3.Error as exc:
        raise RuntimeError(f"SQLite {sqlite3.sqlite_version}, {case['label']}: {exc}") from None
    assert actual == case['expected'], f"SQLite {sqlite3.sqlite_version}, {case['label']}: different results"
conn.close()
print(json.dumps({'sqlite':sqlite3.sqlite_version,'statements':len(cases)}))
'''
    system_python = Path('/usr/bin/python3')
    executable = str(system_python) if system_python.exists() else sys.executable
    result = subprocess.run([executable, '-c', runner, str(database), str(corpus)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['statements'] == 90
