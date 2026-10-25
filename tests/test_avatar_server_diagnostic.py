"""Opt-in server-side template profiling; never acceptance measurements."""
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import subprocess
import time

import pytest
from tests.test_avatar_baseline_browser import baseline_server

pytestmark = pytest.mark.skipif(os.getenv('CSS_AVATAR_BASELINE') != '1', reason='Opt-in server diagnostic')


def test_server_template_profile(baseline_server, app_mod, tmp_path, monkeypatch):
    import httpx
    import jinja2
    from jinja2 import ChoiceLoader, FileSystemLoader
    origin, cookie, _ = baseline_server
    env = app_mod.templates.env
    original_loader = env.loader
    render = jinja2.Template.render
    records = []
    profiles = []
    version = ''

    def measured_render(template, *args, **kwargs):
        profile = cProfile.Profile()
        start = time.perf_counter()
        result = profile.runcall(render, template, *args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
        profiles.append(f'{version} {template.name} {elapsed:.1f}ms\n{stream.getvalue()}')
        records.append({'version': version, 'template': template.name, 'render_ms_profiled': elapsed})
        return result

    monkeypatch.setattr(jinja2.Template, 'render', measured_render)
    loaders = {'current': original_loader}
    for name, commit in [('increment0', '1c964dc'), ('increment2a', '5b580d9')]:
        folder = tmp_path / name
        folder.mkdir()
        for file in ['_avatars.html', '_avatars_art.html']:
            (folder / file).write_bytes(subprocess.check_output(['git', 'show', commit + ':templates/' + file]))
        loaders[name] = ChoiceLoader([FileSystemLoader(folder), original_loader])
    try:
        with httpx.Client(cookies={cookie['name']: cookie['value']}) as client:
            for version, loader in loaders.items():
                env.loader = loader
                env.cache.clear()
                for run in range(5):
                    start = time.perf_counter()
                    response = client.get(origin + '/?view=me')
                    assert response.status_code == 200
                    records[-1].update(run=run, http_ms=(time.perf_counter() - start) * 1000)
    finally:
        env.loader = original_loader
        env.cache.clear()
    out = Path(os.environ['CSS_AVATAR_OUT']).parent
    (out / 'server-template-profile.json').write_text(json.dumps(records, indent=2))
    (out / 'server-template-profile.txt').write_text('\n'.join(profiles))
    print(json.dumps(records, indent=2))
