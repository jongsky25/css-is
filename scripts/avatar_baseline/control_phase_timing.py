"""Frozen uninjected phase/CPU diagnostic, never qualification or corrected timing."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PROTOCOL = 'control-phase-timing-v1'
SOURCES = ['scripts/avatar_baseline/control_phase_timing.py',
           'scripts/avatar_baseline/element_membership_lifecycle.py',
           'scripts/avatar_baseline/mixed_membership_fixture.py',
           'scripts/avatar_baseline/analyze_membership_lifecycle.py',
           'scripts/avatar_baseline/analyze_element_membership.py']
EXPECTED_DOM = {
    'dom':'f53f09aa4f59c5ca7e627f4d44aa8f6801833196040a75d66e735ce5434e5089',
    'svg':'0fd29e8f942dc078e8e7d166ebd03ca133be7ed0207c5a260d1292b72683f89a',
    'style':'e16ec8fdc1e3c2b3ede83c9a95c6b2ed900582ff5b1237e592a72afa4351d58f'}
PHASES = ['navigation','fixed_wait','serialize_before','census','serialize_after',
          'hash_dom','heap_counter','dom_counter','navigation_timing']


def process_stat(raw):
    # comm can contain spaces and parentheses; fields after its closing paren are stable.
    fields = raw[raw.rindex(')')+2:].split()
    return {'parent_pid':int(fields[1]),'user_ticks':int(fields[11]),'system_ticks':int(fields[12]),
            'start_ticks':int(fields[19]),'minor_faults':int(fields[7]),'major_faults':int(fields[9])}


def key_values(raw):
    return {k:int(v) for k,v in (line.split() for line in raw.splitlines())}


class Timing:
    def __init__(self):
        self.data = {'protocol':PROTOCOL,'native_hooks_installed':False,'full_trace_enabled':False,
                     'ticks_per_second':os.sysconf('SC_CLK_TCK'),'phases':[]}

    def initialize(self, browser_pid, renderer_pid, driver_pid):
        self.pids = {'python':os.getpid(),'browser':browser_pid,'renderer':renderer_pid}
        # Pinned Playwright's PipeTransport owns this asyncio subprocess handle.
        driver = process_stat(Path(f'/proc/{driver_pid}/stat').read_text())
        if driver['parent_pid'] != os.getpid():
            raise ValueError('Playwright driver is not a direct Python child')
        self.pids['driver'] = driver_pid
        self.data['driver_identity_source'] = 'playwright-pipe-transport-process-pid'
        self.data['pids'] = self.pids
        self.data['affinity_cpus'] = sorted(os.sched_getaffinity(0))
        self.data['cgroup_membership'] = Path('/proc/self/cgroup').read_text().strip()
        self.data['cpu_max'] = Path('/sys/fs/cgroup/cpu.max').read_text().strip()
        self.data['initial'] = self.snapshot()

    def snapshot(self):
        value = {'begin_ns':time.monotonic_ns(),'processes':{},'optional':{}}
        for label,pid in self.pids.items():
            value['processes'][label] = process_stat(Path(f'/proc/{pid}/stat').read_text())
            try:
                fields = list(map(int,Path(f'/proc/{pid}/schedstat').read_text().split()))
                value['processes'][label]['main_thread_schedstat'] = fields
            except OSError as error:
                value['processes'][label]['schedstat_unavailable'] = type(error).__name__
        value['cgroup_cpu'] = key_values(Path('/sys/fs/cgroup/cpu.stat').read_text())
        value['system_cpu_ticks'] = list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
        value['loadavg'] = Path('/proc/loadavg').read_text().split()[:3]
        for label,name in [('cgroup_pressure','/sys/fs/cgroup/cpu.pressure'),('host_pressure','/proc/pressure/cpu')]:
            try:value['optional'][label] = {'raw':Path(name).read_text()}
            except OSError as error:value['optional'][label] = {'unavailable':type(error).__name__}
        value['end_ns'] = time.monotonic_ns()
        return value

    def measure(self, index, name, operation):
        row = {'index':index,'phase':name,'before':self.snapshot()}
        self.data['phases'].append(row)
        row['begin_ns'] = time.monotonic_ns()
        try:return operation()
        finally:
            row['end_ns'] = time.monotonic_ns()
            row['after'] = self.snapshot()


def validate_capture(p):
    from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE,document
    from scripts.avatar_baseline.analyze_membership_lifecycle import lifecycle_events,validate_selector_reuse
    if (p['protocol']!=PROTOCOL or p['mode']!='control' or p['status']!='captured'
        or p.get('history') or p['messages'] or p['acceptance'] is not False
        or p['forced_gc'] is not False or p['back_forward_cache_disabled'] is not True
        or p['build_id']!='1c5dca8527a61d07372e489142bee26af1bcaf71'
        or p['browser_version']!='156.0.8078.47'):
        raise ValueError('Invalid uninjected diagnostic capture')
    lifecycle_events(p['lifecycle_events']);validate_selector_reuse(p)
    d=p['control_timing']
    if d['protocol']!=PROTOCOL or d['native_hooks_installed'] is not False or d['full_trace_enabled'] is not False:
        raise ValueError('Diagnostic contains injection/trace')
    if list(d['pids'])!=['python','browser','renderer','driver'] or len(set(d['pids'].values()))!=4:
        raise ValueError('Invalid process identity')
    if len(d['phases'])!=12*len(PHASES) or len(p['stages'])!=12:raise ValueError('Incomplete phase schedule')
    if d['pids']['renderer']!=p['pid']:raise ValueError('Wrong telemetry renderer')
    starts={k:v['start_ticks'] for k,v in d['initial']['processes'].items()}
    phase_totals=defaultdict(float);cpu_totals=defaultdict(float);telemetry_ns=0;stages=[]
    ticks=d['ticks_per_second']
    if ticks<=0:raise ValueError('Invalid CPU tick rate')
    previous=p['begin_ns']
    throttle_periods=throttle_us=0
    for index,stage in enumerate(p['stages']):
        if stage['index']!=index or stage['fixture_mode']!=SCHEDULE[index] or not previous<=stage['begin_ns']<=stage['end_ns']<=p['end_ns']:
            raise ValueError('Invalid stage order')
        html_hash=hashlib.sha256(document(SCHEDULE[index])).hexdigest()
        # Browser serializes the doctype and inserts HTML namespace structure.
        # Require unchanged before/after; exact cross-run browser hashes checked by audit.
        if stage['dom_before_sha256']!=stage['dom_after_sha256'] or stage['dom_before_sha256']!=EXPECTED_DOM[SCHEDULE[index]]:raise ValueError('DOM mutated or fixture changed')
        groups=['avatar:0','avatar:1','other:0','other:1']
        if len(stage['censuses'])!=4:raise ValueError('Incomplete census')
        for group,census in zip(groups,stage['censuses']):
            r=census['result'];tag='path' if SCHEDULE[index]=='svg' else 'span' if SCHEDULE[index]=='dom' and group.startswith('other') else 'div'
            if census['phase']!=f'census:{index}:{group}' or r['count']!=32 or r['fixture_count']!=3000 or r['counts']!=[1]*32 or r['tags']!=[tag]*32:
                raise ValueError('Census schedule/observable changed')
        phases=d['phases'][index*len(PHASES):(index+1)*len(PHASES)]
        last=stage['begin_ns'];work_ns=context_ns=0;details=[]
        for name,row in zip(PHASES,phases):
            before,after=row['before'],row['after'];lo,hi=row['begin_ns'],row['end_ns']
            if (row['index']!=index or row['phase']!=name or not last<=before['begin_ns']<=before['end_ns']<=lo<=hi<=after['begin_ns']<=after['end_ns']<=stage['end_ns']):
                raise ValueError('Invalid phase/context bracket')
            cpu={}
            for label in starts:
                a,b=before['processes'][label],after['processes'][label]
                if a['start_ticks']!=starts[label] or b['start_ticks']!=starts[label]:raise ValueError('Process identity changed')
                for k in ['user_ticks','system_ticks','minor_faults','major_faults']:
                    if b[k]<a[k]:raise ValueError('Process counter decreased')
                cpu[label]=(b['user_ticks']+b['system_ticks']-a['user_ticks']-a['system_ticks'])*1000/ticks
                cpu_totals[label]+=cpu[label]
            a,b=before['cgroup_cpu'],after['cgroup_cpu']
            if any(b[k]<a[k] for k in a):raise ValueError('Cgroup counter decreased')
            dt=b['throttled_usec']-a['throttled_usec'];dn=b['nr_throttled']-a['nr_throttled']
            throttle_us+=dt;throttle_periods+=dn
            context=(before['end_ns']-before['begin_ns'])+(after['end_ns']-after['begin_ns'])
            context_ns+=context;work_ns+=hi-lo;phase_totals[name]+=(hi-lo)/1e6
            detail={'phase':name,'wall_ms':(hi-lo)/1e6,'cpu_ms':cpu,'throttle_us':dt,'throttled_periods':dn,
                    'cgroup_usage_ms':(b['usage_usec']-a['usage_usec'])/1000}
            if name=='fixed_wait':
                if hi-lo<220_000_000:raise ValueError('Fixed wait shortened')
                detail['overrun_ms']=(hi-lo)/1e6-220
            details.append(detail);last=after['end_ns']
        telemetry_ns+=context_ns
        stages.append({'index':index,'mode':SCHEDULE[index],'duration_ms':(stage['end_ns']-stage['begin_ns'])/1e6,
                       'telemetry_ms':context_ns/1e6,'unbracketed_ms':(stage['end_ns']-stage['begin_ns']-context_ns-work_ns)/1e6,
                       'phases':details,'navigation_timing':stage['navigation_timing'],'fixture_sha256':html_hash,
                       'dom_sha256':stage['dom_before_sha256']})
        previous=stage['end_ns']
    return {'duration_ms':(p['end_ns']-p['begin_ns'])/1e6,'phase_ms':dict(phase_totals),
            'telemetry_ms':telemetry_ns/1e6,'cpu_ms':dict(cpu_totals),'throttled_periods':throttle_periods,
            'throttle_ms':throttle_us/1000,'stages':stages,
            'limitations':'Diagnostic telemetry changes the workload. CPU ticks cover process threads; schedstat covers only main threads and zero values may be unavailable. Snapshots bracket calls and include their own reads. CPU pressure may be unavailable; cgroup counters are shared context. CPU time and throttle overlap do not establish causation. No corrected or acceptance timing.'}


def audit(root,repo):
    plan=json.loads((root/'experiment.json').read_text());ref=plan['harness_commit']
    if plan['protocol']!=PROTOCOL or plan['order']!=['control']*4 or len(plan['cohorts'])!=4 or plan['acceptance'] is not False:
        raise ValueError('Invalid diagnostic schedule')
    for name in SOURCES:
        if (root/'harness'/name).read_bytes()!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Frozen source mismatch')
    result={'status':'diagnostic_complete','acceptance':False,'instrument_qualified_for_application_calibration':False,
            'harness_commit':ref,'cohorts':[],'errors':[],'source_hashes_verified':len(SOURCES),'files_verified':0}
    hashes=None
    for index,entry in enumerate(plan['cohorts']):
        row={'index':index};result['cohorts'].append(row)
        try:
            if entry['index']!=index or entry['exit_code']!=0:raise ValueError('Failed diagnostic slot')
            folder=root/f'{index}-control'
            if not {'capture.json.gz','identity.json','runner.txt'}<=entry['files_sha256'].keys():raise ValueError('Missing diagnostic evidence')
            for name,digest in entry['files_sha256'].items():
                if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError('Evidence changed')
                result['files_verified']+=1
            p=json.load(gzip.open(folder/'capture.json.gz','rt'))
            if p['harness_commit']!=ref or p['runner_sha256']!=hashlib.sha256((root/'harness'/SOURCES[1]).read_bytes()).hexdigest():raise ValueError('Runtime source mismatch')
            row.update(validate_capture(p))
            current=[s['dom_sha256'] for s in row['stages']]
            if hashes is not None and current!=hashes:raise ValueError('Cross-run fixture changed')
            hashes=current
            from scripts.avatar_baseline.analyze_element_membership import validate_identity
            validate_identity(json.loads((folder/'identity.json').read_text()),p)
        except (ValueError,KeyError,TypeError,OSError) as error:
            row['error']=repr(error);result['errors'].append(f'Slot {index}: {error}')
    if result['errors']:result['status']='diagnostic_failed'
    return result


def run(root):
    repo=Path(__file__).resolve().parents[2];ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    for name in SOURCES:
        if (repo/name).read_bytes()!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Uncommitted diagnostic source')
    root.mkdir(parents=True,exist_ok=False)
    for name in SOURCES:
        dest=root/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((repo/name).read_bytes())
    plan={'protocol':PROTOCOL,'harness_commit':ref,'acceptance':False,'order':['control']*4,'cohorts':[]}
    for index in range(4):
        folder=root/f'{index}-control';log=root/f'{index}.txt'
        with log.open('w') as stream:
            code=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.control_phase_timing','capture','--out',str(folder)],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
        folder.mkdir(exist_ok=True);(folder/'runner.txt').write_bytes(log.read_bytes());log.unlink()
        plan['cohorts'].append({'index':index,'exit_code':code,'files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(folder.iterdir()) if f.is_file()}})
        (root/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n');print('SLOT',index,'exit',code,flush=True)
    result=audit(root,repo);(root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cohorts'}));return result['status']!='diagnostic_complete'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run','capture','audit']);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.action=='capture':
        from scripts.avatar_baseline.element_membership_lifecycle import run as capture
        raise SystemExit(capture(a.out,'control',Timing()))
    if a.action=='audit':print(json.dumps(audit(a.out,Path(__file__).resolve().parents[2])));raise SystemExit(0)
    raise SystemExit(run(a.out))
