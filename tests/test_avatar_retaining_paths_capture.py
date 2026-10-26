import gzip
import json
from tests.test_avatar_retaining_paths_browser import capture_snapshot


def test_forensic_capture_marks_gc_and_removes_listener(tmp_path):
    class CDP:
        def __init__(self):self.calls=[];self.callback=None
        def on(self,name,callback):self.callback=callback
        def remove_listener(self,name,callback):
            assert callback is self.callback
            self.callback=None
        def send(self,name,args=None):
            self.calls.append(name)
            if name=='HeapProfiler.takeHeapSnapshot':
                self.callback({'chunk':'{"snapshot":'})
                self.callback({'chunk':'{}}'})
                return {}
            return {'documents':2} if name=='Memory.getDOMCounters' else {'usedSize':1000}
    for name in ['False-warm.json','navigation-timing.json','navigation-trace.json.gz','timing-provenance.json']:
        (tmp_path/name).write_bytes(b'fixture')
    cdp=CDP();capture_snapshot(cdp,tmp_path)
    assert cdp.callback is None
    assert cdp.calls==['Memory.getDOMCounters','Runtime.getHeapUsage','HeapProfiler.takeHeapSnapshot','Memory.getDOMCounters','Runtime.getHeapUsage']
    assert json.load(gzip.open(tmp_path/'post-workload.heapsnapshot.json.gz','rt'))=={'snapshot':{}}
    provenance=json.loads((tmp_path/'forensic-provenance.json').read_text())
    assert provenance['intentional_forced_gc'] and provenance['acceptance'] is False


def test_runner_requires_explicit_opt_in(tmp_path, monkeypatch):
    import subprocess
    import sys
    monkeypatch.delenv('CSS_AVATAR_FORENSIC_GC',raising=False)
    out=tmp_path/'never-created'
    run=subprocess.run([sys.executable,'scripts/avatar_baseline/run_retaining_paths.py',
        '--output',str(out),'--browser-dir','/usr/bin'],capture_output=True,text=True)
    assert run.returncode!=0 and 'Not authorized' in run.stderr
    assert not out.exists()


def test_adapter_saves_natural_rows_before_context_close():
    from pathlib import Path
    from scripts.avatar_baseline.run_retaining_paths import adapt_fixture
    name='tests/test_avatar_baseline_browser.py'
    adapted=adapt_fixture(name,Path(name).read_bytes())
    assert b"rows.append(json.loads(json.dumps(row))); (out/f'{mobile}-{cache}.json').write_text(json.dumps(rows,indent=2)); context.close()" in adapted
    assert b'rows.append(row);context.close()' not in adapted
