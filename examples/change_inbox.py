"""Collect one change-feed page into a durable local inbox; never writes upstream."""
import argparse
import json
import os
from pathlib import Path
import sqlite3

if __package__:
    from .read_api import ReadClient, ApiFailure
else:
    from read_api import ReadClient, ApiFailure


def collect(client,path,resource,limit=25):
    if client.credential is None:
        raise ValueError('Use a delegated read credential for this example.')
    # Refuse to share saved checkpoints across a site, credential or family.
    binding=json.dumps([client.base_url,client.credential[8:40],resource],separators=(',',':'))
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        os.close(fd)
    except FileExistsError:
        pass
    conn=sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),binding TEXT NOT NULL,cursor TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS notice(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        saved=conn.execute('SELECT binding,cursor FROM state WHERE singleton=1').fetchone()
        if saved and saved[0]!=binding:
            raise ValueError('Choose a separate inbox for this site, credential and resource family.')
        page=client.changes(resource,cursor=saved[1] if saved else '',limit=limit)
        # Both durable notices and progress commit, or neither does. Retrying an
        # old checkpoint cannot add the same notice twice.
        with conn:
            for notice in page['data']:
                conn.execute('INSERT OR IGNORE INTO notice VALUES(?,?)',(notice['id'],json.dumps(notice,sort_keys=True)))
            conn.execute('INSERT OR REPLACE INTO state VALUES(1,?,?)',(binding,page['next_cursor']))
        return {'initialized':page['initialized'],'received':len(page['data']),'has_more':page['has_more']}
    finally:
        conn.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--credential-file',required=True)
    parser.add_argument('--inbox',required=True,help='Private local SQLite inbox; one per site/credential/family')
    parser.add_argument('--resource',choices=('documents','work-items'),required=True)
    parser.add_argument('--limit',type=int,default=25)
    args=parser.parse_args()
    try:
        token=Path(args.credential_file).read_text().strip()
        result=collect(ReadClient(args.base_url,credential=token),args.inbox,args.resource,args.limit)
        print(json.dumps(result))
    except (ApiFailure,ValueError,OSError,sqlite3.Error):
        parser.exit(1,'The inbox was not advanced. Check access and checkpoint recovery guidance; keep the saved inbox.\n')


if __name__=='__main__':
    main()
