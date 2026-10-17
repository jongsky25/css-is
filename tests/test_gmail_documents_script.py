"""Run the production discovery script with read-only Gmail API doubles."""
import pathlib
import shutil
import subprocess
import pytest


def test_gmail_discovery_contracts():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for Apps Script contract tests')
    root = pathlib.Path(__file__).resolve().parents[1]
    result = subprocess.run([node,'tests/js/gmail_documents_harness.js'],cwd=root,
                            capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '10 Gmail discovery contracts passed' in result.stdout
