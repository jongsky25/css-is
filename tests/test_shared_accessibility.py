"""Real shared controls: keyboard journeys, accessible trees and responsive layout.

Chromium's accessibility tree is automated evidence, not a screen-reader session.
All browser writes are intercepted; no external services or staff data are used.
"""
from urllib.parse import urlsplit

import re

import pytest
import storage as st
from playwright.sync_api import expect
from tests.test_document_guidance_browser import browser


@pytest.fixture
def shell_page(browser, app_mod, viewer, sample_ids):
    with st.connect(app_mod.DB) as conn:
        st.set_setting(conn, 'spot_feedback_enabled', '1')
        conn.commit()
    context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                  service_workers='block', reduced_motion='reduce')
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    page = context.new_page()
    state = {'posts': [], 'errors': [], 'overrides': {}, 'responses': {}, 'get_responses': {}}
    page.on('pageerror', lambda error: state['errors'].append(str(error)))

    def serve(route):
        request = route.request
        url = urlsplit(request.url)
        if url.hostname != 'office.test':
            route.abort()
            return
        path = url.path + ('?' + url.query if url.query else '')
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            state['posts'].append(path)
            status, body = state['responses'].get(path, (200, '{"ok":true,"counted":true}'))
            route.fulfill(status=status, content_type='application/json', body=body)
            return
        if path in state['get_responses']:
            route.fulfill(status=200, content_type='application/json', body=state['get_responses'][path])
            return
        if path in state['overrides']:
            route.fulfill(status=200, content_type='text/html', body=state['overrides'][path])
            return
        response = viewer.get(path, follow_redirects=False)
        route.fulfill(status=response.status_code, body=response.content, headers={
            k: v for k, v in response.headers.items()
            if k.lower() not in ('content-length', 'content-encoding', 'set-cookie')})

    page.route('**/*', serve)
    yield page, state, context, sample_ids
    context.close()
    assert not state['errors']


@pytest.fixture
def component_page(shell_page, app_mod):
    page, state, context, ids = shell_page
    state['overrides']['/__a16_components'] = app_mod.templates.env.from_string('''
<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shared components</title><link rel="stylesheet" href="/static/css/app.css">
<script src="/static/js/accessibility.js" defer></script><script src="/static/js/app.js" defer></script>
<script src="/static/js/deck.js" defer></script></head><body>
{% from '_components.html' import deck_defs, deck, deck_slide, field, error_summary %}
{{ deck_defs() }}<main id="maincontent" tabindex="-1" style="padding:1rem;max-width:55rem;margin:auto">
<h1>Shared components</h1>
{% call deck('Office readings') %}
{% call deck_slide('First view') %}<a href="#first">First reading</a>
<label for="caret">Reading note</label><input id="caret" value="office">{% endcall %}
{% call deck_slide('Second view') %}<a href="#second">Second reading</a>{% endcall %}
{% call deck_slide('Third view') %}<a href="#third">Third reading</a>{% endcall %}
{% endcall %}
<form method="post" action="/__a16_save">{{ error_summary({'title':'Enter a title'}) }}
{{ field('title','Title',error='Enter a title',required=true) }}
<button type="submit">Save</button></form></main></body></html>
''').render()
    return shell_page


@pytest.fixture
def snapshot_page(shell_page, app_mod, viewer):
    page, state, context, ids = shell_page
    values = dict(viewer.get('/css').context)
    values.update(snapshot={'user_id': 999999, 'first_name': 'Test colleague', 'score': None,
                            'role': 'arta', 'trend_dir': None, 'standing': None, 'weakest_dim': None},
                  today='2026-10-20')
    state['overrides']['/__a16_snapshot'] = app_mod.templates.env.get_template('home.html').render(values)
    return shell_page


def goto(page, path='/'):
    page.goto('http://office.test' + path)
    expect(page.locator('main')).to_be_visible()


def accessible_names(page):
    session = page.context.new_cdp_session(page)
    try:
        nodes = session.send("Accessibility.getFullAXTree")["nodes"]
        return {node.get("name", {}).get("value", "") for node in nodes if not node["ignored"]}
    finally:
        session.detach()


