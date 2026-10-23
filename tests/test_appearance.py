"""Seasonal publishing, request isolation, schedule boundaries and access control."""
import re
import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import pytest

import appearance as rules
import appearance_storage as store
import storage as st


@pytest.fixture
def conn(app_mod):
    connection = st.connect(app_mod.DB)
    st.init_db(connection)
    yield connection
    connection.close()


def submit(admin, action, **values):
    page = admin.get('/admin/appearance')
    assert page.status_code == 200
    data = {name: re.search(r'name="' + name + r'" value="([^"]*)"', page.text)[1]
            for name in ('csrf', 'revision')}
    return admin.post('/admin/appearance', data={**data, 'action': action, **values}, follow_redirects=False)


def event(**values):
    return {'name': 'Halloween', 'theme': 'halloween', 'outfit': 'halloween', 'effects': '1',
            'start': '2026-10-01T00:00', 'end': '2026-11-01T00:00',
            'timezone': 'Asia/Manila', 'status': 'published', **values}


def test_boundary_precedence_expiry_and_monthly_rollover():
    config = rules.initial()
    config['events'] = [{'id': 'one', 'name': 'Season', 'selection': rules.selection('halloween', 'christmas', True),
                         'start': 100, 'end': 200, 'status': 'published'}]
    assert rules.resolve(config, 99)['source'] == 'default'
    active = rules.resolve(config, 100)
    assert (active['theme'], active['outfit'], active['month'], active['next_transition']) == ('halloween', 'christmas', 12, 200)
    assert rules.resolve(config, 200)['source'] == 'default'
    config['override'] = {'selection': rules.selection('christmas', 'default'), 'expires_at': 150}
    assert rules.resolve(config, 149)['source'] == 'manual'
    assert rules.resolve(config, 149)['next_transition'] == 150
    assert rules.resolve(config, 150)['source'] == 'scheduled'
    config['override']['expires_at'] = None
    assert rules.resolve(config, 150)['next_transition'] is None
    config = rules.initial()
    before = rules.local_timestamp('2026-10-31T23:59')
    after = rules.local_timestamp('2026-11-01T00:00')
    assert rules.resolve(config, before)['next_transition'] == after
    assert rules.resolve(config, before)['month'] == 10
    assert rules.resolve(config, after)['month'] == 11


@pytest.mark.parametrize('date,zone', [('2026-02-30T12:00', 'Asia/Manila'), ('2026-01-01T12:00', 'Unknown/Zone'),
    ('2026-03-08T02:30', 'America/New_York'), ('2026-11-01T01:30', 'America/New_York'),
    ('2026-01-01T12:00+08:00', 'Asia/Manila')])
def test_invalid_or_ambiguous_wall_times(date, zone):
    with pytest.raises(ValueError):
        rules.local_timestamp(date, zone)


def test_overlap_atomicity_adjacent_windows_and_stale_edit(conn):
    config = store.mutate(conn, 'admin', 0, 'event', event())
    with pytest.raises(ValueError, match='overlaps'):
        store.mutate(conn, 'admin', config['revision'], 'event', event(name='Conflicting Christmas', theme='christmas'))
    assert store.load(conn) == config
    adjacent = store.mutate(conn, 'admin', config['revision'], 'event', event(name='Next event', start='2026-11-01T00:00', end='2026-12-01T00:00'))
    assert len(adjacent['events']) == 2
    with pytest.raises(ValueError, match='Another administrator'):
        store.mutate(conn, 'admin', config['revision'], 'reset', {})
    assert store.load(conn) == adjacent
    assert st.verify_audit_chain(conn) == (True, None)


def test_drafts_disabled_events_override_reset_resume_and_restore(conn):
    initial = store.load(conn)
    config = store.mutate(conn, 'admin', 0, 'draft', {'theme': 'christmas', 'outfit': 'halloween'})
    assert rules.resolve(config)['theme'] == 'default'
    assert not store.history(conn)
    config = store.mutate(conn, 'admin', config['revision'], 'event', event(status='draft'))
    assert rules.resolve(config)['source'] == 'default'
    config = store.mutate(conn, 'admin', config['revision'], 'event', event(event_id=config['events'][0]['id']))
    assert rules.resolve(config)['source'] == 'scheduled'
    snapshot = store.history(conn)[0]['id']
    config = store.mutate(conn, 'admin', config['revision'], 'reset', {})
    assert rules.resolve(config)['theme'] == 'default'
    assert rules.resolve(config)['source'] == 'manual'
    config = store.mutate(conn, 'admin', config['revision'], 'resume', {})
    assert rules.resolve(config)['theme'] == 'halloween'
    config = store.mutate(conn, 'admin', config['revision'], 'event', event(event_id=config['events'][0]['id'], status='disabled'))
    assert rules.resolve(config)['source'] == 'default'
    old_revision = config['revision']
    config = store.mutate(conn, 'admin', old_revision, 'restore', {'history_id': snapshot})
    assert config['revision'] == old_revision + 1
    assert rules.resolve(config)['theme'] == 'halloween'
    assert store.history(conn)[0]['action'] == 'restore'
    assert initial['revision'] == 0


