"""Private, disposable Hugging Face preview. Never use as a production entrypoint."""
import ipaddress
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def block_external_connections():
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def allowed(sock, address):
        if sock.family == socket.AF_UNIX:
            return True
        try:
            return ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            return address[0] == 'localhost'

    def connect(sock, address):
        if not allowed(sock, address):
            raise OSError('Outbound network connections are disabled in preview')
        return original(sock, address)

    def connect_ex(sock, address):
        if not allowed(sock, address):
            raise OSError('Outbound network connections are disabled in preview')
        return original_ex(sock, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


def main():
    password = os.environ.get('OFFICE_PREVIEW_PASSWORD', '')
    if len(password) < 16:
        raise SystemExit('Set a private OFFICE_PREVIEW_PASSWORD secret of at least 16 characters.')
    host = os.environ.get('SPACE_HOST', '')
    # Preserve only infrastructure settings, excluding production integrations.
    keep = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}
    kept = {k: v for k, v in os.environ.items() if k in keep}
    os.environ.clear()
    os.environ.update(kept)
    os.chdir(ROOT)
    with tempfile.TemporaryDirectory(prefix='office-preview-') as directory:
        database = str(Path(directory) / 'preview.db')
        with sqlite3.connect(database) as connection:
            connection.execute('PRAGMA user_version=0')
        os.environ.update(CSS_DB=database, CSS_NO_SCHEDULER='1',
                          CSS_SESSION_SECRET=secrets.token_urlsafe(48))
        if host:
            os.environ['CSS_BASE_URL'] = 'https://' + host
        block_external_connections()
        import storage as st
        import auth
        conn = st.connect(database)
        st.init_db(conn)
        hashed, salt = auth.hash_password(password)
        uid = st.create_admin_user(conn, 'preview@example.invalid', hashed, salt,
                                   'admin', created_by='synthetic preview')
        st.mark_onboarded(conn, uid)
        st.get_or_create_blhsd(conn)
        conn.close()
        del password
        import app
        import uvicorn
        from starlette.responses import Response

        class PreviewLabel:
            def __init__(self, application):
                self.application = application

            async def __call__(self, scope, receive, send):
                if scope['type'] == 'http' and scope['path'] == '/preview-health':
                    return await Response('Office Connect preview ready')(scope, receive, send)

                async def labeled(message):
                    if message['type'] == 'http.response.start':
                        message.setdefault('headers', []).extend([
                            (b'x-office-connect-environment', b'preview'),
                            (b'x-robots-tag', b'noindex, nofollow, noarchive')])
                    await send(message)
                await self.application(scope, receive, labeled)

        # asyncio uses the guarded socket API; do not select uvloop here.
        uvicorn.run(PreviewLabel(app.app), host='0.0.0.0', port=7860,
                    loop='asyncio', proxy_headers=True)


if __name__ == '__main__':
    main()