def assert_no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_desktop_dropdowns_and_focus_ring(shell_page, theme):
    page, state, *_ = shell_page
    goto(page)
    page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
    trigger = page.locator('.navgroup > summary').first
    trigger.focus()
    trigger.press('Enter')
    expect(page.locator('.navgroup[open]')).to_have_count(1)
    page.keyboard.press('Tab')
    expect(page.locator('.navgroup[open] a').first).to_be_focused()
    style = page.locator(':focus').evaluate('(el) => ({style:getComputedStyle(el).outlineStyle,width:getComputedStyle(el).outlineWidth})')
    assert style == {'style': 'solid', 'width': '2px'}
    page.keyboard.press('Escape')
    expect(trigger).to_be_focused()
    expect(page.locator('.navgroup[open]')).to_have_count(0)
    settings = page.locator('.right > .settings:not(.helpmenu) > summary')
    settings.focus()
    settings.press('Enter')
    page.keyboard.press('Tab')
    assert page.locator('.settings-menu').first.evaluate('(el) => el.contains(document.activeElement)')
    page.keyboard.press('Escape')
    expect(settings).to_be_focused()
    assert not state['posts']


@pytest.mark.parametrize('width', [320, 390])
def test_mobile_drawer_wraps_focus_and_restores_background(shell_page, width):
    page, state, *_ = shell_page
    page.set_viewport_size({'width': width, 'height': 844})
    goto(page)
    # A pre-existing inert region belongs to its caller and must survive dismissal.
    page.evaluate("document.querySelector('.brand').inert=true")
    trigger = page.locator('.nav-toggle > summary')
    trigger.focus()
    trigger.press('Enter')
    close = page.get_by_role('button', name='Close menu', exact=True)
    expect(close).to_be_focused()
    assert page.locator('main').evaluate('(el) => !!el.closest("[inert]")')
    assert trigger.evaluate('(el) => el.inert')
    close.press('Shift+Tab')
    expect(page.locator('.mm-logout')).to_be_focused()
    page.keyboard.press('Tab')
    expect(close).to_be_focused()
    assert_no_overflow(page)
    page.keyboard.press('Escape')
    expect(trigger).to_be_focused()
    assert not page.locator('main').evaluate('(el) => !!el.closest("[inert]")')
    assert page.locator('.brand').evaluate('(el) => el.inert')
    trigger.press('Enter')
    expect(close).to_be_focused()
    page.set_viewport_size({'width': 1440, 'height': 1000})
    expect(page.locator('.nav-toggle')).not_to_have_attribute('open', '')
    expect(page.locator('main')).to_be_focused()
    assert not page.locator('main').evaluate('(el) => !!el.closest("[inert]")')
    assert not state['posts']


@pytest.mark.parametrize('width', [390, 1440])
def test_search_dialog_and_nested_drawer_restore_focus(shell_page, width):
    page, state, *_ = shell_page
    page.set_viewport_size({'width': width, 'height': 844})
    goto(page)
    opener = page.locator('#navSearchBtn')
    opener.focus()
    opener.press('Enter')
    search = page.get_by_role('combobox', name='Search pages and records')
    close = page.get_by_role('button', name='Close search')
    expect(search).to_be_focused()
    expect(opener).to_have_attribute('aria-expanded', 'true')
    search.press('Shift+Tab')
    expect(close).to_be_focused()
    close.press('Tab')
    expect(search).to_be_focused()
    search.press('ArrowDown')
    assert search.get_attribute('aria-activedescendant')
    search.press('Escape')
    expect(opener).to_be_focused()
    expect(opener).to_have_attribute('aria-expanded', 'false')
    if width < 900:
        page.locator('.nav-toggle > summary').click()
        drawer_close = page.get_by_role('button', name='Close menu')
        expect(drawer_close).to_be_focused()
        page.keyboard.press('Control+k')
        expect(search).to_be_focused()
        page.keyboard.press('Escape')
        expect(drawer_close).to_be_focused()
        assert page.locator('main').evaluate('(el) => el.inert')
        assert not page.locator('.mobile-menu').evaluate('(el) => !!el.closest("[inert]")')
        page.keyboard.press('Escape')
        expect(page.locator('.nav-toggle > summary')).to_be_focused()
    else:
        opener.press('Enter')
        close.click()
        expect(opener).to_be_focused()
    assert not state['posts']


