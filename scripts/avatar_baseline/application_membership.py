"""Frozen real-app receiver proof and observer calibration; never RSS acceptance."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from scripts.avatar_baseline.native_recorder_selftest import validate_live
from scripts.avatar_baseline.analyze_element_membership import generations,join_receivers
from scripts.avatar_baseline.analyze_reader_retention import clock_bounds,mapped,selected_events,position

PRODUCT='cf363bfe547d5e23619eee28cdaf68bd4b6d7753'
HARNESS=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',
 'tests/test_avatar_application_membership_browser.py','tests/avatar_application_membership.py',
 'tests/avatar_page_history_probe.py','scripts/avatar_baseline/native/callback_buffer.js']
BACKEND=['app.py','storage.py','appearance_routes.py','sqlite_reader.py']
SOURCES=[*HARNESS,'scripts/avatar_baseline/application_membership.py',
 'scripts/avatar_baseline/native_recorder_selftest.py','scripts/avatar_baseline/analyze_element_membership.py',
 'scripts/avatar_baseline/analyze_reader_retention.py']
SCENARIOS=['home_idle','home_interaction','wellness_care','picker_growth','seasonal_preview','offscreen','reduced_motion','background']


def source(repo,ref,name):return subprocess.check_output(['git','show',ref+':'+name],cwd=repo)
def digest(data):return hashlib.sha256(data).hexdigest()


def validate_selection(row,group):
    if (row['count']!=32 or row['pool_count']<32 or row['root_count']!=1 or row['values']!=[1]*32
        or len(row['tags'])!=32 or row['ownership']!=[group=='avatar']*32
        or row['namespaces']!=[('http://www.w3.org/2000/svg' if group=='avatar' else 'http://www.w3.org/1999/xhtml')]*32
        or row['before_attributes']!=row['after_attributes']):raise ValueError('Application selection/observable changed')
    attrs=json.loads(row['before_attributes'])
    if len(attrs)!=32 or [a[0] for a in attrs]!=row['tags']:raise ValueError('Invalid selected attribute witness')


def native_identity(p):
    n=p['native'];ready=[m['payload'] for m in n['agent_messages'] if m.get('payload',{}).get('ready')]
    if n['build_id']!='1c5dca8527a61d07372e489142bee26af1bcaf71' or n['frida_version']!='17.5.1' or len(n['identity_markers'])!=1 or n['identity_markers'][0]['pid']!=n['pid']:
        raise ValueError('Native process/build identity mismatch')
    if any(m['type']=='error' for m in n['agent_messages']):raise ValueError('Native agent error')
    if p['mode']=='control':
        if n['enabled'] or ready or n.get('history'):raise ValueError('Injected control')
    else:
        if not n['enabled'] or len(ready)!=1 or ready[0]['pid']!=n['pid']:raise ValueError('Missing native hook readiness')
        validate_live(n['history'],p['native_export_interval_ns'])
    if p['mode']!='control':
        expected={'allocate':0x5ab0350,'pool':0x5ab0550,'receiver':0x100cce80,'shutdown':0x100208d0,'destroy':0x5aa4490,'release':0x5ab09d0}
        if p['mode']=='proof':expected['reference']=0x100b1880
        if n['history']['offsets']!=expected:raise ValueError('Unexpected application native offsets')
    return n


def validate_workload(p,raw):
    if (p['status']!='captured' or p['protocol']!='application-membership-v1' or p['acceptance'] is not False
        or p['forced_gc'] is not False or not p['back_forward_cache_disabled'] or p['snapshots']!=13 or p['mount']!=20
        or len(raw)!=1):raise ValueError('Incomplete application workload')
    r=raw[0]
    if r['run']!=0 or r['mobile'] is not False or r['cache']!='warm' or r['seconds']!=30 or r['cpu_rate']!=1 or set(r['scenarios'])!=set(SCENARIOS) or r['errors']:
        raise ValueError('Application workload/sample changed')
    if [q['mount'] for q in p['navigations']]!=list(range(1,21)) or [q['mount'] for q in p['checkpoints']]!=[1,5,10,15,20]:raise ValueError('Changed mount/checkpoint schedule')
    if r['navigation_trend']!=[{'mount':q['mount'],**q['snapshot']} for q in p['checkpoints']]:raise ValueError('Baseline snapshot changed')
    last=p['begin_ns']
    for q in p['navigations']:
        if not last<=q['begin_ns']<=q['arm_end_ns']<=q['goto_end_ns']<=q['end_ns']<=p['end_ns']:raise ValueError('Invalid navigation bracket')
        last=q['end_ns']
    return native_identity(p)


def proof(p,raw):
    n=validate_workload(p,raw)
    if p['mode']!='proof':raise ValueError('Not a receiver proof')
    h=n['history'];groups={};seen={};queries=p['queries']
    expected=[f'{kind}:0:{group}:{repeat}' for group in ['avatar','other'] for repeat in [0,1] for kind in ['reference','census']]
    if [q['phase'] for q in queries]!=expected:raise ValueError('Changed proof query schedule')
    receivers=[e for e in h['events'] if e['kind'] in ['receiver','reference']]
    if {e['phase'] for e in receivers}!=set(expected):raise ValueError('Unexpected application receiver call')
    for q in queries:
        phase=q['phase'];kind,_,group,repeat=phase.split(':');r=q['result'];validate_selection(r,group)
        es=[e for e in receivers if e['phase']==phase]
        if len(es)!=32 or len({e['address'] for e in es})!=32 or any(not q['begin_ns']<=e['begin_ns']<=e['returned_ns']<=q['end_ns'] for e in es):raise ValueError('Proof receiver identity/bracket mismatch')
        seen[phase]=[e['address'] for e in es]
        if kind=='census' and any(not e['attribute_absent'] for e in es):raise ValueError('Native getter not null')
        if group in groups and groups[group]!=r['tags']:raise ValueError('Proof element tags changed')
        groups[group]=r['tags']
    for group in ['avatar','other']:
        values=[seen[f'{kind}:0:{group}:{repeat}'] for kind in ['reference','census'] for repeat in [0,1]]
        if any(v!=values[0] for v in values[1:]):raise ValueError('Repeated/reference receivers differ')
    if set(seen['census:0:avatar:0'])&set(seen['census:0:other:0']):raise ValueError('Source groups overlap')
    return {'status':'application_receiver_proof_passed','acceptance':False,'groups':groups,'receivers':128,'references':128}


def inspect_slot(p,raw,capability,trace=None):
    n=validate_workload(p,raw);begin,end=p['begin_ns'],p['end_ns'];costs=[]
    for nav in p['navigations']:
        lo,hi=nav['census_interval_ns']
        if not nav['goto_end_ns']<=lo<=hi<=nav['end_ns']:raise ValueError('Census outside navigation')
        costs += [nav['arm_end_ns']-nav['begin_ns'],hi-lo]
        rows=nav['censuses']
        if [(r['group'],r['repeat']) for r in rows]!=[('avatar',0),('avatar',1),('other',0),('other',1)]:raise ValueError('Census sample changed')
        for r in rows:
            validate_selection(r,r['group'])
            if r['tags']!=capability['groups'][r['group']]:raise ValueError('Actual app types differ from proof')
    for q in p['checkpoints']:
        lo,hi=q['interval_ns']
        if not begin<=lo<=hi<=end:raise ValueError('Checkpoint outside window')
        costs.append(hi-lo)
    costs.append(p.get('trace_setup_ns',0))
    h=n.get('history');errors=[];info={}
    if h:
        # Includes pre-navigation native preparation during all eight earlier scenarios.
        costs += [e['callback_ready_ns']-e['begin_ns'] for e in h['events']]
        receivers=[e for e in h['events'] if e['kind']=='receiver']
        expected={f'census:{i}:{g}:{r}' for i in range(1,21) for g in ['avatar','other'] for r in [0,1]}
        if {e['phase'] for e in receivers}!=expected or len(receivers)!=2560:raise ValueError('Missing/extra measured native receivers')
        for nav in p['navigations']:
            seen={};lo,hi=nav['census_interval_ns'];i=nav['mount']
            for g in ['avatar','other']:
                for r in [0,1]:
                    es=[e for e in receivers if e['phase']==f'census:{i}:{g}:{r}']
                    if len(es)!=32 or any(not e['attribute_absent'] or not lo<=e['begin_ns']<=e['returned_ns']<=hi for e in es):raise ValueError('Receiver outside known query/null mismatch')
                    addresses=[e['address'] for e in es]
                    if len(set(addresses))!=32:raise ValueError('Duplicate receiver')
                    if r and addresses!=seen[g]:raise ValueError('Repeated application identities changed')
                    seen[g]=addresses
            if set(seen['avatar'])&set(seen['other']):raise ValueError('Avatar/nonavatar identity overlap')
        spans,unknown=generations([e for e in h['events'] if e['kind'] in ['allocate','pool']]);joined=join_receivers(receivers,spans)
        coverage={g:sum(r['generation'] is not None for r in joined if r['phase'].split(':')[2]==g)/1280 for g in ['avatar','other']}
        if any(v<.9 for v in coverage.values()):errors.append('Application source receiver coverage below 90%')
        if trace is None or p['trace_completion'].get('dataLossOccurred'):raise ValueError('Missing/lost application trace')
        clock=clock_bounds(p,trace['traceEvents']);gc=selected_events(trace['traceEvents'],n['pid'])
        if not any(e['name']=='MajorGC' for e in gc) or not any('Sweep' in e['name'] for e in gc):errors.append('Missing natural MajorGC/native sweep')
        returned=[]
        for s in spans:
            if s['labels'] and s['end_ns'] is not None and begin<=s['end_ns']<=end:
                calls=[e for e in h['events'] if e['kind']=='pool' and e['backend']==s['backend'] and int(e['address'],16)==s['base'] and e['begin_ns']==s['end_ns']]
                if len(calls)!=1:raise ValueError('Ambiguous labelled return')
                event=calls[0];bounds=mapped([event['begin_ns'],event['returned_ns']],clock)
                if event['returned_ns']>end:continue
                labels=sorted({label.split(':')[2] for label in s['labels']})
                overlap=[e for e in gc if 'Sweep' in e['name'] and position(e,bounds)=='overlap_or_uncertain']
                returned.append({'generation':s['generation'],'groups':labels,'return_interval_ns':[event['begin_ns'],event['returned_ns']],'sweep_overlap':overlap})
        for group in ['avatar','other']:
            if not any(group in r['groups'] for r in returned):errors.append('No measured labelled reclamation: '+group)
        for nav in p['navigations']:
            bounds=mapped(nav['census_interval_ns'],clock)
            if not clock['coverage_us'][0]<=bounds[0]<=bounds[1]<=clock['coverage_us'][1]:errors.append('Receiver census outside trace coverage')
        info={'receiver_records':len(receivers),'coverage':coverage,'unknown_pool_returns':unknown,'labelled_returns':returned,'gc_counts':dict(Counter(e['name'] for e in gc)),'clock':clock}
    fraction=sum(costs)/(end-begin);maximum=max(costs)/1e6
    if fraction>.05 or maximum>250:errors.append('Observation bound exceeds 5% or 250ms')
    return {'status':'valid_capture','mode':p['mode'],'duration_ms':(end-begin)/1e6,'workload_duration_ms':(p['workload_end_ns']-p['workload_begin_ns'])/1e6,
            'observation_fraction_bound':fraction,'maximum_observation_ms':maximum,'errors':errors,**info}


def audit(root,repo):
    plan=json.loads((root/'experiment.json').read_text());ref=plan['harness_commit']
    if plan['protocol']!='application-membership-v1' or plan['product_ref']!=PRODUCT or plan['order']!=['control','probe','probe','control'] or len(plan['cohorts'])!=4 or plan['acceptance'] is not False:raise ValueError('Invalid application calibration plan')
    for name in SOURCES:
        if (root/'harness'/name).read_bytes()!=source(repo,ref,name):raise ValueError('Frozen application harness mismatch')
    def read(folder,entry,mode):
        if entry['exit_code']:raise ValueError('Failed application workload')
        for name,sha in entry['files_sha256'].items():
            if Path(name).name!=name or digest((folder/name).read_bytes())!=sha:raise ValueError('Application evidence changed')
        required={'application-membership.json.gz','False-warm.json','environment.json','backend-source.json','runner.txt','junit.xml'}
        if mode=='probe':required.add('application-trace.json.gz')
        if not required<=set(entry['files_sha256']):raise ValueError('Missing application evidence')
        for name,sha in json.loads((folder/'backend-source.json').read_text()).items():
            if name not in BACKEND or digest(source(repo,PRODUCT,name))!=sha:raise ValueError('Backend changed')
        if set(json.loads((folder/'backend-source.json').read_text()))!=set(BACKEND):raise ValueError('Incomplete backend inventory')
        env=json.loads((folder/'environment.json').read_text())
        if env['source_commit']!=PRODUCT or env['chromium']!='156.0.8078.47' or env['playwright']!='1.62.0':raise ValueError('Wrong app/browser source')
        expected_assets={'templates/_avatars.html','templates/_avatars_art.html','templates/me.html','templates/_growth.html','static/js/avatars.js','static/js/avatar-audio.js','static/js/search.js','templates/office_connect.html','templates/dash_layout.html',*HARNESS[:2]}
        tree=subprocess.check_output(['git','ls-tree','-r','--name-only',PRODUCT,'templates'],cwd=repo,text=True).splitlines()
        expected_assets.update(n for n in tree if n.startswith('templates/_avatar_species/') and n.endswith('.html'))
        if 'templates/_avatars_shared.html' in tree:expected_assets.add('templates/_avatars_shared.html')
        if set(env['source_sha256'])!=expected_assets:raise ValueError('Incomplete application asset inventory')
        for name,sha in env['source_sha256'].items():
            if digest(source(repo,ref if name in HARNESS else PRODUCT,name))!=sha:raise ValueError('App asset/source mismatch')
        p=json.load(gzip.open(folder/'application-membership.json.gz','rt'))
        if p['mode']!=mode or p['harness_commit']!=ref:raise ValueError('Runtime app mode/ref changed')
        for name,key in [(HARNESS[2],'probe_sha256'),(HARNESS[3],'selection_sha256')]:
            if digest(source(repo,ref,name))!=p[key]:raise ValueError('Runtime app observer changed')
        n=p['native']
        if n['hook_sha256']!=digest(source(repo,ref,HARNESS[5])) or n['helper_sha256']!=digest(source(repo,ref,HARNESS[4])):raise ValueError('Native helper/agent changed')
        return p,json.loads((folder/'False-warm.json').read_text())
    proofroot=root/'receiver-proof';p,raw=read(proofroot,plan['receiver_proof'],'proof');cap=proof(p,raw)
    result={'status':'application_calibration_failed','acceptance':False,'application_memory_accepted':False,'harness_commit':ref,'receiver_proof':cap,
            'observer_qualified_for_application_attribution':False,'errors':[],'cohorts':[]}
    for i,entry in enumerate(plan['cohorts']):
        row={'index':i};result['cohorts'].append(row)
        try:
            mode=plan['order'][i]
            if entry['index']!=i or entry['mode']!=mode:raise ValueError('Slot schedule changed')
            folder=root/f'{i}-{mode}';p,raw=read(folder,entry,mode)
            row.update(inspect_slot(p,raw,cap,json.load(gzip.open(folder/'application-trace.json.gz','rt')) if mode=='probe' else None))
            result['errors'] += [f'Slot {i}: '+e for e in row['errors']]
        except (ValueError,KeyError,TypeError,OSError) as error:row['error']=repr(error);result['errors'].append(f'Slot {i}: {error}')
    if all('duration_ms' in r for r in result['cohorts']):
        times=[r['duration_ms'] for r in result['cohorts']]
        if abs(times[3]-times[0])>times[0]*.2:result['errors'].append('Control duration varies more than 20%')
        for a,b in [(0,1),(3,2)]:
            if times[b]>times[a]*1.2:result['errors'].append(f'Probe/control exceeds 1.20: {a}/{b}')
        whole=[r['workload_duration_ms'] for r in result['cohorts']]
        if abs(whole[3]-whole[0])>whole[0]*.2:result['errors'].append('Whole-workload controls vary more than 20%')
        for a,b in [(0,1),(3,2)]:
            if whole[b]>whole[a]*1.2:result['errors'].append(f'Whole-workload probe/control exceeds 1.20: {a}/{b}')
    if not result['errors']:
        result['status']='application_calibration_passed';result['observer_qualified_for_application_attribution']=True
    return result


def run(out):
    repo=Path(__file__).resolve().parents[2];ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    for name in SOURCES:
        if (repo/name).read_bytes()!=source(repo,ref,name):raise ValueError('Uncommitted app observer source')
    out.mkdir(parents=True,exist_ok=False)
    for name in SOURCES:
        path=out/'harness'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((repo/name).read_bytes())
    plan={'protocol':'application-membership-v1','acceptance':False,'harness_commit':ref,'product_ref':PRODUCT,'order':['control','probe','probe','control'],'cohorts':[]}
    def save():(out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
    def slot(label,mode):
        dest=out/label;dest.mkdir()
        with tempfile.TemporaryDirectory(prefix='app-membership-') as temp:
            cwd=Path(temp)/'app';subprocess.run(['git','worktree','add','--quiet','--detach',str(cwd),PRODUCT],cwd=repo,check=True);saved={}
            try:
                for name in HARNESS:
                    path=cwd/name;saved[path]=path.read_bytes() if path.exists() else None;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((repo/name).read_bytes())
                (dest/'backend-source.json').write_text(json.dumps({n:digest((cwd/n).read_bytes()) for n in BACKEND},indent=2)+'\n')
                env=dict(os.environ,CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_APP_MEMBERSHIP='1',CSS_AVATAR_APP_MODE=mode,CSS_AVATAR_APP_HARNESS_REF=ref,CSS_AVATAR_KIND='cat',CSS_AVATAR_MATURE='0',CSS_AVATAR_RUNS='1',CSS_AVATAR_SECONDS='30',CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
                with (dest/'runner.txt').open('w') as stream:
                    code=subprocess.run([sys.executable,'-m','pytest','tests/test_avatar_application_membership_browser.py::test_application_membership','-s','--junitxml='+str(dest/'junit.xml')],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
            finally:
                for path,data in saved.items():
                    if data is None:path.unlink(missing_ok=True)
                    else:path.write_bytes(data)
                subprocess.run(['git','worktree','remove',str(cwd)],cwd=repo,check=True)
        return {'mode':mode,'exit_code':code,'files_sha256':{p.name:digest(p.read_bytes()) for p in sorted(dest.iterdir()) if p.is_file()}}
    plan['receiver_proof']=slot('receiver-proof','proof');save()
    if plan['receiver_proof']['exit_code']:raise ValueError('Application receiver proof workload failed; calibration not started')
    p=json.load(gzip.open(out/'receiver-proof/application-membership.json.gz','rt'));raw=json.loads((out/'receiver-proof/False-warm.json').read_text());cap=proof(p,raw)
    (out/'receiver-proof/assessment.json').write_text(json.dumps(cap,indent=2)+'\n')
    # Update the proof descriptor after storing its explicit assessment.
    plan['receiver_proof']['files_sha256']['assessment.json']=digest((out/'receiver-proof/assessment.json').read_bytes());save()
    for i,mode in enumerate(plan['order']):
        entry=slot(f'{i}-{mode}',mode);entry['index']=i;plan['cohorts'].append(entry);save();print('SLOT',i,mode,'exit',entry['exit_code'],flush=True)
    result=audit(out,repo);(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=run(a.out.resolve());print(json.dumps({k:v for k,v in r.items() if k!='cohorts'}));raise SystemExit(r['status']!='application_calibration_passed')
