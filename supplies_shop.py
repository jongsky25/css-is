"""Picture grid for requesters: items with a badge and the most that can be asked for, and the cart-to-lines mapping."""
import re

from supplies_allocations import badge, requestable
from supplies_pictures import picture_for
from supplies_storage import Invalid, rows

MAX_LINES = 20


def shop_items(conn, query='', exclude_request_id=None):
    if not isinstance(query, str) or len(query) > 200 or any(ord(c) < 32 for c in query):
        raise Invalid('Search must contain at most 200 characters without control characters.')
    needle = query.strip().lower()
    items = []
    for item in rows(conn, '''SELECT id,code,description,unit,critical_level,target_level
                              FROM supply_item WHERE active=1 ORDER BY lower(description),id'''):
        if needle and needle not in ' '.join((item['description'], item['code'], item['unit'])).lower():
            continue
        most = requestable(conn, item['id'], exclude_request_id)
        items.append({**item, 'requestable': most, 'badge': badge(most, item),
                      'picture': picture_for(item['description'], item['code'])})
    return items


def lines_from_form(fields):
    """Turn qty_<item id> inputs into request lines; blank and zero quantities mean not chosen."""
    lines = []
    for key, value in fields.items():
        found = re.fullmatch(r'qty_(\d+)', key)
        if not found or str(value).strip() in ('', '0'):
            continue
        lines.append({'item_id': found.group(1), 'requested_quantity': str(value).strip()})
    if not lines:
        raise Invalid('Pick at least one item and a quantity.')
    if len(lines) > MAX_LINES:
        raise Invalid(f'You can pick at most {MAX_LINES} different items in one request.')
    return lines


def chosen_quantities(fields):
    """Quantities typed so far, to show again after an error: {item id: text}."""
    return {int(k[4:]): v for k, v in fields.items() if re.fullmatch(r'qty_\d+', k) and str(v).strip() not in ('', '0')}
