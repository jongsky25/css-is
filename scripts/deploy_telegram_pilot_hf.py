"""Dry-run by default; publish only the isolated protected Telegram pilot."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'equityinhealth/office-connect-telegram-pilot'
REQUIRED_SECRETS = {'OFFICE_TELEGRAM_PILOT_PASSWORDS', 'OFFICE_TELEGRAM_PILOT_SENDERS',
                    'CSS_TELEGRAM_BOT_TOKEN', 'CSS_TELEGRAM_WEBHOOK_SECRET', 'CSS_SESSION_SECRET'}


def stage(destination):
    from scripts import deploy_preview_hf as preview
    preview.stage(destination)
    for name in ('telegram_pilot_app.py', 'telegram_pilot_seed.py'):
        source = ROOT / 'scripts' / name
        if source.is_symlink():
            raise ValueError('Unsafe pilot source')
        shutil.copyfile(source, destination / 'scripts' / name)
    for path in (destination / 'templates').rglob('*.html'):
        path.write_text(path.read_text().replace('PREVIEW — synthetic data only; resets on restart',
            'TELEGRAM PILOT — synthetic data only; resets on restart · <a href="/pilot-fixtures">Test records</a>'))
    docker = destination / 'Dockerfile'
    docker.write_text(docker.read_text().replace('scripts/preview_app.py', 'scripts/telegram_pilot_app.py'))
    (destination / 'preview-build.json').unlink()
    (destination / 'README.md').write_text('''---
title: Office Connect Telegram PILOT
sdk: docker
app_port: 7860
pinned: false
---
# Isolated synthetic Telegram pilot
Protected source, public app with application sign-in. Dedicated test bot only.
Schedulers and outbound providers are disabled. Data and sessions reset on restart.
Do not use production credentials, records, persistence or bot registration here.
''')
    tree = ast.parse((ROOT / 'version.py').read_text())
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'APP_VERSION' for t in n.targets))
    hashes = {}
    for path in sorted(destination.rglob('*')):
        if not path.is_file():
            continue
        if path.suffix in {'.db', '.sqlite', '.sqlite3'} or path.name.startswith('.env'):
            raise ValueError('Data or secrets in bundle')
        hashes[str(path.relative_to(destination))] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {'environment':'telegram-pilot', 'target':TARGET, 'version':version,
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'files':hashes}
    (destination / 'pilot-build.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def verify_target(info, secret_names):
    if info.id != TARGET or getattr(info, 'visibility', None) != 'protected' or not info.private or info.sdk != 'docker':
        raise ValueError('Refusing publication: exact protected Docker pilot target required.')
    missing = REQUIRED_SECRETS - set(secret_names)
    if missing:
        raise ValueError('Missing pilot secrets: ' + ', '.join(sorted(missing)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='office-telegram-pilot-bundle-') as directory:
        manifest = stage(Path(directory))
        print('Pilot bundle:', len(manifest['files']), 'files; version', manifest['version'],
              '; source', manifest['source_commit'], '; target', TARGET)
        if not args.publish:
            print('Dry run only; no network request made.')
            return
        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
            raise SystemExit('Commit the review branch before publishing.')
        if not os.environ.get('HF_TOKEN'):
            raise SystemExit('HF_TOKEN binding required.')
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ['HF_TOKEN'])
        info = api.space_info(TARGET)
        verify_target(info, api.get_space_secrets(TARGET))
        variables = api.get_space_variables(TARGET)
        # A first publish must be paused. Activation is a separate explicit operation.
        if variables.get('OFFICE_TELEGRAM_PILOT_BATCH') and variables['OFFICE_TELEGRAM_PILOT_BATCH'].value != 'off':
            raise SystemExit('Pause the pilot batch before publishing a new disposable build.')
        result = api.upload_folder(repo_id=TARGET, repo_type='space', folder_path=directory,
                                   commit_message='Publish isolated Telegram pilot ' + manifest['source_commit'])
        print('Space commit:', result.oid)
        print('Verify protected visibility, source/version, RUNNING, health and isolation before activation.')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    main()
