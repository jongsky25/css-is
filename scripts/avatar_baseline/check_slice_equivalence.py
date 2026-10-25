"""Verify final stage-label correction leaves measured geometry unchanged."""
import hashlib
from itertools import count
import json
from pathlib import Path
import subprocess
import tempfile
from jinja2 import Environment,FileSystemLoader,StrictUndefined
from gallery import ROOT,CATALOG


def module(folder):
    env=Environment(loader=FileSystemLoader(folder),autoescape=True,undefined=StrictUndefined)
    seq=count(1);families={i['key']:i['family'] for i in CATALOG}
    env.globals.update(avatar_uid=lambda:'check-'+str(next(seq)),avatar_family=lambda k:families[k],
        avatar_is_swimmer=lambda k:k in {'fish','dolphin'},avatar_month=lambda:7,avatar_outfit=lambda:'default',
        avatar_care_verb=lambda k:'water' if families[k]=='plant' else 'feed')
    return env.get_template('_avatars.html').module


with tempfile.TemporaryDirectory() as before:
    for name in ['_avatars.html','_avatars_art.html']:
        Path(before,name).write_bytes((ROOT/'templates'/name).read_bytes() if name=='_avatars.html' else subprocess.check_output(['git','show','0be7fc3:templates/'+name]))
    a=module(before);b=module(ROOT/'templates');primary=0;unchanged=0
    for month,costume in [(m,'default') for m in range(13)]+[(10,c) for c in ['halloween','halloween_vampire','halloween_pumpkin']]+[(12,'christmas')]:
        for kind,stage in [('cat',1)]+[(i['key'],2) for i in CATALOG]+[('cat',s) for s in range(1,7)]:
            assert str(a.avatar_svg(kind,stage,month,costume))==str(b.avatar_svg(kind,stage,month,costume)),(kind,stage)
            primary+=1
        for item in CATALOG:
            for stage in range(1,7):
                kind=item['key']
                if kind=='plant' and stage in [3,4]:continue
                assert str(a.avatar_svg(kind,stage,month,costume))==str(b.avatar_svg(kind,stage,month,costume)),(kind,stage)
                unchanged+=1
    assert str(a.avatar_defs())==str(b.avatar_defs())
    result={'reason':'Restore Seedling at stage 3 and Budding at stage 4; open flowers start at stage 5',
            'measured_source_commit':'0be7fc3',
            'before_art_sha256':hashlib.sha256(Path(before,'_avatars_art.html').read_bytes()).hexdigest(),
            'after_art_sha256':hashlib.sha256((ROOT/'templates/_avatars_art.html').read_bytes()).hexdigest(),
            'byte_identical_primary_fixture_checks':primary,'byte_identical_unaffected_stage_checks':unchanged,
            'surfaces':['Home cat stage 1','16-species picker stage 2','cat growth stages 1..6'],
            'variants':'bare, 12 months, witch/vampire/pumpkin/Christmas','shared_css_defs_identical':True,
            'only_changed_species_stages':[['plant',3],['plant',4]],
            'limitation':'Isolated art check applies the current frame/CSS to both versions. Final performance measurements independently cover the complete final code.'}
    (ROOT/'docs/avatars/increment1/plant-semantics-equivalence.json').write_text(json.dumps(result,indent=2))
    print(primary,'primary fixtures and',unchanged,'unaffected stage variants are byte-identical')
