#!/usr/bin/env python3
"""Rehearse an explicit document plan on a new SQLite copy; never writes the source."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage as st
import work_compat


def rehearse(source, destination, plan, actor_id):
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    if source == destination:
        raise ValueError('The destination must be a new database copy.')
    if not isinstance(plan, list) or not plan:
        raise ValueError('Provide a nonempty explicit list of document decisions.')
    ids = [int(item['document_id']) for item in plan]
    if len(set(ids)) != len(ids):
        raise ValueError('List each document once; grouping is not inferred.')
    # Exclusive creation also refuses existing files and symlinks.
    with destination.open('xb'):
        pass
    source_conn = sqlite3.connect('file:' + quote(str(source)) + '?mode=ro', uri=True)
    copy = st.connect(str(destination))
    try:
        source_conn.backup(copy)
        st.init_db(copy)
        st.set_setting(copy, 'documents.enabled', '1')
        st.set_setting(copy, 'work.enabled', '1')
        st.set_setting(copy, 'documents.sending_enabled', '0')
        results = []
        for item in plan:
            report = work_compat.migrate(copy, {'id': actor_id}, int(item['document_id']), int(item['revision']),
                                         item['outcome'], item['reason'])
            again = work_compat.migrate(copy, {'id': actor_id}, int(item['document_id']), int(item['revision']),
                                        item['outcome'], item['reason'])
            if report != again or not report['source_rows_preserved']:
                raise RuntimeError('Reconciliation or repeat migration failed.')
            for row in report['contributors']:
                expected_owner = None if row['source_status']=='proposed' else row['source_owner_id']
                if not (row['current_status']==row['initial_task_status'] and row['owner_id']==expected_owner
                        and row['due_date']==row['source_due_date'] and row['mandatory']==row['source_mandatory']
                        and row['initial_evidence_preserved']):
                    raise RuntimeError('Owner, status, date, mandatory flag, or evidence did not reconcile.')
            results.append(report)
        return {'rehearsal_only': True, 'source': str(source), 'destination': str(destination),
                'repeat_migration_verified': True, 'documents': results}
    finally:
        copy.close()
        source_conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--plan', required=True, help='JSON list: document_id, revision, outcome, reason')
    parser.add_argument('--actor-id', type=int, required=True, help='Existing concerned officer on the copied database')
    args = parser.parse_args()
    try:
        report = rehearse(args.source, args.destination, json.loads(Path(args.plan).read_text()), args.actor_id)
    except Exception as exc:
        print('Rehearsal failed: ' + str(exc) + '. Any created destination is an incomplete rehearsal, not ready for use.', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