@pytest.mark.parametrize('width', [390, 1440])
def test_feedback_keyboard_pointer_error_and_cancel(shell_page, width):
    page, state, *_ = shell_page
    page.set_viewport_size({'width': width, 'height': 844})
    goto(page)
    opener = page.get_by_role('button', name='Send feedback about this page')
    opener.focus()
    opener.press('Enter')
    text = page.get_by_role('textbox', name='Your feedback')
    expect(text).to_be_focused()
    expect(page.locator('.sf-target')).to_contain_text('This page')
    text.press('Shift+Tab')
    expect(page.locator('.sf-send')).to_be_focused()
    page.keyboard.press('Tab')
    expect(text).to_be_focused()
    page.locator('.sf-send').click()
    expect(text).to_be_focused()
    assert not state['posts']
    state['responses']['/feedback'] = (403, 'Request could not be verified')
    text.fill('Keyboard feedback')
    page.locator('.sf-send').click()
    expect(page.locator('.sf-err')).to_contain_text('Your message is kept')
    expect(text).to_have_value('Keyboard feedback')
    assert 'alert' in page.locator('.sf-backdrop').aria_snapshot()
    page.keyboard.press('Escape')
    expect(opener).to_be_focused()
    # Pointer selection retains the original targeted-feedback journey.
    opener.click()
    expect(page.locator('body')).to_have_class(re.compile('sf-picking'))
    page.locator('h1').first.click()
    expect(text).to_be_focused()
    expect(page.locator('.sf-target')).not_to_contain_text('This page')
    page.locator('.sf-cancel').click()
    expect(opener).to_be_focused()
    assert state['posts'] == ['/feedback']


def test_tour_hidden_back_is_excluded_and_escape_restores(shell_page):
    page, state, *_ = shell_page
    goto(page, '/?tour=1')
    card = page.get_by_role('dialog', name=re.compile('.+'))
    next_button = page.locator('.tour-next')
    expect(next_button).to_be_focused()
    assert 'button "Back"' not in card.aria_snapshot()
    next_button.press('Tab')
    expect(page.locator('.tour-skip')).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(next_button).to_be_focused()
    page.keyboard.press('Escape')
    expect(page.locator('.tour-card')).to_have_count(0)
    expect(page.locator('main')).to_be_focused()
    assert not page.locator('main').evaluate('(el) => el.inert')
    assert not state['posts']


def test_snapshot_daily_dismissal_and_focus(snapshot_page):
    page, state, *_ = snapshot_page
    goto(page, '/__a16_snapshot')
    close = page.locator('#snapshot-close')
    expect(close).to_be_focused()
    close.press('Shift+Tab')
    expect(page.locator('#snapshot-optout')).to_be_focused()
    page.keyboard.press('Tab')
    expect(close).to_be_focused()
    page.keyboard.press('Escape')
    expect(page.locator('#snapshot-bd')).to_be_hidden()
    expect(page.locator('main')).to_be_focused()
    page.reload()
    expect(page.locator('#snapshot-bd')).to_be_hidden()
    assert not page.locator('main').evaluate('(el) => el.inert')
    assert not state['posts']


@pytest.mark.parametrize('width', [320, 390, 720])
def test_growth_strip_keyboard_scroll_and_reflow(shell_page, width):
    page, state, *_ = shell_page
    page.set_viewport_size({'width': width, 'height': 844})
    goto(page)
    strip = page.locator('.gl-strip').first
    expect(strip).to_have_attribute('tabindex', '0')
    strip.focus()
    expect(strip).to_be_focused()
    if strip.evaluate('(el) => el.scrollWidth > el.clientWidth'):
        strip.press('ArrowRight')
        page.wait_for_function('document.querySelector(".gl-strip").scrollLeft > 0')
    assert_no_overflow(page)
    # Larger text must remain readable in the narrow viewport as well.
    page.evaluate('document.documentElement.style.fontSize="200%"')
    assert_no_overflow(page)
    assert not state['posts']


