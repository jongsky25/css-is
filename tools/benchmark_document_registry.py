"""Compare frozen legacy reads with paginated reads on a temporary synthetic DB.

Run with the pinned test Python from the repository root. Never opens production
data. Timings are local observations, not a production capacity prediction.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import sqlite3
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import documents as docs
import documents_registry
import storage as st
from tests.document_registry_reference import legacy_visible, legacy_metrics


def measure(conn, operation):
    statements = []
    conn.set_trace_callback(lambda sql: statements.append(sql) if sql.lstrip().upper().startswith(('SELECT', 'WITH')) else None)
    try:
        operation()
    finally:
        conn.set_trace_callback(None)
    started = time.perf_counter()
    result = operation()
    elapsed = time.perf_counter() - started
    return result, {'select_statements': len(statements), 'elapsed_ms': round(elapsed * 1000, 2)}


def run(size):
    with tempfile.TemporaryDirectory(prefix='registry-benchmark-') as directory:
        conn = st.connect(str(Path(directory) / 'synthetic.db'))
        try:
            st.init_db(conn)
            owner = st.create_admin_user(conn, 'owner@example.test', 'hash', 'salt', 'viewer', active=True)
            viewer_id = st.create_admin_user(conn, 'reader@example.test', 'hash', 'salt', 'admin', active=True)
            viewer = st.get_admin_user_by_id(conn, viewer_id)
            unit = st.add_org_unit(conn, 'Synthetic Division', 'division', 'SYNTHETIC/D1')
            conn.executemany('''INSERT INTO document(id,number,direction,subject,type,sender,creator_id,unit_id,
                verification,status,visibility,matches_json,created_at,updated_at)
                VALUES(?,?,'OUT',?,'memo','Synthetic office',?,?,'verified','registered',?,'{}',
                  '2026-10-20T09:00:00','2026-10-20T09:00:00')''',
                [(n, f'SYNTH-{n}', f'Needle synthetic record {n}', owner, unit,
                  'bureau' if n % 2 == 0 else 'restricted') for n in range(1, size + 1)])
            conn.commit()
            observations = []
            for query in ('', 'Needle'):
                def previous():
                    found = legacy_visible(conn, viewer, query)
                    return found, legacy_metrics(conn, found)
                (old, old_metrics), baseline = measure(conn, previous)
                fetched = []
                original = documents_registry.rows
                def observed(connection, sql, args=()):
                    result = original(connection, sql, args)
                    if 'registry_sort_id' in sql:
                        fetched.append(len(result))
                    return result
                with patch.object(documents_registry, 'rows', observed):
                    page, current = measure(conn, lambda: docs.list_page(conn, viewer, query))
                assert [d['id'] for d in page['documents']] == [d['id'] for d in old[:30]]
                assert page['total'] == len(old) and page['metrics'] == old_metrics
                baseline['registry_rows_fetched'] = size
                current['registry_rows_fetched'] = max(fetched, default=0)
                observations.append({'records': size, 'query': query, 'permitted_matches': len(old),
                                     'legacy': baseline, 'paginated': current})
            return observations
        finally:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[500, 5000])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if any(size < 1 or size > 50000 for size in args.sizes):
        parser.error('Use synthetic sizes between 1 and 50000 records.')
    report = {'method': 'synthetic SQLite; half verified bureau, half restricted; no private grants; '
                        'includes full-register measures; counts from one traced read; elapsed_ms from '
                        'one subsequent warm untraced read; not a production capacity estimate',
              'environment': {'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version,
                              'observed_at': datetime.now(timezone.utc).isoformat()},
              'observations': [row for size in args.sizes for row in run(size)]}
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
