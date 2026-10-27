"""Re-audit then summarize native memberships separately inside/outside measurement."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.avatar_baseline.analyze_membership_lifecycle import audit
from scripts.avatar_baseline.analyze_element_membership import generations, join_receivers
from scripts.avatar_baseline.analyze_reader_retention import clock_bounds, mapped, selected_events, position


def native_periods(p, trace):
    events = p['history']['events']; begin, end = p['begin_ns'], p['end_ns']
    periods = {'inside': [], 'before': [], 'after': [], 'straddling': []}
    for e in events:
        key = 'inside' if begin <= e['begin_ns'] <= e['returned_ns'] <= end else 'before' if e['returned_ns'] < begin else 'after' if e['begin_ns'] > end else 'straddling'
        periods[key].append(e)
    spans, unknown = generations([e for e in events if e['kind'] in ['allocate','pool']])
    receivers = join_receivers(events, spans)
    clock = clock_bounds(p, trace['traceEvents']); gc = selected_events(trace['traceEvents'],p['pid'])
    returns = []
    for span in spans:
        if not span['labels'] or span['end_ns'] is None: continue
        candidates = [e for e in events if e['kind'] == 'pool' and e['backend'] == span['backend']
                      and int(e['address'],16) == span['base'] and e['begin_ns'] == span['end_ns']]
        if len(candidates) != 1: raise ValueError('Ambiguous labelled return')
        e = candidates[0]; bounds = mapped([e['begin_ns'],e['returned_ns']],clock)
        covered = clock['coverage_us'][0] <= bounds[0] <= bounds[1] <= clock['coverage_us'][1]
        returns.append({'generation': span['generation'], 'page_base': hex(span['base']),
            'documents_observed': sorted({int(label.split(':')[1]) for label in span['labels']}),
            'groups_observed': sorted({label.split(':')[2] for label in span['labels']}),
            'request_end_ns': span['begin_ns'], 'return_interval_ns': [e['begin_ns'],e['returned_ns']],
            'in_measured_window': begin <= e['begin_ns'] <= e['returned_ns'] <= end,
            'trace_covered': covered, 'trace_bounds_us': bounds,
            'sweep_overlap': [g for g in gc if 'Sweep' in g['name'] and position(g,bounds) == 'overlap_or_uncertain'] if covered else None})
    return {'native_counts_by_period': {k: dict(Counter(e['kind'] for e in es)) for k,es in periods.items()},
        'unknown_returns': unknown, 'receiver_records': len(receivers),
        'labelled_returned_generations_inside': sum(r['in_measured_window'] for r in returns),
        'labelled_returned_generations_outside': sum(not r['in_measured_window'] for r in returns),
        'labelled_returns': returns,
        'major_gc': [e for e in gc if e['name']=='MajorGC'],
        'limits': 'Membership is not exclusive ownership or attributed bytes. Outside-window returns cannot satisfy measured reclamation. No GC correlation beyond trace coverage.'}


def summarize(root, repo, ref):
    checked = audit(root,repo,ref)
    if checked['files_verified'] != 14 or checked['source_hashes_verified'] != 14:
        raise ValueError('Incomplete archive/source audit')
    result = {'acceptance': False, 'application_qualified': False, 'audit_status': checked['status'],
              'audit_errors': checked['errors'], 'harness_commit': ref, 'cohorts': []}
    for index,mode in enumerate(['control','probe','probe','control']):
        folder = root/f'{index}-{mode}'; path=folder/'capture.json.gz'; p=json.load(gzip.open(path,'rt'))
        item={'index':index,'mode':mode,'capture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'back_forward_cache_disabled':p['back_forward_cache_disabled'],
              'pagehide_count':len(p['lifecycle_events']), 'stages':[],
              'cost_ms': {'duration':(p['end_ns']-p['begin_ns'])/1e6,
                  'census':sum((s['batch_census_interval_ns'][1]-s['batch_census_interval_ns'][0]) if 'batch_census_interval_ns' in s else sum(c['end_ns']-c['begin_ns'] for c in s['censuses']) for s in p['stages'])/1e6,
                  'heap':sum(s['heap']['interval_ns'][1]-s['heap']['interval_ns'][0] for s in p['stages'])/1e6,
                  'dom':sum(s['dom']['interval_ns'][1]-s['dom']['interval_ns'][0] for s in p['stages'])/1e6,
                  'trace_setup':p.get('trace_setup_ns',0)/1e6}}
        item['cost_ms']['native_preparation'] = sum(e['callback_ready_ns']-e['begin_ns'] for e in p.get('history',{}).get('events',[]) if p['begin_ns']<=e['begin_ns']<=e['returned_ns']<=p['end_ns'])/1e6
        for s in p['stages']:
            item['stages'].append({'index':s['index'],'documents':s['dom']['value']['documents'],
                'nodes':s['dom']['value']['nodes'],'js_heap_bytes':s['heap']['value']['usedSize']})
        if mode=='probe': item.update(native_periods(p,json.load(gzip.open(folder/'trace.json.gz','rt'))))
        result['cohorts'].append(item)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--ref',required=True);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    ref=subprocess.check_output(['git','rev-parse',a.ref],text=True).strip()
    result=summarize(a.root,Path(__file__).resolve().parents[2],ref)
    with gzip.open(a.out,'wt') as stream:json.dump(result,stream,indent=2)
    for c in result['cohorts']:
        if c['mode']=='probe':print(json.dumps({k:c[k] for k in ['index','native_counts_by_period','labelled_returned_generations_inside','labelled_returned_generations_outside']}))
