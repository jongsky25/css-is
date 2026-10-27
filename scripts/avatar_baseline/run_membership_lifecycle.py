"""Execute one frozen four-slot synthetic membership calibration; no replacements."""
import argparse
import hashlib
import json
import gzip
from pathlib import Path
import subprocess
import sys
from scripts.avatar_baseline.analyze_membership_lifecycle import SOURCES, PROTOCOL


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True, type=Path); p.add_argument('--receiver-capability',type=Path); a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    for name in SOURCES:
        if (repo / name).read_bytes() != subprocess.check_output(['git', 'show', head + ':' + name], cwd=repo):
            raise ValueError('Uncommitted harness: ' + name)
    if PROTOCOL=='native-membership-lifecycle-v7':
        from scripts.avatar_baseline.absent_attribute_capability import audit as audit_capability
        if a.receiver_capability is None: raise ValueError('Exact getter capability required')
        assessment=json.loads((a.receiver_capability/'assessment.json').read_text())
        proof=audit_capability(a.receiver_capability,repo,assessment['harness_commit'])
        if proof!=assessment or proof['status']!='capability_passed': raise ValueError('Receiver capability failed')
        captured=json.load(gzip.open(a.receiver_capability/'capture.json.gz','rt'))
        for name,sha in captured['source_sha256'].items():
            if hashlib.sha256((repo/name).read_bytes()).hexdigest()!=sha: raise ValueError('Getter changed after proof')
    a.out.mkdir(parents=True, exist_ok=False); out = a.out.resolve()
    plan = {'protocol': PROTOCOL, 'acceptance': False, 'harness_commit': head,
            'order': ['control', 'probe', 'probe', 'control'], 'cohorts': []}
    if PROTOCOL=='native-membership-lifecycle-v7':
        caproot=out/'receiver-capability'; caproot.mkdir()
        for name in ['capture.json.gz','assessment.json']:
            (caproot/name).write_bytes((a.receiver_capability/name).read_bytes())
        plan['receiver_capability']={'harness_commit':assessment['harness_commit'],
            'capture_sha256':hashlib.sha256((caproot/'capture.json.gz').read_bytes()).hexdigest(),
            'assessment_sha256':hashlib.sha256((caproot/'assessment.json').read_bytes()).hexdigest()}
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
