"""The "New advisory" flow (increment 2 of docs/ADVISORY_SLIDES_PLAN.md).

An advisory can be started from the Advisories module for:
  * an activity already in Office Connect ("activity"),
  * a new activity made together with it ("new_activity", stored as kind "activity"), or
  * no activity at all ("general").

start() is one database transaction (activity if new, number, Documents record, access) and no
network. make_file() then asks the relay for the Google Slides copy, outside any transaction; a
failure leaves a record that says so and a "Try again" button, using the same relay request id so
a retry never makes a second file.

The advisory has no saved revision until it is first sent for review (increment 3 takes the
Slides snapshot then), so get_visible/list_visible in advisory_workflow accept a NULL revision."""
import json
import re
import uuid
from datetime import datetime

from pydantic import ValidationError

import activity_advisory as aa
import activity_creation
import activity_permissions
import advisory_slides as slides
import advisory_workflow as aw
import documents as docs
import documents_permissions as permissions
import gdocs_relay
from documents_storage import rows, transaction, event
import storage as st
import tzutil as tz
import work

KINDS = ('activity', 'new_activity', 'general')
LIMITS = {'title': 200, 'dates': 200, 'venue': 240, 'message': 2000, 'attention': 600, 'contact': 600, 'link': 500}
STEPS = ('Draft', 'Division Chief', 'Director', 'Issued')
THUMB_MAX_AGE_SECONDS = 3600


class FieldError(ValueError):
    """A mistake in one form field; the page links straight to it (long forms on phones)."""
    def __init__(self, message, field):
        super().__init__(message)
        self.field = field


PLAIN_NAMES = {'number': 'number', 'title': 'title', 'dates': 'dates', 'venue': 'venue', 'message': 'main message',
               'attention': '"Attention" line', 'contact': 'contact person', 'link': 'link', 'qr': 'QR code'}


class AlreadyHasAdvisory(ValueError):
    def __init__(self, advisory_id):
        super().__init__('This activity already has an advisory.')
        self.advisory_id = advisory_id


def switched_on(conn):
    """Plain reason the flow cannot be used, or '' when it can."""
    if not aw.available(conn):
        return 'Advisories are paused while Documents or Shared work is switched off.'
    if not gdocs_relay.configured():
        return 'Making advisories in Google Slides is not switched on yet. Ask the system administrator.'
    return ''


# ---- people and units ----

def _unit(conn, unit_id):
    found = rows(conn, 'SELECT id,name,short_name,level,path FROM org_unit WHERE id=?', (unit_id,)) if unit_id else []
    return found[0] if found else None


def home_unit(conn, user):
    rp = rows(conn, 'SELECT org_unit_id FROM resource_person WHERE id=?', (user.get('rp_id'),)) if user.get('rp_id') else []
    return _unit(conn, rp[0]['org_unit_id']) if rp else None


def division_of(conn, unit):
    """The division a unit sits in (itself if it is one). Division Chief review follows it."""
    if not unit:
        return None
    if unit['level'] == 'division':
        return unit
    parts = unit['path'].split('/')
    for cut in range(len(parts) - 1, 0, -1):
        found = rows(conn, "SELECT id,name,short_name,level,path FROM org_unit WHERE path=? AND level='division'",
                     ('/'.join(parts[:cut]),))
        if found:
            return found[0]
    return None


def _address(row):
    for value in (row.get('email'), row.get('username')):
        value = (value or '').strip().casefold()
        if re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
            return value
    return ''


def section_people(conn, unit):
    """Current internal people in the unit (and units under it): their account id (if any) and address."""
    if not unit:
        return []
    found = rows(conn, '''SELECT r.id AS rp_id,r.email,a.id AS account_id,a.username FROM resource_person r
        JOIN org_unit u ON u.id=r.org_unit_id LEFT JOIN admin_user a ON a.rp_id=r.id AND a.active=1
        WHERE r.is_internal=1 AND r.archived_at IS NULL AND (u.path=? OR u.path LIKE ?)
        ORDER BY r.id''', (unit['path'], unit['path'] + '/%'))
    out, seen = [], set()
    for person in found:
        address = _address(person)
        key = (person['account_id'], address)
        if key not in seen and (address or person['account_id']):
            seen.add(key)
            out.append({'account_id': person['account_id'], 'email': address})
    return out


