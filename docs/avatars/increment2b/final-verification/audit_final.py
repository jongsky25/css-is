import json,hashlib,statistics,subprocess
from pathlib import Path
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('evidence',type=Path,help='Extracted compact archive directory')
parser.add_argument('--repo',type=Path,default=Path.cwd())
args=parser.parse_args();r=args.evidence;repo=args.repo
def read(p): return json.loads((r/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read('review-manifest.json'); checked=[];omitted=[]
for f,v in m['files'].items():
 p=r/f
 if p.exists():
  assert sha(p)==v['sha256'] and p.stat().st_size==v['bytes'],f
  checked.append(f)
 else:
  assert f.endswith('.json.gz'),f
  omitted.append(f)
for phase in ['functional','focused','runtime','matrix']:
 d=read(phase+'/assessment.json')
 assert d['status']=='passed' and not d['harness_errors']
 assert d['source_commit']=='e909de12c42fe8fe99ce58d922bbef71c711e574'
 assert d['expected_chromium']=='156.0.8078.47'
 for f,h in d['source_sha256'].items():assert hashlib.sha256(subprocess.check_output(['git','show',d['source_commit']+':'+f],cwd=repo)).hexdigest()==h
v=read('functional/static-preview-visual/assessment.json')
assert v['cells']==4896 and len(v['sheets'])==51 and v['all_pixel_identical']
for row in v['sheets']:
 assert sha(r/'functional/static-preview-visual'/row['file'])==row['preview_sha256']==row['reference_sha256'] and row['pixel_identical']
comparison=read('matrix/after/comparison.json');memory=[]
for group in comparison['groups']:
 key=f"{group['mobile']}-{group['cache']}"
 arms={a:read(f'matrix/{a}/application/{key}.json') for a in ['before','after']}
 for a,rows in arms.items():
  assert len(rows)==5 and {x['run'] for x in rows}==set(range(5))
  for x in rows:
   assert x['seconds']>=30 and not x['errors'] and not x['external_attempts']
   assert len(x['picker_selected'])==16
 for scenario,metrics in group['scenarios'].items():
  counts={a:[x['scenarios'][scenario]['renderer_process_count'] for x in rows] for a,rows in arms.items()}
  assert sorted(counts['before'])==sorted(counts['after']) and min(counts['before'])>0
  for metric in ['renderer_rss_sum_bytes','js_heap_bytes','lcp_ms','frame_p95_ms']:
   if metric not in metrics:continue
   samples={a:[x['scenarios'][scenario][metric] for x in rows] for a,rows in arms.items()}
   medians={a:statistics.median(xs) for a,xs in samples.items()}
   delta=medians['after']-medians['before']
   assert delta==metrics[metric]['median_delta'],(key,scenario,metric)
   if metric in ['renderer_rss_sum_bytes','js_heap_bytes']:
    assert delta<=10485760
    memory.append(dict(group=key,scenario=scenario,metric=metric,samples=samples,medians=medians,delta=delta,counts=counts))
out={'status':'passed','retained_file_hashes_verified':len(checked),'trace_hashes_retained_only':len(omitted),'static_pngs_verified':51,'static_cells':4896,'matrix_samples':40,'memory_recomputed':memory,'release_ready':False}
(r/'independent-audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='memory_recomputed'}))
