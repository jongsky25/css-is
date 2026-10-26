"""Paired attribution cannot hide unstable controls, missing slots or source drift."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import pytest
from scripts.avatar_baseline.analyze_paired_variance import (
    analyze,audit,validate_plan,slots,points,REFS,BLOCKS,BUDGET,required_sources,HARNESS,expected_fixture,slot_points)
from tests.test_avatar_targeted_memory import cohort

TARGET='navigation_20'
METRIC='renderer_rss_sum_bytes'


def data(tmp_path,effect=20*1024*1024):
    _,_,rows=cohort(tmp_path);row=rows[0]
    result=[]
    for slot in slots():
        p=points([copy.deepcopy(row)],1)
        value=100*1024*1024+(effect if slot['arm']=='current' else 0)
        p[TARGET][METRIC]={'samples':[value],'median':value}
        result.append({**slot,'points':p})
    return result,row


def target(result):
    return next(r for r in result['records'] if r['checkpoint']==TARGET and r['metric']==METRIC)


def bump(cohorts,index,delta):
    p=cohorts[index]['points'][TARGET][METRIC]
    p['samples'][0]+=delta;p['median']+=delta


@pytest.mark.parametrize('effect,classification',[(20,'repeatable_increase'),(-20,'repeatable_decrease'),(10,'no_repeatable_effect'),(0,'no_repeatable_effect')])
def test_known_paired_effect_and_exact_budget(tmp_path,effect,classification):
    rows,_=data(tmp_path,effect*1024*1024);result=analyze(rows);r=target(result)
    assert len(result['records'])==26 and result['acceptance'] is False
    assert r['classification']==classification
    for order in r['orders'].values():
        assert order['paired_median_delta_bytes']==effect*1024*1024
        assert order['difference_of_medians_bytes']==effect*1024*1024
        assert len(order['pairs'])==5
    assert r['negative_controls_within_10_mib']


def test_one_unstable_negative_pair_cannot_be_hidden_by_its_median(tmp_path):
    rows,_=data(tmp_path);bump(rows,2,BUDGET+1)
    r=target(analyze(rows))
    assert r['classification']=='unstable_negative_controls'
    assert r['negative_control_max_abs_delta_bytes']==BUDGET+1


def test_both_orders_and_four_of_five_signs_are_required(tmp_path):
    rows,_=data(tmp_path)
    for slot in rows:
        if slot['block'] in [0,1] and slot['arm']=='current':bump(rows,slot['index'],-20*1024*1024)
    r=target(analyze(rows))
    assert r['negative_controls_within_10_mib']
    assert all(o['paired_median_delta_bytes']>BUDGET for o in r['orders'].values())
    assert r['classification']=='no_repeatable_effect'


@pytest.mark.parametrize('fault',['missing','duplicate','counts','nan','missing_checkpoint'])
def test_invalid_slots_are_inconclusive(tmp_path,fault):
    rows,_=data(tmp_path)
    if fault=='missing':rows.pop()
    elif fault=='duplicate':rows[-1]=copy.deepcopy(rows[0])
    elif fault=='counts':rows[7]['points'][TARGET]['renderer_counts']=[9]
    elif fault=='nan':rows[7]['points'][TARGET][METRIC]['samples']=[float('nan')]
    else:del rows[7]['points'][TARGET]
    with pytest.raises(ValueError):analyze(rows)


def plan(ref):
    return {'protocol':'paired-variance-v1','acceptance':False,'harness_commit':ref,'fixture_adapter':'sample-ordinal-v1',
            'refs':REFS,'blocks':BLOCKS,'samples_per_slot':1,'seconds':30,
            'browser':'156.0.8078.47','budget_bytes':BUDGET,
            'cohorts':[{**slot,'exit_code':0} for slot in slots()]}


@pytest.mark.parametrize('fault',['none','order','exit','budget','missing','ref','acceptance'])
def test_frozen_plan_identity(fault):
    p=copy.deepcopy(plan('commit'))
    if fault=='order':p['cohorts'][0]['arm']='current'
    elif fault=='exit':p['cohorts'][0]['exit_code']=1
    elif fault=='budget':p['budget_bytes']+=1
    elif fault=='missing':p['cohorts'].pop()
    elif fault=='ref':p['refs']['original']='current'
    elif fault=='acceptance':p['acceptance']=True
    if fault=='none':validate_plan(p,'commit')
    else:
        with pytest.raises(ValueError):validate_plan(p,'commit')


def test_full_identity_audit_and_tampering(tmp_path):
    repo=Path(__file__).resolve().parents[1]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    _,row=data(tmp_path);root=tmp_path/'evidence';root.mkdir()
    p=plan(ref)
    for name in HARNESS:
        dest=root/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(expected_fixture(repo,ref,name))
    cache={}
    for arm,source_ref in REFS.items():
        cache[arm]={name:hashlib.sha256(expected_fixture(repo,ref,name) if name in HARNESS else subprocess.check_output(['git','show',source_ref+':'+name],cwd=repo)).hexdigest() for name in required_sources(repo,source_ref)}
    for slot,entry in zip(slots(),p['cohorts']):
        folder=root/f"{slot['index']:02d}-{slot['arm']}";folder.mkdir()
        raw=folder/'False-warm.json';sample=copy.deepcopy(row);sample['run']=slot['block'];raw.write_text(json.dumps([sample]))
        entry['raw_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
        (folder/'environment.json').write_text(json.dumps({'source_commit':REFS[slot['arm']],
            'chromium':'156.0.8078.47','source_sha256':cache[slot['arm']]}))
    (root/'experiment.json').write_text(json.dumps(p))
    result=audit(root,repo,ref)
    assert not result['errors'] and len(result['cohorts'])==20
    assert result['source_hashes_verified']==390
    assert result['status']=='controls_within_budget' and not result['acceptance']
    env=root/'00-original/environment.json';d=json.loads(env.read_text());d['source_sha256'].pop('static/js/avatars.js');env.write_text(json.dumps(d))
    assert audit(root,repo,ref)['status']=='inconclusive'


def test_sample_ordinal_is_checked_without_changing_raw_rows(tmp_path):
    _,row=data(tmp_path);row['run']=4
    assert slot_points([row],4) and row['run']==4
    with pytest.raises(ValueError):slot_points([row],0)


def test_workload_adapter_changes_only_the_loop():
    from scripts.avatar_baseline.paired_variance import adapt_fixture
    repo=Path(__file__).resolve().parents[1]
    name='tests/test_avatar_baseline_browser.py'
    before=(repo/name).read_bytes();after=adapt_fixture(name,before)
    assert after==expected_fixture(repo,'HEAD',name)
    assert sum(a!=b for a,b in zip(before.splitlines(),after.splitlines()))==1
    assert b'if run==0:page.screenshot' in after
