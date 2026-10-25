"""Fail-closed evidence accounting for avatar verification (no browser imports)."""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

FRAME_LIMIT_MS = 33.3  # Explicit user-approved 0.3ms exception, no callback waiver.


def frame_pass(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value <= FRAME_LIMIT_MS + 1e-8


def read_json(path):
    return json.loads(Path(path).read_text())


def validate_samples(rows, expected):
    if len(rows) != expected or len({(r['version'], r['run']) for r in rows}) != expected:
        raise ValueError(f'Expected {expected} distinct samples, received {len(rows)}')
    if any(r['seconds'] < 30 or not r['actions'] or not r['scenario']['frame_count'] for r in rows):
        raise ValueError('Incomplete input or frame recording')


def pytest_evidence(path, expected):
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    if len(cases) != expected or any(c.find('skipped') is not None or c.find('error') is not None for c in cases):
        raise ValueError('Missing, skipped, or errored tests')
    return not any(c.find('failure') is not None for c in cases)


class Results:
    def __init__(self):
        self.gates = {}
        self.errors = {}
        self.environment = {}

    def check(self, name, operation, *, environment=False):
        """A missing file must not prevent the next independent check."""
        try:
            target = self.environment if environment else self.gates
            target[name] = bool(operation())
        except Exception as error:
            self.errors[name] = f'{type(error).__name__}: {error}'

    @property
    def status(self):
        if self.errors or not self.gates or not all(self.environment.values()):
            return 'inconclusive'
        return 'passed' if all(self.gates.values()) else 'application_regression'

    def as_dict(self):
        return {'status': self.status, 'gates': self.gates, 'environment_checks': self.environment,
                'harness_errors': self.errors}
