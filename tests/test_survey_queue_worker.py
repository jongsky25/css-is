"""Page and Background Sync queue consumers require the same server receipt."""
import json
import subprocess

import pytest


@pytest.fixture(scope='module')
def worker_results():
    run=subprocess.run(['node','tests/js/survey_queue_harness.cjs'],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    return json.loads(run.stdout)


@pytest.mark.parametrize('mode',['html','wrong','network','server','combined-malformed'])
def test_unconfirmed_worker_result_keeps_queue_and_does_not_clear_draft(worker_results,mode):
    result=worker_results[mode]
    assert len(result['rows'])==1 and result['rows'][0]['status']=='pending'
    assert result['calls']==1 and result['messages']==[]


def test_worker_confirmation_dequeues_and_notifies_matching_device_revision(worker_results):
    result=worker_results['confirmed']
    assert result['rows']==[]
    assert result['messages']==[{'type':'survey-confirmed','key':'device-key','revision':'revision'}]


@pytest.mark.parametrize('mode,reason',[('refused',None),('combined-partial','partial'),('combined-previous','previous')])
def test_refused_or_uncertain_combined_result_keeps_readable_payload_for_review(worker_results,mode,reason):
    row=worker_results[mode]['rows'][0]
    assert row['status']=='failed' and row['body']=='submission_id=attempt'
    assert row.get('reason')==reason and worker_results[mode]['messages']==[]
