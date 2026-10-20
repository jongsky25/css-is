"""Fault injection for dependency audit coverage and reproducible lock gates."""
import hashlib
import json

import pytest

from scripts.check_dependency_audit import check_report, check_shared
from scripts.lock_dependencies import LOCKS, check_locks


@pytest.fixture
def evidence(tmp_path):
    inventory = tmp_path / 'installed.txt'
    inventory.write_text('Example_Package==1.2\npip==26.2.1\n')
    report = tmp_path / 'audit.json'
    report.write_text(json.dumps({'dependencies': [
        {'name': 'example-package', 'version': '1.2', 'vulns': []},
        {'name': 'pip', 'version': '26.2.1', 'vulns': []},
    ]}))
    return inventory, report


def test_complete_clean_audit(evidence):
    assert check_report(*evidence) == 2


@pytest.mark.parametrize('fault', ['missing', 'skip', 'vulnerable', 'wrong-version', 'duplicate', 'missing-vulns'])
def test_audit_rejects_incomplete_or_vulnerable_evidence(evidence, fault):
    inventory, report = evidence
    data = json.loads(report.read_text())
    dep = data['dependencies'][0]
    if fault == 'missing':
        data['dependencies'].pop()
    elif fault == 'skip':
        dep['skip_reason'] = 'lookup failed'
    elif fault == 'vulnerable':
        dep['vulns'] = [{'id': 'SYNTHETIC-ADVISORY'}]
    elif fault == 'wrong-version':
        dep['version'] = '1.1'
    elif fault == 'duplicate':
        data['dependencies'].append(dep.copy())
    else:
        dep.pop('vulns')
    report.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        check_report(inventory, report)


@pytest.mark.parametrize('content', ['', 'example>=1.0\n', 'example==1\nexample==2\n'])
def test_inventory_requires_nonempty_unique_exact_versions(tmp_path, content):
    inventory = tmp_path / 'inventory.txt'
    inventory.write_text(content)
    with pytest.raises(ValueError):
        check_shared(inventory, inventory)


def test_test_only_packages_are_allowed_but_shared_versions_must_match(evidence, tmp_path):
    runtime, _ = evidence
    tested = tmp_path / 'test.txt'
    tested.write_text(runtime.read_text() + 'pytest==9.1.1\n')
    assert check_shared(runtime, tested) == 2
    tested.write_text(tested.read_text().replace('Example_Package==1.2', 'Example_Package==1.1'))
    with pytest.raises(ValueError, match='mismatch'):
        check_shared(runtime, tested)


def test_changed_input_or_runtime_constraint_requires_regeneration(tmp_path):
    for sources in LOCKS.values():
        for source in sources:
            (tmp_path / source).write_text('example==1\n')
    for lock, sources in LOCKS.items():
        stamps = ''.join(f'# Input-SHA256: {source}={hashlib.sha256((tmp_path / source).read_bytes()).hexdigest()}\n'
                         for source in sources)
        (tmp_path / lock).write_text(stamps + 'example==1\n')
    check_locks(tmp_path)
    # A changed production constraint must invalidate the test lock too.
    runtime = tmp_path / 'requirements.txt'
    runtime.write_text(runtime.read_text() + '# changed artifact hashes\n')
    with pytest.raises(ValueError, match='requirements-test.txt is stale'):
        check_locks(tmp_path)


def test_changed_direct_input_requires_regeneration(tmp_path):
    for sources in LOCKS.values():
        for source in sources:
            (tmp_path / source).write_text('example==1\n')
    for lock, sources in LOCKS.items():
        (tmp_path / lock).write_text(''.join(
            f'# Input-SHA256: {source}={hashlib.sha256((tmp_path / source).read_bytes()).hexdigest()}\n'
            for source in sources))
    (tmp_path / 'requirements.in').write_text('example==2\n')
    with pytest.raises(ValueError, match='stale'):
        check_locks(tmp_path)
