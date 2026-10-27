"""Perturbed root graphs after natural GC; never qualification or acceptance."""
import argparse
from array import array
from collections import Counter, deque
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

from scripts.avatar_baseline import element_membership_lifecycle as lifecycle
from scripts.avatar_baseline.analyze_membership_lifecycle import analyze
from scripts.avatar_baseline.hosted_native_calibration import SOURCES as BASE_SOURCES
from scripts.avatar_baseline.native_recorder_selftest import validate_live
from scripts.avatar_baseline.runner_isolation_inventory import inventory

PROTOCOL = 'native-root-retention-diagnostic-v1'
SOURCES = list(dict.fromkeys([*BASE_SOURCES, 'scripts/avatar_baseline/native_root_retention.py',
    'scripts/avatar_baseline/runner_isolation_inventory.py', 'requirements-test.txt',
    'requirements-avatar-native.txt']))


def graph(snapshot):
    """Shortest root paths excluding weak references and display shortcuts."""
    meta = snapshot['snapshot']['meta']
    nf, ef = meta['node_fields'], meta['edge_fields']
    nodes, edges, strings = snapshot['nodes'], snapshot['edges'], snapshot['strings']
    nw, ew = len(nf), len(ef)
    if not nw or not ew or len(nodes) % nw or len(edges) % ew:
        raise ValueError('Malformed graph arrays')
    ni = {name: nf.index(name) for name in ['type', 'name', 'id', 'edge_count']}
    ei = {name: ef.index(name) for name in ['type', 'name_or_index', 'to_node']}
    nt, et = meta['node_types'][ni['type']], meta['edge_types'][ei['type']]
    count = len(nodes) // nw
    if count != snapshot['snapshot']['node_count'] or len(edges)//ew != snapshot['snapshot']['edge_count']:
        raise ValueError('Graph totals differ')
    starts, cursor = [], 0
    for index in range(count):
        offset = index*nw
        kind, name, size = nodes[offset+ni['type']], nodes[offset+ni['name']], nodes[offset+ni['edge_count']]
        if not 0 <= kind < len(nt) or not 0 <= name < len(strings) or size < 0:
            raise ValueError('Invalid graph node')
        starts.append(cursor)
        cursor += size*ew
    if cursor != len(edges) or not count or nt[nodes[ni['type']]] != 'synthetic':
        raise ValueError('Invalid graph root or edge totals')
    for offset in range(0, len(edges), ew):
        target, kind, name = (edges[offset+ei[k]] for k in ['to_node', 'type', 'name_or_index'])
        if not 0 <= target < len(nodes) or target % nw or not 0 <= kind < len(et):
            raise ValueError('Invalid graph edge')
        if et[kind] not in ['element', 'hidden'] and not 0 <= name < len(strings):
            raise ValueError('Invalid edge name')
    parent, via = array('q', [-1])*count, array('q', [-1])*count
    parent[0] = 0
    queue = deque([0])
    while queue:
        index = queue.popleft()
        stop = starts[index] + nodes[index*nw+ni['edge_count']]*ew
        for offset in range(starts[index], stop, ew):
            if et[edges[offset+ei['type']]] in ['weak', 'shortcut']:
                continue
            target = edges[offset+ei['to_node']]//nw
            if parent[target] == -1:
                parent[target], via[target] = index, offset
                queue.append(target)
    def describe(index):
        offset = index*nw
        return {'id': nodes[offset+ni['id']], 'type': nt[nodes[offset+ni['type']]],
                'name': strings[nodes[offset+ni['name']]],
                **({'detachedness': nodes[offset+nf.index('detachedness')]} if 'detachedness' in nf else {})}
    targets, categories = [], Counter()
    for index in range(count):
        node = describe(index)
        if node['type'] not in ['native', 'object', 'hidden'] or not re.search(r'Document|Window|NativeContext', node['name']):
            continue
        path, current = [], index
        if parent[index] != -1:
            while current:
                offset = via[current]
                kind = et[edges[offset+ei['type']]]
                value = edges[offset+ei['name_or_index']]
                path.append({'from': describe(parent[current]), 'edge_type': kind,
                             'edge_name': value if kind in ['element', 'hidden'] else strings[value]})
                current = parent[current]
            path.reverse()
        root_names = [part['from']['name'] for part in path
                      if part['from']['type']=='synthetic' and part['from']['name']]
        category = root_names[-1] if root_names else '(root)' if path else '(unreachable)'
        categories[category] += 1
        targets.append({'node': node, 'reachable_without_weak_or_shortcut': parent[index]!=-1,
                        'root_category': category, 'path': path})
    return {'nodes': count, 'edges': len(edges)//ew, 'targets': targets,
            'target_root_categories': dict(categories), 'excluded_edges': ['weak', 'shortcut'],
            'limits': 'Graph paths describe this perturbed diagnostic only; no exclusive ownership, byte attribution or prior-run causation.'}


