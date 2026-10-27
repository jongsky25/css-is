"""Reproduce compact comparisons from audited, symbolized native history."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def summarize(root):
    audit = json.loads((root / 'comparison.json').read_text())
    path = root / 'symbolized.json.gz'
    symbols = json.loads(gzip.decompress(path.read_bytes()))
    assert audit['status'] == 'complete_history_diagnostic'
    assert audit['harness_commit'] == symbols['harness_commit']
    rows = []
    for cohort, native in zip(audit['cohorts'], symbols['cohorts'], strict=True):
        assert (cohort['index'], cohort['arm']) == (native['index'], native['arm'])
        callers = native['exclusive_nearest_blink_callers']
        count = lambda fragment: sum(v['requests'] for k, v in callers.items() if fragment in k)
        rows.append({
            **cohort,
            'inside_window_requests': count(''),
            'returned_within_window': sum(v['returned_within_window'] for v in callers.values()),
            'shareable_element_data_caller_requests': count('ShareableElementData'),
            'svg_named_caller_requests': count('SVG'),
            'top_four_callers': dict(list(callers.items())[:4]),
        })
    pairs = []
    for original, current in [(0, 1), (3, 2), (5, 4), (6, 7)]:
        o, c = rows[original], rows[current]
        pairs.append({'original_slot': original, 'current_slot': current,
                      'request_delta': c['inside_window_requests'] - o['inside_window_requests'],
                      'shareable_caller_request_delta': c['shareable_element_data_caller_requests'] - o['shareable_element_data_caller_requests'],
                      'svg_named_caller_request_delta': c['svg_named_caller_requests'] - o['svg_named_caller_requests']})
    return {'acceptance': False, 'harness_commit': audit['harness_commit'],
            'symbolized_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'cohorts': rows, 'pairs': pairs,
            'limits': symbols['limits']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root), indent=2))
