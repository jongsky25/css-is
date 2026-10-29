"""Increment 1.4: item pictures generated from the item name."""
import os

import pytest

import supplies_pictures as pictures

ROOT = os.path.dirname(os.path.dirname(__file__))
CATALOG = os.path.join(ROOT, 'tests', 'data', 'supplies_catalog_names.tsv')
KNOWN_FALLBACK = {'Epson 0442'}


def names():
    with open(CATALOG) as f:
        return [line.split('\t')[0] for line in f if line.strip() and not line.startswith('#')]


def name_of(src):
    return os.path.basename(src)[:-4]


def test_every_real_catalog_name_gets_a_specific_picture_except_the_known_fallback():
    found = names()
    assert len(found) == 99
    fallback = {n for n in found if name_of(pictures.picture_for(n, 'X')['src']) == 'generic'}
    assert fallback == KNOWN_FALLBACK


def test_catalog_uses_exactly_the_planned_set_of_pictures():
    used = {name_of(pictures.picture_for(n)['src']) for n in names()} - {'generic'}
    assert len(used) == 49
    assert used == {name for name, _ in pictures.RULES}


def test_every_rule_has_its_svg_file_and_generic_exists():
    for name, _ in pictures.RULES:
        assert os.path.isfile(os.path.join(ROOT, 'static', 'img', 'supplies', name + '.svg')), name
    assert os.path.isfile(os.path.join(ROOT, 'static', 'img', 'supplies', 'generic.svg'))


@pytest.mark.parametrize('description,expected', [
    ('Stapler Remover', 'staple-remover'), ('Stapler Wire', 'staples'), ('Stapler', 'stapler'),
    ('Sign Pen (Black)', 'sign-pen'), ('Ballpen (Blue)', 'ballpen'), ('Pencil', 'pencil'),
    ('Correction Tape', 'correction-tape'), ('Tape (Transparent)', 'tape'),
    ('Tape (Duck 2x2)', 'tape-wide'), ('Tape (Packin 1x1)', 'tape-wide'), ('Tape (Silver 2x2)', 'tape-wide'),
    ('Tape (Maskin 1x1)', 'tape'), ('Battery Charger', 'battery-charger'), ('Battery (AA size)', 'battery'),
    ('Stamp Pad', 'stamp-pad'), ('Stamp Pad (Ink)', 'ink-bottle'), ('Brother Ink (Cyan)', 'ink-bottle'),
    ('Envelope Expanding', 'expanding-file'), ('Envelope (Brown Long)', 'envelope'),
    ('Folder Expanding (Green)', 'expanding-file'), ('Folder Short', 'folder'),
    ('Clip Binder Joy 2', 'binder-clip'), ('File System (Clip)', 'box-file'), ('ID Holder With Clip', 'id-holder'),
    ('Typewritter Ribbon', 'ribbon-cartridge'), ('Air Freshner', 'air-freshener'), ('Scissor', 'scissors'),
    ("Cd's DVD", 'disc'), ('Cannon', 'paper-ream'), ('Post it (Sign Here)', 'sticky-notes'),
])
def test_specific_rules_beat_general_ones_and_tolerate_the_office_spellings(description, expected):
    assert name_of(pictures.picture_for(description)['src']) == expected


def test_colour_words_tint_the_tile_and_uncoloured_names_stay_neutral():
    red = pictures.picture_for('Fancy Folder (Red)')
    blue = pictures.picture_for('Fancy Folder (Blue)')
    assert red['src'] == blue['src'] and red['tint'] != blue['tint']
    assert red['tint'] == pictures.TINTS['red'] and blue['tint'] == pictures.TINTS['blue']
    for word, tint in pictures.TINTS.items():
        assert pictures.tint_for(f'Thing ({word.title()})') == tint
    assert pictures.picture_for('Scissor')['tint'] == pictures.NEUTRAL_TINT
    assert pictures.picture_for('Folder Brown Long')['tint'] == pictures.TINTS['brown']


def test_unknown_names_fall_back_to_an_initials_tile_with_a_stable_colour_per_code():
    one = pictures.picture_for('Epson 0442', 'EPS-1')
    assert one['src'].endswith('generic.svg') and one['initials'] == 'E0'
    assert pictures.picture_for('Epson 0442', 'EPS-1') == one
    assert pictures.picture_for('Zebra gizmo', 'Z-1')['initials'] == 'ZG'
    tints = {pictures.picture_for('Mystery', f'CODE-{i}')['tint'] for i in range(40)}
    assert tints <= set(pictures.FALLBACK_TINTS) and len(tints) > 1
    assert pictures.picture_for('Scissor')['initials'] == ''
