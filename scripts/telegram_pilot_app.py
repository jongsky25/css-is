"""Disposable synthetic Telegram pilot; never a production entrypoint."""
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TARGET_HOST = 'equityinhealth-office-connect-telegram-pilot.hf.space'
WEBHOOK = '/integrations/telegram/webhook'
ALIASES = ('staff', 'officer', 'peer', 'admin')
BASE = ('inbound', 'delivery', 'link')
BATCHES = {
    'off': (),
    'A': ('calendar_read',),
    'B': ('calendar_read', 'calendar_create', 'calendar_reschedule', 'calendar_cancel',
          'rooms_read', 'rooms_request', 'rooms_withdraw', 'rooms_move'),
    'C': ('work_read', 'tasks_acknowledge', 'tasks_submit', 'tasks_create', 'tasks_deadline',
          'tasks_accept', 'tasks_return', 'tasks_assign', 'tasks_reassign', 'tasks_reopen',
          'tasks_cancel', 'tasks_block', 'tasks_unblock', 'tasks_dependency_add',
          'tasks_dependency_remove', 'tasks_review_read', 'tasks_blockers_read'),
    'D': ('work_read', 'work_comment', 'tasks_comment', 'work_reply', 'tasks_reply',
          'work_comment_edit', 'tasks_comment_edit', 'work_mentions', 'work_updates_read',
          'work_updates_acknowledge', 'work_follow', 'work_follows_read',
          'work_discussion_search', 'work_discussion_read'),
    'E': ('supplies_read', 'supplies_draft', 'supplies_submit'),
    'F': ('documents_read', 'travel_read', 'meals_read', 'arrangements_read',
          'supplies_read', 'work_read', 'calendar_read', 'rooms_read'),
}


def configuration(env):
    """Validate without echoing any supplied value, including on errors."""
    try:
        passwords = json.loads(env.get('OFFICE_TELEGRAM_PILOT_PASSWORDS', ''))
        senders = json.loads(env.get('OFFICE_TELEGRAM_PILOT_SENDERS', ''))
        token = env.get('CSS_TELEGRAM_BOT_TOKEN', '')
        secret = env.get('CSS_TELEGRAM_WEBHOOK_SECRET', '')
        session = env.get('CSS_SESSION_SECRET', '')
        batch = env.get('OFFICE_TELEGRAM_PILOT_BATCH', 'off')
        host = env.get('SPACE_HOST', TARGET_HOST)
        if (not isinstance(passwords, dict) or set(passwords) != set(ALIASES)
                or any(not isinstance(p, str) or not 16 <= len(p) <= 128 for p in passwords.values())
                or len(set(passwords.values())) != 4):
            raise ValueError()
        if (not isinstance(senders, list) or not 1 <= len(senders) <= 2
                or any(type(x) is not int or not 0 < x < 2**63 for x in senders)
                or len(set(senders)) != len(senders)):
            raise ValueError()
        if (not re.fullmatch(r'[1-9][0-9]{4,19}:[A-Za-z0-9_-]{20,128}', token)
                or int(token.split(':', 1)[0]) >= 2**63
                or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret)
                or not 32 <= len(session) <= 256 or batch not in BATCHES
                or host != TARGET_HOST):
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ValueError('Pilot configuration missing or invalid; check the documented secret names.') from None
    return {'passwords': passwords, 'senders': frozenset(senders), 'token': token,
            'webhook_secret': secret, 'session_secret': session, 'batch': batch}


def isolate(config, database):
    keep = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}
    infrastructure = {k: v for k, v in os.environ.items() if k in keep}
    os.environ.clear()
    os.environ.update(infrastructure)
    os.environ.update(CSS_DB=str(database), CSS_NO_SCHEDULER='1',
                      CSS_SESSION_SECRET=config['session_secret'],
                      CSS_BASE_URL='https://' + TARGET_HOST,
                      CSS_TELEGRAM_BOT_TOKEN=config['token'],
                      CSS_TELEGRAM_WEBHOOK_SECRET=config['webhook_secret'],
                      CSS_TELEGRAM_REPLY_TRANSPORT='webhook', CSS_APPRISE_TELEGRAM_ENABLED='0')
    from telegram_storage import SWITCHES
    active = set(BASE + BATCHES[config['batch']]) if config['batch'] != 'off' else set()
    for name in SWITCHES:
        os.environ['CSS_TELEGRAM_' + name.upper() + '_ENABLED'] = '1' if name in active else '0'


