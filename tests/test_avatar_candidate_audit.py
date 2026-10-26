"""Raw candidate audit rejects source mismatches and retains every comparison."""
import hashlib
import json
from scripts.avatar_baseline import audit_lifecycle_candidate as auditor
from scripts.avatar_baseline.lifecycle_candidate import ORDER, read_cohort, compare
from tests.test_avatar_memory_audit import cohorts


def artifact(tmp_path,monkeypatch):
    refs={'1c964dc':'a'*40,'f700187':'b'*40,'candidate':'c'*40}
    def git(args,**kwargs):
        if args[1]=='rev-parse':return refs[args[2]]+'\n'
        if args[1]=='ls-tree':return ''
        if args[1]=='show':return args[2].encode()
        raise AssertionError(args)
    monkeypatch.setattr(auditor.subprocess,'check_output',git)
    old,_=cohorts(tmp_path);rows=json.loads((old/'False-warm.json').read_text())
    for r in rows:r.update(errors=[],cpu_rate=1)
    root=tmp_path/'artifact';root.mkdir()
    files=['templates/_avatars.html','templates/_avatars_art.html','templates/me.html','templates/_growth.html',
        'static/js/avatars.js','static/js/avatar-audio.js','static/js/search.js',
        'templates/office_connect.html','templates/dash_layout.html','tests/test_avatar_baseline_browser.py','tests/avatar_browser_fixture.py']
    sources={'original':'1c964dc','current':'f700187','candidate':'candidate'}
    report={'cohorts':[],'comparisons':[]}
    for i,arm in enumerate(ORDER):
        folder=root/f'{i}-{arm}';(folder/'application').mkdir(parents=True)
        raw=folder/'application/False-warm.json';raw.write_text(json.dumps(rows))
        env={key:'same' for key in ['platform','python','chromium','playwright','fixture_date_local','browser_date','random_seed','process_tree_cpu_affinity','requested_renderer_pin_cpu','proxy_compression']}
        env.update(source_commit=refs[sources[arm]],source_sha256={name:hashlib.sha256(((('candidate' if name.startswith('tests/') else sources[arm])+':'+name).encode())).hexdigest() for name in files})
        (folder/'application/environment.json').write_text(json.dumps(env))
        report['cohorts'].append({'index':i,'arm':arm,'exit_code':0,'source_commit':refs[sources[arm]],'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'points':read_cohort(folder)})
    for name,a,b in auditor.PAIRS:
        report['comparisons'].append({'name':name,'before_index':a,'after_index':b,**compare(report['cohorts'][a]['points'],report['cohorts'][b]['points'])})
    (root/'assessment.json').write_text(json.dumps(report))
    return root


def test_audit_all_pairs_without_mutating_later_comparisons(tmp_path,monkeypatch):
    result=auditor.audit(artifact(tmp_path,monkeypatch),'candidate')
    assert result['candidate_targeted_status']=='passed' and not result['errors']
    assert sum(len(c['records']) for c in result['comparisons'])==234
    assert result['source_hashes_verified']==66 and not result['release_ready']
    assert all('worst' in r['after'] for c in result['comparisons'] for r in c['records'])


def test_audit_rejects_source_hash_mismatch(tmp_path,monkeypatch):
    root=artifact(tmp_path,monkeypatch);path=root/'3-candidate/application/environment.json'
    data=json.loads(path.read_text());data['source_sha256']['static/js/avatars.js']='wrong';path.write_text(json.dumps(data))
    result=auditor.audit(root,'candidate')
    assert result['candidate_targeted_status']=='inconclusive'
    assert any('Source hash mismatch' in e.get('error','') for e in result['errors'])


def test_audit_rejects_summary_that_hides_raw_failure(tmp_path,monkeypatch):
    root=artifact(tmp_path,monkeypatch);path=root/'assessment.json'
    data=json.loads(path.read_text());data['comparisons'][1]['records'][0]['median_delta_bytes']=-100;path.write_text(json.dumps(data))
    result=auditor.audit(root,'candidate')
    assert result['candidate_targeted_status']=='inconclusive'
    assert any('Stored comparison disagrees' in e.get('error','') for e in result['errors'])
