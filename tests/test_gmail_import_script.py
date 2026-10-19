"""Execute the actual Apps Script importer against failure-injecting API doubles."""
import json
import pathlib
import shutil
import subprocess
import pytest
from test_documents_email import setup
import documents_email

ROOT = pathlib.Path(__file__).resolve().parents[1]


def harness(*args):
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required for Apps Script contract tests')
    result=subprocess.run([node,'tests/js/gmail_import_harness.js',*args],cwd=ROOT,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    return result.stdout


def test_importer_failure_contracts():
    assert '37 Gmail importer contracts passed' in harness()


def test_javascript_signature_and_payload_register_in_python(setup):
    conn,path,uid,client=setup
    envelope=json.loads(harness('--envelope'))
    result=client.post(documents_email.PATH,content=envelope['body'].encode(),headers=envelope['headers'])
    assert result.status_code==201,result.text
    replay=client.post(documents_email.PATH,content=envelope['body'].encode(),headers=envelope['headers'])
    assert replay.status_code==200 and replay.json()['duplicate']
    assert conn.execute('SELECT count(*) FROM document').fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM document_file_version').fetchone()[0]==2
