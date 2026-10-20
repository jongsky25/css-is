"""Reject missing/incomplete audit evidence and mismatched runtime/test packages."""
import argparse
import json
from pathlib import Path
import re


def packages(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+)', line)
        if not match:
            raise ValueError(f'Non-versioned installed package in {path}')
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        if name in result:
            raise ValueError(f'Duplicate installed package {name}')
        result[name] = match[2]
    if not result:
        raise ValueError('Installed dependency inventory is empty')
    return result


def check_report(inventory, report):
    expected = packages(inventory)
    data = json.loads(Path(report).read_text())
    scanned = {}
    for dep in data.get('dependencies', []):
        if 'skip_reason' in dep or not isinstance(dep.get('vulns'), list):
            raise ValueError('Audit skipped a dependency or omitted vulnerability results')
        name = re.sub(r'[-_.]+', '-', dep['name']).lower()
        if name in scanned:
            raise ValueError(f'Duplicate audit result for {name}')
        if dep['vulns']:
            raise ValueError(f'Unresolved advisories in {name}')
        scanned[name] = dep['version']
    if scanned != expected:
        raise ValueError('Audit coverage differs from the installed inventory')
    return len(scanned)


def check_shared(runtime, tests):
    production = packages(runtime)
    tested = packages(tests)
    mismatches = [name for name, version in production.items() if tested.get(name) != version]
    if mismatches:
        raise ValueError('Runtime/test dependency mismatch: ' + ', '.join(sorted(mismatches)))
    return len(production)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    report = sub.add_parser('report')
    report.add_argument('inventory')
    report.add_argument('audit')
    shared = sub.add_parser('shared')
    shared.add_argument('runtime')
    shared.add_argument('tests')
    args = parser.parse_args()
    if args.command == 'report':
        count = check_report(args.inventory, args.audit)
        print(f'Audit gate OK: {count} installed packages, complete coverage, no known advisories')
    else:
        count = check_shared(args.runtime, args.tests)
        print(f'Dependency parity OK: {count} runtime packages match the test environment')
