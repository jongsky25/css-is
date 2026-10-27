"""One fixed native-recorder calibration on the declared GitHub hosted condition."""
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
from scripts.avatar_baseline.analyze_membership_lifecycle import SOURCES as SCREEN_SOURCES, audit as audit_screen
from scripts.avatar_baseline.native_recorder_selftest import SOURCES as NATIVE_SOURCES, audit as audit_native
from scripts.avatar_baseline.mixed_getter_capability import sources_for_backend, audit as audit_receiver
from scripts.avatar_baseline.element_membership_lifecycle import BROWSER, BUILD
from scripts.avatar_baseline.runner_isolation_inventory import inventory
from scripts.avatar_baseline.summarize_membership_lifecycle import summarize

SOURCES=list(dict.fromkeys([*SCREEN_SOURCES,*NATIVE_SOURCES,*sources_for_backend('cmodule-buffer-v1'),
    'scripts/avatar_baseline/hosted_native_calibration.py',
    'scripts/avatar_baseline/runner_isolation_inventory.py',
    'scripts/avatar_baseline/summarize_membership_lifecycle.py',
    'requirements-test.txt','requirements-avatar-native.txt']))


def summary(result):
    lines=['# Cloud native-recorder calibration','',
           '**Result: '+result['status'].replace('_',' ')+'**','',
           'This calibrates the measurement instrument. It does not accept 2B or deploy the app.','']
    if result.get('error'):lines+=['Error: `'+result['error'].replace('`',"'")+'`','']
    checked=result.get('calibration_audit')
    if checked:
        lines+=['| Slot | Mode | Duration ms | Observation bound |','| --- | --- | ---: | ---: |']
        for c in checked['cohorts']:
            duration=f"{c['duration_ms']:.2f}" if 'duration_ms' in c else 'unavailable'
            fraction=f"{c['observation_fraction_bound']*100:.3f}%" if 'observation_fraction_bound' in c else 'unavailable'
            lines.append(f"| {c['index']+1} | {c.get('mode','invalid')} | {duration} | {fraction} |")
        lines+=['']
        for error in checked['errors']:lines.append('- '+error)
    if result['instrument_qualified_for_application_calibration']:
        lines+=['','All frozen instrument gates passed on this runner condition.',
                'Application memory measurements still require a separately frozen protocol.']
    else:lines+=['','The instrument is not qualified for application calibration.']
    lines+=['','Download **avatar-native-calibration** for every proof, raw slot, trace, audit and failure.',
            'No failed sample is replaced and no automatic retry or application comparison follows.','']
    return '\n'.join(lines)


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    result={'status':'setup_failed','acceptance':False,'application_qualified':False,
            'instrument_qualified_for_application_calibration':False,'harness_commit':ref,
            'runner_condition':'standard-github-ubuntu-24.04-python3.12.14-sys-ptrace',
            'source_sha256':{},'steps':[],'python':platform.python_version(),
            'github':{k:os.environ[k] for k in ['GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY',
                'GITHUB_WORKFLOW_REF','GITHUB_SHA','GITHUB_REF','RUNNER_OS','RUNNER_ARCH','RUNNER_ENVIRONMENT'] if k in os.environ}}
    try:
        for name in SOURCES:
            raw=(repo/name).read_bytes()
            if raw!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Uncommitted calibration source: '+name)
            dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            result['source_sha256'][name]=hashlib.sha256(raw).hexdigest()
        if platform.machine()!='x86_64' or result['python']!='3.12.14':raise ValueError('Wrong machine/Python')
        result['dependencies']={k:importlib.metadata.version(k) for k in ['playwright','frida']}
        if result['dependencies']!={'playwright':'1.62.0','frida':'17.5.1'}:raise ValueError('Wrong native toolchain')
        if 'Build ID: '+BUILD not in subprocess.check_output(['readelf','-n',str(BROWSER)],text=True):raise ValueError('Wrong Chromium ELF')
        caps=next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:'))
        result['sys_ptrace_effective']=bool(int(caps,16)&(1<<19))
        if not result['sys_ptrace_effective']:raise ValueError('Declared container SYS_PTRACE capability absent')
        (out/'runner-inventory.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        def step(label,module,args):
            with (out/(label+'.txt')).open('w') as stream:
                code=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.'+module,*args],cwd=repo,
                                    stdout=stream,stderr=subprocess.STDOUT).returncode
            result['steps'].append({'name':label,'exit_code':code})
            if code:raise ValueError(label+' failed; later phases not launched')
        native=out/'native-preflight'
        step('native-preflight','native_recorder_selftest',['--out',str(native)])
        result['native_preflight']=audit_native(native,repo,ref)
        if result['native_preflight']!=json.loads((native/'assessment.json').read_text()) or result['native_preflight']['status']!='selftest_passed':raise ValueError('Native preflight audit failed')
        receiver=out/'receiver-capability'
        step('receiver-capability','mixed_getter_capability',['--native-recorder-preflight',str(native),'--out',str(receiver)])
        result['receiver_capability']=audit_receiver(receiver,repo,ref)
        if result['receiver_capability']!=json.loads((receiver/'assessment.json').read_text()) or result['receiver_capability']['status']!='capability_passed':raise ValueError('Receiver proof audit failed')
        screen=out/'calibration'
        # The runner records all four slots even when an individual slot exits nonzero.
        with (out/'calibration-runner.txt').open('w') as stream:
            code=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.run_membership_lifecycle',
                '--receiver-capability',str(receiver),'--out',str(screen)],cwd=repo,
                stdout=stream,stderr=subprocess.STDOUT).returncode
        result['steps'].append({'name':'calibration','exit_code':code})
        checked=audit_screen(screen,repo,ref);result['calibration_audit']=checked
        with gzip.open(out/'calibration-audit.json.gz','wt') as stream:json.dump(checked,stream,indent=2)
        if checked['files_verified']==14 and checked['source_hashes_verified']==16:
            periods=summarize(screen,repo,ref)
            with gzip.open(out/'native-periods.json.gz','wt') as stream:json.dump(periods,stream,indent=2)
        result['instrument_qualified_for_application_calibration']=bool(
            code==0 and checked.get('instrument_qualified_for_application_calibration') and not checked['errors'])
        result['status']='calibration_passed' if result['instrument_qualified_for_application_calibration'] else 'calibration_failed'
    except Exception as error:result.update(status='calibration_failed',error=repr(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    text=summary(result);(out/'SUMMARY.md').write_text(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write(text)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(text);return result['status']!='calibration_passed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();raise SystemExit(run(a.out.resolve()))
