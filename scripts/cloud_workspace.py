"""Isolated cloud commands: doctor, test [pytest arguments], serve [uvicorn arguments]."""
from pathlib import Path
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit('Run with .venv/bin/python (Python 3.11 required).')
    command = sys.argv[1] if len(sys.argv) > 1 else 'doctor'
    if command not in {'doctor', 'test', 'serve'}:
        raise SystemExit('Usage: cloud_workspace.py doctor|test|serve [arguments]')
    # Allowlist infrastructure variables; do not inherit app/provider credentials,
    # persistence paths, or deployment configuration from the parent session.
    allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT',
               'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
               'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
               'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE',
               'CURL_CA_BUNDLE', 'NODE_EXTRA_CA_CERTS', 'PLAYWRIGHT_BROWSERS_PATH'}
    env = {k: v for k, v in os.environ.items() if k in allowed}
    with tempfile.TemporaryDirectory(prefix='office-cloud-') as directory:
        # Existing empty SQLite file prevents app._ensure_live_db from copying
        # any local css_is.db seed into this isolated development instance.
        database = Path(directory) / 'development.db'
        with sqlite3.connect(database) as connection:
            connection.execute('PRAGMA user_version=0')
        env.update(CSS_DB=str(database),
                   CSS_NO_SCHEDULER='1', CSS_SESSION_SECRET=secrets.token_urlsafe(48),
                   CSS_TEST_NOW='2026-10-20T06:00:00',
                   PYTHONPYCACHEPREFIX=str(Path(directory) / 'pycache'))
        if command == 'doctor':
            commands = [
                [sys.executable, '-m', 'pip', 'check'],
                ['node', '-e', 'if(process.versions.node.split(".")[0]!=="24") process.exit(1)'],
                ['tesseract', '--list-langs'],
                [sys.executable, '-c', 'from playwright.sync_api import sync_playwright; '
                 'p=sync_playwright().start(); b=p.chromium.launch(args=["--no-sandbox"]); '
                 'page=b.new_page(); page.set_content("<title>Office cloud ready</title>"); '
                 'assert page.title()=="Office cloud ready"; b.close(); p.stop()'],
            ]
        elif command == 'test':
            commands = [[sys.executable, '-m', 'pytest', *sys.argv[2:]]]
        else:
            # Explicit local-only default; phone access belongs to the staging step.
            commands = [[sys.executable, '-m', 'uvicorn', 'app:app',
                         '--host', '127.0.0.1', '--port', '8000', *sys.argv[2:]]]
        for args in commands:
            if args[0] == 'tesseract':
                result = subprocess.run(args, cwd=ROOT, env=env, check=True,
                                        capture_output=True, text=True)
                if 'eng' not in result.stdout.splitlines():
                    raise SystemExit('Tesseract English language data is missing.')
            else:
                subprocess.run(args, cwd=ROOT, env=env, check=True)
    print('Cloud command completed successfully.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
