"""Exact HTML/SVG receiver capability on the retained mixed fixture."""
import argparse
from copy import deepcopy
import gzip
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time
from playwright.sync_api import sync_playwright
from tests import avatar_page_history_probe as helper
from scripts.avatar_baseline.absent_attribute_capability import validate_receivers
from scripts.avatar_baseline.mixed_membership_fixture import Handler, MODES, SELECT_JS, tag

BROWSER=Path('/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium')
HOOK=Path(__file__).resolve().parent/'native/absent_attribute_membership.js'
SOURCES=['scripts/avatar_baseline/mixed_getter_capability.py',
         'scripts/avatar_baseline/mixed_membership_fixture.py',
         'scripts/avatar_baseline/absent_attribute_capability.py',
         'scripts/avatar_baseline/native/absent_attribute_membership.js',
         'tests/avatar_page_history_probe.py']


def validate(capture):
    if capture.get('error'):raise ValueError(capture['error'])
    if [d['mode'] for d in capture['documents']]!=MODES or [d['index'] for d in capture['documents']]!=[0,1,2]:
        raise ValueError('Incomplete mixed capability schedule')
    expected={f'{prefix}:{i}:{group}:{repeat}' for prefix in ['reference','census'] for i in range(3) for group in ['avatar','other'] for repeat in [0,1]}
    actual={e['phase'] for e in capture['native']['history']['events'] if e['kind'] in ['receiver','reference']}
    if actual!=expected:raise ValueError('Extra/missing mixed capability receiver phase')
    checks=[]
    for d in capture['documents']:
        i=d['index'];native=deepcopy(capture['native'])
        native['history']['events']=[e for e in native['history']['events'] if e['kind'] not in ['receiver','reference'] or e['phase'].split(':')[1]==str(i)]
        result=validate_receivers({**d,'native':native},document_index=i,fixture_count=3000)
        for q in d['queries']:
            group=q['phase'].split(':')[2]
            if q['result']['tags']!=[tag(d['mode'],group)]*32:raise ValueError('Wrong selected element types')
        checks.append({'index':i,'mode':d['mode'],'dom_sha256':d['dom_before_sha256'],**result})
    return {'status':'capability_passed','acceptance':False,'performance_qualified':False,
            'receiver_records':384,'reference_records':384,'native_null_returns':384,'documents':checks}


def audit(root,repo,ref):
    p=json.load(gzip.open(root/'capture.json.gz','rt'))
    if p['harness_commit']!=ref or set(p['source_sha256'])!=set(SOURCES):raise ValueError('Capability source inventory mismatch')
    for name,sha in p['source_sha256'].items():
        if hashlib.sha256(subprocess.check_output(['git','show',ref+':'+name],cwd=repo)).hexdigest()!=sha:raise ValueError('Capability source mismatch')
    if p['native']['helper_sha256']!=p['source_sha256'][SOURCES[-1]] or p['native']['hook_sha256']!=p['source_sha256'][SOURCES[-2]]:
        raise ValueError('Runtime capability source mismatch')
    return {**validate(p),'harness_commit':ref,'source_hashes_verified':len(SOURCES),
            'capture_sha256':hashlib.sha256((root/'capture.json.gz').read_bytes()).hexdigest()}


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    hashes={}
    for name in SOURCES:
        raw=(repo/name).read_bytes()
        if raw!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Uncommitted capability source')
        hashes[name]=hashlib.sha256(raw).hexdigest()
    result={'harness_commit':ref,'acceptance':False,'source_sha256':hashes,'documents':[]}
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.lifecycle_events=[]
    threading.Thread(target=server.serve_forever,daemon=True).start();old_hook=helper.HOOK;probe=None
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(BROWSER),args=['--no-sandbox'])
            if browser.version!='156.0.8078.47':raise ValueError('Wrong browser version')
            page=browser.new_page();origin=f'http://127.0.0.1:{server.server_port}'
            page.goto(origin+'/empty');helper.HOOK=HOOK;probe=helper.PageHistory(page,True);probe.script.exports_sync.enablereference()
            for index,mode in enumerate(MODES):
                d={'index':index,'mode':mode,'queries':[]};result['documents'].append(d)
                probe.phase(f'navigation:{index}');page.goto(origin+f'/fixture/{index}');page.wait_for_timeout(220)
                before=page.evaluate('document.documentElement.outerHTML')
                for group in ['avatar','other']:
                    for repeat in [0,1]:
                        for kind in ['reference','census']:
                            phase=f'{kind}:{index}:{group}:{repeat}';q={'phase':phase,'begin_ns':time.monotonic_ns()};d['queries'].append(q)
                            probe.phase(phase)
                            q['result']=page.evaluate('''({mode,group,kind}) => {'''+SELECT_JS+'''
                                const {nodes,fixture_count}=selectMembership(mode,group,32);
                                return {fixture_count,count:nodes.length,tags:nodes.map(n=>n.localName),
                                  values:nodes.map(n=>kind==='reference'?Number(n.getClientRects().length===1):
                                   Number(n.getAttributeNodeNS('urn:css-is:membership:absent','absent')===null))};
                            }''',{'mode':mode,'group':group,'kind':kind})
                            probe.phase('between');q['end_ns']=time.monotonic_ns()
                after=page.evaluate('document.documentElement.outerHTML')
                d['dom_before_sha256']=hashlib.sha256(before.encode()).hexdigest();d['dom_after_sha256']=hashlib.sha256(after.encode()).hexdigest()
            result['native']=probe.finish();probe=None;browser.close()
    except Exception as e:result['error']=repr(e)
    finally:
        if probe:result['native']=probe.finish()
        helper.HOOK=old_hook;server.shutdown();server.server_close()
        with gzip.open(out/'capture.json.gz','wt') as f:json.dump(result,f)
    try:assessment=audit(out,repo,ref)
    except (ValueError,KeyError,TypeError,OSError) as e:assessment={'status':'capability_failed','acceptance':False,'error':repr(e),'harness_commit':ref}
    (out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n');print(json.dumps(assessment))
    return assessment['status']!='capability_passed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();raise SystemExit(run(a.out))
