"""Configured New Year boundaries and real appearance routes/browser updates."""
import pytest

import appearance as rules
import appearance_storage as store
from tests.test_appearance import submit, conn
from tests.test_appearance_browser import seasonal_browser, page_for, pw


def test_target_timezone_fixed_year_and_saved_preferences():
    config = rules.initial()
    config['default'] = rules.selection('newyear', 'christmas', False, False, 'Our greeting', 2027)
    target = rules.local_timestamp('2027-01-01T00:00')
    assert target == rules.local_timestamp('2026-12-31T16:00', 'UTC')
    before, after = [rules.resolve(config, target + offset) for offset in (-1, 1)]
    assert before['newyear_target'] == after['newyear_target'] == target
    assert after['target_year'] == 2027 and after['banner'] == 'Our greeting'
    assert not after['effects'] and not after['artwork'] and after['outfit'] == 'christmas'
    assert rules.selection('christmas')['banner'] != rules.BANNER


@pytest.mark.parametrize('year', ['bad', '', '2027.0', 2026, 2101, True, None])
def test_invalid_target_year(year):
    with pytest.raises(ValueError, match='target'):
        rules.selection('newyear', target_year=year)


def test_schedule_requires_target_and_failure_is_atomic(conn):
    data = dict(name='New Year', theme='newyear', outfit='default', target_year='2027',
                start='2026-12-28T00:00', end='2027-01-08T00:00', status='published')
    saved = store.mutate(conn, 'test', 0, 'event', data)
    with pytest.raises(ValueError, match='include midnight'):
        store.mutate(conn, 'test', 1, 'event', {**data, 'target_year': '2028'})
    assert store.load(conn) == saved
    assert rules.resolve(saved, rules.local_timestamp('2027-01-08T00:00'))['theme'] == 'default'


def test_preview_target_does_not_publish(admin, viewer):
    response = admin.get('/?appearance_preview=1&theme=newyear&outfit=default&target_year=2028')
    assert response.status_code == 200
    assert 'data-year="2028"' in response.text
    assert viewer.get('/appearance/current').json()['theme'] == 'default'
    assert admin.get('/?appearance_preview=1&theme=newyear&target_year=no').status_code == 400


def test_countdown_real_home_wrong_device_clock_and_live_form(seasonal_browser, admin, viewer, monkeypatch):
    target = rules.newyear_target(2027)
    original = rules.resolve
    monkeypatch.setattr(rules, 'resolve', lambda config, now=None: original(config, target - 3))
    assert submit(admin, 'publish', theme='newyear', outfit='default', target_year='2027',
                  artwork_present='1', artwork='1', effects='1').status_code == 303
    context, page = page_for(seasonal_browser, viewer, viewport={'width': 390, 'height': 844})
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        page.clock.install(time=rules.local_timestamp('2030-01-01T00:00') * 1000)
        page.goto('http://testserver/?view=me')
        pw.expect(page.locator('[data-countdown]')).to_be_visible()
        assert page.locator('[data-countdown-unit=days]').inner_text() == '00'
        page.clock.fast_forward(3500)
        pw.expect(page.locator('[data-newyear-greeting]')).to_be_visible()
        pw.expect(page.locator('[data-countdown]')).to_be_hidden()
        assert page.locator('.celebrating').count() == 1
        page.clock.fast_forward(4500)
        assert page.locator('.celebrating').count() == 0
        page.goto('http://testserver/me')
        page.locator('#avatar_name').fill('Preserve this edit')
        assert submit(admin, 'publish', theme='christmas', outfit='christmas',
                      artwork_present='1', artwork='1').status_code == 303
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        pw.expect(page.locator('html')).to_have_attribute('data-season','christmas')
        pw.expect(page.locator('#avatar_name')).to_have_value('Preserve this edit')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.emulate_media(media='print')
        pw.expect(page.locator('.celebration')).to_be_hidden()
        assert not errors
    finally:
        context.close()


def test_post_midnight_no_script_fallback_and_independent_artwork(seasonal_browser, admin, viewer, monkeypatch):
    original = rules.resolve
    monkeypatch.setattr(rules, 'resolve', lambda config, now=None: original(config, rules.newyear_target(2027) + 1))
    assert submit(admin, 'publish', theme='newyear', outfit='default', target_year='2027',
                  artwork_present='1').status_code == 303
    context, page = page_for(seasonal_browser, viewer, java_script_enabled=False)
    try:
        page.goto('http://testserver/?view=me')
        pw.expect(page.locator('[data-newyear-greeting]')).to_be_visible()
        pw.expect(page.locator('.newyear-date')).to_contain_text('2027')
        pw.expect(page.locator('.celebration-art')).to_be_hidden()
        assert page.locator('.celebrating').count() == 0
    finally:
        context.close()


def test_real_seasonal_layouts_and_accessibility_modes(seasonal_browser, admin, viewer, tmp_path):
    context, page = page_for(seasonal_browser, viewer, reduced_motion='reduce')
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    try:
        for theme in ('christmas', 'newyear'):
            assert submit(admin, 'publish', theme=theme, outfit='christmas',
                          artwork_present='1', artwork='1', effects='1').status_code == 303
            for width in (320, 390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 900})
                for mode in ('light', 'dark'):
                    for path in ('/?view=me', '/me'):
                        page.goto('http://testserver' + path)
                        page.evaluate('(mode)=>{document.documentElement.dataset.theme=mode;document.documentElement.dataset.textscale="lg";}', mode)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme, width, mode, path)
                    if width in (390, 1440):
                        page.goto('http://testserver/?view=me')
                        page.evaluate('(mode)=>document.documentElement.dataset.theme=mode', mode)
                        page.screenshot(path=str(tmp_path / f'{theme}-{mode}-{width}.png'), full_page=True)
            assert page.locator('.celebration-art').evaluate('(el)=>getComputedStyle(el).animationName') == 'none'
            page.evaluate('document.documentElement.dataset.theme="contrast"')
            assert page.evaluate('getComputedStyle(document.documentElement).getPropertyValue("--accent").trim()') == '#002060'
            pw.expect(page.locator('.celebration-art')).to_be_hidden()
    finally:
        context.close()
