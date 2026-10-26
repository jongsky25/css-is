"""Retain all JSON/XML/log evidence and hashes of the separately retained traces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
root=args.directory.resolve()

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def read(relative):
    return json.loads((root/relative).read_text())

summary={'source_run_id':40247047928,'audit_commit':os.getenv('GITHUB_SHA'),'errors':{}}
try:
    summary['overall']=read('overall-assessment.json')
except Exception as error:summary['errors']['overall']=repr(error)
for phase in ['focused','runtime']:
    summary[phase]={}
    for kind in ['fern','mushroom','succulent']:
        try:
            arms={}
            for arm in ['before','after']:
                data=read(f'focused/traces/{kind}/summary.json' if phase=='focused' else f'runtime/{arm}/{kind}/summary.json')
                rows=[r for r in data['samples'] if r['version']==arm] if phase=='focused' else data['samples']
                arms[arm]={'callback_maxima_ms':[r['max_owned_call_wall_ms'] for r in rows],
                           'frame_p95_ms':[r['scenario']['frame_p95_ms'] for r in rows]}
            summary[phase][kind]=arms
        except Exception as error:summary['errors'][phase+'-'+kind]=repr(error)
try:
    comparison=read('matrix/after/comparison.json')
    summary['css_js_gzip_delta_bytes']=comparison['css_js_gzip_delta_bytes']
    summary['matrix_groups']=[{'mobile':g['mobile'],'cache':g['cache'],'runs':g['runs'],
      'home_encoded_delta':g['home_encoded_delta'],'picker_encoded_delta':g['picker_encoded_delta'],
      'scenario_deltas':{name:{metric:values['median_delta'] for metric,values in metrics.items() if isinstance(values,dict) and 'median_delta' in values} for name,metrics in g['scenarios'].items()}}
      for g in comparison['groups']]
    summary['native_frame_p95_ms']={kind:[r['scenario']['frame_p95_ms'] for r in read(f'focused/native/{kind}/native-control.json')['samples']] for kind in ['fern','mushroom','succulent']}
    summary['matrix_mobile_frame_p95_ms']={cache:[r['scenarios']['home_interaction']['frame_p95_ms'] for r in read(f'matrix/after/application/True-{cache}.json')] for cache in ['cold','warm']}
except Exception as error:summary['errors']['matrix_or_native']=repr(error)
(root/'review-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('AVATAR_REVIEW_SUMMARY='+json.dumps(summary,separators=(',',':')))

files=[path for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'review-manifest.json']
manifest={'source_run_id':40247047928,'source_artifact_name':'avatar-2b-complete',
          'audit_commit':os.getenv('GITHUB_SHA'),'generated_during_audit':['overall-assessment.json','review-summary.json','review-manifest.json'],
          'source_run_url':'https://github.com/jongsky25/css-is/actions/runs/40247047928',
          'files':{str(p.relative_to(root)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files},
          'packaged':'All JSON, XML and text logs; binary screenshots and compressed traces remain in source artifact and are hashed here.'}
(root/'review-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open('avatar-2b-review.tar.gz','w:gz',compresslevel=9) as archive:
    for path in [*files,root/'review-manifest.json']:
        if path.suffix in {'.json','.xml','.txt'}:
            archive.add(path,arcname=str(path.relative_to(root)),recursive=False)
assert Path('avatar-2b-review.tar.gz').stat().st_size < 25*1024*1024, 'Review bundle exceeds transport budget; full original artifact is preserved.'
print('Numeric evidence bundle bytes:',Path('avatar-2b-review.tar.gz').stat().st_size)
