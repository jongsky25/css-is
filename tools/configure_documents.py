"""Offline, explicit bootstrap for a copied acceptance database; never sends mail.

Run from the repository root:
python tools/configure_documents.py --db /path/to/acceptance.db --grant-admin ACCOUNT_ID --reason 'Named by records owner'
Operational enablement remains a D12 decision; this command does not enable it.
"""
import argparse
import pathlib
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import storage as st
import documents_permissions as permissions
from documents_storage import transaction,event
import tzutil as tz


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True)
    parser.add_argument('--grant-admin',required=True,type=int)
    parser.add_argument('--reason',required=True)
    args=parser.parse_args()
    if not pathlib.Path(args.db).is_file():
        parser.error('Choose an existing database copy.')
    if not args.reason.strip():
        parser.error('Record the owner authorization for this bootstrap.')
    conn=st.connect(args.db);st.init_db(conn)
    try:
        with transaction(conn):
            account=permissions.actor(conn,{'id':args.grant_admin})
            for role in ('grant_admin','workflow_admin'):
                if not permissions.has_role(conn,account,role):
                    conn.execute('INSERT INTO document_role_grant(user_id,role,granted_by,created_at) VALUES (?,?,?,?)',
                                 (account['id'],role,account['id'],tz.now_iso()))
            event(conn,None,account,'bootstrap_grants',{'authorization':args.reason,'method':'offline database operator'})
        print('Named workflow/grant administrator recorded. Module and send switches were not changed.')
    finally:
        conn.close()


if __name__=='__main__':
    main()
