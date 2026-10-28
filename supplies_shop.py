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


def _matches(item, words):
    hay = f"{item['description']} {item['code']}".lower()
    return all(w in hay for w in words)


def shop_items(conn, query='', exclude_request_id=None):
    """The active catalog as cards, A to Z, narrowed by the words in `query` (every word must appear in the name or code)."""
    words = [w for w in re.findall(r'\S+', (query or '').lower())][:8]
    items = rows(conn, 'SELECT id,code,description,unit,critical_level,target_level FROM supply_item WHERE active=1 '
                       'ORDER BY description COLLATE NOCASE, code')
    out = []
    for item in items:
        if words and not _matches(item, words):
            continue
        can = allocations.requestable(conn, item['id'], exclude_request_id)
        label = allocations.badge(can, item)
        out.append({'id': item['id'], 'code': item['code'], 'description': item['description'], 'unit': item['unit'],
                    'max': can, 'badge': label, 'tone': BADGE_TONE[label], 'picture': tile(item['description'], item['code'])})
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
