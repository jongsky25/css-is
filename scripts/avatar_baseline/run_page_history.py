"""Fixed fresh-process native page-history calibration/comparison; no acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from scripts.avatar_baseline.run_navigation_light import adapt_fixture

REFS={'original':'1c964dcba2fa19de1eab077b00e0e5748d742554','current':'cf363bfe547d5e23619eee28cdaf68bd4b6d7753'}
HARNESS=('tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py',
 'tests/test_avatar_page_history_browser.py','tests/avatar_page_history_probe.py',
 'scripts/avatar_baseline/native/page_history.js')
BACKEND=('app.py','storage.py','appearance_routes.py','sqlite_reader.py')
BLOCKS=[['original','current','current','original'],['current','original','original','current']]


def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['calibration','comparison'],required=True)
 p.add_argument('--out',type=Path,required=True);p.add_argument('--calibration',type=Path);args=p.parse_args()
 root=Path(__file__).resolve().parents[2];head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 if args.phase=='comparison':
  gate=json.loads(args.calibration.read_text()) if args.calibration else {}
  if gate.get('status')!='calibration_passed' or gate.get('harness_commit')!=head:raise ValueError('Qualified frozen calibration required')
 args.out.mkdir(parents=True,exist_ok=False);out=args.out.resolve()
 blocks=[['current']*4] if args.phase=='calibration' else BLOCKS
 plan={'protocol':'native-page-history-v1','acceptance':False,'phase':args.phase,'refs':REFS,'harness_commit':head,'blocks':blocks,
       'calibration_sha256':hashlib.sha256(args.calibration.read_bytes()).hexdigest() if args.calibration else None,'cohorts':[]}
 for name in HARNESS:
  raw=(root/name).read_bytes()
  if raw!=subprocess.check_output(['git','show',head+':'+name],cwd=root):raise ValueError('Uncommitted harness')
  dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(adapt_fixture(name,raw))
 def save():(out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
 save();roots={};saved={}
 with tempfile.TemporaryDirectory(prefix='native-history-') as temp:
  try:
   for arm,ref in REFS.items():
    cwd=Path(temp)/arm;subprocess.run(['git','worktree','add','--quiet','--detach',str(cwd),ref],cwd=root,check=True)
    roots[arm]=cwd;saved[arm]={}
    for name in HARNESS:
     path=cwd/name;saved[arm][path]=path.read_bytes() if path.exists() else None
     path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((out/'harness'/name).read_bytes())
   for block,arms in enumerate(blocks):
    for position,arm in enumerate(arms):
     index=block*4+position;mode='control' if args.phase=='calibration' and position in (0,3) else 'probe'
     dest=out/f'{index:02d}-{arm}';dest.mkdir()
     env=dict(os.environ,PATH='/workspace/scratch/chromium156-bin'+os.pathsep+os.environ['PATH'],
       CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',CSS_AVATAR_MEMORY_DIAGNOSTIC='1',
       CSS_AVATAR_PAGE_HISTORY='1',CSS_AVATAR_HISTORY_MODE=mode,CSS_AVATAR_RUNS='1',CSS_AVATAR_RUN_START=str(block),
       CSS_AVATAR_SECONDS='30',CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
     with (dest/'runner.txt').open('w') as log:
      code=subprocess.run([sys.executable,'-m','pytest','tests/test_avatar_page_history_browser.py::test_page_history','-s',
          '--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,stdout=log,stderr=subprocess.STDOUT).returncode
     backend={n:hashlib.sha256((roots[arm]/n).read_bytes()).hexdigest() for n in BACKEND if (roots[arm]/n).exists()}
     (dest/'backend-source.json').write_text(json.dumps(backend,sort_keys=True)+'\n')
     plan['cohorts'].append({'index':index,'arm':arm,'mode':mode,'block':block,'position':position,'exit_code':code,
       'files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(dest.iterdir()) if f.is_file()}});save()
     print('SLOT',index,arm,mode,'exit',code,flush=True)
  finally:
   for arm,files in saved.items():
    for path,data in files.items():
     if data is None:path.unlink(missing_ok=True)
     else:path.write_bytes(data)
    subprocess.run(['git','worktree','remove',str(roots[arm])],cwd=root,check=True)
 return any(c['exit_code'] for c in plan['cohorts'])

if __name__=='__main__':raise SystemExit(main())
