"""Counterbalanced source screening, not acceptance or a product rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ARMS=('current','geometry','preview','svg','svg','preview','geometry','current')


def source(root, ref, path):
    return subprocess.check_output(['git','show',ref+':'+path],cwd=root)


def variant(root,cwd,arm):
    changed={}
    if arm=='geometry':
        path='static/js/avatars.js';s=(cwd/path).read_text()
        assert s.count('if (window.ResizeObserver) {')==1
        changed[path]=s.replace('if (window.ResizeObserver) {','if (false && window.ResizeObserver) {',1).encode()
    elif arm=='preview':
        for path in ['templates/_avatars.html','templates/_growth.html','templates/me.html']:
            changed[path]=source(root,'f700187^',path)
    elif arm=='svg':
        path='templates/_avatars_art.html';s=source(root,'1c964dc',path).decode()
        assert s.count('macro species_art(kind, s, m=0, costume="")')==1
        changed[path]=s.replace('macro species_art(kind, s, m=0, costume="")','macro species_art(kind, s, m=0, costume="", scope="")',1).encode()
        path='templates/_avatars.html';s=(cwd/path).read_text()
        line=next(x for x in s.splitlines() if x.startswith('{% set scope = avatar_uid()'))
        changed[path]=s.replace(line,'{% set scope = "" %}',1).encode()
    for path,data in changed.items():(cwd/path).write_bytes(data)
    return changed


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser-dir',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan={'acceptance':False,'base':'f700187','order':ARMS,'samples_per_arm':2,
        'protocol':'Full 30-second warm desktop workload, no tracing, native sampling, dump requests or concurrent analysis. Two-sample source screen only; never final acceptance.',
        'variants':{'geometry':'Disable only avatar ResizeObserver registrations; keep cache, pointer, audio, SVG and static policy unchanged. Diagnostic can regress resize behavior.',
                    'preview':'Revert only f700187 static-preview wrapper/reaction omission, using its parent versions of three templates. Artwork remains current.',
                    'svg':'Original species-art dispatcher with unused scope adapter; disable v2 scope/gradient emission. Current runtime and static-preview policy retained. Intentional visual reversion, never promotable unchanged.'},
        'selection':'Require RSS improvement of at least 5 MiB at both navigation 10 and 20 in both orders, no RSS or heap checkpoint worsening >10 MiB, and valid samples/counts. Screen only; five-sample validation needed.',
        'cohorts':[]}
    (out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
    saved={};roots={}
    with tempfile.TemporaryDirectory(prefix='avatar-source-screen-') as temp:
        try:
            for arm in dict.fromkeys(ARMS):
                cwd=Path(temp)/arm
                subprocess.run(['git','worktree','add','--quiet','--detach',str(cwd),'f700187'],cwd=root,check=True)
                roots[arm]=cwd;saved[arm]={}
                paths=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py','static/js/avatars.js','templates/_avatars.html','templates/_avatars_art.html','templates/_growth.html','templates/me.html']
                for path in paths:
                    p=cwd/path;saved[arm][p]=p.read_bytes() if p.exists() else None
                for path in paths[:2]:(cwd/path).write_bytes((root/path).read_bytes())
                changes=variant(root,cwd,arm)
                evidence=out/'variants'/arm;evidence.mkdir(parents=True)
                for path,data in changes.items():
                    target=evidence/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                (evidence/'diff.patch').write_bytes(subprocess.check_output(['git','diff','--','static','templates'],cwd=cwd))
                (evidence/'hashes.json').write_text(json.dumps({p:hashlib.sha256(d).hexdigest() for p,d in changes.items()},indent=2)+'\n')
            for index,arm in enumerate(ARMS):
                dest=out/f'{index}-{arm}';dest.mkdir()
                env=dict(os.environ,PATH=str(args.browser_dir.resolve())+os.pathsep+os.environ['PATH'],
                    CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',
                    CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_RUNS='2',CSS_AVATAR_SECONDS='30',
                    CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
                with (dest/'runner.txt').open('w') as stream:
                    result=subprocess.run([sys.executable,'-m','pytest',
                        'tests/test_avatar_baseline_browser.py::test_real_application_baseline[warm-desktop]',
                        '-s','--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,stdout=stream,stderr=subprocess.STDOUT)
                plan['cohorts'].append({'index':index,'arm':arm,'exit_code':result.returncode})
                (out/'experiment.json').write_text(json.dumps(plan,indent=2)+'\n')
                print(index,arm,'exit',result.returncode,flush=True)
                if result.returncode:return result.returncode
        finally:
            for arm,files in saved.items():
                for path,data in files.items():
                    if data is None:path.unlink(missing_ok=True)
                    else:path.write_bytes(data)
                subprocess.run(['git','worktree','remove',str(roots[arm])],cwd=root,check=True)
    return 0


if __name__=='__main__':sys.exit(main())
