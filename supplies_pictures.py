"""Item pictures chosen from the item name: ordered regex rules, colour tint and an initials fallback."""
import re
import zlib

PICTURE_DIR = '/static/img/supplies/'

# Specific before general: the first rule that matches wins.
RULES = [
    ('staple-remover', r'stapl\w*\s+remover'),
    ('staples', r'stapl\w*\s+wire'),
    ('stapler', r'stapl'),
    ('correction-tape', r'correction\s+tape'),
    ('correction-fluid', r'correction\s+fluid'),
    ('battery-charger', r'batter\w*\s+charger'),
    ('battery', r'batter'),
    ('ribbon-cartridge', r'ribbon'),
    ('ink-bottle', r'\bink\b|\binj?et\b'),
    ('stamp-pad', r'stamp\s+pad'),
    ('sign-pen', r'sign\s+pen'),
    ('ballpen', r'ball\s*pen'),
    ('pencil', r'pencil'),
    ('highlighter', r'highlight'),
    ('marker', r'marker'),
    ('crayon', r'crayon'),
    ('tape-wide', r'tape.*(duc?k|pack\w*|silver)'),
    ('tape', r'tape'),
    ('carbon-paper', r'carbon'),
    ('fax-roll', r'\bfax\b'),
    ('photo-paper', r'avia|matte|parchment'),
    ('colored-paper', r'cartolina|wrapping\s+paper'),
    ('paper-ream', r'bond\s+paper|^cann?on$'),
    ('sticky-notes', r'post\s*-?\s*it'),
    ('index-card', r'index'),
    ('expanding-file', r'expanding|organi[sz]er|document\s+file'),
    ('envelope', r'envelope'),
    ('box-file', r'file\s+system'),
    ('ring-binder', r'ring\s+binder'),
    ('clear-book', r'clear\s+book'),
    ('folder', r'folder'),
    ('notebook', r'record\s+book|ruled\s+pad|note\s*book|binder\s+filler'),
    ('puncher', r'punch'),
    ('fastener', r'fastener'),
    ('id-holder', r'\bid\s+holder'),
    ('binder-clip', r'clip\s+(binder|double)'),
    ('map-pins', r'map\s+pin'),
    ('rubber-bands', r'rubber\s+band'),
    ('glue', r'\bglue'),
    ('scissors', r'scissor'),
    ('cutter', r'cutter'),
    ('clay', r'\bclay'),
    ('disc', r'\bcds?\b|\bdvds?\b|\bcd\'?s'),
    ('speaker', r'speaker'),
    ('alcohol', r'alcohol'),
    ('air-freshener', r'air\s+fresh'),
    ('tissue', r'tissue'),
    ('waste-basket', r'waste\s*basket'),
    ('sweetener', r'splenda|sweetener'),
]
_COMPILED = [(name, re.compile(pattern, re.I)) for name, pattern in RULES]

TINTS = {'black': '#475569', 'blue': '#60a5fa', 'red': '#f87171', 'yellow': '#fde047', 'green': '#4ade80',
         'peach': '#fdba74', 'white': '#f1f5f9', 'brown': '#b08968', 'cyan': '#22d3ee', 'magenta': '#e879f9'}
NEUTRAL_TINT = '#fef3c7'
FALLBACK_TINTS = ('#fecaca', '#fed7aa', '#fef08a', '#bbf7d0', '#a5f3fc', '#bfdbfe', '#ddd6fe', '#fbcfe8')


def tint_for(description):
    """Background colour for the picture tile; the first colour word in the name wins."""
    for word in re.findall(r'[a-z]+', description.lower()):
        if word in TINTS:
            return TINTS[word]
    return NEUTRAL_TINT


def initials(description):
    words = re.findall(r'[A-Za-z0-9]+', description)[:2]
    return ''.join(w[0] for w in words).upper()


def picture_for(description, code=''):
    """{'src','tint','initials'}: initials is empty when a real picture matched, else shown on the tile."""
    for name, pattern in _COMPILED:
        if pattern.search(description):
            return {'src': PICTURE_DIR + name + '.svg', 'tint': tint_for(description), 'initials': ''}
    tint = FALLBACK_TINTS[zlib.crc32((code or description).encode()) % len(FALLBACK_TINTS)]
    return {'src': PICTURE_DIR + 'generic.svg', 'tint': tint, 'initials': initials(description)}
