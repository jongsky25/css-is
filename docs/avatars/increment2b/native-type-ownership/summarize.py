"""Reproduce endpoint type summaries; no acceptance or causal attribution."""
import gzip
import json
from pathlib import Path
root=Path(__file__).resolve().parent
p=json.load(gzip.open(root/'analysis.json.gz','rt'))
rows=[]
for c in p['cohorts']:
    types=c['types']
    rows.append({'index':c['index'],'arm':c['arm'],'named_types':c['named_type_count'],
        'allocated_mib':c['allocated_objects_bytes']/2**20,
        'heap_size_mib':c['heap_size_bytes']/2**20,'pooled_mib':c['pooled_bytes']/2**20,
        'svg_named_mib':sum(v['allocated_bytes'] for name,v in types.items() if 'SVG' in name)/2**20,
        'html_documents':types.get('HTMLDocument',{}).get('object_count',0),
        'xml_documents':types.get('XMLDocument',{}).get('object_count',0),
        'largest_types': sorted([{'type':k,**v} for k,v in types.items()],key=lambda x:(-x['allocated_bytes'],x['type']))[:20]})
a,b=p['cohorts'][4],p['cohorts'][7]
s={'acceptance':False,'new_browser_measurements':0,'archive_members_verified':p['archive_members_verified'],
   'all_eight_type_page_heap_reconciliations_pass':all(c['type_page_and_heap_totals_match'] for c in p['cohorts']),
   'cohorts':rows,
   'slot4_minus7':{'allocated_mib':(a['allocated_objects_bytes']-b['allocated_objects_bytes'])/2**20,
       'heap_size_mib':(a['heap_size_bytes']-b['heap_size_bytes'])/2**20,
       'pooled_mib':(a['pooled_bytes']-b['pooled_bytes'])/2**20,
       'svg_named_mib':rows[4]['svg_named_mib']-rows[7]['svg_named_mib'],
       'largest_type_increases':sorted([{'type':v['type'],'allocated_bytes':-v['allocated_bytes_delta'],
           'object_count':-v['object_count_delta']} for v in p['comparisons'][-1]['type_differences']],
           key=lambda v:(-v['allocated_bytes'],v['type']))[:20]},
   'limits':p['limits']}
(root/'summary.json').write_text(json.dumps(s,indent=2)+'\n')
print(json.dumps({k:v for k,v in s.items() if k not in ('cohorts','limits')},indent=2))
