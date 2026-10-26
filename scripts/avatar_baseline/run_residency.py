"""Run four serialized original/current native-residency diagnostics."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser-dir',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest={'acceptance':False,'order':['original','current','current','original'],
        'refs':{'original':'1c964dc','current':'f700187'},'cohorts':[]}
    (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    saved={};roots={}
    with tempfile.TemporaryDirectory(prefix='avatar-residency-') as temp:
        try:
            for arm,ref in manifest['refs'].items():
                cwd=Path(temp)/arm
                subprocess.run(['git','worktree','add','--detach',str(cwd),ref],cwd=root,check=True)
                roots[arm]=cwd;saved[arm]={}
                for name in ['test_avatar_baseline_browser.py','avatar_browser_fixture.py','test_avatar_collection_attribution.py']:
                    dest=cwd/'tests'/name;saved[arm][dest]=dest.read_bytes() if dest.exists() else None
                    dest.write_bytes((root/'tests'/name).read_bytes())
            for index,arm in enumerate(manifest['order']):
                dest=out/f'{index}-{arm}';dest.mkdir()
                env=dict(os.environ,PATH=str(args.browser_dir.resolve())+os.pathsep+os.environ['PATH'],
                    CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',
                    CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_COLLECTION_DIAGNOSTIC='1',
                    CSS_AVATAR_RESIDENCY_DIAGNOSTIC='1',CSS_AVATAR_RUNS='1',CSS_AVATAR_SECONDS='30',
                    CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
                with (dest/'runner.txt').open('w') as stream:
                    result=subprocess.run([sys.executable,'-m','pytest','tests/test_avatar_collection_attribution.py',
                        '-s','--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,stdout=stream,stderr=subprocess.STDOUT)
                manifest['cohorts'].append({'index':index,'arm':arm,'exit_code':result.returncode})
                (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
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
