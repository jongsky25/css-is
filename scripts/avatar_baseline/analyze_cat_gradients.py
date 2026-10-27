"""Independent source/hash audit for the shared cat gradient screen."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from scripts.avatar_baseline.analyze_paired_variance import required_sources,source
from scripts.avatar_baseline.analyze_source_isolation import points
from scripts.avatar_baseline.lifecycle_candidate import compare

REFS={'current':'cf363bfe547d5e23619eee28cdaf68bd4b6d7753','candidate':'cd94bf35d29b796ca0d6467756221e4b545a40be'}
ORDER=['current','candidate','candidate','current']
HARNESS=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py']
BUDGET=10485760


def expected_fixture(repo, ref, name):
    return source(repo, ref, name)


def decision(cohorts):
    if len(cohorts)!=4:raise ValueError('Incomplete four-cohort screen')
    comparisons=[]
    for name,left,right in [('forward',0,1),('reverse',3,2),('current-control',0,3),('candidate-control',1,2)]:
        result=compare(cohorts[left],cohorts[right]);result.update(name=name,left=left,right=right)
        result['absolute_control_pass']=all(abs(r['median_delta_bytes'])<=BUDGET for r in result['records'])
        targets=[r for r in result['records'] if r['checkpoint'] in ['navigation_10','navigation_20'] and r['metric']=='renderer_rss_sum_bytes']
        result['target_improvements_pass']=len(targets)==2 and all(r['median_delta_bytes']<=-5242880 for r in targets)
        comparisons.append(result)
    valid=all(c['status']!='inconclusive' for c in comparisons)
    controls=all(c['absolute_control_pass'] for c in comparisons[2:])
    effect=all(c['status']=='passed' and c['target_improvements_pass'] for c in comparisons[:2])
    return {'acceptance':False,'status':'inconclusive' if not valid else 'qualified_for_five_sample_validation' if controls and effect else 'screen_failed',
        'controls_stable':valid and controls,'effect_qualified_both_orders':valid and effect,'comparisons':comparisons}


def audit(root,repo,ref):
    result={'acceptance':False,'status':'inconclusive','errors':[],'source_hashes_verified':0,'files_verified':0,'cohorts':[]}
    try:
        plan=json.loads((root/'experiment.json').read_text())
        if (plan['protocol']!='shared-cat-gradients-screen-v1' or plan['acceptance'] is not False or plan['harness_commit']!=ref or plan['refs']!=REFS or plan['order']!=ORDER or plan['samples']!=2 or plan['seconds']!=30 or plan['browser']!='156.0.8078.47' or plan['budget_bytes']!=BUDGET or plan['minimum_improvement_bytes']!=5242880 or len(plan['cohorts'])!=4):raise ValueError('Protocol mismatch')
        visual=(root/'visual-assessment.json').read_bytes()
        assessment=json.loads(visual)
        from scripts.avatar_baseline.run_cat_gradients import validate_visual
        validate_visual(assessment)
        if hashlib.sha256(visual).hexdigest()!=plan['visual_assessment_sha256']:raise ValueError('Visual hash mismatch')
        changed=subprocess.check_output(['git','diff','--name-only',REFS['current'],REFS['candidate']],cwd=repo,text=True).splitlines()
        if changed!=['templates/_avatar_species/cat.html','templates/_avatars.html','templates/_avatars_art.html']:raise ValueError('Candidate scope changed')
        for name in HARNESS:
            if (root/'harness'/name).read_bytes()!=expected_fixture(repo,ref,name):raise ValueError('Harness mismatch')
        for index,(entry,arm) in enumerate(zip(plan['cohorts'],ORDER)):
            if entry['index']!=index or entry['arm']!=arm or entry['exit_code']!=0:raise ValueError('Failed or invalid cohort')
            folder=root/f'{index}-{arm}'
            if not {'False-warm.json','environment.json','runner.txt','junit.xml','profile-False-warm.png','backend-source.json'}<=set(entry['files_sha256']):raise ValueError('Missing required evidence')
            for name,digest in entry['files_sha256'].items():
                if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError('Evidence identity mismatch')
                result['files_verified']+=1
            env=json.loads((folder/'environment.json').read_text());expected=required_sources(repo,REFS[arm])
            backend=json.loads((folder/'backend-source.json').read_text())
            if set(backend)!={'app.py','storage.py','appearance_routes.py','sqlite_reader.py'}:raise ValueError('Backend manifest incomplete')
            for name,digest in backend.items():
                if hashlib.sha256(source(repo,REFS[arm],name)).hexdigest()!=digest:raise ValueError('Backend source mismatch')
                result['source_hashes_verified']+=1
            if env['source_commit']!=REFS[arm] or env['chromium']!='156.0.8078.47' or set(env['source_sha256'])!=expected:raise ValueError('Source environment mismatch')
            for name,digest in env['source_sha256'].items():
                data=expected_fixture(repo,ref,name) if name in HARNESS else source(repo,REFS[arm],name)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source hash mismatch')
                result['source_hashes_verified']+=1
            rows=json.loads((folder/'False-warm.json').read_text());observed=points(rows,2)
            result['cohorts'].append({'index':index,'arm':arm,'points':observed})
        result.update(decision([c['points'] for c in result['cohorts']]))
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as e:result['errors'].append(repr(e))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--harness-ref',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    repo=Path(__file__).resolve().parents[2];ref=subprocess.check_output(['git','rev-parse',a.harness_ref],cwd=repo,text=True).strip()
    result=audit(a.root,repo,ref);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result.get(k) for k in ['status','errors','source_hashes_verified','files_verified','controls_stable','effect_qualified_both_orders']}))
    sys.exit(bool(result['errors']))
