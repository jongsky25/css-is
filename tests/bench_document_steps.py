"""Opt-in synthetic benchmark, not collected by the normal test suite.

Run explicitly with cloud_workspace.py test tests/bench_document_steps.py -s.
Compares shipped 6452931 with the working tree on identical disposable fixtures.
No real database, provider, browser or notification calls are used.
"""
import json
import cProfile
import pstats
import io
import statistics
import subprocess
import time
import tracemalloc
import types
import sys
from pathlib import Path

import pytest
import documents_actions as candidate
from tests.test_documents import registry
from tests.test_document_registry_pagination import seed_many


class MeasuredCursor:
    def __init__(self,cursor,metrics):
        self.cursor=cursor;self.metrics=metrics

    def __getattr__(self,key):return getattr(self.cursor,key)

    def record(self,rows):
        self.metrics['rows']+=len(rows)
        self.metrics['logical_bytes']+=sum(sum(len(str(v).encode()) for v in row if v is not None) for row in rows)
        return rows

    def fetchone(self):
        row=self.cursor.fetchone()
        if row is not None:self.record([row])
        return row

    def fetchall(self):return self.record(self.cursor.fetchall())
    def fetchmany(self,*args):return self.record(self.cursor.fetchmany(*args))
    def __iter__(self):return self
    def __next__(self):return self.record([next(self.cursor)])[0]


class MeasuredConnection:
    def __init__(self,conn):
        self.conn=conn;self.metrics={'rows':0,'logical_bytes':0}

    def __getattr__(self,key):return getattr(self.conn,key)
    def execute(self,*args):return MeasuredCursor(self.conn.execute(*args),self.metrics)


def shipped():
    # Pin every changed read module, not just the entry point: otherwise a
    # candidate helper optimization also changes the supposedly shipped baseline.
    modules={}
    for name in ('documents_actions','documents_guidance','work_review','work_completion','work'):
        source=subprocess.run(['git','show',f'6452931b25d953b10a20dcea4750003e2ecd147d:{name}.py'],
                              check=True,text=True,capture_output=True).stdout
        module=types.ModuleType('shipped_'+name)
        exec(compile(source,'shipped_'+name+'.py','exec'),module.__dict__)
        modules[name]=module
    for module in modules.values():
        for alias,value in list(module.__dict__.items()):
            if isinstance(value,types.ModuleType) and value.__name__ in modules:
                module.__dict__[alias]=modules[value.__name__]
    return modules['documents_actions']


def seed_scenario(c,u,unit,size,scenario):
    ids=seed_many(c,u[0],unit,size)
    c.execute("UPDATE document SET lead_id=?,instruction_state='routed'",(u[0]['id'],))
    if scenario=='linked_contributions':
        c.execute("UPDATE document SET direction='IN',policy_json=?",(json.dumps({'closure':[]}),))
        c.executemany("""INSERT INTO work_case(id,title,outcome,unit_id,creator_id,created_at,updated_at)
            VALUES (?,'Synthetic linked case','Synthetic',?,?,'2026-11-01','2026-11-01')""",[(did,unit,u[0]['id']) for did in ids])
        c.executemany("INSERT INTO work_document VALUES (?,?,'reference',?,'2026-11-01')",[(did,did,u[0]['id']) for did in ids])
        c.executemany("""INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at)
            VALUES (?,?,'contributor','Synthetic','assigned','2026-11-01')""",[(did,u[0]['id']) for did in ids])
    elif scenario=='restricted_aliases':
        for n,did in enumerate(ids):
            if n%3==0:c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(did,))
            elif n%3==1:c.execute('UPDATE document SET canonical_id=? WHERE id=?',(ids[n+1] if n+1<len(ids) else ids[0],did))
    if scenario == 'review_release_graph':
        import work_review
        # Ten linked outgoing sources and three accepted tasks per case. Every
        # source has a current review packet and reaches the release gate.
        for start in range(0,len(ids),10):
            group=ids[start:start+10];cid=group[0]
            c.execute("INSERT INTO work_case(id,title,outcome,unit_id,creator_id,created_at,updated_at) VALUES (?,'Graph','Synthetic',?,?,'2026-11-01','2026-11-01')",(cid,unit,u[0]['id']))
            for did in group:
                c.execute("INSERT INTO work_document VALUES (?,?,'reference',?,'2026-11-01')",(cid,did,u[0]['id']))
                c.execute("INSERT INTO document_file_version(id,document_id,url,file_id,fingerprint,role,actor_id,created_at) VALUES (?,?,'https://example.test/draft','fake','hash','draft',?,'2026-11-01')",(did,did,u[0]['id']))
                c.execute("UPDATE document SET current_version=?,approved_version=?,status='approved',policy_json=? WHERE id=?",(did,did,json.dumps({'closure':[],'signature_required':False,'release':[],'ack_required':False}),did))
            for n in range(3):
                c.execute("INSERT INTO work_task(case_id,title,expected_output,unit_id,creator_id,status,submission,created_at,updated_at) VALUES (?,'Accepted task','Synthetic',?,?,'done','Synthetic evidence','2026-11-01','2026-11-01')",(cid,unit,u[0]['id']))
            for did in group:
                snapshot,digest=work_review.snapshot(c,cid,did)
                c.execute("INSERT INTO work_review_packet(case_id,document_id,version_id,reviewer_id,actor_id,snapshot_json,snapshot_hash,reason,created_at) VALUES (?,?,?,?,?,?,?,'Synthetic benchmark','2026-11-01')",(cid,did,did,u[0]['id'],u[0]['id'],json.dumps(snapshot),digest))
    c.commit()


