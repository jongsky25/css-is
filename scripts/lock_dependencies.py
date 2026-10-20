"""Regenerate hashed dependency locks with the reviewed uv tool version."""
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LOCKS = {
    'requirements.txt': ('requirements.in',),
    'requirements-test.txt': ('requirements-test.in', 'requirements.in', 'requirements.txt'),
    'requirements-tools.txt': ('requirements-tools.in',),
    'requirements-deploy.txt': ('requirements-deploy.in',),
}


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_locks(root=ROOT):
    for lock, sources in LOCKS.items():
        content = (root / lock).read_text()
        for source in sources:
            stamp = f'# Input-SHA256: {source}={fingerprint(root / source)}'
            if stamp not in content.splitlines():
                raise ValueError(f'{lock} is stale for {source}; regenerate dependency locks')


def regenerate(*, upgrade=False):
    expected = next(line.split('==', 1)[1].strip() for line in
                    (ROOT / 'requirements-tools.in').read_text().splitlines() if line.startswith('uv=='))
    actual = subprocess.check_output(['uv', '--version'], text=True).split()[1]
    if actual != expected:
        raise ValueError(f'Use the locked uv version {expected}; found {actual}')
    for lock, sources in LOCKS.items():
        subprocess.run(['uv', 'pip', 'compile', sources[0], '--universal',
                        '--python-version', '3.11', '--generate-hashes',
                        '--output-file', lock, '--quiet'] + (['--upgrade'] if upgrade else []),
                       cwd=ROOT, check=True)
        path = ROOT / lock
        stamps = ''.join(f'# Input-SHA256: {source}={fingerprint(ROOT / source)}\n'
                         for source in sources)
        path.write_text(stamps + path.read_text())
    check_locks()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Check input fingerprints without network access')
    mode.add_argument('--upgrade', action='store_true', help='Refresh transitive versions deliberately')
    args = parser.parse_args()
    if args.check:
        check_locks()
        print('Dependency lock inputs are current')
    else:
        regenerate(upgrade=args.upgrade)
