"""Prove lazy artwork modules preserve every rendered SVG and bound compilation."""
import argparse
import hashlib
from itertools import count
import json
from pathlib import Path
import re
import subprocess
import tempfile
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from gallery import ROOT, CATALOG

parser = argparse.ArgumentParser()
parser.add_argument('--before', default='f47124a')
parser.add_argument('--out', default='docs/avatars/increment2b/lcp-unblock')
args = parser.parse_args()


def module(folder):
    env = Environment(loader=FileSystemLoader(folder), autoescape=True, undefined=StrictUndefined)
    seq = count(1)
    families = {i['key']: i['family'] for i in CATALOG}
    env.globals.update(avatar_uid=lambda: 'check-' + str(next(seq)), avatar_family=lambda k: families.get(k, 'plant'),
        avatar_is_swimmer=lambda k: k in {'fish', 'dolphin'}, avatar_month=lambda: 7, avatar_outfit=lambda: 'default',
        avatar_care_verb=lambda k: 'water' if families.get(k, 'plant') == 'plant' else 'feed')
    return env, env.get_template('_avatars.html').module


def normalized(svg):
    # Only dispatcher whitespace between SVG elements changes. Retain every
    # attribute, path byte and text node; do not normalize geometry or IDs.
    return re.sub(r'>\s+<', '><', svg).strip()


with tempfile.TemporaryDirectory() as before:
    for name in ['_avatars.html', '_avatars_art.html']:
        Path(before, name).write_bytes(subprocess.check_output(['git', 'show', args.before + ':templates/' + name]))
    _, old = module(before)
    env, new = module(ROOT / 'templates')
    new.avatar_svg('cat', 1, 0, 'default')
    compiled = sorted(t.name for t in env.cache.values())
    assert [n for n in compiled if n.startswith('_avatar_species/')] == ['_avatar_species/cat.html']
    # Reset the deterministic UUID counters after the cache check.
    _, new = module(ROOT / 'templates')
    checks = 0
    variants = [(m, 'default') for m in range(13)] + [(10, c) for c in ['halloween', 'halloween_vampire', 'halloween_pumpkin']] + [(12, 'christmas')]
    for month, costume in variants:
        for kind in [i['key'] for i in CATALOG] + ['unknown']:
            for stage in range(1, 7):
                assert normalized(str(old.avatar_svg(kind, stage, month, costume))) == normalized(str(new.avatar_svg(kind, stage, month, costume))), (kind, stage, month, costume)
                checks += 1
    current_defs = re.sub(r"  /\* Static preview policy:.*?  /\* End static preview policy\. \*/\n", "", str(new.avatar_defs()), flags=re.S)
    assert re.sub(r"avatars\.js\?v=[0-9.]+", "avatars.js?v=CACHE", str(old.avatar_defs())) == re.sub(r"avatars\.js\?v=[0-9.]+", "avatars.js?v=CACHE", current_defs)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    result = {'before_commit': args.before, 'svg_equivalence_checks': checks, 'species': 16,
              'stages': 6, 'outfit_variants': 17, 'unknown_fallback_checked': True,
              'normalization': 'Whitespace between XML elements only; paths, attributes, text and deterministic IDs compared exactly.',
              'single_cat_compiled_templates': compiled, 'css_defs_identical_except_runtime_cache_key_and_static_preview_policy': True,
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted([ROOT / 'templates/_avatars_art.html', ROOT / 'templates/_avatars_shared.html', * (ROOT / 'templates/_avatar_species').glob('*.html')]) if p.is_file()}}
    (out / 'artwork-equivalence.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
