"""One fixed diagnostic on a new hosted runner; no application calibration/release."""
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
from scripts.avatar_baseline.control_phase_timing import SOURCES, audit
from scripts.avatar_baseline.element_membership_lifecycle import BROWSER, BUILD
from scripts.avatar_baseline.runner_isolation_inventory import inventory
from scripts.avatar_baseline.summarize_control_timing import summarize

EXTRA_SOURCES = ['scripts/avatar_baseline/hosted_runner_diagnostic.py',
                 'scripts/avatar_baseline/runner_isolation_inventory.py',
                 'scripts/avatar_baseline/summarize_control_timing.py',
                 'requirements-test.txt','requirements-avatar-native.txt']


def mobile_summary(result):
    lines=['# Cloud runner diagnostic', '',
           'This checks the new GitHub runner. It does not accept 2B or deploy the app.', '',
           '**Result: '+result['status'].replace('_',' ')+'**', '']
    if result.get('error'):lines+=['Capture error: `'+result['error'].replace('`',"'")+'`','']
    if 'context' in result:
        lines+=['| Control | Duration (ms) | CPU steal context |','| --- | ---: | ---: |']
        for c in result['context']['cohorts']:
            fraction=c['system_steal_fraction'];percent=f'{fraction*100:.2f}%' if fraction is not None else 'unavailable'
            lines.append(f"| {c['index']+1} | {c['duration_ms']:.2f} | {percent} |")
        lines+=['','CPU steal is shared CPU context, not an adjustment to durations.','']
    lines+=['Download the **avatar-runner-diagnostic** artifact for all raw results, including failures.',
            'The earlier failed calibration remains failed. No automatic retry or application comparison follows.','']
    return '\n'.join(lines)


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    result={'status':'setup_failed','acceptance':False,'instrument_qualified_for_application_calibration':False,
            'runner_condition':'standard-github-ubuntu-24.04-new-environment','isolation_established':False,
            'harness_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
            'python':platform.python_version(),'dependencies':{},'source_sha256':{},
            'github':{key:os.environ[key] for key in ['GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY',
                      'GITHUB_WORKFLOW_REF','GITHUB_SHA','GITHUB_REF','RUNNER_OS','RUNNER_ARCH','RUNNER_ENVIRONMENT'] if key in os.environ}}
    try:
        for name in [*SOURCES,*EXTRA_SOURCES]:
            raw=(repo/name).read_bytes()
            if raw!=subprocess.check_output(['git','show',result['harness_commit']+':'+name],cwd=repo):raise ValueError('Uncommitted diagnostic source: '+name)
            dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            result['source_sha256'][name]=hashlib.sha256(raw).hexdigest()
        if platform.machine()!='x86_64' or result['python']!='3.12.14':raise ValueError('Wrong machine/Python')
        for name,expected in [('playwright','1.62.0'),('frida','17.5.1')]:
            result['dependencies'][name]=importlib.metadata.version(name)
            if result['dependencies'][name]!=expected:raise ValueError('Wrong '+name+' version')
        notes=subprocess.check_output(['readelf','-n',str(BROWSER)],text=True)
        if 'Build ID: '+BUILD not in notes:raise ValueError('Wrong browser ELF build')
        result['browser_build_id']=BUILD
        (out/'runner-inventory.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        diagnostic=out/'controls'
        with (out/'diagnostic-runner.txt').open('w') as stream:
            result['runner_exit_code']=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.control_phase_timing','run',
                          '--out',str(diagnostic)],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
        checked=audit(diagnostic,repo)
        with gzip.open(out/'audit.json.gz','wt') as stream:json.dump(checked,stream,indent=2)
        if result['runner_exit_code'] or checked['status']!='diagnostic_complete':raise ValueError('One or more fixed controls failed; retained without replacement')
        context=summarize(diagnostic,repo)
        (out/'cpu-context-summary.json').write_text(json.dumps(context,indent=2)+'\n')
        result['context']=context
        result['status']='hosted_diagnostic_complete'
    except Exception as error:
        result.update(status='diagnostic_failed',error=repr(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    summary=mobile_summary(result);(out/'SUMMARY.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write(summary)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(summary);return result['status']!='hosted_diagnostic_complete'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();raise SystemExit(run(a.out.resolve()))
