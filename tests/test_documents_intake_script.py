"""Execute the real Apps Script intake operations against an in-memory Drive."""
import pathlib
import shutil
import subprocess
import pytest


def test_drive_intake_relay_recovery():
    if not shutil.which('node'): pytest.skip('Node is required for Apps Script simulation')
    root=pathlib.Path(__file__).resolve().parents[1]
    result=subprocess.run(['node','tests/js/documents_intake_harness.js'],cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_content_checked_intake_ocr():
    node=shutil.which('node')
    if not node:pytest.skip('Node is required for Apps Script contract tests')
    root=pathlib.Path(__file__).resolve().parents[1]
    result=subprocess.run([node,'tests/js/intake_ocr_harness.js'],cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'Intake OCR:' in result.stdout
