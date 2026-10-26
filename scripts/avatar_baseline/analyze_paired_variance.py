"""Independent identity audit and predeclared paired/negative-control analysis."""
import argparse
import copy
import math
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

if __package__:
    from .analyze_source_isolation import points
    from .memory_audit import BUDGET, SCENARIOS, MOUNTS
else:
    from analyze_source_isolation import points
    from memory_audit import BUDGET, SCENARIOS, MOUNTS

REFS={'original':'1c964dcba2fa19de1eab077b00e0e5748d742554',
      'current':'f700187553bd555dd3a9b638d5aa8e5fb59f3142'}
BLOCKS=[['original','current','current','original'],
        ['current','original','original','current'],
        ['original','current','current','original'],
        ['current','original','original','current'],
        ['original','current','current','original']]
CHECKPOINTS=[*SCENARIOS,*('navigation_'+str(m) for m in MOUNTS)]
METRICS=['renderer_rss_sum_bytes','js_heap_bytes']
HARNESS=['tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py']


def slots():
    return [{'index':b*4+p,'block':b,'position':p,'arm':arm}
            for b,arms in enumerate(BLOCKS) for p,arm in enumerate(arms)]


def validate_plan(plan,harness_commit):
    if (plan['protocol']!='paired-variance-v1' or plan['acceptance'] is not False or
        plan['harness_commit']!=harness_commit or plan['refs']!=REFS or plan['fixture_adapter']!='sample-ordinal-v1' or
        plan['blocks']!=BLOCKS or plan['samples_per_slot']!=1 or plan['seconds']!=30 or
        plan['browser']!='156.0.8078.47' or plan['budget_bytes']!=BUDGET):
        raise ValueError('Protocol identity mismatch')
    if len(plan['cohorts'])!=20:raise ValueError('Incomplete schedule')
    for expected,actual in zip(slots(),plan['cohorts']):
        if any(actual.get(k)!=v for k,v in expected.items()) or actual.get('exit_code')!=0:
            raise ValueError('Invalid slot identity or failed workload: '+str(expected['index']))


def analyze(cohorts):
    if len(cohorts)!=20:raise ValueError('Require all 20 slots')
    for expected,actual in zip(slots(),cohorts):
        if any(actual.get(k)!=v for k,v in expected.items()):raise ValueError('Slot order mismatch')
        if set(actual['points'])!=set(CHECKPOINTS):raise ValueError('Missing checkpoints')
    records=[]
    for checkpoint in CHECKPOINTS:
        counts=[c['points'][checkpoint]['renderer_counts'] for c in cohorts]
        if any(len(c)!=1 or type(c[0]) is not int or c[0]<=0 for c in counts) or len({c[0] for c in counts})!=1:
            raise ValueError('Unmatched renderer counts: '+checkpoint)
        for metric in METRICS:
            values=[c['points'][checkpoint][metric]['samples'] for c in cohorts]
            if any(len(v)!=1 for v in values):raise ValueError('Not one sample per slot')
            values=[v[0] for v in values]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):
                raise ValueError('Invalid memory observation')
            controls={arm:[] for arm in REFS};pairs={'forward':[],'reverse':[]}
            for block,arms in enumerate(BLOCKS):
                for arm in REFS:
                    early,late=[block*4+i for i,a in enumerate(arms) if a==arm]
                    controls[arm].append({'block':block,'early_index':early,'late_index':late,
                        'delta_bytes':values[late]-values[early]})
                for left,right in [(block*4,block*4+1),(block*4+2,block*4+3)]:
                    forward=cohorts[left]['arm']=='original'
                    original,current=(left,right) if forward else (right,left)
                    pairs['forward' if forward else 'reverse'].append({'block':block,
                        'original_index':original,'current_index':current,
                        'original_bytes':values[original],'current_bytes':values[current],
                        'delta_bytes':values[current]-values[original]})
            negative_stable=all(abs(p['delta_bytes'])<=BUDGET for ps in controls.values() for p in ps)
            orders={}
            for order,ps in pairs.items():
                delta=[p['delta_bytes'] for p in ps]
                aggregate=statistics.median(p['current_bytes'] for p in ps)-statistics.median(p['original_bytes'] for p in ps)
                orders[order]={'pairs':ps,'paired_median_delta_bytes':statistics.median(delta),
                    'difference_of_medians_bytes':aggregate,'positive_pairs':sum(d>0 for d in delta),
                    'negative_pairs':sum(d<0 for d in delta),'within_10_mib':aggregate<=BUDGET}
            increase=all(o['paired_median_delta_bytes']>BUDGET and o['difference_of_medians_bytes']>BUDGET and o['positive_pairs']>=4 for o in orders.values())
            decrease=all(o['paired_median_delta_bytes']<-BUDGET and o['difference_of_medians_bytes']<-BUDGET and o['negative_pairs']>=4 for o in orders.values())
            classification=('unstable_negative_controls' if not negative_stable else
                'repeatable_increase' if increase else 'repeatable_decrease' if decrease else 'no_repeatable_effect')
            records.append({'checkpoint':checkpoint,'metric':metric,'renderer_count':counts[0][0],
                'negative_controls':controls,'negative_controls_within_10_mib':negative_stable,
                'negative_control_max_abs_delta_bytes':max(abs(p['delta_bytes']) for ps in controls.values() for p in ps),
                'orders':orders,'classification':classification})
    return {'acceptance':False,'records':records,
        'unstable_control_metrics':sum(r['classification']=='unstable_negative_controls' for r in records),
        'repeatable_increases':[{'checkpoint':r['checkpoint'],'metric':r['metric']} for r in records if r['classification']=='repeatable_increase'],
        'repeatable_decreases':[{'checkpoint':r['checkpoint'],'metric':r['metric']} for r in records if r['classification']=='repeatable_decrease'],
        'status':'measurement_variation' if any(not r['negative_controls_within_10_mib'] for r in records) else 'controls_within_budget',
        'limits':'Diagnostic fresh-browser paired ordering only. Not an acceptance test, causal proof, or replacement for historical failures. Negative-control stability is required separately at every checkpoint/metric before calling its source effect repeatable.'}


