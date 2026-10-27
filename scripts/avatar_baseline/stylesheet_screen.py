"""Fixed current/candidate allocation screen with unchanged same-source controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REFS={'current':'f700187553bd555dd3a9b638d5aa8e5fb59f3142','candidate':'69605628393d044f9a0426ea0be3abdf99527bc3'}
ORDER=('current','candidate','candidate','current')
HARNESS=('tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py')


def fixture(name,data):
    if name==HARNESS[0]:
        old=b"    if Path('templates/_avatars_shared.html').exists():"
        new=b"    if Path('static/css/avatars.css').exists():\n        sources.append('static/css/avatars.css')\n"+old
        if data.count(old)!=1:raise ValueError('Unexpected source manifest fixture')
        data=data.replace(old,new,1)
    return data



def validate_visual(assessment):
    if (assessment.get('same_source_control', False)
            or assessment.get('all_pixels_identical') is not True
            or assessment.get('template_reconstructed_exactly') is not True
            or assessment.get('browser') != '156.0.8078.47'
            or assessment.get('cells') != 2880
            or assessment.get('stylesheet_sha256') != '06601d2d375c768da0b55c75b2a4569e23a84dae4ceb687d86ae499ac3956bad'
            or len(assessment.get('sheets', [])) != 30
            or not all(row.get('pixel_identical') is True and row.get('cssom_identical') is True
                       for row in assessment['sheets'])):
        raise ValueError('Visual prerequisite has not passed; memory collection blocked')


def main():
    p=argparse.ArgumentParser();p.add_argument('--visual-assessment',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--browser-dir',type=Path,required=True);a=p.parse_args()
    visual=a.visual_assessment.read_bytes();validate_visual(json.loads(visual))
    root=Path(__file__).resolve().parents[2];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    plan={'visual_assessment_sha256':hashlib.sha256(visual).hexdigest(),'protocol':'shared-stylesheet-screen-v1','acceptance':False,'harness_commit':head,'refs':REFS,'order':ORDER,'samples':2,'seconds':30,'browser':'156.0.8078.47','budget_bytes':10485760,'minimum_improvement_bytes':5242880,'cohorts':[]}
    (out/'visual-assessment.json').write_bytes(visual)
    def save():(out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
    for name in HARNESS:
        data=(root/name).read_bytes()
        if data!=subprocess.check_output(['git','show',head+':'+name],cwd=root):raise ValueError('Uncommitted fixture')
        path=out/'harness'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(fixture(name,data))
    save();roots={};saved={}
    with tempfile.TemporaryDirectory(prefix='avatar-stylesheet-screen-') as temp:
        try:
            for arm,ref in REFS.items():
                cwd=Path(temp)/arm;subprocess.run(['git','worktree','add','--quiet','--detach',str(cwd),ref],cwd=root,check=True)
                roots[arm]=cwd;saved[arm]={}
                for name in HARNESS:
                    path=cwd/name;saved[arm][path]=path.read_bytes() if path.exists() else None
                    path.write_bytes((out/'harness'/name).read_bytes())
            for index,arm in enumerate(ORDER):
                dest=out/f'{index}-{arm}';dest.mkdir()
                env=dict(os.environ,PATH=str(a.browser_dir.resolve())+os.pathsep+os.environ['PATH'],CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_RUNS='2',CSS_AVATAR_SECONDS='30',CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
                with (dest/'runner.txt').open('w') as stream:
                    code=subprocess.run([sys.executable,'-m','pytest','tests/test_avatar_baseline_browser.py::test_real_application_baseline[warm-desktop]','-s','--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
                plan['cohorts'].append({'index':index,'arm':arm,'exit_code':code,'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.iterdir()) if p.is_file()}});save()
                print('COHORT',index,arm,'exit',code,flush=True)
        finally:
            for arm,files in saved.items():
                for path,data in files.items():
                    if data is None:path.unlink(missing_ok=True)
                    else:path.write_bytes(data)
                subprocess.run(['git','worktree','remove',str(roots[arm])],cwd=root,check=True)
    return 0 if len(plan['cohorts'])==4 and all(c['exit_code']==0 for c in plan['cohorts']) else 1


if __name__=='__main__':sys.exit(main())