def test_avatar_native_sibling_controls_and_single_care(shell_page):
    page, state, *_ = shell_page
    goto(page, '/wellness')
    avatar = page.locator('.avwrap[data-interactive]').first
    play = avatar.locator('.av-play-btn')
    care = avatar.locator('.av-care-btn')
    sound = avatar.locator('.av-sound-btn')
    assert avatar.get_attribute('role') == 'group'
    assert not avatar.locator('button button').count()
    tree = avatar.aria_snapshot()
    assert 'button "Play with ' in tree and 'button "Turn companion sounds' in tree
    play.focus()
    play.press('Space')
    expect(avatar.locator('.av-bubble')).to_have_class(re.compile('show'))
    assert not state['posts']
    care.focus()
    care.press('Enter')
    page.wait_for_function('document.querySelector(".av-care-btn").disabled === false')
    assert state['posts'] == ['/avatar/care']
    sound.focus()
    sound.press('Space')
    expect(sound).to_have_attribute('aria-pressed', 'true')
    assert state['posts'] == ['/avatar/care']


@pytest.mark.parametrize('width', [320, 1440])
def test_deck_semantics_navigation_caret_and_resize(component_page, width):
    page, state, *_ = component_page
    page.set_viewport_size({'width': width, 'height': 844})
    goto(page, '/__a16_components')
    deck = page.get_by_role('group', name='Office readings', exact=True)
    dots = page.get_by_role('group', name='Choose a view').get_by_role('button')
    expect(dots).to_have_count(3)
    assert not page.get_by_role('tablist').count()
    for button in dots.all():
        size = button.bounding_box()
        assert size['width'] >= 44 and size['height'] >= 44
        assert page.locator('#' + button.get_attribute('aria-controls')).count() == 1
    # Inactive slides do not expose links to the accessibility tree or tab order.
    assert 'First reading' in accessible_names(page)
    assert 'Second reading' not in accessible_names(page)
    caret = page.get_by_role('textbox', name='Reading note')
    caret.focus()
    caret.evaluate('(el) => el.setSelectionRange(0,0)')
    caret.press('ArrowRight')
    assert caret.evaluate('(el) => el.selectionStart') == 1
    expect(page.locator('.deck-ind')).to_have_text('View 1 of 3')
    dots.nth(0).focus()
    dots.nth(0).press('ArrowRight')
    expect(dots.nth(1)).to_be_focused()
    expect(page.locator('.deck-ind')).to_have_text('View 2 of 3')
    expect(dots.nth(1)).to_have_attribute('aria-current', 'true')
    assert 'First reading' not in accessible_names(page)
    assert 'Second reading' in accessible_names(page)
    dots.nth(1).press('End')
    expect(page.locator('.deck-ind')).to_have_text('View 3 of 3')
    dots.nth(2).press('Home')
    expect(page.locator('.deck-ind')).to_have_text('View 1 of 3')
    next_button = page.get_by_role('button', name='Next view')
    next_button.click()
    expect(page.locator('.deck-ind')).to_have_text('View 2 of 3')
    next_button.click()
    expect(dots.nth(2)).to_be_focused()
    page.set_viewport_size({'width': 720 if width == 320 else 390, 'height': 844})
    expect(page.locator('.deck-ind')).to_have_text('View 3 of 3')
    assert_no_overflow(page)
    assert not state['posts']


def test_validation_preserves_name_error_description_and_keyboard_recovery(component_page):
    page, state, *_ = component_page
    goto(page, '/__a16_components')
    title = page.get_by_role('textbox', name='Title', exact=True)
    expect(title).to_be_focused()
    expect(title).to_have_attribute('aria-invalid', 'true')
    expect(title).to_have_accessible_description('Enter a title')
    page.get_by_role('link', name='Enter a title').click()
    expect(title).to_be_focused()
    page.get_by_role('button', name='Save', exact=True).click()
    expect(title).to_be_focused()
    assert not state['posts']


