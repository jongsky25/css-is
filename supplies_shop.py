"""The requester's picture grid (Supplies 2.1): one card per catalog item, with the most a person may ask for.

Read-only. Quantities shown are never stock numbers: each card carries a badge (Out of stock / Limited / Available) and a
`max` for its quantity box that is the requestable amount of rule R1 (`supplies_allocations.requestable`). The server still
enforces R1 when the draft is saved, so `max` is only a convenience.

Pictures come from `supplies_pictures` (Supplies 1.4) when that module is present; until then each card shows a tinted tile
with the item's initials, and nothing else changes."""
from __future__ import annotations
import importlib
import re
import zlib

import supplies_allocations as allocations
from supplies_storage import rows

TINTS = ('#fecaca', '#fed7aa', '#fef08a', '#bbf7d0', '#a5f3fc', '#bfdbfe', '#ddd6fe', '#fbcfe8')
BADGE_TONE = {'Available': 'ok', 'Limited': 'warn', 'Out of stock': 'out'}


def _initials(description):
    return ''.join(w[0] for w in re.findall(r'[A-Za-z0-9]+', description or '')[:2]).upper()


def tile(description, code=''):
    """{'src', 'tint', 'initials'} for a card: a real picture when 1.4 is installed, else an initials tile."""
    try:
        pictures = importlib.import_module('supplies_pictures')
    except ImportError:
        pictures = None
    if pictures is not None:
        got = pictures.picture_for(description, code)
        return {'src': got.get('src', ''), 'tint': got.get('tint', TINTS[0]), 'initials': got.get('initials', '')}
    return {'src': '', 'tint': TINTS[zlib.crc32((code or description or '').encode()) % len(TINTS)],
            'initials': _initials(description)}


# Extra words a card also answers to, so people find an item by the name they use. Each entry adds words when the pattern
# is in the item's name: common alternative names, plural forms and the misspellings the office's own list carries.
ALIASES = (
    (r'ball\s*pen', 'pen ballpoint'), (r'bond\s+paper', 'copy paper photocopy xerox'), (r'post\s*-?\s*it', 'sticky notes memo'),
    (r'scissor', 'scissors'), (r'batter', 'batteries'), (r'fresh(?:e)?ner', 'freshener freshner air freshener'),
    (r'maskin', 'masking'), (r'packin', 'packing'), (r'typewrit+er', 'typewriter'), (r'inj?et', 'inkjet ink jet'),
    (r'cann?on', 'canon copy paper'), (r'folder', 'file'), (r'staple', 'staples stapler'), (r'tape', 'adhesive'),
    (r'marker', 'pentel whiteboard'), (r'clip', 'clips paper clip'),
)


def _words(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower())


def search_text(description, code=''):
    """Everything a card can be found by: its name and code plus the alternative words in ALIASES."""
    low = f"{description or ''} {code or ''}".lower()
    extra = [words for pattern, words in ALIASES if re.search(pattern, low)]
    return ' '.join([low] + extra)


def _within_one(a, b):
    """True when two words differ by one typo: a letter added, dropped or changed, or two neighbouring letters swapped."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        wrong = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        # one letter changed, or two neighbouring letters swapped
        return len(wrong) <= 1 or (len(wrong) == 2 and wrong[1] == wrong[0] + 1 and a[wrong[0]] == b[wrong[1]] and a[wrong[1]] == b[wrong[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def text_matches(text, query_words):
    """Every word typed must be found: inside the text, at the start of one of its words, or one typo away from one
    (typos only for words of four letters or more, so "pen" does not match "pan")."""
    have = _words(text)
    low = ' '.join(have)
    for w in query_words:
        if w in low:
            continue
        if len(w) >= 4 and any(_within_one(w, h) for h in have if len(h) >= 4):
            continue
        return False
    return True


def shop_items(conn, query='', exclude_request_id=None):
    """The active catalog as cards, A to Z, narrowed by the words in `query` (every word must appear in the name or code)."""
    words = _words(query)[:8]
    items = rows(conn, 'SELECT id,code,description,unit,critical_level,target_level FROM supply_item WHERE active=1 '
                       'ORDER BY description COLLATE NOCASE, code')
    out = []
    for item in items:
        text = search_text(item['description'], item['code'])
        if words and not text_matches(text, words):
            continue
        can = allocations.requestable(conn, item['id'], exclude_request_id)
        label = allocations.badge(can, item)
        out.append({'id': item['id'], 'code': item['code'], 'description': item['description'], 'unit': item['unit'],
                    'max': can, 'badge': label, 'tone': BADGE_TONE[label], 'picture': tile(item['description'], item['code']),
                    'search': text})
    return out


def quantities_from(fields):
    """[{'item_id', 'requested_quantity'}] from the grid's `qty_<item id>` boxes, in item order; empty and zero boxes are skipped."""
    found = []
    for key, value in fields.items():
        if not key.startswith('qty_'):
            continue
        text = str(value or '').strip()
        if text and text != '0' and key[4:].isdigit():
            found.append((int(key[4:]), text))
    return [{'item_id': str(i), 'requested_quantity': q} for i, q in sorted(found)]


def narrow(items, query, keep=()):
    """The plain list's items narrowed by what was typed; items in `keep` (already chosen) always stay."""
    words = _words(query)[:8]
    if not words:
        return items
    return [i for i in items if str(i['id']) in {str(k) for k in keep}
            or text_matches(search_text(i['description'], i['code']), words)]