def _user_address(conn, user):
    rp = rows(conn, 'SELECT email FROM resource_person WHERE id=?', (user.get('rp_id'),)) if user.get('rp_id') else []
    return _address({'email': rp[0]['email'] if rp else '', 'username': user.get('username')})


# ---- step 1: choose ----

def activities_for(conn, user, q='', limit=30):
    """Activities this person can make an advisory for: upcoming first, then the most recent past ones."""
    user = permissions.actor(conn, user)
    today = tz.today_local().isoformat()
    q = (q or '').strip()[:100]
    found = rows(conn, '''SELECT e.id,e.event_token,e.title,e.event_date,e.end_date,e.venue,e.created_by,e.event_kind,
            e.lead_org_id,u.short_name AS section,a.id AS advisory_id
        FROM event e LEFT JOIN org_unit u ON u.id=e.lead_org_id LEFT JOIN advisory_record a ON a.event_id=e.id
        WHERE (?='' OR lower(e.title) LIKE ?) AND e.event_date>=date(?,'-90 days')
        ORDER BY CASE WHEN e.event_date>=? THEN 0 ELSE 1 END,
                 CASE WHEN e.event_date>=? THEN e.event_date END ASC, e.event_date DESC, e.id DESC LIMIT 400''',
                 (q, '%' + q.lower() + '%', today, today, today))
    out = []
    for ev in found:
        if st.event_is_archived(conn, ev['id']) or not activity_permissions.can_manage(user, ev, conn):
            continue
        out.append(dict(ev, upcoming=ev['event_date'] >= today, dates=aa.dates_text(ev)))
        if len(out) >= limit:
            break
    return out


# ---- step 2: details ----

def defaults(conn, user, kind, ev=None):
    user = permissions.actor(conn, user)
    section = _unit(conn, ev['lead_org_id']) if ev and ev.get('lead_org_id') else home_unit(conn, user)
    division = division_of(conn, section) or division_of(conn, home_unit(conn, user))
    remembered = st.get_setting(conn, f'advisory.contact.{user["id"]}') or ''
    values = {'title': (ev or {}).get('title') or '', 'dates': aa.dates_text(ev) if ev else '',
              'venue': (ev or {}).get('venue') or '', 'message': '', 'attention': '', 'contact': remembered,
              'link': '', 'audience': 'internal', 'external': '', 'variant': '1',
              'unit_id': str(division['id']) if division else '', 'activity_date': '', 'section_id':
              str(section['id']) if section and section['level'] == 'section' else ''}
    return values


def _clean(value, limit, *, lines=False):
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    text = '\n'.join(' '.join(line.split()) for line in text.split('\n')).strip() if lines else ' '.join(text.split())
    if len(text) > limit:
        raise ValueError(f'Keep it within {limit} characters.')
    return text


