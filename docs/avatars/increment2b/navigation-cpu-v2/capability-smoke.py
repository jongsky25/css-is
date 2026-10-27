import json,gzip,time,collections,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  i=int(self.path.strip("/") or "0");body=("<script>function smokeWork"+str(i)+"(){let t=performance.now();while(performance.now()-t<120){Math.sqrt(Math.random())}}smokeWork"+str(i)+"()</script>").encode();self.send_response(200);self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/workspace/scratch/chromium156-bin/chromium',args=['--no-sandbox'])
 page=b.new_page();s=b.new_browser_cdp_session();done=[];s.on('Tracing.tracingComplete',lambda e:done.append(e))
 s.send('Tracing.start',{'transferMode':'ReturnAsStream','traceConfig':{'excludedCategories':['*'],'includedCategories':['devtools.timeline','disabled-by-default-v8.cpu_profiler'],'recordMode':'recordUntilFull','traceBufferSizeInKb':65536}})
 for i in range(3):
  page.goto(f'http://127.0.0.1:{server.server_port}/{i}');page.wait_for_timeout(200)
 s.send('Tracing.end')
 while not done:page.wait_for_timeout(10)
 chunks=[];handle=done[0]['stream']
 while True:
  c=s.send('IO.read',{'handle':handle});chunks.append(c['data'])
  if c.get('eof'):break
 s.send('IO.close',{'handle':handle});b.close()
events=json.loads(''.join(chunks))['traceEvents']
with gzip.open('/workspace/scratch/cpu-trace-smoke.json.gz','wt') as f:json.dump({'completion':done[0],'traceEvents':events},f)
selected=[e for e in events if e.get('name') in ['Profile','ProfileChunk']]
print('completion',done[0],'counts',collections.Counter(e['name'] for e in selected))
for e in selected[:5]:print(json.dumps(e)[:1600])
print('smoke functions',sorted({n['callFrame']['functionName'] for e in selected for n in e.get('args',{}).get('data',{}).get('cpuProfile',{}).get('nodes',[]) if n['callFrame']['functionName'].startswith('smokeWork')}))
