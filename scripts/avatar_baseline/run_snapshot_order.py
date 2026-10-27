"""Four frozen current-only calibration slots; never release acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from scripts.avatar_baseline.analyze_cat_gradients import REFS

HARNESS = ['tests/test_avatar_baseline_browser.py', 'tests/avatar_browser_fixture.py',
           'tests/test_avatar_snapshot_order_browser.py', 'tests/avatar_snapshot_timing.py']
BACKEND = ['app.py', 'storage.py', 'appearance_routes.py', 'sqlite_reader.py']
BUILD = '1c5dca8527a61d07372e489142bee26af1bcaf71'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--browser', type=Path, required=True); a = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    for name in HARNESS:
        if (repo / name).read_bytes() != subprocess.check_output(['git', 'show', head + ':' + name], cwd=repo):
            raise ValueError('Uncommitted harness: ' + name)
    browser = a.browser.resolve()
    build = subprocess.check_output(['readelf', '-n', str(browser)], text=True)
    version = subprocess.check_output([str(browser), '--version'], text=True).strip()
    if 'Build ID: ' + BUILD not in build or 'Chromium 156.0.8078.47' not in version:
        raise ValueError('Wrong pinned browser build/version')
    a.out.mkdir(parents=True, exist_ok=False); out = a.out.resolve()
    plan = {'protocol': 'snapshot-order-v1', 'acceptance': False, 'phase': 'calibration',
            'harness_commit': head, 'source_commit': REFS['current'], 'build_id': BUILD,
            'browser_sha256': digest(browser), 'browser_version': version,
            'order': ['control', 'probe', 'probe', 'control'], 'seconds': 30, 'cohorts': []}
    for name in HARNESS:
        dest = out / 'harness' / name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((repo / name).read_bytes())
    def save():
        (out / 'experiment.json').write_text(json.dumps(plan, indent=2) + '\n')
    save()
    with tempfile.TemporaryDirectory(prefix='snapshot-order-') as temp:
        cwd = Path(temp) / 'current'
        subprocess.run(['git', 'worktree', 'add', '--quiet', '--detach', str(cwd), REFS['current']], cwd=repo, check=True)
        try:
            for name in HARNESS:
                (cwd / name).write_bytes((repo / name).read_bytes())
            bindir = Path(temp) / 'bin'; bindir.mkdir()
            (bindir / 'chromium').symlink_to(browser)
            for index, mode in enumerate(plan['order']):
                dest = out / f'{index}-{mode}'; dest.mkdir()
                env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                    CSS_TEST_NOW='2026-07-15T12:00:00', CSS_AVATAR_BASELINE='1', CSS_AVATAR_PIN_RENDERER='0',
                    CSS_AVATAR_MEMORY_DIAGNOSTIC='1', CSS_AVATAR_SNAPSHOT_ORDER='1', CSS_AVATAR_ORDER_MODE=mode,
                    CSS_AVATAR_RUNS='1', CSS_AVATAR_SECONDS='30', CSS_AVATAR_CHROMIUM='156.0.8078.47', CSS_AVATAR_OUT=str(dest))
                with (dest / 'runner.txt').open('w') as log:
                    code = subprocess.run([sys.executable, '-m', 'pytest',
                        'tests/test_avatar_snapshot_order_browser.py::test_snapshot_order', '-s',
                        '--junitxml=' + str(dest / 'junit.xml')], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
                (dest / 'backend-source.json').write_text(json.dumps({n: digest(cwd / n) for n in BACKEND}, indent=2) + '\n')
                plan['cohorts'].append({'index': index, 'mode': mode, 'exit_code': code,
                    'files_sha256': {f.name: digest(f) for f in sorted(dest.iterdir()) if f.is_file()}})
                save(); print('SLOT', index, mode, 'exit', code, flush=True)
        finally:
            # Remove only this runner's disposable checkout, including copied probe files.
            subprocess.run(['git', 'worktree', 'remove', '--force', str(cwd)], cwd=repo, check=True)
    return int(any(c['exit_code'] for c in plan['cohorts']))


if __name__ == '__main__':
    raise SystemExit(main())
