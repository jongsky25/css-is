import json,sqlite3,tempfile,time,statistics,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import storage
statements=['PRAGMA busy_timeout = 5000','PRAGMA foreign_keys = ON','PRAGMA journal_mode = WAL','PRAGMA synchronous = NORMAL']
rows=[]
with tempfile.TemporaryDirectory(prefix='avatar-sqlite-setup-') as d:
 path=Path(d)/'fixture.db';c=storage.connect(str(path));storage.init_db(c);schema_count=c.execute('select count(*) from sqlite_master').fetchone()[0];c.close()
 for mode in ['full','without_wal','without_wal','full']:
  for run in range(50):
   start=time.thread_time_ns();c=sqlite3.connect(str(path));open_ns=time.thread_time_ns()-start;steps=[]
   for sql in statements:
    if mode=='without_wal' and sql=='PRAGMA journal_mode = WAL':continue
    start=time.thread_time_ns();c.execute(sql);steps.append({'sql':sql,'cpu_ns':time.thread_time_ns()-start})
   # Verify connection settings only after the timed setup.
   settings={key:c.execute('PRAGMA '+key).fetchone()[0] for key in ['journal_mode','foreign_keys','synchronous','busy_timeout']}
   start=time.thread_time_ns();c.close();close_ns=time.thread_time_ns()-start
   rows.append({'block':len(rows)//50,'mode':mode,'run':run,'open_cpu_ns':open_ns,'steps':steps,'close_cpu_ns':close_ns,'settings':settings})
result={'acceptance':False,'scope':'Serial fresh connections to a newly created synthetic current schema; no browser, no production DB or product edit. Full/no-WAL/no-WAL/full fixed blocks, 50 samples each. Skipping WAL is a diagnostic ablation after initial WAL setup, not a proposed safe product policy. Per-connection PRAGMAs and observed settings retained.','sqlite_version':sqlite3.sqlite_version,'storage_sha256':hashlib.sha256(Path('storage.py').read_bytes()).hexdigest(),'schema_objects':schema_count,'samples':rows}
Path('docs/avatars/increment2b/navigation-cpu-v2/sqlite-setup-probe.json').write_text(json.dumps(result,indent=2)+'\n')
for block in range(4):
 group=rows[block*50:(block+1)*50]
 print(block,group[0]['mode'],'median_setup_ms',statistics.median(sum(s['cpu_ns'] for s in r['steps'])+r['open_cpu_ns'] for r in group)/1e6)
 for sql in statements:
  vals=[s['cpu_ns']/1e6 for r in group for s in r['steps'] if s['sql']==sql]
  if vals:print(sql,statistics.median(vals))
 assert all(r['settings']=={'journal_mode':'wal','foreign_keys':1,'synchronous':1,'busy_timeout':5000} for r in group)
