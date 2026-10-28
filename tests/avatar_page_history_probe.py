"""Thread/page history instrument; no collection or allocator-dump APIs."""
import hashlib
from pathlib import Path
import time
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT/'scripts/avatar_baseline/native/page_history.js'


class PageHistory:
    def __init__(self, page, enabled):
        import frida  # Optional: only explicit native diagnostics instantiate this helper.
        self.session = None
        self.script = None
        self.messages = []
        self.metadata = {'enabled': enabled, 'frida_version': frida.__version__,
                         'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         'hook_sha256': hashlib.sha256(HOOK.read_bytes()).hexdigest()}
        cdp = page.context.browser.new_browser_cdp_session()
        done = []
        cdp.on('Tracing.tracingComplete', lambda e: done.append(e))
        begin = time.monotonic_ns()
        cdp.send('Tracing.start', {'transferMode':'ReturnAsStream','traceConfig':{
            'excludedCategories':['*'],'includedCategories':['devtools.timeline'],
            'recordMode':'recordUntilFull'}})
        page.evaluate("console.timeStamp('native-page-identity')")
        cdp.send('Tracing.end')
        deadline = time.monotonic()+15
        while not done:
            if time.monotonic()>deadline: raise TimeoutError('Renderer identity trace')
            page.wait_for_timeout(10)
        parts=[];handle=done[0]['stream']
        while True:
            chunk=cdp.send('IO.read',{'handle':handle});parts.append(chunk['data'])
            if chunk.get('eof'): break
        cdp.send('IO.close',{'handle':handle});cdp.detach()
        events=json.loads(''.join(parts))['traceEvents']
        markers=[e for e in events if e.get('name')=='TimeStamp' and
                 e.get('args',{}).get('data',{}).get('message')=='native-page-identity']
        if len(markers)!=1 or done[0].get('dataLossOccurred'):
            raise ValueError('Renderer identity ambiguity')
        notes=subprocess.check_output(['readelf','-n',f"/proc/{markers[0]['pid']}/exe"],text=True)
        if 'Build ID: 1c5dca8527a61d07372e489142bee26af1bcaf71' not in notes:
            raise ValueError('Unexpected renderer ELF build')
        self.metadata['build_id']='1c5dca8527a61d07372e489142bee26af1bcaf71'
        self.metadata.update(pid=markers[0]['pid'], identity_markers=markers,
                             setup_begin_ns=begin)
        if enabled:
            self.session=frida.attach(markers[0]['pid'])
            self.script=self.session.create_script(HOOK.read_text())
            self.script.on('message',lambda m,d:self.messages.append(m))
            self.script.load()
            if not any(m.get('payload',{}).get('ready') for m in self.messages):
                self.close();raise ValueError('Native hooks not ready')
        self.metadata['setup_end_ns']=time.monotonic_ns()

    def phase(self, name):
        if self.script: self.script.exports_sync.setphase(name)

    def finish(self):
        result = {**self.metadata, 'agent_messages': self.messages}
        if self.script: result['history'] = self.script.exports_sync.result()
        self.close()
        return result

    def close(self):
        try:
            if self.script: self.script.unload()
        finally:
            self.script=None
            if self.session: self.session.detach()
            self.session=None
