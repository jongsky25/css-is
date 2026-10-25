"""Assess 2B evidence without substituting failed samples or relaxing budgets."""
import json
import statistics
from pathlib import Path

out=Path('docs/avatars/increment2b')
read=lambda p:json.loads((out/p).read_text())
primary=read('comparison.json');current=read('application/False-cold.json')
control=read('reproduced-overlay-control/application/False-cold.json')
fs=read('reproduced-overlay-control/filesystem.json')
proof=read('control-protocol-proof.json')
assert primary['complete'] and len(current)==len(control)==5
assert fs['current_filesystem']==fs['control_filesystem']=='overlayfs'
assert all(proof['protocol_ast_identical'].values()) and all(proof['unchanged_inputs'].values()) and proof['probe_identical']
for row in current+control:
    assert not row['mobile'] and row['cache']=='cold' and row['cpu_rate']==1 and row['seconds']>=30 and row['chromium']=='154.0.8037.57'
env=read('application/environment.json');before_env=read('reproduced-overlay-control/application/environment.json')
for key in ['chromium','playwright','python','platform','fixture_date_local','random_seed']:
    assert env[key]==before_env[key],key
assert env['source_commit'].startswith('6ddce82') and before_env['source_commit'].startswith('1c964dc')
def stats(rows,key):
    values=[r['scenarios']['home_idle'][key] for r in rows]
    return {'values':values,'median':statistics.median(values),'worst':max(values)}
old,new=stats(control,'lcp_ms'),stats(current,'lcp_ms')
secondary={}
for group in primary['groups']:
    for name,metrics in group['scenarios'].items():
        if name in ['home_idle','home_interaction']:continue
        for metric,budget in [('lcp_ms',100),('interaction_duration_per_run_median_ms',20),('renderer_rss_sum_bytes',10*1048576),('js_heap_bytes',10*1048576)]:
            if metric in metrics:
                secondary[f"{group['mobile']}-{group['cache']}-{name}-{metric}"]={'delta':metrics[metric]['median_delta'],'budget':budget,'passed':metrics[metric]['median_delta']<=budget}
result={'status':'blocked','primary_samples':20,'historical_comparison':'comparison.json','historical_gates':primary['gates'],
    'same_filesystem_control':{'reference_commit':before_env['source_commit'],'current_commit':env['source_commit'],'runs_each':5,'control':old,'current':new,'median_delta_ms':new['median']-old['median'],'budget_ms':100,'passed':new['median']-old['median']<=100,'same_filesystem':True,'protocol_proof':'control-protocol-proof.json'},
    'secondary_scenario_gates':secondary,'secondary_gates_passed':all(s['passed'] for s in secondary.values()),
    'excluded_from_acceptance':['Initial five tmpfs control samples: filesystem differs from current overlayfs source.','Three instrumented full-scenario navigation diagnostic runs: attribution only, no acceptance resampling.','Twenty 2s counterbalanced art-only loads, including an experimental compositing CSS variant: attribution only, no product change.'],
    'remaining_gate':'Cold-desktop Home LCP regression exceeds100ms against both historical and same-filesystem original-source reference; cause not isolated.','next_step':'Investigate response/static-resource delivery and full-scenario sequencing; keep 2B blocked and do not advance to3A.'}
if all(primary['gates'].values()) and result['same_filesystem_control']['passed'] and result['secondary_gates_passed']:
    result['status']='complete'
(out/'assessment.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'status':result['status'],'matched_lcp_delta_ms':result['same_filesystem_control']['median_delta_ms'],'secondary_gates_passed':result['secondary_gates_passed']},indent=2))