def retained_bytes(value,seen=None):
    """Count the membership graph once, including shared tuple/string references."""
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value))
    total=sys.getsizeof(value)
    if isinstance(value,dict):
        total+=sum(retained_bytes(k,seen)+retained_bytes(v,seen) for k,v in value.items())
    elif isinstance(value,(tuple,list)):
        total+=sum(retained_bytes(v,seen) for v in value)
    return total


def process_rss_bytes():
    # Linux snapshot includes interpreter, SQLite and previously allocated arenas.
    # It is not an isolated cache delta or a peak-memory claim.
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024
    raise AssertionError('Process RSS is unavailable on this benchmark host.')


@pytest.mark.parametrize('scenario',['ordinary','linked_contributions','restricted_aliases','review_release_graph'])
@pytest.mark.parametrize('size',[100,1000,10000])
def test_measure_document_steps(registry,size,scenario,tmp_path):
    candidate.clear_step_indexes()
    c,u,unit,_=registry;seed_scenario(c,u,unit,size,scenario)
    result={'size':size,'scenario':scenario,'samples':30,'page_size':30}
    for name,module in [('baseline',shipped()),('candidate',candidate)]:
        if name=='candidate':candidate.clear_step_indexes()
        start=time.perf_counter();module.page(c,u[0],today='2026-11-07');cold=time.perf_counter()-start
        samples=[]
        for _ in range(30):
            start=time.perf_counter();module.page(c,u[0],today='2026-11-07');samples.append(time.perf_counter()-start)
        rss=process_rss_bytes()
        resident=retained_bytes(candidate._INDEXES) if name=='candidate' else 0
        sql=[];c.set_trace_callback(sql.append)
        module.page(c,u[0],today='2026-11-07')
        c.set_trace_callback(None)
        # Do not charge retained SQL trace strings to application peak memory.
        tracemalloc.start();module.page(c,u[0],today='2026-11-07');_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        measured=MeasuredConnection(c);module.page(measured,u[0],today='2026-11-07')
        query=next(s for s in sql if 'action_candidates AS (' in s)
        plan=[row[3] for row in c.execute('EXPLAIN QUERY PLAN '+query)]
        profile=cProfile.Profile();profile.runcall(module.page,c,u[0],today='2026-11-07')
        stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(15)
        (tmp_path/f'{name}-profile.txt').write_text(stream.getvalue())
        misses=[]
        if name=='candidate':
            for _ in range(30):
                # Real committed dependency changes, not just a manual cache clear.
                c.execute('UPDATE document SET revision=revision+1 WHERE id=(SELECT MIN(id) FROM document)');c.commit()
                start=time.perf_counter();module.page(c,u[0],today='2026-11-07');misses.append(time.perf_counter()-start)
            c.execute('UPDATE document SET revision=revision+1 WHERE id=(SELECT MIN(id) FROM document)');c.commit()
            profile=cProfile.Profile();profile.runcall(module.page,c,u[0],today='2026-11-07')
            stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(30)
            (tmp_path/'candidate-cold-profile.txt').write_text(stream.getvalue())
        result[name]={'first_ms':round(cold*1000,3),'median_ms':round(statistics.median(samples)*1000,3),
                      'p95_ms':round(sorted(samples)[28]*1000,3),'python_peak_bytes':peak,
                      'resident_index_python_bytes':resident,'process_rss_bytes':rss,
                      'queries':sum(s.lstrip().upper().startswith(('SELECT','WITH')) for s in sql),
                      **measured.metrics,'plan':plan,
                      'invalidation_miss_samples':len(misses),
                      'invalidation_miss_p95_ms':round(sorted(misses)[28]*1000,3) if misses else None,
                      'invalidation_miss_median_ms':round(statistics.median(misses)*1000,3) if misses else None}
    (tmp_path/'result.json').write_text(json.dumps(result,indent=2))
    print('DOCUMENT_STEPS_BENCHMARK '+json.dumps(result),flush=True)
