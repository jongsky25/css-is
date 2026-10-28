"""Offline numeric/hash audit only. No browser or instrumentation starts here."""
import argparse,hashlib,json,statistics,subprocess,sys
from pathlib import Path
from xml.etree import ElementTree
sys.path.insert(0,'scripts/avatar_baseline')
from memory_audit import audit_memory
from verification_result import frame_pass,validate_samples
P=argparse.ArgumentParser();P.add_argument('root',type=Path);P.add_argument('phase');P.add_argument('--source',default='fecd276a9d888691c000c297d4ca1c1f6a958535');P.add_argument('--out',type=Path,required=True);a=P.parse_args()
root=a.root;phase=a.phase;checks={};notes=[];details={}
def read(p):return json.loads((root/p).read_text())
def check(k,v):checks[k]=bool(v)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
d=read(phase+'/assessment.json');check('phase_complete',d['status']=='passed' and bool(d['gates']) and all(d['gates'].values()) and not d['harness_errors'] and all(d['environment_checks'].values()))
check('source_and_browser',d['source_commit']==a.source and d['expected_chromium']=='156.0.8078.47' and d['chromium'].split()[1]==d['expected_chromium'])
check('unchanged_budgets',d['callback_budget_ms']==50 and d['frame_budget_ms']==33.3)
hashes={**d['source_sha256'],**{'templates/_avatar_species/'+k+'.html':v for k,v in d['species_sha256'].items()}}
for name,expected in hashes.items():check('source:'+name,hashlib.sha256(subprocess.check_output(['git','show',a.source+':'+name])).hexdigest()==expected)
manifest=root/'review-manifest.json'
if manifest.exists():
 m=json.loads(manifest.read_text());present=missing=0
 for name,item in m['files'].items():
  f=root/name
  if f.exists():check('artifact:'+name,f.stat().st_size==item['bytes'] and sha(f)==item['sha256']);present+=1
  else:check('remote_trace:'+name,name.endswith('.json.gz'));missing+=1
 details['artifact_hashes_verified']=present;details['trace_hashes_retained_remotely']=missing
 if missing:notes.append('Trace bytes retained in full hosted artifacts; compact audit rehashes numeric/visual evidence only.')
if phase=='completion-functional':
 for name,count in [('browser-regressions',9),('wardrobe-and-core',104),('customizer',3),('animal-care',8),('seasonal',1),('visibility',1)]:
  cases=list(ElementTree.parse(root/phase/(name+'.xml')).getroot().iter('testcase'))
  check('junit:'+name,len(cases)==count and all(not any(c.tag in {'skipped','failure','error'} for c in case) for case in cases))
 check('rig_cases',read(phase+'/motion/motion-rig-check.json')['cases']==432)
 sheets=read(phase+'/sheets/index.json');check('contact_sheets',len(sheets)==6 and sum(x['cards'] for x in sheets)==1170)
else:
 controls=read(phase+'/control/empty-control.json')['samples'];check('control_identities',len(controls)==6 and {(r['cpu'],r['run']) for r in controls}=={(cpu,n) for cpu in [1,4] for n in range(3)})
 check('control_timing',all(r['actions'] and r['scenario']['frame_count'] and r['max_empty_callback_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in controls))
if phase=='runtime':
 maxima=[];frames=[]
 for kind in ['cat','fern','fish','bat']:
  for arm,source in [('before','0a91f73cf2ef2a72af70a149dc2deca2fb9c8b9a'),('after',a.source)]:
   data=read(f'runtime/{arm}/{kind}/summary.json');rows=data['samples'];validate_samples(rows,5)
   check(arm+':'+kind+':source',data['source_commit']==source and data['runtime_sha256']==hashlib.sha256(subprocess.check_output(['git','show',source+':static/js/avatars.js'])).hexdigest())
   check(arm+':'+kind+':samples',data['after_only'] and {r['run'] for r in rows}==set(range(5)) and all(r['seconds']==30 and r['cpu']==4 and r['mature'] and r['actions'] and r['owned_call_count'] and not r['trace_data_loss'] and not r['errors'] for r in rows))
   if arm=='after':
    check(kind+':timing',all(r['max_owned_call_wall_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in rows));maxima.extend(r['max_owned_call_wall_ms'] for r in rows);frames.extend(r['scenario']['frame_p95_ms'] for r in rows)
 details.update(max_owned_callback_ms=max(maxima),max_frame_p95_ms=max(frames),current_samples=len(maxima))
if phase=='matrix':
 memory=audit_memory(root/'matrix/before/application',root/'matrix/after/application');details['memory_audit']=memory
 check('full_memory',memory['status']=='passed' and len(memory['records'])==104)
 comparison=read('matrix/after/comparison.json');check('retained_memory_matches',comparison['full_memory_audit']==memory);check('comparison_gates',comparison['complete'] and all(comparison['gates'].values()))
 details['code_gzip_delta_bytes']=comparison['css_js_gzip_delta_bytes'];details['groups']=comparison['groups']
 for g in comparison['groups']:
  name=f"{g['mobile']}-{g['cache']}";arms={arm:read(f'matrix/{arm}/application/{name}.json') for arm in ['before','after']}
  for arm,rows in arms.items():check(name+arm+':protocol',len(rows)==5 and {r['run'] for r in rows}==set(range(5)) and all(r['seconds']>=30 and r['chromium']=='156.0.8078.47' and not r['errors'] and not r['external_attempts'] and len(r['picker_selected'])==16 for r in rows))
  for scenario,metrics in g['scenarios'].items():
   for metric,budget in [('lcp_ms',100),('renderer_rss_sum_bytes',10485760),('js_heap_bytes',10485760)]:
    if metric in metrics:
     delta=statistics.median(r['scenarios'][scenario][metric] for r in arms['after'])-statistics.median(r['scenarios'][scenario][metric] for r in arms['before'])
     check(name+scenario+metric,delta==metrics[metric]['median_delta'] and delta<=budget)
  if g['mobile']:check(name+':frames',all(frame_pass(r['scenarios']['home_interaction']['frame_p95_ms']) for r in arms['after']))
result={'source_commit':a.source,'phase':phase,'status':'passed' if all(checks.values()) else 'failed_or_inconclusive','checks':checks,'failed':[k for k,v in checks.items() if not v],'details':details,'limitations':notes+['No physical-phone testing','No archived GC experiment or forced collection','This audit does not authorize deployment or main merge']}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['checks','details']}));sys.exit(0 if result['status']=='passed' else 1)
