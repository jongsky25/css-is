"""Independent fixed-protocol source audit and allocation-screen decision."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from scripts.avatar_baseline.analyze_paired_variance import required_sources,source
from scripts.avatar_baseline.analyze_source_isolation import points
from scripts.avatar_baseline.lifecycle_candidate import compare

REFS={'current':'f700187553bd555dd3a9b638d5aa8e5fb59f3142','candidate':'69605628393d044f9a0426ea0be3abdf99527bc3'}
ORDER=['current','candidate','candidate','current']
HARNESS=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py']
BUDGET=10485760


def expected_fixture(repo,ref,name):
    data=source(repo,ref,name)
    if name==HARNESS[0]:
        before=b"    if Path('templates/_avatars_shared.html').exists():"
        if data.count(before)!=1:raise ValueError('Manifest adapter mismatch')
        data=data.replace(before,b"    if Path('static/css/avatars.css').exists():\n        sources.append('static/css/avatars.css')\n"+before,1)
    return data


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
        if (plan['protocol']!='shared-stylesheet-screen-v1' or plan['acceptance'] is not False or plan['harness_commit']!=ref or plan['refs']!=REFS or plan['order']!=ORDER or plan['samples']!=2 or plan['seconds']!=30 or plan['browser']!='156.0.8078.47' or plan['budget_bytes']!=BUDGET or plan['minimum_improvement_bytes']!=5242880 or len(plan['cohorts'])!=4):raise ValueError('Protocol mismatch')
        visual=(root/'visual-assessment.json').read_bytes()
        assessment=json.loads(visual)
        if (hashlib.sha256(visual).hexdigest()!=plan['visual_assessment_sha256'] or assessment.get('same_source_control',False) or assessment.get('all_pixels_identical') is not True or assessment.get('cells')!=2880 or len(assessment.get('sheets',[]))!=30 or not all(r.get('pixel_identical') is True and r.get('cssom_identical') is True for r in assessment['sheets'])):raise ValueError('Visual prerequisite missing or invalid')
        old=source(repo,REFS['current'],'templates/_avatars.html');new=source(repo,REFS['candidate'],'templates/_avatars.html');css=source(repo,REFS['candidate'],'static/css/avatars.css')
        link=b'<link rel="stylesheet" href="/static/css/avatars.css?v=1">'
        changed=subprocess.check_output(['git','diff','--name-only',REFS['current'],REFS['candidate'],'--','static','templates'],cwd=repo,text=True).splitlines()
        if changed!=['static/css/avatars.css','templates/_avatars.html'] or new.count(link)!=1 or new.replace(link,b'<style>'+css+b'</style>')!=old:raise ValueError('Candidate scope differs from exact CSS extraction')
        for name in HARNESS:
            if (root/'harness'/name).read_bytes()!=expected_fixture(repo,ref,name):raise ValueError('Harness mismatch')
        for index,(entry,arm) in enumerate(zip(plan['cohorts'],ORDER)):
            if entry['index']!=index or entry['arm']!=arm or entry['exit_code']!=0:raise ValueError('Failed or invalid cohort')
            folder=root/f'{index}-{arm}'
            if not {'False-warm.json','environment.json','runner.txt','junit.xml','profile-False-warm.png'}<=set(entry['files_sha256']):raise ValueError('Missing required evidence')
            for name,digest in entry['files_sha256'].items():
                if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError('Evidence identity mismatch')
                result['files_verified']+=1
            env=json.loads((folder/'environment.json').read_text());expected=required_sources(repo,REFS[arm])
            if arm=='candidate':expected.add('static/css/avatars.css')
            if env['source_commit']!=REFS[arm] or env['chromium']!='156.0.8078.47' or set(env['source_sha256'])!=expected:raise ValueError('Source environment mismatch')
            for name,digest in env['source_sha256'].items():
                data=expected_fixture(repo,ref,name) if name in HARNESS else source(repo,REFS[arm],name)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source hash mismatch')
                result['source_hashes_verified']+=1
            rows=json.loads((folder/'False-warm.json').read_text());observed=points(rows,2)
            if arm=='candidate':
                for row in rows:
                    if not any('/static/css/avatars.css?v=1' in r['name'] for r in row['scenarios']['home_idle']['resources']):raise ValueError('Candidate stylesheet not observed in workload')
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