@pytest.mark.parametrize('theme', ['light', 'dark', 'contrast'])
def test_survey_na_targets_and_muted_text_contrast(shell_page, theme):
    page, state, context, ids = shell_page
    goto(page, '/r/' + ids['qr_token'])
    page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
    na = page.locator('.na-row input').first
    expect(na).to_have_accessible_name('Not applicable')
    size = na.bounding_box()
    assert size['width'] >= 24 and size['height'] >= 24
    na.focus()
    na.press('Space')
    expect(na).to_be_checked()
    assert page.locator('.na-row label').first.bounding_box()['height'] >= 44
    # Calculate actual rendered foreground/background contrast; no dependency on a token value.
    ratio = page.locator('.pub-foot').evaluate('''el => {
      const rgb=s=>s.match(/[\\d.]+/g).slice(0,3).map(Number);
      const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4})
        .reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
      let bg, node=el;
      while(node){const c=getComputedStyle(node).backgroundColor;
        if(c!=='rgba(0, 0, 0, 0)' && c!=='transparent'){bg=c;break}node=node.parentElement}
      const a=lum(rgb(getComputedStyle(el).color)),b=lum(rgb(bg||'rgb(255,255,255)'));
      return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    }''')
    assert ratio >= 4.5
    assert not state['posts']


def test_public_display_settings_are_keyboard_operable(shell_page):
    page, state, context, ids = shell_page
    goto(page, '/r/' + ids['qr_token'])
    trigger = page.locator('.pub-top .settings > summary')
    expect(trigger).to_have_accessible_name('Display settings')
    trigger.focus()
    trigger.press('Enter')
    dark = page.get_by_role('button', name='Dark', exact=True)
    dark.focus()
    dark.press('Enter')
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    page.keyboard.press('Escape')
    expect(trigger).to_be_focused()
    expect(dark).to_be_hidden()
    assert not state['posts']


def test_search_dynamic_options_and_scoped_exit_keep_single_interactive_control(shell_page):
    import json
    page, state, *_ = shell_page
    state['get_responses']['/api/search?q=zzrecord'] = json.dumps([
        {'title': 'ZZ record', 'url': '/help', 'hint': 'Synthetic record', 'section': 'People'}])
    goto(page)
    page.keyboard.press('Control+k')
    search = page.get_by_role('combobox', name='Search pages and records')
    search.fill('zzrecord')
    option = page.get_by_role('option', name='ZZ record Synthetic record People')
    expect(option).to_be_visible()
    assert option.evaluate('(el) => el.tagName') == 'A'
    assert not page.locator('[role=option] a, [role=option] button').count()
    search.press('ArrowDown')
    expect(option).to_have_attribute('aria-selected', 'true')
    expect(search).to_have_attribute('aria-activedescendant', option.get_attribute('id'))
    option.hover()
    search.press('Enter')
    page.wait_for_url('http://office.test/help')
    goto(page, '/css')
    scoped = page.locator('.gsearch-input')
    scoped.fill('zznothing')
    exit_option = page.get_by_role('option', name=re.compile('Search everything for'))
    expect(exit_option).to_be_visible()
    assert exit_option.evaluate('(el) => el.tagName') == 'A'
    scoped.press('Enter')
    expect(page.locator('#cmdkInput')).to_be_focused()
    expect(page.locator('#cmdkInput')).to_have_value('zznothing')
    assert not state['posts']


def test_deck_native_scroll_without_javascript(component_page):
    page, state, context, ids = component_page
    # Disable scripts on this page through CDP while retaining the same real assets/fixture routes.
    session = context.new_cdp_session(page)
    session.send('Emulation.setScriptExecutionDisabled', {'value': True})
    page.set_viewport_size({'width': 320, 'height': 844})
    page.goto('http://office.test/__a16_components')
    expect(page.locator('.deck-nav')).to_have_count(0)
    first = page.get_by_role('link', name='First reading')
    second = page.get_by_role('link', name='Second reading')
    first.focus()
    first.press('Tab')
    expect(page.get_by_role('textbox', name='Reading note')).to_be_focused()
    page.keyboard.press('Tab')
    expect(second).to_be_focused()
    session.send('Emulation.setScriptExecutionDisabled', {'value': False})
    page.wait_for_function('document.querySelector(".deck-track").scrollLeft > 0')
    assert_no_overflow(page)
    session.detach()
    assert not state['posts']