def source(repo,ref,name):
    return subprocess.check_output(['git','show',ref+':'+name],cwd=repo)


def required_sources(repo,ref):
    base={'templates/_avatars.html','templates/_avatars_art.html','templates/me.html',
          'templates/_growth.html','static/js/avatars.js','static/js/avatar-audio.js',
          'static/js/search.js','templates/office_connect.html','templates/dash_layout.html',*HARNESS}
    tree=subprocess.check_output(['git','ls-tree','-r','--name-only',ref,'templates'],cwd=repo,text=True).splitlines()
    base.update(p for p in tree if p.startswith('templates/_avatar_species/') and p.endswith('.html'))
    if 'templates/_avatars_shared.html' in tree:base.add('templates/_avatars_shared.html')
    return base


def expected_fixture(repo,ref,name):
    data=source(repo,ref,name)
    if name=='tests/test_avatar_baseline_browser.py':
        before=b'for run in range(runs):'
        after=b"for run in range(int(os.getenv('CSS_AVATAR_RUN_START', '0')), int(os.getenv('CSS_AVATAR_RUN_START', '0')) + runs):"
        if data.count(before)!=1:raise ValueError('Workload adapter identity mismatch')
        data=data.replace(before,after,1)
    return data


def slot_points(rows,block):
    if len(rows)!=1 or type(rows[0].get('run')) is not int or rows[0]['run']!=block:
        raise ValueError('Incorrect workload sample ordinal')
    normalized=copy.deepcopy(rows);normalized[0]['run']=0
    return points(normalized,1)


def audit(root,repo,harness_commit):
    result={'acceptance':False,'status':'inconclusive','source_hashes_verified':0,'cohorts':[],'errors':[]}
    try:
        plan=json.loads((root/'experiment.json').read_text());validate_plan(plan,harness_commit)
        for name in HARNESS:
            if (root/'harness'/name).read_bytes()!=expected_fixture(repo,harness_commit,name):
                raise ValueError('Frozen fixture mismatch: '+name)
        for slot,entry in zip(slots(),plan['cohorts']):
            folder=root/f"{slot['index']:02d}-{slot['arm']}";ref=REFS[slot['arm']]
            env=json.loads((folder/'environment.json').read_text())
            if env['source_commit']!=ref or env['chromium']!='156.0.8078.47' or set(env['source_sha256'])!=required_sources(repo,ref):
                raise ValueError('Environment identity mismatch: '+str(slot['index']))
            for name,digest in env['source_sha256'].items():
                data=expected_fixture(repo,harness_commit,name) if name in HARNESS else source(repo,ref,name)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source hash mismatch: '+name)
                result['source_hashes_verified']+=1
            raw=folder/'False-warm.json';digest=hashlib.sha256(raw.read_bytes()).hexdigest()
            if entry.get('raw_sha256')!=digest:raise ValueError('Raw hash mismatch: '+str(slot['index']))
            result['cohorts'].append({**slot,'raw_sha256':digest,'points':slot_points(json.loads(raw.read_text()),slot['block'])})
        result.update(analyze(result['cohorts']))
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        result['errors'].append(repr(error));result['status']='inconclusive'
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    parser.add_argument('--harness-ref',required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args();repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse',args.harness_ref],cwd=repo,text=True).strip()
    result=audit(args.root,repo,ref)
    (args.out or args.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','source_hashes_verified','errors']}|
        {k:result.get(k) for k in ['unstable_control_metrics','repeatable_increases','repeatable_decreases']},indent=2))
    return 1 if result['errors'] else 0


if __name__=='__main__':sys.exit(main())
