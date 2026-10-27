"""Execute one frozen four-slot synthetic membership calibration; no replacements."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from scripts.avatar_baseline.analyze_membership_lifecycle import SOURCES, PROTOCOL


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True, type=Path); a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    for name in SOURCES:
        if (repo / name).read_bytes() != subprocess.check_output(['git', 'show', head + ':' + name], cwd=repo):
            raise ValueError('Uncommitted harness: ' + name)
    a.out.mkdir(parents=True, exist_ok=False); out = a.out.resolve()
    plan = {'protocol': PROTOCOL, 'acceptance': False, 'harness_commit': head,
            'order': ['control', 'probe', 'probe', 'control'], 'cohorts': []}
    for name in SOURCES:
        dest = out / 'harness' / name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((repo / name).read_bytes())
    def save(): (out / 'experiment.json').write_text(json.dumps(plan, indent=2) + '\n')
    save()
    for index, mode in enumerate(plan['order']):
        dest = out / f'{index}-{mode}'
        log = out / f'{index}-{mode}.txt'
        with log.open('w') as stream:
            code = subprocess.run([sys.executable, '-m', 'scripts.avatar_baseline.element_membership_lifecycle',
                                   '--out', str(dest), '--mode', mode], cwd=repo, stdout=stream, stderr=subprocess.STDOUT).returncode
        dest.mkdir(exist_ok=True); (dest / 'runner.txt').write_bytes(log.read_bytes()); log.unlink()
        plan['cohorts'].append({'index': index, 'mode': mode, 'exit_code': code,
            'files_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(dest.iterdir()) if f.is_file()}})
        save(); print('SLOT', index, mode, 'exit', code, flush=True)
    return int(any(c['exit_code'] for c in plan['cohorts']))


if __name__ == '__main__': raise SystemExit(main())
