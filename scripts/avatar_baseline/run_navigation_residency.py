"""Eight-slot per-navigation allocator/residency diagnosis; no acceptance claim."""
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
HARNESS=('tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',
         'tests/test_avatar_navigation_residency_browser.py')


def adapt_fixture(name,data):
    if name=='tests/test_avatar_baseline_browser.py':
        old=b'for run in range(runs):'
        if data.count(old)!=1:raise ValueError('Unexpected workload loop')
        data=data.replace(old,b"for run in range(int(os.getenv('CSS_AVATAR_RUN_START', '0')), int(os.getenv('CSS_AVATAR_RUN_START', '0')) + runs):",1)
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser-dir',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    plan={'protocol':'navigation-residency-v2','acceptance':False,'harness_commit':head,
          'refs':REFS,'blocks':BLOCKS,'samples_per_slot':1,'seconds':30,'fixture_adapter':'sample-ordinal-v1',
          'browser':'156.0.8078.47','budget_bytes':10*1024*1024,
          'session_policy':'Fresh pytest process, fixture database and browser for each slot. Existing warm-up and full workload unchanged. Diagnostic session/order change; not historical acceptance replacement.',
          'selection':'Eight fixed slots; 20 natural detailed dumps per slot, determinism none. Status sampling every 100ms during navigation. Keep all samples and failures. Descriptive correlations only; no acceptance, outlier removal or source-effect classification.',
          'cohorts':[]}
    def save():(out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
    for name in HARNESS:
        data=(root/name).read_bytes()
        if data!=subprocess.check_output(['git','show',head+':'+name],cwd=root):
            raise ValueError('Commit fixture changes before measurement: '+name)
        dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(adapt_fixture(name,data))
    save();roots={};saved={}
    with tempfile.TemporaryDirectory(prefix='avatar-navigation-residency-') as temp:
        try:
            for arm,ref in REFS.items():
                cwd=Path(temp)/arm
                subprocess.run(['git','worktree','add','--quiet','--detach',str(cwd),ref],cwd=root,check=True)
                roots[arm]=cwd;saved[arm]={}
                for name in HARNESS:
                    path=cwd/name;saved[arm][path]=path.read_bytes() if path.exists() else None
                    path.write_bytes((out/'harness'/name).read_bytes())
            for block,arms in enumerate(BLOCKS):
                for position,arm in enumerate(arms):
                    index=block*4+position;dest=out/f'{index:02d}-{arm}';dest.mkdir()
                    env=dict(os.environ,PATH=str(args.browser_dir.resolve())+os.pathsep+os.environ['PATH'],
                        CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',
                        CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_NAVIGATION_RESIDENCY='1',CSS_AVATAR_RUNS='1',CSS_AVATAR_RUN_START=str(block),CSS_AVATAR_SECONDS='30',
                        CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
                    with (dest/'runner.txt').open('w') as stream:
                        code=subprocess.run([sys.executable,'-m','pytest',
                            'tests/test_avatar_navigation_residency_browser.py::test_navigation_residency',
                            '-s','--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,
                            stdout=stream,stderr=subprocess.STDOUT).returncode
                    row={'index':index,'block':block,'position':position,'arm':arm,'exit_code':code}
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
    return 0 if len(plan['cohorts'])==8 and all(c['exit_code']==0 for c in plan['cohorts']) else 1


if __name__=='__main__':sys.exit(main())
