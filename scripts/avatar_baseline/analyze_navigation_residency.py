"""Audit natural allocator dumps against bounded clock intervals and RSS samples."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from scripts.avatar_baseline.analyze_paired_variance import REFS, expected_fixture, required_sources, slot_points, source
from scripts.avatar_baseline.analyze_residency import allocator_family

BLOCKS=[['original','current','current','original'],['current','original','original','current']]
PROBE='tests/test_avatar_navigation_residency_browser.py'
HARNESS=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',PROBE]
BUDGET=10*1024*1024


def join_dump(events,pid,before,after):
    groups={}
    for e in events:
        alloc=e.get('args',{}).get('dumps',{}).get('allocators')
        if e.get('ph')!='v' or e.get('pid')!=pid or not alloc or not before<=e['ts']<=after:continue
        key=(e['id'],e['ts']);group=groups.setdefault(key,{})
        if set(group)&set(alloc):raise ValueError('Overlapping allocator fragments')
        group.update(alloc)
    if len(groups)!=1:raise ValueError('Missing or ambiguous bounded allocator dump')
    (identity,ts),alloc=next(iter(groups.items()))
    return {'trace_id':identity,'trace_ts':ts,'allocators':{n:{k:int(v['value'],16) for k,v in d.get('attrs',{}).items() if v.get('units')=='bytes'} for n,d in alloc.items() if allocator_family(n)}}


def observation(events,records,status):
    if any(e.get('args',{}).get('forced') for e in events):raise ValueError('Forced collection observed')
    pids={e['pid'] for e in events if e.get('name')=='CommitLoad' and e.get('args',{}).get('data',{}).get('url','').startswith('http://127.0.0.1:')}
    if len(pids)!=1:raise ValueError('Ambiguous app renderer')
    pid=next(iter(pids));clocks=[e for e in events if e.get('name')=='clock_sync']
    markers={e['args']['sync_id']:e['ts'] for e in clocks}
    if len(clocks)!=40 or set(markers)!={f'nav-{m}-{s}' for m in range(1,21) for s in ['before','after']}:raise ValueError('Invalid clock markers')
    if [r['mount'] for r in records]!=list(range(1,21)):raise ValueError('Incomplete navigations')
    if not status:raise ValueError('Missing continuous status samples')
    output=[];previous=None;used=set();cpp=[e for e in events if e.get('pid')==pid and 'cppgc' in e.get('cat','').lower()]
    anchors=[]
    for r in records:
        m=r['mount'];before=markers[f'nav-{m}-before'];after=markers[f'nav-{m}-after']
        if after<=before or (previous is not None and before<=previous):raise ValueError('Nonchronological dump interval')
        if not r['dump_request'].get('success') or r['dump_request']['dumpGuid'] in used:raise ValueError('Failed or duplicate dump request')
        used.add(r['dump_request']['dumpGuid'])
        times=[*r['snapshot_interval_ns'],r['before_marker']['begin_ns'],r['before_marker']['end_ns'],r['after_marker']['begin_ns'],r['after_marker']['end_ns'],*r['after_snapshot_interval_ns']]
        if times!=sorted(times):raise ValueError('Nonchronological host probes')
        for side in ['before','after']:
            interval=r[side+'_marker'];anchors.append({'host_us':(interval['begin_ns']+interval['end_ns'])/2000,'trace_us':markers[f'nav-{m}-{side}'],'uncertainty_us':(interval['end_ns']-interval['begin_ns'])/2000})
        dump=join_dump(events,pid,before,after)
        def app(snap):
            rows=[d for d in snap['renderer_memory_detail'] if d['pid']==pid]
            if len(rows)!=1:raise ValueError('App PID missing from snapshot')
            return rows[0]
        natural=[e for e in events if e.get('pid')==pid and (previous or before)<e.get('ts',0)<before]
        during=[e for e in events if e.get('pid')==pid and before<=e.get('ts',0)<=after]
        output.append({'mount':m,'before_trace_us':before,'after_trace_us':after,'dump_ms':(after-before)/1000,
            'snapshot':{'app':app(r['snapshot']),'rss':r['snapshot']['renderer_rss_sum_bytes'],'heap':r['snapshot']['js_heap_bytes'],'dom':r['snapshot']['dom_counters'],'lcp_ms':r['snapshot']['lcp_ms'],'long_tasks':r['snapshot']['long_tasks']},
            'after_dump':{'app':app(r['after_dump_snapshot']),'rss':r['after_dump_snapshot']['renderer_rss_sum_bytes'],'heap':r['after_dump_snapshot']['js_heap_bytes'],'dom':r['after_dump_snapshot']['dom_counters']},
            **dump,'between_dump_gc_counts':dict(collections.Counter(e['name'] for e in natural if 'gc' in e.get('cat','').lower() or e.get('name') in ['MajorGC','MinorGC'])),
            'during_dump_gc_counts':dict(collections.Counter(e['name'] for e in during if 'gc' in e.get('cat','').lower() or e.get('name') in ['MajorGC','MinorGC']))})
        previous=after
    sampled=[];drops=[]
    for item in status:
        if item['end_ns']<item['begin_ns']:raise ValueError('Invalid status interval')
        rows=[d for d in item['renderers'] if d['pid']==pid]
        if len(rows)>1:raise ValueError('Duplicate sampled PID')
        if not rows:continue
        host=(item['begin_ns']+item['end_ns'])/2000
        anchor=min(anchors,key=lambda a:abs(a['host_us']-host))
        estimate=anchor['trace_us']+host-anchor['host_us'];uncertainty=anchor['uncertainty_us']+(item['end_ns']-item['begin_ns'])/2000
        value={'begin_ns':item['begin_ns'],'end_ns':item['end_ns'],'trace_estimate_us':estimate,'alignment_uncertainty_us':uncertainty,'status':rows[0]['status']}
        if sampled:
            prior=sampled[-1]
            if value['begin_ns']<=prior['end_ns']:raise ValueError('Overlapping status polls')
            delta=value['status']['VmRSS']-prior['status']['VmRSS']
            if delta<=-5*1024*1024:
                low=prior['trace_estimate_us']-prior['alignment_uncertainty_us'];high=estimate+uncertainty
                nearby=[e for e in events if e.get('pid')==pid and e.get('ts',0)<=high and e.get('ts',0)+e.get('dur',0)>=low and ('gc' in e.get('cat','').lower() or e.get('name') in ['MajorGC','MinorGC'])]
                drops.append({'delta_bytes':delta,'status_deltas':{k:value['status'][k]-prior['status'][k] for k in value['status']},'trace_interval_with_uncertainty_us':[low,high],
                    'overlapping_dump_mounts':[p['mount'] for p in output if p['before_trace_us']<=high and p['after_trace_us']>=low],
                    'overlapping_gc_events':nearby,'host_interval_ns':[prior['begin_ns'],item['end_ns']]})
        sampled.append(value)
    if len(sampled)<2:raise ValueError('Insufficient app status samples')
    return {'app_pid':pid,'navigation':output,'status_samples':sampled,'rss_drops_at_least_5_mib':drops,'cpp_gc_event_count':len(cpp),
        'max_clock_roundtrip_ms':max(a['uncertainty_us'] for a in anchors)/500,
        'interpretation':'Clock estimates use nearest sync midpoint plus explicit request uncertainty, not exact GC attribution. Dump intervals are separate from navigation intervals. Allocator families overlap; do not sum or subtract from RSS. No acceptance claim.'}



def capture_issue(entry,provenance):
    if provenance['trace_completion'].get('dataLossOccurred'):return 'Trace data loss; retained but excluded from correlation, not replaced'
    if entry['exit_code']!=0:return 'Workload failed; retained but not valid evidence'
    return None


def pair_comparisons(cohorts):
    by_index={c['index']:c for c in cohorts};output=[]
    for name,left,right in [('block0-source-forward',0,1),('block0-source-reverse',3,2),
                            ('block0-original-control',0,3),('block0-current-control',1,2),
                            ('block1-source-reverse',5,4),('block1-source-forward',6,7),
                            ('block1-original-control',5,6),('block1-current-control',4,7)]:
        a,b=by_index[left],by_index[right]
        row={'name':name,'left':left,'right':right,'acceptance':False}
        if a['status']!='valid_capture' or b['status']!='valid_capture':
            row.update(status='unavailable_invalid_capture',navigation=[])
        else:
            rows=[]
            for x,y in zip(a['navigation'],b['navigation']):
                assert x['mount']==y['mount']
                delta={family:{attr:y['allocators'][family][attr]-value for attr,value in values.items() if attr in y['allocators'][family]} for family,values in x['allocators'].items() if family in y['allocators']}
                rows.append({'mount':x['mount'],'app_rss_delta':y['snapshot']['app']['status']['VmRSS']-x['snapshot']['app']['status']['VmRSS'],
                    'js_heap_delta':y['snapshot']['heap']-x['snapshot']['heap'],'allocator_deltas':delta})
            row.update(status='descriptive_only',navigation=rows)
        output.append(row)
    return output


def audit(root, repo, ref):
    result={'acceptance':False,'status':'inconclusive','errors':[], 'source_hashes_verified':0,
            'files_verified':0,'cohorts':[]}
    try:
        plan=json.loads((root/'experiment.json').read_text())
        if (plan['protocol']!='navigation-residency-v2' or plan['acceptance'] is not False or
            plan['harness_commit']!=ref or plan['refs']!=REFS or plan['blocks']!=BLOCKS or
            plan['samples_per_slot']!=1 or plan['seconds']!=30 or plan['browser']!='156.0.8078.47' or
            plan['budget_bytes']!=BUDGET or plan['fixture_adapter']!='sample-ordinal-v1' or len(plan['cohorts'])!=8):
            raise ValueError('Protocol identity mismatch')
        for name in HARNESS:
            if (root/'harness'/name).read_bytes()!=expected_fixture(repo,ref,name):raise ValueError('Harness mismatch')
        for index,entry in enumerate(plan['cohorts']):
            block,position=divmod(index,4);arm=BLOCKS[block][position]
            if any(entry.get(k)!=v for k,v in dict(index=index,block=block,position=position,arm=arm).items()):
                raise ValueError('Failed or misidentified slot '+str(index))
            folder=root/f'{index:02d}-{arm}'
            files=entry['files_sha256']
            required={'False-warm.json','environment.json','runner.txt','junit.xml',
                      'navigation-residency.json','navigation-residency-trace.json.gz','residency-provenance.json','renderer-status.json'}
            if entry['exit_code']!=0:required.remove('False-warm.json')
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
            provenance=json.loads((folder/'residency-provenance.json').read_text())
            if (provenance.get('trace_scope')!='navigation-only-v2' or provenance['acceptance'] is not False or provenance['native_sampling'] is not False or
                provenance['allocator_dumps']!=20 or provenance.get('forced_gc') is not False or provenance.get('dump_determinism')!='none' or provenance['snapshots']!=13 or
                provenance['navigation_observations']!=20 or
                provenance['probe_sha256']!=hashlib.sha256(source(repo,ref,PROBE)).hexdigest()):
                raise ValueError('Invalid probe provenance')
            result['source_hashes_verified']+=1
            issue=capture_issue(entry,provenance)
            if issue:
                result['errors'].append(f'Slot {index}: '+issue)
                result['cohorts'].append({'index':index,'arm':arm,'status':'invalid_capture','reason':issue,
                    'exit_code':entry['exit_code'],'trace_completion':provenance['trace_completion'],
                    'captured_navigation_records':len(json.loads((folder/'navigation-residency.json').read_text()))})
                continue
            raw=folder/'False-warm.json'
            if entry['raw_sha256']!=hashlib.sha256(raw.read_bytes()).hexdigest():raise ValueError('Raw identity mismatch')
            points=slot_points(json.loads(raw.read_text()),block)
            events=json.load(gzip.open(folder/'navigation-residency-trace.json.gz','rt'))['traceEvents']
            observed=observation(events,json.loads((folder/'navigation-residency.json').read_text()),json.loads((folder/'renderer-status.json').read_text()))
            rawrows=json.loads(raw.read_text())
            for snap in [*rawrows[0]['scenarios'].values(),*rawrows[0]['navigation_trend']]:
                if observed['app_pid'] not in [d['pid'] for d in snap['renderer_memory_detail']]:
                    raise ValueError('Trace app PID absent from baseline renderer observations')
            result['cohorts'].append({'index':index,'arm':arm,'status':'valid_capture','points':points,**observed})
        result['status']='inconclusive' if result['errors'] else 'complete_diagnostic'
        result['pair_comparisons']=pair_comparisons(result['cohorts'])
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as e:result['errors'].append(repr(e))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--harness-ref',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    repo=Path(__file__).resolve().parents[2];ref=subprocess.check_output(['git','rev-parse',a.harness_ref],cwd=repo,text=True).strip()
    result=audit(a.root,repo,ref);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','errors','source_hashes_verified','files_verified']}))
    sys.exit(bool(result['errors']))
