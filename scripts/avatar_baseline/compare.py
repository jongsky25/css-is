"""Compare retained full-duration groups; never conceal existing baseline failures."""
import argparse
import os
import gzip
import json
from pathlib import Path
import subprocess
import statistics
from verification_result import frame_pass
from memory_audit import audit_memory

p=argparse.ArgumentParser();p.add_argument('--before',default='docs/avatars/application');p.add_argument('--after',default='docs/avatars/increment1/application');a=p.parse_args()
left=Path(a.before);right=Path(a.after)
base=json.loads((left/'summary.json').read_text());after=json.loads((right/'summary.json').read_text())
result={'complete':after['full_duration_complete'],'groups':[],'limits':base['limits'], 'gates':{},
        'frame_budget_ms':33.3,'original_frame_budget_ms':33}
lookup={(g['mobile'],g['cache']):g for g in base['groups']}
for g in after['groups']:
 b=lookup[g['mobile'],g['cache']]; scenarios={}
 for name in ['home_idle','home_interaction','picker_growth','seasonal_preview','wellness_care']:
  old=b['scenarios'][name];new=g['scenarios'][name];metrics={}
  for metric in ['lcp_ms','frame_p95_ms','interaction_duration_per_run_median_ms','js_heap_bytes','renderer_rss_sum_bytes']:
   if old.get(metric) and new.get(metric):metrics[metric]={'before':old[metric],'after':new[metric],'median_delta':new[metric]['median']-old[metric]['median']}
  metrics['long_task_counts']={'before':len(old['long_tasks_over_50_ms']),'after':len(new['long_tasks_over_50_ms'])}
  scenarios[name]=metrics
 result['groups'].append({'mobile':g['mobile'],'cache':g['cache'],'runs':g['runs'],'scenarios':scenarios,
   'home_encoded_delta':g['home_encoded_bytes']['median']-b['home_encoded_bytes']['median'],
   'picker_encoded_delta':g['picker_encoded_bytes']['median']-b['picker_encoded_bytes']['median']})
# Inline CSS is compressed separately for the CSS+JS budget, while complete
# actual HTTP documents above include its contribution to transferred pages.
budget_base=os.getenv('CSS_AVATAR_COMPARE_BASE','1c964dc')
result['budget_base']=budget_base
old_template=subprocess.check_output(['git','show',budget_base+':templates/_avatars.html'],text=True)
new_template=Path('templates/_avatars.html').read_text()
def css_bytes(s):return len(gzip.compress(s.split('<style>',1)[1].split('</style>',1)[0].encode(),mtime=0))
css_delta=css_bytes(new_template)-css_bytes(old_template)
def previous_script(name):
 path='static/js/'+name
 exists=subprocess.check_output(['git','ls-tree','--name-only',budget_base,path],text=True).strip()
 return subprocess.check_output(['git','show',budget_base+':'+path]) if exists else b''
js_delta=sum(len(gzip.compress(Path(f'static/js/{name}').read_bytes(),mtime=0))-len(gzip.compress(previous_script(name),mtime=0)) for name in ['avatars.js','avatar-audio.js','search.js','appearance.js','companion-customizer.js'])
result['css_js_gzip_delta_bytes']=css_delta+js_delta
result['gates']={
 'css_js_added_le_15kib':css_delta+js_delta<=15*1024,
 'home_added_le_30kib':all(g['home_encoded_delta']<=30*1024 for g in result['groups']),
 'picker_added_le_120kib':all(g['picker_encoded_delta']<=120*1024 for g in result['groups']),
 'home_lcp_median_regression_le_100ms':all(g['scenarios']['home_idle']['lcp_ms']['median_delta']<=100 for g in result['groups']),
 'home_interaction_median_regression_le_20ms':all(g['scenarios']['home_interaction']['interaction_duration_per_run_median_ms']['median_delta']<=20 for g in result['groups']),
 'mobile_interaction_p95_medians_le_33ms':all(frame_pass(g['scenarios']['home_interaction']['frame_p95_ms']['after']['median']) for g in result['groups'] if g['mobile']),
 'mobile_interaction_p95_all_runs_le_33ms':all(frame_pass(g['scenarios']['home_interaction']['frame_p95_ms']['after']['worst']) for g in result['groups'] if g['mobile']),
 'home_renderer_rss_median_growth_le_10mib':all(g['scenarios']['home_interaction']['renderer_rss_sum_bytes']['median_delta']<=10*1048576 for g in result['groups']),
 'no_javascript_errors':not after['failures']['javascript_errors'],
 'no_external_requests':not after['failures']['external_attempts'],
}
memory=audit_memory(left,right)
result['full_memory_audit']=memory
result['environment_checks']=memory['environment_checks']
result['gates'].update({'memory-'+name:passed for name,passed in memory['gates'].items()})
result['gates']['complete_valid_memory_cohorts']=memory['status']!='inconclusive'
result['requires_investigation']=['Page-wide long tasks need attribution before declaring the avatar-specific long-task gate passed.',
 'Renderer RSS must be compared at identical renderer-process counts; shared pages are not private memory.',
 'The mobile hard frame gate applies to each sample; median-only reporting cannot hide slower samples.',
 'Existing hidden/offscreen/picker/remount issues are retained; this tool does not approve release.']
(right.parent/'comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps({'complete':result['complete'],'gates':result['gates']},indent=2))
