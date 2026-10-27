"""Exact native receiver cross-check; no performance or application acceptance."""
import argparse
from collections import defaultdict
import gzip
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
from playwright.sync_api import sync_playwright
from tests import avatar_page_history_probe as helper
from scripts.avatar_baseline.element_membership_lifecycle import BROWSER, Handler

HOOK = Path(__file__).resolve().parent/'native/absent_attribute_membership.js'
SOURCES = ['scripts/avatar_baseline/absent_attribute_capability.py',
           'scripts/avatar_baseline/native/absent_attribute_membership.js', 'tests/avatar_page_history_probe.py']
NAMESPACE = 'urn:css-is:membership:absent'
LOCAL_NAME = 'absent'


def validate_receivers(capture, document_index=0, fixture_count=4096):
    if capture.get('error'): raise ValueError(capture['error'])
    if capture['dom_before_sha256'] != capture['dom_after_sha256']: raise ValueError('DOM changed')
    native = capture['native']; history = native['history']
    if native['build_id']!='1c5dca8527a61d07372e489142bee26af1bcaf71' or native['frida_version']!='17.5.1':
        raise ValueError('Wrong native build/version')
    markers=native['identity_markers']
    ready=[m['payload'] for m in native['agent_messages'] if m.get('payload',{}).get('ready')]
    if len(markers)!=1 or markers[0]['pid']!=native['pid'] or len(ready)!=1 or ready[0]['pid']!=native['pid']:
        raise ValueError('Native receiver process identity mismatch')
    if history['dropped'] or any(m.get('type')=='error' for m in native['agent_messages']):
        raise ValueError('Dropped native record or agent error')
    if history['offsets']['receiver'] != 0x100cce80 or history['offsets']['reference'] != 0x100b1880:
        raise ValueError('Wrong receiver offsets')
    groups = defaultdict(list)
    for e in history['events']:
        if e['kind'] in ['receiver','reference']:
            if not 0 < e['begin_ns'] <= e['callback_ready_ns'] <= e['returned_ns']:
                raise ValueError('Invalid native bracket')
            groups[e['phase']].append(e)
    expected = {f'{prefix}:{document_index}:{group}:{repeat}' for prefix in ['census','reference'] for group in ['avatar','other'] for repeat in [0,1]}
    if set(groups) != expected: raise ValueError('Missing or additional receiver phases')
    seen = {}
    for group in ['avatar','other']:
        for repeat in [0,1]:
            actual = groups[f'census:{document_index}:{group}:{repeat}']; reference = groups[f'reference:{document_index}:{group}:{repeat}']
            if len(actual)!=32 or len(reference)!=32: raise ValueError('Receiver count mismatch')
            addresses=[e['address'] for e in actual]
            if len(set(addresses))!=32 or addresses != [e['address'] for e in reference]:
                raise ValueError('Getter/geometry receiver identities differ')
            if any(e.get('attribute_absent') is not True for e in actual): raise ValueError('Getter did not return null')
            seen[(group,repeat)] = addresses
        if seen[(group,0)] != seen[(group,1)]: raise ValueError('Repeat identities differ')
    if set(seen[('avatar',0)]) & set(seen[('other',0)]): raise ValueError('Disjoint groups overlap')
    if len(capture['queries'])!=8: raise ValueError('Incomplete known query schedule')
    for q in capture['queries']:
        if q['result']['fixture_count']!=fixture_count or q['result']['count']!=32 or q['result']['values'] != [1]*32:
            raise ValueError('Known JS query result mismatch')
        for e in groups[q['phase']]:
            if not q['begin_ns'] <= e['begin_ns'] <= e['returned_ns'] <= q['end_ns']:
                raise ValueError('Receiver outside known query')
    return {'status':'capability_passed','receiver_records':128,'reference_records':128,
            'receiver_identities_match':True,'null_native_returns':128,'dom_unchanged':True,
            'acceptance':False,'performance_qualified':False}


def audit(root,repo,ref):
    p=json.load(gzip.open(root/'capture.json.gz','rt'))
    if p['harness_commit']!=ref: raise ValueError('Capability source changed')
    for name,digest in p['source_sha256'].items():
        raw=subprocess.check_output(['git','show',ref+':'+name],cwd=repo)
        if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Capability source hash mismatch')
    if set(p['source_sha256'])!=set(SOURCES): raise ValueError('Incomplete capability source inventory')
    if p['native']['helper_sha256']!=p['source_sha256'][SOURCES[2]] or p['native']['hook_sha256']!=p['source_sha256'][SOURCES[1]]:
        raise ValueError('Runtime helper/hook mismatch')
    return {**validate_receivers(p),'harness_commit':ref,'source_hashes_verified':3,
            'capture_sha256':hashlib.sha256((root/'capture.json.gz').read_bytes()).hexdigest()}


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    source_hashes={}
    for name in SOURCES:
        raw=(repo/name).read_bytes()
        if raw != subprocess.check_output(['git','show',head+':'+name],cwd=repo): raise ValueError('Uncommitted capability')
        source_hashes[name]=hashlib.sha256(raw).hexdigest()
    result={'harness_commit':head,'acceptance':False,'source_sha256':source_hashes,'queries':[]}
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.lifecycle_events=[]
    threading.Thread(target=server.serve_forever,daemon=True).start();probe=None;old_hook=helper.HOOK
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(BROWSER),args=['--no-sandbox'])
            if browser.version!='156.0.8078.47': raise ValueError('Wrong browser version')
            page=browser.new_page();origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/empty');helper.HOOK=HOOK;probe=helper.PageHistory(page,True)
            probe.script.exports_sync.enablereference()
            probe.phase('navigation:0');page.goto(origin+'/fixture/0');page.wait_for_timeout(220)
            before=page.evaluate('document.documentElement.outerHTML')
            import time
            for group in ['avatar','other']:
                for repeat in [0,1]:
                    for kind in ['reference','census']:
                        phase=f'{kind}:0:{group}:{repeat}';q={'phase':phase,'begin_ns':time.monotonic_ns()};result['queries'].append(q)
                        probe.phase(phase)
                        q['result']=page.evaluate('''({group,kind,ns,name}) => {
                            let nodes=[...document.querySelectorAll('[data-group="'+group+'"]')];
                            const fixture_count=nodes.length;
                            nodes=group==='avatar'?nodes.slice(-32):nodes.slice(0,32);
                            return {fixture_count,count:nodes.length,values:nodes.map(node=>
                              kind==='reference'?Number(node.getClientRects().length===1):Number(node.getAttributeNodeNS(ns,name)===null))};
                        }''',{'group':group,'kind':kind,'ns':NAMESPACE,'name':LOCAL_NAME})
                        probe.phase('between');q['end_ns']=time.monotonic_ns()
            after=page.evaluate('document.documentElement.outerHTML')
            result['dom_before_sha256']=hashlib.sha256(before.encode()).hexdigest()
            result['dom_after_sha256']=hashlib.sha256(after.encode()).hexdigest()
            result['native']=probe.finish();probe=None;browser.close()
    except Exception as error: result['error']=repr(error)
    finally:
        if probe:
            result['native']=probe.finish()
        helper.HOOK=old_hook;server.shutdown();server.server_close()
        with gzip.open(out/'capture.json.gz','wt') as f:json.dump(result,f)
    try: assessment=audit(out,repo,head)
    except (ValueError,KeyError,TypeError,OSError) as error:
        assessment={'acceptance':False,'status':'capability_failed','error':repr(error),'harness_commit':head}
    (out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
    print(json.dumps(assessment));return assessment['status']!='capability_passed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();raise SystemExit(run(a.out))
