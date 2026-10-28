"""Allowlisted companion equipment and request-scoped appearance preferences."""
from contextvars import ContextVar
import json

PLANTS = frozenset({'plant', 'cactus', 'bonsai', 'sunflower', 'fern', 'mushroom', 'succulent'})
ANIMALS = frozenset({'cat', 'dog', 'rabbit', 'bird', 'turtle', 'fish', 'dolphin', 'owl', 'bat'})
MODES = {'seasonal': 'Follow seasonal appearance', 'personal': 'My accessories', 'none': 'No accessories'}
# Each slot has one owner transform. Placement is inside the species' growth rig.
CATALOG = {
    'bandana': dict(name='Bandana', species=ANIMALS, slot='secondary', anchor='neck', order=30),
    'bow_tie': dict(name='Bow tie', species=ANIMALS, slot='secondary', anchor='neck', order=30),
    'small_cap': dict(name='Small cap', species=ANIMALS, slot='primary', anchor='head', order=40),
    'flower_crown': dict(name='Flower crown', species=ANIMALS, slot='primary', anchor='head', order=40),
    'scarf': dict(name='Scarf', species=ANIMALS, slot='secondary', anchor='neck', order=20),
    'simple_cape': dict(name='Simple cape', species=ANIMALS, slot='primary', anchor='back', order=0),
    'terracotta': dict(name='Terracotta pot', species=PLANTS, slot='primary', anchor='pot', order=20),
    'ceramic': dict(name='Ceramic pot', species=PLANTS, slot='primary', anchor='pot', order=20),
    'pot_wrap': dict(name='Pot wrap', species=PLANTS, slot='primary', anchor='pot', order=20),
    'ribbon': dict(name='Ribbon', species=PLANTS, slot='secondary', anchor='pot', order=30),
    'plant_label': dict(name='Plant label', species=PLANTS, slot='secondary', anchor='ornament', order=10),
    'small_trellis': dict(name='Small trellis', species=frozenset({'plant', 'bonsai'}), slot='secondary', anchor='back', order=0),
    'decorative_stake': dict(name='Decorative stake', species=PLANTS, slot='secondary', anchor='ornament', order=10),
}
current = ContextVar('companion_wardrobe', default=None)


def validate(kind, mode, items):
    if mode not in MODES:
        raise ValueError('Choose a listed companion appearance mode.')
    if not isinstance(items, (list, tuple)) or len(items) > 2:
        raise ValueError('Choose at most two accessories.')
    slots = set()
    for key in items:
        entry = CATALOG.get(key) if isinstance(key, str) else None
        if not entry or kind not in entry['species']:
            raise ValueError('Choose accessories compatible with this companion.')
        if entry['slot'] in slots:
            raise ValueError('Choose only one accessory in each slot.')
        slots.add(entry['slot'])
    return {'mode': mode, 'items': sorted(items, key=lambda key: CATALOG[key]['order'])}


def normalize(kind, mode='seasonal', items=()):
    """Retired/corrupt saved IDs must never prevent a page from rendering."""
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except (ValueError, TypeError):
            items = []
    if not isinstance(items, (list, tuple)):
        items = []
    kept, slots = [], set()
    for key in items[:2]:
        entry = CATALOG.get(key) if isinstance(key, str) else None
        if entry and kind in entry['species'] and entry['slot'] not in slots:
            kept.append(key)
            slots.add(entry['slot'])
    return validate(kind, mode if mode in MODES else 'seasonal', kept)


def for_kind(kind):
    actor = current.get()
    return actor['preferences'] if actor and actor['kind'] == kind else {'mode': 'seasonal', 'items': []}


def from_form(kind, data, previous_kind=None):
    items = [data.get('avatar_primary', ''), data.get('avatar_secondary', '')]
    items = [item for item in items if item]
    # Changing species clears previously selected incompatible equipment. Unknown
    # IDs are still rejected, rather than treated as a species-switch exception.
    if any(key not in CATALOG for key in items):
        raise ValueError('Choose a listed companion accessory.')
    if previous_kind and previous_kind != kind:
        items = [key for key in items if kind in CATALOG[key]['species']]
    return validate(kind, data.get('avatar_appearance_mode', 'seasonal'), items)
