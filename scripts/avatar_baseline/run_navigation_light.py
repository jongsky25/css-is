"""Calibrated bounded-trace navigation diagnosis; no acceptance claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REFS={'original':'1c964dcba2fa19de1eab077b00e0e5748d742554',
      'current':'f700187553bd555dd3a9b638d5aa8e5fb59f3142'}
BLOCKS=(('original','current','current','original'),
        ('current','original','original','current'))
BACKEND=('app.py','appearance_routes.py','storage.py','sqlite_reader.py')
HARNESS=('tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',
         'tests/test_avatar_navigation_light_browser.py','tests/avatar_scheduler_probe.py')


def adapt_fixture(name,data):
    if name=='tests/test_avatar_baseline_browser.py':
        old=b'for run in range(runs):'
        if data.count(old)!=1:raise ValueError('Unexpected workload loop')
        data=data.replace(old,b"for run in range(int(os.getenv('CSS_AVATAR_RUN_START', '0')), int(os.getenv('CSS_AVATAR_RUN_START', '0')) + runs):",1)
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate-ref', help='Explicit committed current candidate; historical default stays unchanged')
    parser.add_argument('--phase',choices=['calibration','comparison'],required=True)
    parser.add_argument('--calibration-audit',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser-dir',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    refs=dict(REFS)
    if args.candidate_ref:
        refs['current']=subprocess.check_output(['git','rev-parse',args.candidate_ref+'^{commit}'],cwd=root,text=True).strip()
    if args.phase=='comparison':
        if not args.calibration_audit:raise ValueError('Calibration audit required')
        gate=json.loads(args.calibration_audit.read_text())
        if gate.get('status')!='calibration_passed' or gate.get('protocol')!='navigation-light-v6':raise ValueError('Calibration did not pass')
    blocks=(('current','current','current','current'),) if args.phase=='calibration' else BLOCKS
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    plan={'protocol':'navigation-light-v6','phase':args.phase,'acceptance':False,'harness_commit':head,
          'refs':refs,'blocks':blocks,'samples_per_slot':1,'seconds':30,'fixture_adapter':'sample-ordinal-v1',
          'browser':'156.0.8078.47','budget_bytes':10*1024*1024,
          'session_policy':'Fresh pytest process, fixture database and browser for each slot. Existing warm-up and full workload unchanged. Diagnostic session/order change; not historical acceptance replacement.',
          'selection':'Fixed calibration control/trace/trace/control; then eight comparison trace slots if calibration passes. Two bounded navigation traces with deferred stream transfer, one post-workload dump. Scheduler/cgroup counters and navigation intervals in every arm. No replacements or forced GC.',
          'calibration_audit_sha256':hashlib.sha256(args.calibration_audit.read_bytes()).hexdigest() if args.calibration_audit else None,
          'cohorts':[]}
    def save():(out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
    for name in HARNESS:
        data=(root/name).read_bytes()
        if data!=subprocess.check_output(['git','show',head+':'+name],cwd=root):
            raise ValueError('Commit fixture changes before measurement: '+name)
        dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(adapt_fixture(name,data))
    if args.phase=='comparison' and (gate['harness_commit']!=head or gate.get('candidate_refs', REFS)!=refs):raise ValueError('Calibration harness or source changed')
    save();roots={};saved={}
    with tempfile.TemporaryDirectory(prefix='avatar-navigation-light-') as temp:
        try:
            for arm,ref in refs.items():
                cwd=Path(temp)/arm
                subprocess.run(['git','worktree','add','--quiet','--detach',str(cwd),ref],cwd=root,check=True)
                roots[arm]=cwd;saved[arm]={}
                for name in HARNESS:
                    path=cwd/name;saved[arm][path]=path.read_bytes() if path.exists() else None
                    path.write_bytes((out/'harness'/name).read_bytes())
            for block,arms in enumerate(blocks):
                for position,arm in enumerate(arms):
                    index=block*4+position;dest=out/f'{index:02d}-{arm}';dest.mkdir()
                    env=dict(os.environ,PATH=str(args.browser_dir.resolve())+os.pathsep+os.environ['PATH'],
                        CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',
                        CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_NAVIGATION_LIGHT='1',CSS_AVATAR_TRACE_MODE=('control' if args.phase=='calibration' and position in (0,3) else 'trace'),CSS_AVATAR_RUNS='1',CSS_AVATAR_RUN_START=str(block),CSS_AVATAR_SECONDS='30',
                        CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
                    with (dest/'runner.txt').open('w') as stream:
                        code=subprocess.run([sys.executable,'-m','pytest',
                            'tests/test_avatar_navigation_light_browser.py::test_navigation_light',
                            '-s','--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,
                            stdout=stream,stderr=subprocess.STDOUT).returncode
                    if args.candidate_ref:
                        backend={name:hashlib.sha256((roots[arm]/name).read_bytes()).hexdigest()
                                 for name in BACKEND if (roots[arm]/name).exists()}
                        (dest/'backend-source.json').write_text(json.dumps(backend,sort_keys=True)+'\n')
                    row={'index':index,'block':block,'position':position,'arm':arm,'mode':env['CSS_AVATAR_TRACE_MODE'],'exit_code':code}
                    raw=dest/'False-warm.json'
                    if raw.exists():row['raw_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
                    row['files_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.iterdir()) if p.is_file()}
                    plan['cohorts'].append(row);save()
                    print('SLOT',index,'BLOCK',block,'POSITION',position,arm,'exit',code,flush=True)
        finally:
            for arm,files in saved.items():
                for path,data in files.items():
                    if data is None:path.unlink(missing_ok=True)
                    else:path.write_bytes(data)
                subprocess.run(['git','worktree','remove',str(roots[arm])],cwd=root,check=True)
    return 0 if len(plan['cohorts'])==sum(map(len,blocks)) and all(c['exit_code']==0 for c in plan['cohorts']) else 1


if __name__=='__main__':sys.exit(main())
