"""Regenerate compact findings from the preserved audited cohorts."""
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
cal = json.loads((root / 'calibration.json').read_text())
comparison = json.loads((root / 'comparison.json').read_text())

def failures(rows):
    return [{"pair": r['name'], **m, 'delta_mib': m['delta_bytes'] / 2**20}
            for r in rows for m in r['metrics']
            if not m['within_10_mib'] or not m['renderer_counts_match']]

pairs = comparison['comparisons']
source = [r for r in pairs if r['name'].startswith('source-')]
control = [r for r in pairs if not r['name'].startswith('source-')]
summary = {
    'acceptance': False,
    'candidate': comparison['candidate_refs']['current'],
    'harness': comparison['harness_commit'],
    'calibration': {
        'status': cal['status'],
        'navigation_ms': [c['navigation_ms'] for c in cal['cohorts']],
        'control_change_percent': 100 * (cal['cohorts'][3]['navigation_ms'] / cal['cohorts'][0]['navigation_ms'] - 1),
        'paired_trace_increase_percent': [100 * (cal['cohorts'][t]['navigation_ms'] / cal['cohorts'][c]['navigation_ms'] - 1) for c,t in [(0,1),(3,2)]],
    },
    'comparison_capture_status': comparison['status'],
    'source_checks': sum(len(r['metrics']) for r in source),
    'source_failures': failures(source),
    'control_checks': sum(len(r['metrics']) for r in control),
    'control_failures': failures(control),
    'renderer_counts_all_match': all(m['renderer_counts_match'] for r in pairs for m in r['metrics']),
    'heap_checks_all_pass': all(m['within_10_mib'] for r in pairs for m in r['metrics'] if m['metric'] == 'js_heap_bytes'),
    'source_hashes_verified': cal['source_hashes_verified'] + comparison['source_hashes_verified'],
    'files_verified': cal['files_verified'] + comparison['files_verified'],
}
with zipfile.ZipFile(root / 'comparison-evidence.zip') as z:
    observations = []
    for slot in (4,7):
        raw = json.loads(z.read(f'{slot:02d}-current/False-warm.json'))[0]
        p = raw['navigation_trend'][3]
        observations.append({'slot': slot, 'mount': p['mount'],
            'rss_mib': p['renderer_rss_sum_bytes'] / 2**20,
            'js_heap_mib': p['js_heap_bytes'] / 2**20,
            'live_nodes': p['nodes'], 'dom_counters': p['dom_counters'],
            'status_mib': {k: sum(r['status'].get(k,0) for r in p['renderer_memory_detail']) / 2**20 for k in ('VmRSS','RssAnon','RssFile','RssShmem')},
            'post_workload_blink_size_mib': comparison['cohorts'][slot]['endpoint']['allocators']['blink_gc']['size'] / 2**20})
    summary['largest_control_pair_navigation_15'] = observations
summary['disposition'] = 'Memory screen failed; same-source controls unstable; candidate is not a 2B fix. No causal attribution from these pairs.'
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('source_failures','control_failures','largest_control_pair_navigation_15')}, indent=2))