def details(form, *, kind, variants):
    """Check step 2. Raises ValueError with a sentence that names the field to fix."""
    labels = {'title': 'the title', 'dates': 'the dates', 'venue': 'the venue', 'message': 'the message',
              'attention': 'the "Attention" line', 'contact': 'the contact details', 'link': 'the link'}
    out = {}
    for key, limit in LIMITS.items():
        try:
            out[key] = _clean(form.get(key), limit, lines=key in ('message', 'attention', 'contact'))
        except ValueError:
            raise FieldError(f'Shorten {labels[key]}: keep it within {limit} characters.', key) from None
    if not out['title']:
        raise FieldError('Give the advisory a title.', 'title')
    if out['link'] and not re.fullmatch(r'https?://\S+', out['link']):
        raise FieldError('The link should start with https:// (or leave it empty).', 'link')
    audience = form.get('audience') or ''
    if audience not in ('internal', 'external', 'both'):
        raise FieldError('Choose who the advisory is for.', 'audience')
    external = str(form.get('external') or '')
    addresses = sorted({x.strip().casefold() for x in re.split(r'[,;\s]+', external) if x.strip()})
    if len(addresses) > 500 or any(len(a) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', a) for a in addresses):
        bad = next((a for a in addresses if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', a)), '')
        raise FieldError(f'"{bad[:60]}" is not an email address. Check the outside recipients.' if bad
                         else 'Use at most 500 outside email addresses.', 'external')
    if audience == 'internal' and addresses:
        raise FieldError('You added outside email addresses but chose office staff only. Choose "Office staff and outside recipients" or remove them.', 'external')
    if audience in ('external', 'both') and not addresses:
        raise FieldError('Add at least one outside email address.', 'external')
    try:
        variant = int(form.get('variant') or 0)
    except ValueError:
        variant = 0
    if variant not in [v['variant'] for v in variants]:
        raise FieldError('Choose a design for the advisory.', 'designs')
    try:
        unit_id = int(form.get('unit_id') or 0)
    except ValueError:
        unit_id = 0
    out.update(audience=audience, external=addresses, variant=variant, unit_id=unit_id)
    return out


# ---- template designs (cached thumbnails) ----

def designs(conn, *, refresh=False, fetch=None):
    """The master's slides as choices. Asks the relay at most once an hour; tests pass `fetch`."""
    cached = rows(conn, 'SELECT variant,slide_id,placeholders_json,png IS NOT NULL AS has_png,fetched_at '
                        'FROM advisory_template_cache ORDER BY variant')
    fresh = bool(cached) and _age_seconds(cached[0]['fetched_at']) < THUMB_MAX_AGE_SECONDS
    if cached and fresh and not refresh:
        return [dict(c, placeholders=json.loads(c['placeholders_json'])) for c in cached], ''
    result = (fetch or (lambda: slides.info(thumbnails=True)))()
    if not result.ok:
        if cached:     # keep showing the last known designs rather than blocking people
            return [dict(c, placeholders=json.loads(c['placeholders_json'])) for c in cached], ''
        return [], slides.describe(result.error)
    now = tz.now_iso()
    with transaction(conn):
        conn.execute('DELETE FROM advisory_template_cache')
        for v in result.value:
            conn.execute('INSERT INTO advisory_template_cache VALUES (?,?,?,?,?)',
                         (v['variant'], v['slide_id'], json.dumps(v['placeholders']), v['png'] or None, now))
    return [dict(v, has_png=bool(v['png'])) for v in result.value], ''


def _age_seconds(stamp):
    try:
        then = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return float('inf')
    now = tz.now_local()
    if then.tzinfo is None:
        now = now.replace(tzinfo=None)
    return (now - then).total_seconds()


def design_png(conn, variant):
    found = conn.execute('SELECT png FROM advisory_template_cache WHERE variant=?', (variant,)).fetchone()
    return found[0] if found and found[0] else None


# ---- create ----

def _reserve_number(conn, day):
    prefix = aa.format_number(day, 0)[:-3]
    legacy = conn.execute('SELECT COALESCE(MAX(seq),0) FROM event_advisory WHERE seq_date=?', (day.isoformat(),)).fetchone()[0]
    mine = [int(n[-3:]) for (n,) in conn.execute('SELECT number FROM advisory_record WHERE number LIKE ?', (prefix + '%',))
            if n[-3:].isdigit()]
    return aa.format_number(day, max([legacy] + mine) + 1)


def start(conn, user, form, *, variants, today=None):
    """Create the advisory record (and the activity, for "new activity"). No network. Returns the advisory id."""
    user = permissions.actor(conn, user)
    kind = form.get('kind')
    if kind not in KINDS:
        raise ValueError('Choose what the advisory is for.')
    try:
        operation_key = str(uuid.UUID(form.get('operation_key') or ''))
    except ValueError:
        raise ValueError('Reload the page and try again.') from None
    values = details(form, kind=kind, variants=variants)
    activity = {}
    if kind == 'new_activity':
        activity = {'activity_name': values['title'], 'event_date': form.get('activity_date') or '',
                    'section_id': form.get('section_id') or '', 'venue': values['venue']}
        if not activity['event_date']:
            raise FieldError('Choose the date of the new activity.', 'activity_date')
        try:
            activity['section_id'] = int(activity['section_id'])
        except (TypeError, ValueError):
            raise FieldError('Choose the section organizing the new activity.', 'section_id') from None
    request_hash = aw.digest(aw.encoded([kind, form.get('event_token') or '', values, activity]))
    with transaction(conn):
        user = permissions.actor(conn, user)
        docs.writable(conn); work.writable(conn)
        replay = rows(conn, 'SELECT * FROM advisory_start_request WHERE actor_id=? AND operation_key=?', (user['id'], operation_key))
        if replay:
            if replay[0]['payload_hash'] != request_hash:
                raise docs.Conflict('This form was already used to start a different advisory. Reload the page.')
            return replay[0]['advisory_id']
        ev = None
        if kind == 'activity':
            ev = st.get_event(conn, form.get('event_token') or '')
            if not ev or not activity_permissions.can_manage(user, ev, conn):
                raise permissions.Denied('Activity not found or unavailable to you.')
            if st.event_is_archived(conn, ev['id']):
                raise ValueError('This activity is archived. Restore it first, or choose another activity.')
            existing = aw.for_event(conn, ev['id'])
            if existing:
                raise AlreadyHasAdvisory(existing['id'])
        elif kind == 'new_activity':
            try:
                made, _form = activity_creation.create_bureau_in_transaction(conn, user, activity)
            except permissions.Denied:
                raise permissions.Denied('Your account cannot create activities. Ask your section head, or choose "Not about an activity".') from None
            except ValidationError:
                raise ValueError('Check the new activity: it needs a title, a date and a section.') from None
            ev = st.get_event(conn, made['event_token'])
        section = _unit(conn, ev['lead_org_id']) if ev and ev.get('lead_org_id') else home_unit(conn, user)
        division = _unit(conn, values['unit_id']) if values['unit_id'] else division_of(conn, section)
        if not division or division['level'] != 'division' or not st.unit_is_active(conn, division['id'], 'division'):
            raise FieldError('Choose the division that owns this advisory. Its Division Chief reviews it.', 'unit_id')
        now = tz.now_iso()
        day = today or tz.today_local()
        number = _reserve_number(conn, day)
        doc = docs.register_in_transaction(conn, user, {'direction': 'OUT', 'subject': values['title'], 'type': 'advisory',
                                                        'unit_id': division['id']}, suppress_assignments=True,
                                           defer_rules=True, quiet=True)
        conn.execute("UPDATE document SET visibility='restricted',policy_json=? WHERE id=?",
                     (aw.encoded({'workflow': 'advisory_draft', 'editor': 'slides'}), doc['id']))
        conn.execute('INSERT INTO document_access VALUES (?,?,?)', (doc['id'], user['id'], 'advisory_initiator'))
        for person in section_people(conn, section):
            if person['account_id'] and person['account_id'] != user['id']:
                conn.execute('INSERT OR IGNORE INTO document_access VALUES (?,?,?)',
                             (doc['id'], person['account_id'], 'advisory_editor'))
        stored = {k: values[k] for k in ('title', 'dates', 'venue', 'message', 'attention', 'contact', 'link',
                                         'audience', 'external', 'variant')}
        aid = conn.execute('''INSERT INTO advisory_record(document_id,event_id,number,reservation_date,initiator_id,unit_id,
            created_at,kind,details_json,section_id) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (doc['id'], ev['id'] if ev else None, number, day.isoformat(), user['id'], division['id'], now,
             'general' if kind == 'general' else 'activity', aw.encoded(stored), section['id'] if section else None)).lastrowid
        event(conn, doc['id'], user, 'advisory_started', {'advisory_id': aid, 'kind': kind, 'number': number,
                                                          'activity_id': ev['id'] if ev else None})
        conn.execute('INSERT INTO advisory_start_request VALUES (?,?,?,?)', (user['id'], operation_key, request_hash, aid))
        if values['contact']:
            conn.execute('INSERT INTO app_setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (f'advisory.contact.{user["id"]}', values['contact']))
        return aid


def _record(conn, aid):
    found = rows(conn, '''SELECT a.*,e.event_token,e.title AS activity_title,e.event_date,e.end_date,e.venue AS activity_venue
        FROM advisory_record a LEFT JOIN event e ON e.id=a.event_id WHERE a.id=?''', (aid,))
    return found[0] if found else None


def can_edit(conn, user, record):
    if record['initiator_id'] == user['id']:
        return True
    return bool(conn.execute("SELECT 1 FROM document_access WHERE document_id=? AND user_id=? AND source='advisory_editor'",
                             (record['document_id'], user['id'])).fetchone())


def make_file(conn, user, aid, *, base_url='', create=None):
    """Ask the relay for the Slides copy (network; call outside a transaction). Safe to repeat."""
    user = permissions.actor(conn, user)
    aw.get_visible(conn, user, aid)
    record = _record(conn, aid)
    if not record.get('kind'):
        raise ValueError('This advisory was made with the old editor.')
    if record['slides_file_id']:
        return json.loads(record['slides_json'])
    if not can_edit(conn, user, record):
        raise permissions.Denied('Only the people preparing this advisory can make its Slides file.')
    stored = json.loads(record['details_json'])
    link = stored['link'] or (f"{base_url}/e/{record['event_token']}" if record['event_token'] and base_url else '')
    editors = [p['email'] for p in section_people(conn, _unit(conn, record['section_id'])) if p['email']]
    editors.insert(0, _user_address(conn, st.get_admin_user_by_id(conn, record['initiator_id'])))
    values = slides.fields(number=record['number'], title=stored['title'], dates=stored['dates'], venue=stored['venue'],
                           message=stored['message'], attention=stored['attention'], contact=stored['contact'], link=link)
    domain = st.get_setting(conn, 'advisory.slides_domain') or 'doh.gov.ph'
    result = (create or slides.create)(request_id=f'advisory-{aid}-create', folder_key=f'advisory-{aid}',
                                       variant=int(stored['variant']), title=f"{record['number']} {stored['title']}",
                                       values=values, link=link, editors=[e for e in editors if e], domain=domain)
    with transaction(conn):
        if result.ok:
            made = result.value
            info = {'id': made.id, 'url': made.url, 'version': made.version, 'qr': made.qr,
                    'unfilled': [PLAIN_NAMES.get(k, k.replace('_', ' ')) for k in made.unfilled if k != 'qr' or made.qr == 'none']}
            conn.execute('UPDATE advisory_record SET slides_file_id=?,slides_json=?,slides_error=NULL WHERE id=? AND slides_file_id IS NULL',
                         (made.id, aw.encoded(info), aid))
            event(conn, record['document_id'], user, 'advisory_slides_created', {'advisory_id': aid, 'file_id': made.id})
            return info
        conn.execute('UPDATE advisory_record SET slides_error=? WHERE id=?', (result.error[:80], aid))
    raise ValueError(slides.describe(result.error))


# ---- the advisory's home page ----

def home(conn, user, aid):
    user = permissions.actor(conn, user)
    visible = aw.get_visible(conn, user, aid)
    record = _record(conn, aid)
    stored = json.loads(record['details_json'] or '{}')
    status = visible['status']
    stage = rows(conn, 'SELECT review_class FROM document WHERE id=?', (record['document_id'],))[0]['review_class']
    issued = conn.execute('SELECT 1 FROM advisory_issue WHERE advisory_id=?', (aid,)).fetchone()
    step = 3 if issued else 2 if status == 'approved' or (status == 'in_review' and stage == 'director') \
        else 1 if status == 'in_review' else 0
    slides_info = json.loads(record['slides_json']) if record['slides_json'] else None
    editable = can_edit(conn, user, record) and status in ('draft', 'changes_requested')
    initiator = st._account_display_name(conn, record['initiator_id']) or 'the preparer'
    if not slides_info:
        headline = ('The Google Slides file is not made yet. ' + slides.describe(record['slides_error'])
                    if record['slides_error'] else 'The Google Slides file is being made.')
        next_line = 'Press "Try again" to make it.' if editable else f'{initiator} can make it.'
    elif status == 'changes_requested':
        headline, next_line = 'Sent back with comments.', 'Make the changes in Google Slides, then send it for review again.'
    elif status == 'draft':
        headline = 'Draft. Edit it in Google Slides.'
        next_line = 'Sending it to your Division Chief for review comes in the next update.'
    else:
        headline, next_line = STEPS[step], ''
    unit = _unit(conn, record['unit_id'])
    section = _unit(conn, record['section_id'])
    return {'record': dict(record, status=status, revision=visible['revision']), 'details': stored, 'steps': STEPS,
            'step': step, 'slides': slides_info, 'editable': editable, 'headline': headline, 'next_line': next_line,
            'division': unit, 'section': section, 'initiator': initiator,
            'activity': {'token': record['event_token'], 'title': record['activity_title'],
                         'dates': aa.dates_text({'event_date': record['event_date'], 'end_date': record['end_date']})}
                        if record['event_token'] else None}
