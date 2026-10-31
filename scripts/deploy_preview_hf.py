"""Stage a code-only preview bundle; publish only to the dedicated private Space."""
import argparse
import ast
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'equityinhealth/office-connect-preview'


def stage(destination):
    tree = ast.parse((ROOT / 'deploy_hf.py').read_text())
    runtime = next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'RUNTIME_PY' for t in n.targets))
    tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
    names = set(runtime + ['version.py', 'requirements.txt', 'scripts/preview_app.py'])
    names.update(name for name in tracked if name.startswith(('templates/', 'static/', 'assets/')))
    for name in sorted(names):
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing or unsafe runtime source: ' + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Label copied templates only; production templates stay untouched.
    for template in (destination / 'templates').rglob('*.html'):
        text = template.read_text()
        text = re.sub(r'(<body\b[^>]*>)', r'\1<div role="note" style="background:#fff3cd;color:#332701;padding:8px;text-align:center;font:14px sans-serif">PREVIEW — synthetic data only; resets on restart</div>',
                      text, count=1, flags=re.I)
        template.write_text(text)
    (destination / 'Dockerfile').write_text('''FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt && python -m pip check
COPY . .
EXPOSE 7860
CMD ["python", "scripts/preview_app.py"]
''')
    (destination / 'README.md').write_text('''---
title: Office Connect PREVIEW - synthetic data only
sdk: docker
app_port: 7860
pinned: false
---
# Disposable private preview
Synthetic data only. All entered data resets on restart. External server connections
are disabled. Login: preview@example.invalid, using the private preview secret.
''')
    (destination / 'preview-build.json').write_text(json.dumps({
        'environment': 'preview', 'source_commit': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='office-preview-bundle-') as directory:
        destination = Path(directory)
        stage(destination)
        files = list(destination.rglob('*'))
        assert not any(p.suffix in {'.db', '.sqlite', '.sqlite3'} or p.name.startswith('.env')
                       for p in files if p.is_file())
        print(f'Code-only preview bundle verified: {sum(p.is_file() for p in files)} files. Target: {TARGET}')
        if not args.publish:
            print('Dry run only; no Hugging Face request made.')
            return
        if not os.environ.get('HF_TOKEN'):
            raise SystemExit('Configure HF_TOKEN in cloud secret settings; never paste it in chat.')
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            raise SystemExit('Commit workspace changes before publishing so source provenance is reproducible.')
        from huggingface_hub import HfApi
        from huggingface_hub.errors import RepositoryNotFoundError
        api = HfApi(token=os.environ['HF_TOKEN'])
        try:
            info = api.repo_info(TARGET, repo_type='space')
        except RepositoryNotFoundError:
            api.create_repo(TARGET, repo_type='space', space_sdk='docker', private=True,
                            space_hardware='cpu-basic')
            info = api.repo_info(TARGET, repo_type='space')
        if not info.private:
            raise SystemExit('Refusing to publish: preview Space must be private.')
        password = os.environ.get('OFFICE_PREVIEW_PASSWORD', '')
        if password:
            if len(password) < 16:
                raise SystemExit('Preview password must contain at least 16 characters.')
            api.add_space_secret(TARGET, 'OFFICE_PREVIEW_PASSWORD', password)
        elif 'OFFICE_PREVIEW_PASSWORD' not in api.get_space_secrets(TARGET):
            raise SystemExit('Set OFFICE_PREVIEW_PASSWORD in the preview Space secret settings before uploading.')
        api.upload_folder(repo_id=TARGET, repo_type='space', folder_path=directory,
                          commit_message='Deploy isolated Office Connect preview')
        print('Upload accepted. Verify Space build, private access and mobile login before marking step 4 complete.')


if __name__ == '__main__':
    main()