def capture(out, mode):
    out.mkdir(parents=True)
    target = out/'first-natural-major.heapsnapshot'
    original = lifecycle.sync_playwright
    class Manager:
        def __enter__(self):
            self.manager = original()
            instance = self.manager.__enter__()
            launch = instance.chromium.launch
            def diagnostic_launch(*args, **kwargs):
                flags = kwargs.get('args', [])
                if any('--js-flags' in flag for flag in flags):
                    raise ValueError('Unexpected existing JS flags')
                extra = '--heap-snapshot-on-gc=1 --heap-snapshot-path='+str(target)
                kwargs['args'] = [*flags, '--js-flags='+extra]
                (out/'diagnostic-flags.json').write_text(json.dumps(kwargs['args'])+'\n')
                return launch(*args, **kwargs)
            instance.chromium.launch = diagnostic_launch
            return instance
        def __exit__(self, *args):
            return self.manager.__exit__(*args)
    lifecycle.sync_playwright = Manager
    # The unchanged runner creates its own output directory.
    code = lifecycle.run(out/'capture', mode)
    if target.exists():
        with target.open('rb') as src, gzip.open(str(target)+'.gz', 'wb') as dest:
            import shutil
            shutil.copyfileobj(src, dest)
        target.unlink()
    return code


def run(out):
    repo = Path(__file__).resolve().parents[2]
    out.mkdir(parents=True, exist_ok=False)
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    result = {'protocol': PROTOCOL, 'harness_commit': ref, 'acceptance': False,
              'instrument_qualified': False, 'application_qualified': False,
              'snapshot_perturbs_sweeping_and_scheduling': True, 'order': ['control','probe','probe','control'],
              'cohorts': [], 'errors': []}
    try:
        for name in SOURCES:
            raw = (repo/name).read_bytes()
            if raw != subprocess.check_output(['git','show',ref+':'+name],cwd=repo):
                raise ValueError('Unfrozen diagnostic source: '+name)
            dest = out/'harness'/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        if platform.machine()!='x86_64' or platform.python_version()!='3.12.14' or {n:importlib.metadata.version(n) for n in ['playwright','frida']}!={'playwright':'1.62.0','frida':'17.5.1'}:
            raise ValueError('Unexpected diagnostic toolchain')
        (out/'runner-inventory.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        for index, mode in enumerate(result['order']):
            folder = out/f'{index}-{mode}'
            folder.mkdir()
            row = {'index': index, 'mode': mode}
            result['cohorts'].append(row)
            with (folder/'runner.txt').open('w') as stream:
                env = dict(os.environ, DEBUG='pw:browser')
                row['exit_code'] = subprocess.run([sys.executable, '-m', 'scripts.avatar_baseline.native_root_retention',
                    '--capture', '--mode',mode,'--out',str(folder/'slot')],cwd=repo,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
            try:
                if row['exit_code']:
                    raise ValueError('Diagnostic capture failed')
                p = json.load(gzip.open(folder/'slot/capture/capture.json.gz','rt'))
                if p['status']!='captured' or p['forced_gc'] is not False or p['harness_commit']!=ref or len(p['stages'])!=12:
                    raise ValueError('Incomplete or changed diagnostic workload')
                if mode=='probe':
                    validate_live(p['history'],p['native_export_interval_ns'])
                    trace = json.load(gzip.open(folder/'slot/capture/trace.json.gz','rt'))
                    row['perturbed_lifecycle_analysis'] = analyze(p,trace)
                row['stage_counters'] = [{'index':s['index'],**s['dom']['value'],'heap':s['heap']['value']['usedSize']} for s in p['stages']]
                snapshot = folder/'slot/first-natural-major.heapsnapshot.gz'
                if not snapshot.exists():
                    raise ValueError('First natural major GC snapshot absent')
                row['graph'] = graph(json.load(gzip.open(snapshot,'rt')))
                row['snapshot_sha256'] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            except Exception as error:
                row['error'] = repr(error)
                result['errors'].append(f'Slot {index}: {error}')
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    except Exception as error:
        result['errors'].append(repr(error))
    result['status'] = 'diagnostic_failed' if result['errors'] else 'diagnostic_complete'
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    lines = ['# Natural-GC root diagnostic','',result['status'],'',
             'Perturbed root evidence only. No native/application qualification or memory acceptance.','']
    for row in result['cohorts']:
        lines.append(f"- Slot {row['index']} {row['mode']}: "+str(row.get('error',row.get('graph',{}).get('target_root_categories',{}))))
    lines.extend(['','No automatic calibration, retry, merge or deployment follows.'])
    summary = '\n'.join(lines)+'\n'
    (out/'SUMMARY.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:
            stream.write(summary)
    manifest = {str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(summary)
    return bool(result['errors'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--mode',choices=['control','probe'])
    args = parser.parse_args()
    raise SystemExit(capture(args.out.resolve(),args.mode) if args.capture else run(args.out.resolve()))