class PilotBoundary:
    """Authenticate and bound provider intake before any application processing."""
    def __init__(self, application, config, manifest, *, started=None):
        self.application = application
        self.config = config
        self.started = int(time.time()) if started is None else started
        self.health = {'environment': 'telegram-pilot', 'source_commit': manifest['source_commit'],
                       'version': manifest['version'], 'batch': config['batch'],
                       'boot_id': secrets.token_hex(16), 'started_at_unix': self.started,
                       'disposable': True, 'scheduler_enabled': False}

    async def __call__(self, scope, receive, send):
        from starlette.responses import JSONResponse
        if scope['type'] != 'http':
            return await self.application(scope, receive, send)
        headers = {'Cache-Control': 'no-store', 'X-Office-Connect-Environment': 'telegram-pilot',
                   'X-Robots-Tag': 'noindex, nofollow, noarchive'}
        async def reply(status, body):
            await JSONResponse(body, status_code=status, headers=headers)(scope, receive, send)
        path = scope['path']
        if path == '/pilot-health' and scope['method'] == 'GET':
            return await reply(200, self.health)
        if path == WEBHOOK:
            if self.config['batch'] == 'off':
                return await reply(503, {'error': 'paused'})
            supplied = [v for k, v in scope['headers'] if k.lower() == b'x-telegram-bot-api-secret-token']
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0], self.config['webhook_secret'].encode()):
                return await reply(403, {'error': 'forbidden'})
            if scope['method'] != 'POST':
                return await reply(405, {'error': 'method'})
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > 65536:
                    return await reply(413, {'error': 'too_large'})
                if not message.get('more_body', False):
                    break
            try:
                packet = json.loads(body)
                msg = packet['message']
                sender, chat = msg['from'], msg['chat']
                sid = sender['id']
                if (type(sid) is not int or sid not in self.config['senders']
                        or type(chat['id']) is not int or chat['id'] != sid
                        or chat['type'] != 'private' or sender.get('is_bot') is not False
                        or 'message_thread_id' in msg or 'callback_query' in packet):
                    return await reply(403, {'error': 'forbidden'})
                # A reset must not execute an old retry against an empty dedupe ledger.
                if type(msg['date']) is not int or not self.started < msg['date'] <= int(time.time()) + 300:
                    return await reply(200, {'ok': True})
            except (KeyError, TypeError, ValueError, RecursionError):
                return await reply(400, {'error': 'invalid_input'})
            original_receive = receive
            sent = False
            async def replay():
                nonlocal sent
                if sent:
                    return await original_receive()
                sent = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            receive = replay
        async def labeled(message):
            if message['type'] == 'http.response.start':
                current = message.setdefault('headers', [])
                current.extend((k.lower().encode(), v.encode()) for k, v in headers.items())
            await send(message)
        return await self.application(scope, receive, labeled)


def main():
    try:
        config = configuration(os.environ)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    manifest = json.loads((ROOT / 'pilot-build.json').read_text())
    if manifest.get('environment') != 'telegram-pilot':
        raise SystemExit('Pilot build manifest required.')
    os.chdir(ROOT)
    with tempfile.TemporaryDirectory(prefix='office-telegram-pilot-') as directory:
        database = Path(directory) / 'pilot.db'
        with sqlite3.connect(database) as conn:
            conn.execute('PRAGMA user_version=0')
        isolate(config, database)
        from scripts.preview_app import block_external_connections
        block_external_connections()
        from scripts.telegram_pilot_seed import seed
        fixtures = seed(database, config['passwords'])
        del config['passwords']
        import app
        import uvicorn
        from fastapi import Request
        from starlette.responses import HTMLResponse, RedirectResponse
        import html

        @app.app.get('/pilot-fixtures', response_class=HTMLResponse)
        def fixture_index(request: Request):
            if not getattr(request.state, 'user', None):
                return RedirectResponse('/login?next=/pilot-fixtures', status_code=303)
            return HTMLResponse('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Telegram pilot fixtures</title></head><body><h1>TELEGRAM PILOT</h1>'
                '<p>Synthetic records only. IDs, records and sessions reset on every restart. '
                'Use source screens to inspect current state. Restricted/foreign IDs are denial fixtures.</p>'
                '<p><a href="/">Home</a> · <a href="/account/telegram">Telegram consent</a></p>'
                '<pre style="white-space:pre-wrap;overflow-wrap:anywhere">' + html.escape(json.dumps(fixtures, indent=2)) + '</pre></body></html>')

        uvicorn.run(PilotBoundary(app.app, config, manifest), host='0.0.0.0', port=7860,
                    loop='asyncio', proxy_headers=True, access_log=False)


if __name__ == '__main__':
    main()
