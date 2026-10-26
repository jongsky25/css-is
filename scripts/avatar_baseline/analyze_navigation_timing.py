"""Independent audit of fixed eight-slot natural collection timing diagnosis."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

from scripts.avatar_baseline.analyze_paired_variance import (
    REFS, expected_fixture, required_sources, slot_points, source,
)

BLOCKS = [['original','current','current','original'], ['current','original','original','current']]
PROBE = 'tests/test_avatar_navigation_timing_browser.py'
HARNESS = ['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',PROBE]
BUDGET = 10*1024*1024


def phase_interval(events, pid, before, after):
    if not (math.isfinite(before) and math.isfinite(after) and before < after):
        raise ValueError('Invalid observation interval')
    gc = []
    for e in events:
        if e.get('pid') != pid or e.get('name') != 'MajorGC':continue
        if e.get('ph') != 'X' or type(e.get('dur')) not in (int,float) or not math.isfinite(e['dur']) or e['dur'] < 0:
            raise ValueError('Unsupported MajorGC event')
        gc.append((e['ts'], e['ts']+e['dur']))
    overlap = any(start <= after and finish >= before for start,finish in gc)
    completed = [finish for _,finish in gc if finish < before]
    if not completed:return {'phase':None,'age_ms':None,'gc_overlap':overlap}
    last = max(completed); low,high = (before-last)/1000,(after-last)/1000
    def bucket(age):return 0 if age < 1000 else 1 if age < 3000 else 2
    phase = bucket(low) if not overlap and bucket(low)==bucket(high) else None
    return {'phase':phase,'age_ms':[low,high],'gc_overlap':overlap}


def timing(events, records):
    if any(e.get('args',{}).get('forced') for e in events):raise ValueError('Forced collection')
    if not any('cppgc' in e.get('cat','').lower() for e in events):raise ValueError('Missing C++ GC trace')
    pids = {e['pid'] for e in events if e.get('name')=='CommitLoad'
            and e.get('args',{}).get('data',{}).get('url','').startswith('http://127.0.0.1:')}
    if len(pids)!=1:raise ValueError('Ambiguous app renderer')
    pid = next(iter(pids))
    clocks = [e for e in events if e.get('name')=='clock_sync']
    markers = {e['args']['sync_id']:e['ts'] for e in clocks}
    expected = {f'nav-{m}-{side}' for m in range(1,21) for side in ['before','after']}
    if len(clocks)!=40 or set(markers)!=expected:raise ValueError('Incomplete or duplicate clock markers')
    if [r['mount'] for r in records]!=list(range(1,21)):raise ValueError('Incomplete navigation sequence')
    output=[]; previous=0
    for r in records:
        mount=r['mount']; before,after=[markers[f'nav-{mount}-{side}'] for side in ['before','after']]
        if before <= previous:raise ValueError('Nonchronological navigation markers')
        previous=after
        times=[r[k] for k in ['start_ns','dom_start_ns','dom_end_ns','heap_end_ns','finish_ns']]
        if any(type(t) is not int for t in times) or times!=sorted(times) or times[-1]<=times[0]:
            raise ValueError('Invalid host timing')
        if output and times[0]<=records[len(output)-1]['finish_ns']:raise ValueError('Overlapping host probes')
        docs,nodes,heap = r['dom']['documents'],r['dom']['nodes'],r['heap']['usedSize']
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in [docs,nodes,heap]):
            raise ValueError('Invalid memory observation')
        output.append({'mount':mount,'documents':docs,'nodes':nodes,'js_heap_bytes':heap,
            'probe_ms':(times[-1]-times[0])/1e6,'trace_interval_ms':(after-before)/1000,
            **phase_interval(events,pid,before,after)})
    return {'app_pid':pid,'navigation':output,
        'overhead_ms':{'total':sum(r['probe_ms'] for r in output),
            'median':statistics.median(r['probe_ms'] for r in output),
            'max':max(r['probe_ms'] for r in output)}}


def compare(left, right):
    records=[]
    for a,b in zip(left['navigation'],right['navigation']):
        if a['mount']!=b['mount']:raise ValueError('Mismatched navigation ordinal')
        records.append({'mount':a['mount'],'left_phase':a['phase'],'right_phase':b['phase'],
            'phase_matched':a['phase'] is not None and a['phase']==b['phase'],
            'documents_delta':b['documents']-a['documents'],
            'nodes_delta':b['nodes']-a['nodes'],
            'js_heap_delta_bytes':b['js_heap_bytes']-a['js_heap_bytes']})
    return records


def audit(root, repo, ref):
    result={'acceptance':False,'status':'inconclusive','errors':[], 'source_hashes_verified':0,
            'files_verified':0,'cohorts':[]}
    try:
        plan=json.loads((root/'experiment.json').read_text())
        if (plan['protocol']!='navigation-timing-v1' or plan['acceptance'] is not False or
            plan['harness_commit']!=ref or plan['refs']!=REFS or plan['blocks']!=BLOCKS or
            plan['samples_per_slot']!=1 or plan['seconds']!=30 or plan['browser']!='156.0.8078.47' or
            plan['budget_bytes']!=BUDGET or plan['fixture_adapter']!='sample-ordinal-v1' or len(plan['cohorts'])!=8):
            raise ValueError('Protocol identity mismatch')
        for name in HARNESS:
            if (root/'harness'/name).read_bytes()!=expected_fixture(repo,ref,name):raise ValueError('Harness mismatch')
        for index,entry in enumerate(plan['cohorts']):
            block,position=divmod(index,4);arm=BLOCKS[block][position]
            if any(entry.get(k)!=v for k,v in dict(index=index,block=block,position=position,arm=arm,exit_code=0).items()):
                raise ValueError('Failed or misidentified slot '+str(index))
            folder=root/f'{index:02d}-{arm}'
            files=entry['files_sha256']
            required={'False-warm.json','environment.json','runner.txt','junit.xml',
                      'navigation-timing.json','navigation-trace.json.gz','timing-provenance.json'}
            if not required<=set(files):raise ValueError('Missing required evidence')
            for name,digest in files.items():
                if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
                    raise ValueError('Evidence hash mismatch')
                result['files_verified']+=1
            env=json.loads((folder/'environment.json').read_text())
            if env['source_commit']!=REFS[arm] or env['chromium']!='156.0.8078.47' or set(env['source_sha256'])!=required_sources(repo,REFS[arm]):
                raise ValueError('Source environment mismatch')
            for name,digest in env['source_sha256'].items():
                data=expected_fixture(repo,ref,name) if name in HARNESS else source(repo,REFS[arm],name)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Product source mismatch')
                result['source_hashes_verified']+=1
            provenance=json.loads((folder/'timing-provenance.json').read_text())
            if (provenance['acceptance'] is not False or provenance['native_sampling'] is not False or
                provenance['allocator_dumps'] is not False or provenance['snapshots']!=13 or
                provenance['navigation_observations']!=20 or provenance['trace_completion'].get('dataLossOccurred') or
                provenance['probe_sha256']!=hashlib.sha256(source(repo,ref,PROBE)).hexdigest()):
                raise ValueError('Invalid probe provenance')
            result['source_hashes_verified']+=1
            raw=folder/'False-warm.json'
            if entry['raw_sha256']!=hashlib.sha256(raw.read_bytes()).hexdigest():raise ValueError('Raw identity mismatch')
            points=slot_points(json.loads(raw.read_text()),block)
            events=json.load(gzip.open(folder/'navigation-trace.json.gz','rt'))['traceEvents']
            observation=timing(events,json.loads((folder/'navigation-timing.json').read_text()))
            rawrows=json.loads(raw.read_text())
            for snap in [*rawrows[0]['scenarios'].values(),*rawrows[0]['navigation_trend']]:
                if observation['app_pid'] not in [d['pid'] for d in snap['renderer_memory_detail']]:
                    raise ValueError('Trace app PID absent from baseline renderer observations')
            result['cohorts'].append({'index':index,'arm':arm,'points':points,**observation})
        cohorts=result['cohorts']
        for checkpoint in cohorts[0]['points']:
            counts=[c['points'][checkpoint]['renderer_counts'] for c in cohorts]
            if any(c!=counts[0] for c in counts) or counts[0][0]<=0:raise ValueError('Unmatched renderer counts')
        result['source_pairs']=[]
        for left,right in [(0,1),(2,3),(4,5),(6,7)]:
            original,current=(left,right) if cohorts[left]['arm']=='original' else (right,left)
            result['source_pairs'].append({'original':original,'current':current,
                'order':'forward' if original==left else 'reverse',
                'records':compare(cohorts[original],cohorts[current])})
        result['negative_controls']=[]
        for early,late in [(0,3),(1,2),(4,7),(5,6)]:
            baseline=[]
            for checkpoint,point in cohorts[early]['points'].items():
                for metric in ['renderer_rss_sum_bytes','js_heap_bytes']:
                    delta=cohorts[late]['points'][checkpoint][metric]['samples'][0]-point[metric]['samples'][0]
                    baseline.append({'checkpoint':checkpoint,'metric':metric,'delta_bytes':delta,'within_absolute_10_mib':abs(delta)<=BUDGET})
            result['negative_controls'].append({'arm':cohorts[early]['arm'],'early':early,'late':late,
                'records':compare(cohorts[early],cohorts[late]),'baseline_differences':baseline})
        result['status']='complete_descriptive_diagnostic'
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as error:
        result['errors'].append(repr(error))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--harness-ref',required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse',args.harness_ref],cwd=repo,text=True).strip()
    result=audit(args.root,repo,ref);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','errors','source_hashes_verified','files_verified']}))
    sys.exit(bool(result['errors']))
