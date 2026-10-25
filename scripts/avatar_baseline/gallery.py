"""Local-only actual-macro fixtures. No app import, database, or production route."""
import ast
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
# Read the actual catalog without importing storage (which initializes app dependencies).
TREE = ast.parse((ROOT / 'storage.py').read_text())
CATALOG = next(ast.literal_eval(n.value) for n in TREE.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'AVATAR_CATALOG' for t in n.targets))

def render(scene='gallery', theme='light', outfit='default', month=0):
    env = Environment(loader=FileSystemLoader(ROOT / 'templates'), autoescape=True,
                      undefined=StrictUndefined)
    families = {a['key']: a['family'] for a in CATALOG}
    env.globals.update(avatar_family=lambda k: families.get(k, 'plant'),
                       avatar_is_swimmer=lambda k: k in {'fish', 'dolphin'},
                       avatar_care_verb=lambda k: 'water' if families[k] == 'plant' else 'feed',
                       avatar_month=lambda: month, avatar_outfit=lambda: outfit)
    macro = env.get_template('_avatars.html').module
    cards = []
    for item in CATALOG if scene != 'home' else [CATALOG[7]]:
        for stage in range(1, 7) if scene in {'gallery', 'sheet'} else [4]:
            for mood in ['happy', 'okay', 'droopy'] if scene == 'gallery' else ['okay']:
                art = macro.avatar(item['key'], stage, name='Synthetic companion' if scene != 'sheet' else '', size=64 if scene == 'sheet' else 170,
                                   interactive=scene == 'home', mood=mood, care=scene == 'home',
                                   drag=scene == 'home', drag_key='baseline', chase=True)
                cards.append(f'<article><p>{item["label"]} · {stage} · {mood}</p>{art}</article>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Avatar baseline</title>'
            '<style>body{font:16px system-ui;margin:24px;--accent:#547bb5;background:'
            + ('#162032;color:#f2f4fa' if theme == 'dark' else ('#fff;color:#000' if theme == 'contrast' else '#f4f6fa;color:#182236'))
            + '}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:24px}'
            'article{padding:20px;border:1px solid #8886;border-radius:16px} .av-play{min-height:450px}'
            + ('main{grid-template-columns:repeat(6,1fr)}article{padding:6px}article p{font-size:12px;margin:4px}' if scene == 'sheet' else '')
            + '</style>' + str(macro.avatar_defs()) + '<h1>Local synthetic avatar fixture</h1>'
            '<main class="av-play">' + ''.join(cards) + '</main></html>')

if __name__ == '__main__':
    import argparse
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs
    p = argparse.ArgumentParser(); p.add_argument('--port', type=int, default=8765); args = p.parse_args()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path); q = parse_qs(u.query)
            if u.path.startswith('/static/'):
                path = (ROOT / u.path.lstrip('/')).resolve()
                if not path.is_relative_to(ROOT / 'static') or not path.is_file():
                    self.send_error(404); return
                body = path.read_bytes(); mime = 'text/javascript' if path.suffix == '.js' else 'application/octet-stream'
            else:
                body = render(**{k: v[0] for k,v in q.items() if k in {'scene','theme','outfit'}},
                              month=int(q.get('month', ['0'])[0])).encode(); mime = 'text/html'
            self.send_response(200); self.send_header('Content-Type', mime); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    print(f'Gallery: http://127.0.0.1:{args.port}', flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
