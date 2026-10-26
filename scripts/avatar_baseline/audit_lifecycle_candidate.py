"""Independently recompute every targeted comparison and verify source provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

try:
    from .lifecycle_candidate import read_cohort, compare, ORDER
except ImportError:
    from lifecycle_candidate import read_cohort, compare, ORDER

PAIRS=(('original-to-candidate-forward',0,2),('original-to-candidate-reverse',5,3),
       ('current-to-candidate-forward',1,2),('current-to-candidate-reverse',4,3),
       ('original-to-current-forward',0,1),('original-to-current-reverse',5,4),
       ('original-repeat',0,5),('current-repeat',1,4),('candidate-repeat',2,3))


def audit(directory,candidate_ref):
    root=Path(directory)
    stored=json.loads((root/'assessment.json').read_text())
    refs={'original':'1c964dc','current':'f700187','candidate':candidate_ref}
    full_refs={arm:subprocess.check_output(['git','rev-parse',ref],text=True).strip() for arm,ref in refs.items()}
    cohorts=[];environments=[];errors=[];verified=0;comparisons=[]
    for i,arm in enumerate(ORDER):
        folder=root/f'{i}-{arm}'
        try:
            raw=folder/'application/False-warm.json'
            env=json.loads((folder/'application/environment.json').read_text())
            record=stored['cohorts'][i]
            if record['index']!=i or record['arm']!=arm or record['exit_code']!=0:
                raise ValueError('Cohort identity/exit mismatch')
            if record['source_commit']!=full_refs[arm] or env['source_commit']!=full_refs[arm]:
                raise ValueError('Source ref mismatch')
            if hashlib.sha256(raw.read_bytes()).hexdigest()!=record['raw_sha256']:
                raise ValueError('Raw file checksum mismatch')
            required={'templates/_avatars.html','templates/_avatars_art.html','templates/me.html','templates/_growth.html',
                'static/js/avatars.js','static/js/avatar-audio.js','static/js/search.js',
                'templates/office_connect.html','templates/dash_layout.html',
                'tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py'}
            listed=subprocess.check_output(['git','ls-tree','-r','--name-only',refs[arm],'templates/_avatar_species','templates/_avatars_shared.html'],text=True).splitlines()
            required.update(listed)
            if set(env['source_sha256'])!=required:raise ValueError('Source inventory mismatch')
            for name,digest in env['source_sha256'].items():
                source_ref=candidate_ref if name.startswith('tests/') else refs[arm]
                content=subprocess.check_output(['git','show',source_ref+':'+name])
                if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Source hash mismatch: '+name)
                verified+=1
            rows=json.loads(raw.read_text())
            if any(r['cpu_rate']!=1 for r in rows):raise ValueError('CPU throttle mismatch')
            points=read_cohort(folder)
            if points!=record['points']:raise ValueError('Stored cohort statistics disagree with raw samples')
            cohorts.append(points);environments.append(env)
        except (OSError,KeyError,ValueError,TypeError,subprocess.CalledProcessError) as exc:
            errors.append({'cohort':i,'arm':arm,'error':repr(exc)});cohorts.append(None)
    if len(environments)==6:
        for key in ('platform','python','chromium','playwright','fixture_date_local','browser_date','random_seed','process_tree_cpu_affinity','requested_renderer_pin_cpu','proxy_compression'):
            if len({json.dumps(e[key],sort_keys=True) for e in environments})!=1:errors.append({'environment_mismatch':key})
    for name,a,b in PAIRS:
        if cohorts[a] is None or cohorts[b] is None:continue
        result=compare(cohorts[a],cohorts[b])
        old=next((c for c in stored['comparisons'] if c['name']==name),None)
        if old is None or old['before_index']!=a or old['after_index']!=b or any(old[k]!=v for k,v in result.items()):
            errors.append({'comparison':name,'error':'Stored comparison disagrees with raw recomputation'})
        for row in result['records']:
            row['before']={**row['before'],'worst':max(row['before']['samples'])}
            row['after']={**row['after'],'worst':max(row['after']['samples'])}
        comparisons.append({'name':name,'before_index':a,'after_index':b,**result})
    complete=len(comparisons)==9 and sum(len(c['records']) for c in comparisons)==234
    # Other pairs quantify unchanged-source drift and candidate effects; they
    # must remain visible, not be folded into the candidate's original-baseline gate.
    target=[c for c in comparisons if c['name'].startswith('original-to-candidate-')]
    status='inconclusive' if errors or not complete or any(c['status']=='inconclusive' for c in target) else ('passed' if all(c['status']=='passed' for c in target) else 'application_regression')
    return {'candidate_targeted_status':status,'acceptance':False,'release_ready':False,
        'coverage':'Warm desktop only; original/current/candidate in both orders. Full matrix and callback/frame gates remain required.',
        'candidate_source':full_refs['candidate'],'source_hashes_verified':verified,
        'all_comparisons_complete':complete,'errors':errors,'comparisons':comparisons}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--candidate-ref',required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    result=audit(args.directory,args.candidate_ref)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='comparisons'},indent=2))
    raise SystemExit(0 if result['candidate_targeted_status']=='passed' else 1)
