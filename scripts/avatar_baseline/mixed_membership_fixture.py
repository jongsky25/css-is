"""Byte-identical legacy DOM/SVG/style documents with a declared receiver sample."""
from http.server import BaseHTTPRequestHandler
import json
import time

MODES = ['dom', 'svg', 'style']
SCHEDULE = MODES * 4
COUNT = 3000
SAMPLE = 32


def document(mode):
    if mode == 'dom':
        body='<main>'+''.join(f'<div class="n{i}"><span>row {i}</span></div>' for i in range(COUNT))+'</main>'
    elif mode == 'svg':
        body='<svg width="400" height="400">'+''.join(f'<path d="M{i%400} 0L200 300" stroke="blue"/>' for i in range(COUNT))+'</svg>'
    elif mode == 'style':
        body='<style>'+''.join(f'.n{i}{{color:rgb({i%255},20,30);padding:{i%10}px}}' for i in range(COUNT))+'</style>'
        body+=''.join(f'<div class="n{i}">row {i}</div>' for i in range(COUNT))
    else:
        body='<p>Empty control</p>'
    return ('<!doctype html><html><head><link rel="icon" href="data:,"></head><body>'+body+'</body></html>').encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        path=self.path.split('?',1)[0]
        mode=SCHEDULE[int(path.rsplit('/',1)[1])] if path.startswith('/fixture/') else 'empty'
        data=document(mode)
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        if self.path!='/lifecycle':self.send_error(404);return
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=256:self.send_error(400);return
        data=json.loads(self.rfile.read(length))
        if set(data)!={'index','persisted'} or type(data['index']) is not int or type(data['persisted']) is not bool:
            self.send_error(400);return
        self.server.lifecycle_events.append({**data,'received_ns':time.monotonic_ns()})
        self.send_response(204);self.send_header('Content-Length','0');self.end_headers()


# Group names remain diagnostic labels, not claims about production components.
SELECT_JS = '''const selectMembership = (mode, group, count) => {
    const selector = mode === 'dom' ? (group === 'avatar' ? 'main > div' : 'main > div > span')
                   : mode === 'svg' ? 'svg > path' : 'body > div';
    const pool = [...document.querySelectorAll(selector)];
    const nodes = mode === 'dom' || group === 'other' ? pool.slice(-count) : pool.slice(-2*count, -count);
    return {nodes, fixture_count: pool.length};
};'''


def tag(mode,group):
    return ('div' if group=='avatar' else 'span') if mode=='dom' else 'path' if mode=='svg' else 'div'
