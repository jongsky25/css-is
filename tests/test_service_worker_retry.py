"""Run the real service worker against ambiguous response simulations."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_worker_does_not_replay_committed_writes():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute service worker regressions')
    result = subprocess.run([node, 'tests/js/service_worker_retry.js'],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
