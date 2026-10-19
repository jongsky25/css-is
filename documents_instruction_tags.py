"""Resolve explicit instruction mentions against current staff and document access."""
import documents_permissions as permissions
from documents_storage import rows


def section_members(conn, section_id):
    return [row['id'] for row in rows(conn, '''SELECT u.id FROM admin_user u
        JOIN resource_person r ON r.id=u.rp_id
        WHERE u.active=1 AND r.archived_at IS NULL AND r.is_internal=1
          AND r.org_unit_id=? ORDER BY u.id''', (section_id,))]


def choices(conn, doc, *, initial=False):
    people = rows(conn, '''SELECT u.id,COALESCE(NULLIF(r.name,''),u.username) AS name
        FROM admin_user u LEFT JOIN resource_person r ON r.id=u.rp_id
        WHERE u.active=1 ORDER BY name,u.id''')
    if not initial:
        people = [person for person in people if permissions.can_view(conn, person, doc)]
    sections = rows(conn,"SELECT id,name FROM org_unit WHERE level='section' ORDER BY path")
    sections = [section for section in sections if any(
        initial or permissions.can_view(conn, {'id': uid}, doc)
        for uid in section_members(conn, section['id']))]
    return people, sections


def selected(data):
    people = [int(key.split(':', 1)[1]) for key, value in data.items()
              if key.startswith('mention_person:') and value == 'yes']
    sections = [int(key.split(':', 1)[1]) for key, value in data.items()
                if key.startswith('mention_section:') and value == 'yes']
    if len(people) + len(sections) > 20:
        raise ValueError('Choose at most 20 people and sections to mention.')
    return set(people), set(sections)


def resolve(conn, doc, data, *, initial=False):
    people, sections = selected(data)
    recipients = set()
    for uid in people:
        user = permissions.actor(conn, {'id': uid})
        if not initial and not permissions.can_view(conn, user, doc):
            raise ValueError('A mentioned person no longer has access to this document.')
        recipients.add(uid)
    for section_id in sections:
        section = conn.execute("SELECT id FROM org_unit WHERE id=? AND level='section'", (section_id,)).fetchone()
        if not section:
            raise ValueError('A mentioned section no longer exists.')
        members = section_members(conn, section_id)
        if not members:
            raise ValueError('A mentioned section has no active staff accounts.')
        eligible = [uid for uid in members if initial or permissions.can_view(conn, {'id': uid}, doc)]
        if not eligible:
            raise ValueError('No one in the mentioned section can access this document.')
        recipients.update(eligible)
    if len(recipients) > 30:
        raise ValueError('Mentions resolve to more than 30 staff members.')
    return people, sections, recipients


def save(conn, directive_id, people, sections):
    for target_type, identifiers in (('person', people), ('section', sections)):
        for target_id in sorted(identifiers):
            conn.execute('INSERT INTO document_instruction_tag VALUES (?,?,?)',
                         (directive_id, target_type, target_id))
