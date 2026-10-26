import os,subprocess,shutil,json,hashlib
from pathlib import Path
root=Path('/workspace/css-is');out=Path('/workspace/scratch/collection-attribution')
work=out/'original'
subprocess.run(['git','worktree','add','--detach',str(work),'1c964dc'],cwd=root,check=True)
for name in ['test_avatar_baseline_browser.py','avatar_browser_fixture.py','test_avatar_collection_attribution.py']:
    shutil.copy2(root/'tests'/name,work/'tests'/name)
for index,arm in enumerate(['original','current','current','original']):
    dest=out/f'{index}-{arm}';dest.mkdir()
    cwd=work if arm=='original' else root
    env=dict(os.environ,PATH='/workspace/scratch/chromium156-bin:'+os.environ['PATH'],CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0',CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_COLLECTION_DIAGNOSTIC='1',CSS_AVATAR_RUNS='1',CSS_AVATAR_SECONDS='30',CSS_AVATAR_CHROMIUM='156.0.8078.47',CSS_AVATAR_OUT=str(dest))
    with (dest/'runner.txt').open('w') as log:
        result=subprocess.run([str(root/'.venv/bin/python'),'-m','pytest','tests/test_avatar_collection_attribution.py','-s','--junitxml='+str(dest/'junit.xml')],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
    print(index,arm,result.returncode,flush=True)
    if result.returncode:break
