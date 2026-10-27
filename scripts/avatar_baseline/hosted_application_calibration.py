"""Gate one hosted real-application calibration on retained native qualification."""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile
from scripts.avatar_baseline.application_membership import run as calibrate,audit,SOURCES as APP_SOURCES
from scripts.avatar_baseline.analyze_membership_lifecycle import audit as native_audit
from scripts.avatar_baseline.hosted_native_calibration import SOURCES as NATIVE_SOURCES
from scripts.avatar_baseline.runner_isolation_inventory import inventory

QUALIFIED='docs/avatars/increment2b/hosted-native-calibration/calibration-v1-evidence.zip'
QUALIFIED_SHA='2c1de48749d1eefeb04782e2034879bf7392ce137bddb1b3a16f734159b25a0d'
SOURCES=list(dict.fromkeys([*APP_SOURCES,*NATIVE_SOURCES,'scripts/avatar_baseline/hosted_application_calibration.py',
 'scripts/avatar_baseline/runner_isolation_inventory.py','scripts/avatar_baseline/analyze_membership_lifecycle.py',
 'requirements-test.txt','requirements-avatar-native.txt']))


def summary(result):
    lines=['# Application observer calibration','','**Result: '+result['status'].replace('_',' ')+'**','',
           'This checks measurement integrity and cost on the real app. It is not memory acceptance or deployment.','']
    if result.get('error'):lines+=['Error: `'+result['error'].replace('`',"'")+'`','']
    a=result.get('audit')
    if a:
        lines+=['| Slot | Mode | Navigation ms | Observation bound |','| --- | --- | ---: | ---: |']
        for c in a['cohorts']:
            duration=f"{c['duration_ms']:.2f}" if 'duration_ms' in c else 'unavailable'
            fraction=f"{c['observation_fraction_bound']*100:.3f}%" if 'observation_fraction_bound' in c else 'unavailable'
            lines.append(f"| {c['index']+1} | {c.get('mode','invalid')} | {duration} | {fraction} |")
        lines+=['']+['- '+e for e in a['errors']]
    lines+=['','Observer qualified for application attribution: **'+('yes' if result.get('observer_qualified_for_application_attribution') else 'no')+'**.',
            'All prior memory failures remain. No automatic app comparison, retry, candidate promotion or 2B acceptance follows.',
            'Download **avatar-application-calibration** for every prerequisite, workload, trace, source hash and failure.','']
    return '\n'.join(lines)


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2];ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    result={'status':'application_calibration_failed','acceptance':False,'application_memory_accepted':False,
            'observer_qualified_for_application_attribution':False,'harness_commit':ref,
            'github':{k:os.environ[k] for k in ['GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY','GITHUB_WORKFLOW_REF','GITHUB_SHA','GITHUB_REF','RUNNER_OS','RUNNER_ARCH'] if k in os.environ},'source_sha256':{}}
    try:
        for name in SOURCES:
            data=(repo/name).read_bytes()
            if data!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Uncommitted application calibration source')
            dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);result['source_sha256'][name]=hashlib.sha256(data).hexdigest()
        if platform.python_version()!='3.12.14' or platform.machine()!='x86_64' or {n:importlib.metadata.version(n) for n in ['playwright','frida']}!={'playwright':'1.62.0','frida':'17.5.1'}:raise ValueError('Wrong application observer toolchain')
        caps=next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('CapEff:'))
        if not int(caps,16)&(1<<19):raise ValueError('Declared container ptrace capability absent')
        raw=(repo/QUALIFIED).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=QUALIFIED_SHA:raise ValueError('Native qualification artifact changed')
        prior=out/'qualified-native'
        with zipfile.ZipFile(repo/QUALIFIED) as z:
            for name in z.namelist():
                rel=Path(name)
                if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe qualification archive')
                dest=prior/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
        manifest=json.loads((prior/'result/files-sha256.json').read_text())
        for name,sha in manifest.items():
            if hashlib.sha256((prior/'result'/name).read_bytes()).hexdigest()!=sha:raise ValueError('Prior native artifact evidence changed')
        previous=json.loads((prior/'result/result.json').read_text());qualified=native_audit(prior/'result/calibration',repo,previous['harness_commit'])
        if qualified!=previous['calibration_audit'] or not qualified['instrument_qualified_for_application_calibration'] or qualified['errors']:raise ValueError('Native instrument is unqualified')
        agent='scripts/avatar_baseline/native/callback_buffer.js'
        if (repo/agent).read_bytes()!=subprocess.check_output(['git','show',previous['harness_commit']+':'+agent],cwd=repo):raise ValueError('Native agent changed after qualification')
        current=inventory()
        (out/'runner-inventory.json').write_text(json.dumps(current,indent=2)+'\n')
        result['qualified_native_manifest_entries']=len(manifest)
        # Standard hosted allocations can change CPU model. Qualify this very job
        # afresh instead of retrying until a previous model happens to be allocated.
        fresh=out/'native-qualification'
        with (out/'native-qualification.txt').open('w') as stream:
            code=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.hosted_native_calibration',
                '--out',str(fresh)],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
        result['native_qualification_exit_code']=code
        native_result=json.loads((fresh/'result.json').read_text())
        result['fresh_native_qualification']={'status':native_result['status'],
            'instrument_qualified_for_application_calibration':native_result['instrument_qualified_for_application_calibration']}
        if code or not native_result['instrument_qualified_for_application_calibration']:
            raise ValueError('Fresh same-job native qualification failed; application not launched')
        qualified_here=native_audit(fresh/'calibration',repo,ref)
        if qualified_here!=native_result['calibration_audit'] or not qualified_here['instrument_qualified_for_application_calibration'] or qualified_here['errors']:
            raise ValueError('Same-job native qualification audit failed')
        fresh_inventory=json.loads((fresh/'runner-inventory.json').read_text())
        for key in ['machine','affinity_cpus']:
            if current[key]!=fresh_inventory[key]:raise ValueError('Resource condition changed inside job')
        if current['cpu_topology']!=fresh_inventory['cpu_topology'] or current['cgroup_files']['cpu.max']['raw']!=fresh_inventory['cgroup_files']['cpu.max']['raw']:
            raise ValueError('CPU condition changed inside job')
        with (out/'application-runner.txt').open('w') as stream:
            code=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.application_membership','--out',str(out/'application')],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
        result['application_exit_code']=code
        if not (out/'application/assessment.json').exists():raise ValueError('Application receiver prerequisite/capture failed; see raw proof and runner log')
        checked=audit(out/'application',repo)
        if checked!=json.loads((out/'application/assessment.json').read_text()):raise ValueError('Independent application audit differs')
        result['audit']=checked
        result['observer_qualified_for_application_attribution']=bool(code==0 and checked['observer_qualified_for_application_attribution'])
        if result['observer_qualified_for_application_attribution']:result['status']='application_calibration_passed'
    except Exception as error:result['error']=repr(error)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');text=summary(result);(out/'SUMMARY.md').write_text(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write(text)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n');print(text);return result['status']!='application_calibration_passed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();raise SystemExit(run(a.out.resolve()))
