"""Re-audit retained cat-gradient evidence, then expose every navigation sample."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.avatar_baseline.analyze_cat_gradients import audit, ORDER


def analyze(root, repo, harness):
    checked = audit(root, repo, harness)
    if checked['errors']:
        raise ValueError(checked['errors'])
    samples = []
    for index, arm in enumerate(ORDER):
        path = root / f'{index}-{arm}' / 'False-warm.json'
        for raw in json.loads(path.read_text()):
            pids = []
            for point in raw['navigation_trend']:
                details = point['renderer_memory_detail']
                # No app-role inference from RSS size: sum every renderer.
                if len({r['pid'] for r in details}) != point['renderer_process_count']:
                    raise ValueError('Incomplete or duplicate detailed renderer census')
                census = sorted(r['pid'] for r in details)
                pids.append(census)
                statuses = {k: sum(r['status'][k] for r in details)
                            for k in ['VmRSS', 'RssAnon', 'RssFile', 'RssShmem']}
                smaps = {k: sum(r['smaps_rollup'][k] for r in details)
                         for k in ['Rss', 'Private_Clean', 'Private_Dirty', 'Shared_Clean', 'Shared_Dirty', 'Pss']}
                samples.append({'cohort': index, 'arm': arm, 'run': raw['run'],
                    'mount': point['mount'], 'raw_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'rss_bytes': point['renderer_rss_sum_bytes'], 'heap_bytes': point['js_heap_bytes'],
                    'live_nodes': point['nodes'], 'dom': point['dom_counters'], 'pids': census,
                    'status_sum': statuses, 'smaps_sum': smaps,
                    'status_minus_gate_rss_bytes': statuses['VmRSS'] - point['renderer_rss_sum_bytes']})
            if any(p != pids[0] for p in pids):
                raise ValueError('Renderer PID changed within navigation')
    transitions = []
    for a, b in zip(samples, samples[1:]):
        if (a['cohort'], a['run']) == (b['cohort'], b['run']):
            transitions.append({'cohort': a['cohort'], 'run': a['run'], 'from_mount': a['mount'], 'to_mount': b['mount'],
                'rss_delta_bytes': b['rss_bytes'] - a['rss_bytes'],
                'anonymous_delta_bytes': b['status_sum']['RssAnon'] - a['status_sum']['RssAnon'],
                'heap_delta_bytes': b['heap_bytes'] - a['heap_bytes'],
                'documents_delta': b['dom']['documents'] - a['dom']['documents']})
    return {'acceptance': False, 'audit': checked, 'samples': samples, 'transitions': transitions,
            'limits': 'Sequential proc/heap/DOM observations; no GC timestamps or native allocation owners. No phase matching, sample exclusions, RSS adjustments or causal claim.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    result = analyze(args.root, Path(__file__).resolve().parents[2], '52ed2ea48af397c146c24013f2acea9f2726a77f')
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Verified {len(result['samples'])} navigation samples and {len(result['transitions'])} adjacent transitions")
