"""One read-only check of frozen CModule-owned record storage; no live hooks."""
import hashlib,json,subprocess,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
import frida
from playwright.sync_api import sync_playwright
from tests import avatar_page_history_probe as helper
from scripts.avatar_baseline.mixed_membership_fixture import Handler
ref='6e7a8f1c28b3140988f264134eb433b4e784fa19'
agent=subprocess.check_output(['git','show',ref+':scripts/avatar_baseline/native/callback_buffer.js'],text=True)
tail='\nrpc.exports.storageinfo=()=>({record_size:size(),record_storage:Process.findRangeByAddress(buffer())});\n'
result={'acceptance':False,'harness_commit':ref,'agent_sha256':hashlib.sha256(agent.encode()).hexdigest(),
        'inspection_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'messages':[]}
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.lifecycle_events=[]
threading.Thread(target=server.serve_forever,daemon=True).start();session=None
try:
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/workspace/scratch/avatar-runtime/root/usr/lib/chromium/chromium',args=['--no-sandbox'])
        assert browser.version=='156.0.8078.47'
        page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/empty')
        identity=helper.PageHistory(page,False);result['identity']=identity.finish()
        session=frida.attach(result['identity']['pid'])
        script=session.create_script('globalThis.RECORDER_SELF_TEST_ONLY=true;\n'+agent+tail)
        script.on('message',lambda m,d:result['messages'].append(m));script.load()
        result['storage']=script.exports_sync.storageinfo()
        script.unload();session.detach();session=None;browser.close()
except Exception as e:result['error']=repr(e)
finally:
    if session:
        try:session.detach()
        except Exception:pass
    server.shutdown();server.server_close()
Path('docs/avatars/increment2b/native-callback-recorder/storage-inspection.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result.get('storage',{'error':result.get('error')})))