@pytest.mark.parametrize('values', [{'theme': 'unknown', 'outfit': 'default'},
    {'theme': 'default', 'outfit': 'unknown'}, {'theme': 'christmas', 'outfit': 'default', 'expires': '2020-01-01T00:00'}])
def test_bad_publications_rollback(conn, values):
    with pytest.raises(ValueError):
        store.mutate(conn, 'admin', 0, 'publish', values)
    assert store.load(conn) == rules.initial()
    assert not store.history(conn)


def test_editor_draft_publish_preview_isolation_and_public_payload(admin, viewer, conn):
    assert 'Themes &amp; avatar' in admin.get('/admin/appearance').text
    assert submit(admin, 'draft', theme='christmas', outfit='halloween', effects='1').status_code == 303
    assert viewer.get('/appearance/current').json()['theme'] == 'default'
    preview = admin.get('/?view=me&appearance_preview=1&theme=christmas&outfit=halloween&effects=1')
    assert preview.status_code == 200, preview.text[:500]
    assert 'data-season="christmas"' in preview.text
    assert 'Private appearance preview' in preview.text
    assert viewer.get('/appearance/current').json()['theme'] == 'default'
    assert 'data-season="default"' in viewer.get('/me?appearance_preview=1&theme=christmas').text
    assert submit(admin, 'publish', theme='halloween', outfit='christmas', effects='1').status_code == 303
    public = viewer.get('/appearance/current')
    assert public.json()['theme'] == 'halloween' and public.json()['month'] == 12
    assert 'no-store' in public.headers['cache-control']
    assert not {'draft', 'events', 'actor', 'override'} & public.json().keys()
    avatar = viewer.get('/appearance/avatar/cat/3')
    assert avatar.status_code == 200 and 'data-avatar-month="12"' in avatar.text
    assert viewer.get('/appearance/avatar/dragon/3').status_code == 404
    assert viewer.get('/appearance/avatar/cat/7').status_code == 404
    assert submit(admin, 'resume').status_code == 303
    assert viewer.get('/appearance/current').json()['source'] == 'default'
    assert st.verify_audit_chain(conn) == (True, None)


def test_schedule_routes_edit_disable_remove_and_overlap_errors(admin, viewer, conn):
    assert submit(admin, 'event', **event()).status_code == 303
    assert viewer.get('/appearance/current').json()['source'] == 'scheduled'
    response = submit(admin, 'event', **event(name='Conflicting <Christmas>'))
    assert response.status_code == 400 and 'overlaps' in response.text
    assert 'Conflicting &lt;Christmas&gt;' in response.text
    item = store.load(conn)['events'][0]
    page = admin.get('/admin/appearance?edit=' + item['id'])
    assert 'value="2026-10-01T00:00"' in page.text
    assert submit(admin, 'event', **event(event_id=item['id'], status='disabled')).status_code == 303
    assert viewer.get('/appearance/current').json()['source'] == 'default'
    assert submit(admin, 'delete_event', event_id=item['id']).status_code == 303
    assert not store.load(conn)['events']


def test_access_csrf_origin_and_revision_guards(admin, viewer, encoder, manager, client):
    for other in (viewer, encoder, manager):
        assert other.get('/admin/appearance').status_code == 403
        assert other.post('/admin/appearance', data={'action': 'reset'}).status_code == 403
    assert client.get('/admin/appearance', follow_redirects=False).status_code == 303
    assert client.get('/appearance/current', follow_redirects=False).status_code == 303
    assert admin.post('/admin/appearance', data={'action': 'reset'}).status_code == 400
    page = admin.get('/admin/appearance')
    csrf = re.search(r'name="csrf" value="([^"]*)"', page.text)[1]
    assert admin.post('/admin/appearance', data={'csrf': csrf, 'action': 'reset', 'revision': '0'},
                      headers={'Origin': 'https://evil.example'}).status_code == 403
    assert submit(admin, 'reset').status_code == 303
    response = admin.post('/admin/appearance', data={'csrf': csrf, 'action': 'resume', 'revision': '0'})
    assert response.status_code == 400 and 'Another administrator' in response.text


def test_avatar_art_all_species_stages_outfits_and_request_context(app_mod):
    module = app_mod.templates.env.get_template('_avatars.html').module
    for month in (0, 10, 12):
        token = rules.current.set({**rules.selection('halloween', 'halloween'), 'month': month})
        try:
            for species in st.AVATAR_CATALOG:
                for stage in range(1, 7):
                    svg = str(module.avatar_svg(species['key'], stage, month))
                    assert f'data-avatar-month="{month}"' in svg
                    assert 'class="av-acc"' in svg
        finally:
            rules.current.reset(token)
    assert rules.current.get() is None


def test_parallel_preview_context_does_not_bleed(admin):
    def preview(theme):
        return admin.get('/me?appearance_preview=1&theme=' + theme + '&outfit=' + theme).text
    with ThreadPoolExecutor(max_workers=2) as workers:
        halloween, christmas = workers.map(preview, ('halloween', 'christmas'))
    assert 'data-season="halloween"' in halloween and 'data-avatar-month="10"' in halloween
    assert 'data-season="christmas"' in christmas and 'data-avatar-month="12"' in christmas
    assert admin.get('/appearance/current').json()['theme'] == 'default'


def test_legacy_configuration_and_history_get_visual_defaults(conn):
    legacy = {'revision': 7, 'default': {'theme': 'halloween', 'outfit': 'halloween', 'effects': False},
              'draft': {'theme': 'default', 'outfit': 'monthly', 'effects': False}, 'override': None, 'events': []}
    st.set_setting(conn, store.KEY, json.dumps(legacy))
    conn.execute('INSERT INTO appearance_history(created_at,actor,action,snapshot) VALUES (?,?,?,?)',
                 (1, 'admin', 'legacy publication', json.dumps(legacy)))
    conn.commit()
    current = rules.resolve(store.load(conn))
    assert current['artwork'] and current['banner'] == rules.BANNER and not current['effects']
    restored = store.mutate(conn, 'admin', 7, 'restore', {'history_id': 1})
    assert restored['default']['artwork'] and restored['draft']['artwork'] is False


def test_artwork_animation_and_banner_roundtrip_and_escape(admin, viewer, conn):
    message = '<script>alert("boo")</script> Welcome!'
    result = submit(admin, 'publish', theme='halloween', outfit='halloween_vampire',
                    artwork_present='1', banner=message)
    assert result.status_code == 303
    active = viewer.get('/appearance/current').json()
    assert active['artwork'] is False and active['effects'] is False and active['banner'] == message
    page = viewer.get('/me').text
    assert 'data-season-artwork="0"' in page
    assert '&lt;script&gt;alert' in page and message not in page
    assert submit(admin, 'publish', theme='halloween', outfit='halloween_pumpkin',
                  artwork_present='1', artwork='1', effects='1', banner='Boo, team!').status_code == 303
    active = viewer.get('/appearance/current').json()
    assert active['artwork'] and active['effects'] and active['outfit'] == 'halloween_pumpkin'
    revision = store.load(conn)['revision']
    result = submit(admin, 'publish', theme='halloween', outfit='halloween', banner='x' * 101)
    assert result.status_code == 400 and store.load(conn)['revision'] == revision


def test_three_costumes_render_for_every_species_and_growth_stage(app_mod):
    module = app_mod.templates.env.get_template('_avatars.html').module
    for species in st.AVATAR_CATALOG:
        for stage in range(1, 7):
            variants = []
            for outfit in ('halloween', 'halloween_vampire', 'halloween_pumpkin'):
                svg = ET.fromstring(str(module.avatar_svg(species['key'], stage, 10, outfit)))
                assert svg.attrib['data-avatar-outfit'] == outfit
                assert svg.find('.//g[@class="av-costume-back"]/path') is not None or svg.find('.//g[@class="av-costume-back"]/ellipse') is not None
                if stage > 1:
                    assert svg.find('.//g[@class="av-regalia"]') is not None
                variants.append(ET.tostring(svg))
            assert len(set(variants)) == 3
