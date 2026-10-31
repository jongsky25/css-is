"""Companion audio: real decoding, gesture playback and cancellation in Chromium."""
import hashlib
import json
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader
import pytest
from playwright.sync_api import expect

import storage as st
from tests.test_document_guidance_browser import browser

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'static/audio/avatars'
MANIFEST = json.loads((PACK / 'manifest.json').read_text())


@pytest.fixture
def audio_page(browser):
    env = Environment(loader=FileSystemLoader(ROOT / 'templates'), autoescape=True)
    env.globals.update(avatar_family=st.avatar_family, avatar_care_verb=st.avatar_care_verb,
                       avatar_is_swimmer=st.avatar_is_swimmer, avatar_month=lambda: 0,
                       avatar_outfit=lambda: 'default', avatar_uid=lambda: 'av-' + uuid4().hex)
    context = browser.new_context(viewport={'width': 390, 'height': 850},
                                  reduced_motion='reduce', service_workers='block')
    # Observe actual AudioBufferSourceNodes without replacing the audio engine.
    context.add_init_script('''
      window.audioStarts = []; window.liveVoices = new Set(); window.maxVoices = 0;
      const start = AudioBufferSourceNode.prototype.start;
      const stop = AudioBufferSourceNode.prototype.stop;
      AudioBufferSourceNode.prototype.start = function (...args) {
        if (this.buffer && this.buffer.length > 1) {
          audioStarts.push({duration:this.buffer.duration, rate:this.buffer.sampleRate});
          liveVoices.add(this); maxVoices = Math.max(maxVoices, liveVoices.size);
          this.addEventListener('ended', () => liveVoices.delete(this));
        }
        return start.apply(this, args);
      };
      AudioBufferSourceNode.prototype.stop = function (...args) {
        liveVoices.delete(this); return stop.apply(this, args);
      };
    ''')
    page = context.new_page()
    state = {'requests': [], 'posts': [], 'errors': []}
    page.on('pageerror', lambda error: state['errors'].append(str(error)))

    def serve(route):
        url = urlsplit(route.request.url)
        state['requests'].append(url.path)
        if route.request.method != 'GET':
            state['posts'].append(url.path)
            route.fulfill(status=200, content_type='application/json', body='{"ok":true}')
        elif url.path.startswith('/static/'):
            path = ROOT / url.path.lstrip('/')
            content_type = ('audio/mpeg' if path.suffix == '.mp3' else
                            'application/json' if path.suffix == '.json' else 'text/javascript')
            route.fulfill(status=200, content_type=content_type, body=path.read_bytes())
        else:
            html = env.from_string('''<!doctype html><html lang="en"><head><meta charset="utf-8">
              <meta name="viewport" content="width=device-width,initial-scale=1">
              <title>Companion audio test</title></head><body><main>
              {% from '_avatars.html' import avatar, avatar_defs %}{{ avatar_defs() }}
              <div class="av-play" style="width:300px;min-height:400px">
              {{ avatar(kind,3,name='Test companion',interactive=true,care=care,drag=true) }}
              </div></main></body></html>''').render(kind=state['kind'], care=state['care'])
            route.fulfill(status=200, content_type='text/html', body=html)

    page.route('**/*', serve)

    def open_page(kind='dog', care=False):
        state.update(kind=kind, care=care)
        page.goto('http://office.test/companion')
        page.wait_for_function('!!window.AvatarAudio')
        return page, state

    yield open_page
    context.close()
    assert not state['errors']


def test_pack_covers_catalog_with_credited_intact_assets():
    assert set(MANIFEST['species']) == st.AVATAR_KEYS
    used = set(MANIFEST['events']['water'])
    for species in MANIFEST['species'].values():
        assert species['voice']
        for files in species.values():
            used.update(files)
    assert used == set(MANIFEST['clips']) == {p.name for p in PACK.glob('*.mp3')}
    assert sum((PACK / name).stat().st_size for name in used) < 1_000_000
    for name, clip in MANIFEST['clips'].items():
        assert hashlib.sha256((PACK / name).read_bytes()).hexdigest() == clip['sha256']
        assert .1 < clip['duration_seconds'] < 3
        for layer in clip['layers']:
            source = MANIFEST['sources'][layer['source']]
            assert source['author'] and source['url'] and source['license_url']
            assert len(source['sha256']) == 64
    assert 'CC BY-SA 4.0' in (PACK / 'CREDITS.md').read_text()


def test_all_recordings_decode_to_audible_unclipped_mono(audio_page):
    page, _ = audio_page()
    results = page.evaluate('''async () => {
      const m = await (await fetch('/static/audio/avatars/manifest.json')).json();
      const ctx = new OfflineAudioContext(1, 44100, 44100), results = [];
      for (const name of Object.keys(m.clips)) {
        const buffer = await ctx.decodeAudioData(await (await fetch('/static/audio/avatars/' + name)).arrayBuffer());
        const values = buffer.getChannelData(0);
        let peak=0, energy=0;
        for (const v of values) { peak=Math.max(peak,Math.abs(v)); energy+=v*v; }
        results.push({name, channels:buffer.numberOfChannels, duration:buffer.duration,
                      peak, rms:Math.sqrt(energy/values.length)});
      }
      return results;
    }''')
    for result in results:
        assert result['channels'] == 1, result
        assert .002 < result['rms'] < .15, result
        assert .01 < result['peak'] < .8, result
        assert abs(result['duration'] - MANIFEST['clips'][result['name']]['duration_seconds']) < .06


@pytest.mark.parametrize('kind', sorted(st.AVATAR_KEYS))
def test_each_companion_plays_its_recording_on_home_toggle(audio_page, kind):
    page, state = audio_page(kind)
    assert not any('/audio/' in path for path in state['requests'])
    assert not page.evaluate('AvatarAudio.isOn()')
    assert page.locator('.av-care-btn').count() == 0
    page.locator('.av-sound-btn').focus()
    page.keyboard.press('Space')
    page.wait_for_function('audioStarts.length === 1')
    requested = {Path(path).name for path in state['requests'] if path.endswith('.mp3')}
    assert len(requested) == 1
    assert requested <= set(MANIFEST['species'][kind]['voice'])
    expect(page.locator('.av-volume')).to_be_visible()
    assert not state['posts']
    assert page.evaluate('maxVoices') == 1


def test_default_off_volume_and_toggle_do_not_trigger_play_or_care(audio_page):
    page, state = audio_page(care=True)
    page.locator('.av-play-btn').click()
    assert not any('/audio/' in path for path in state['requests'])
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    page.locator('.avwrap').evaluate("el => el.classList.remove('happy')")
    page.locator('.av-volume').focus()
    page.keyboard.press('ArrowRight')
    expect(page.locator('.av-volume')).to_have_value('85')
    assert page.evaluate("localStorage.getItem('css-av-volume')") == '0.85'
    assert not page.locator('.avwrap').evaluate("el => el.classList.contains('happy')")
    assert not state['posts']
    page.locator('.av-sound-btn').click()
    page.wait_for_function('liveVoices.size === 0')
    expect(page.locator('.av-volume')).to_be_hidden()
    page.reload()
    expect(page.locator('.av-sound-btn')).to_have_attribute('aria-pressed', 'false')
    assert page.evaluate('audioStarts.length') == 0


def test_muting_cancels_a_pending_download(audio_page):
    page, state = audio_page()
    pending = []
    page.route('**/manifest.json?*', lambda route: pending.append(route))
    page.locator('.av-sound-btn').click()
    page.wait_for_timeout(50)
    assert pending
    page.locator('.av-sound-btn').click()
    pending[0].fulfill(status=200, content_type='application/json', body=json.dumps(MANIFEST))
    page.wait_for_timeout(150)
    assert page.evaluate('audioStarts.length') == 0
    assert not any(path.endswith('.mp3') for path in state['requests'])
    assert not state['posts']


def test_rapid_taps_do_not_overlap_and_hidden_tabs_stop_audio(audio_page):
    page, _ = audio_page()
    # A remembered preference alone must not let an idle timer create audio.
    page.evaluate('AvatarAudio.setOn(true)')
    assert page.evaluate("AvatarAudio.play('voice','dog',true)") is False
    assert page.evaluate('audioStarts.length') == 0
    page.locator('.av-play-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    for _ in range(3):
        page.locator('.av-play-btn').click()
    assert page.evaluate('audioStarts.length') == 1
    page.wait_for_timeout(500)
    page.locator('.av-play-btn').click()
    page.wait_for_function('audioStarts.length === 2')
    assert page.evaluate('maxVoices') == 1
    page.evaluate('''Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
                     document.dispatchEvent(new Event('visibilitychange'));''')
    page.wait_for_function('liveVoices.size === 0')
    assert page.evaluate("AvatarAudio.play('tap','dog')") is False


def test_cat_petting_uses_purr_and_failed_audio_does_not_block_feeding(audio_page):
    page, state = audio_page('cat', care=True)
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    page.wait_for_timeout(500)
    page.locator('.av-play-btn').hover()
    page.mouse.down()
    page.wait_for_function('audioStarts.length === 2')
    page.mouse.up()
    assert '/static/audio/avatars/cat-purr.mp3' in state['requests']
    page.route('**/feed.mp3', lambda route: route.fulfill(status=503, body='unavailable'))
    page.wait_for_timeout(500)
    page.locator('.av-care-btn').click()
    page.wait_for_function('document.querySelector(".av-care-btn").disabled === false')
    assert state['posts'] == ['/avatar/care']
    assert page.locator('.avwrap').evaluate("el => el.classList.contains('av-caring-feed')")


def test_audio_waits_for_a_suspended_context_to_resume(audio_page):
    page, _ = audio_page()
    page.add_init_script('''
      const NativeAudioContext = window.AudioContext;
      window.AudioContext = class extends NativeAudioContext {
        constructor() { super(); this.gated = true; }
        get state() { return this.gated ? 'suspended' : super.state; }
        resume() { return new Promise(resolve => {
          window.releaseAudio = () => { this.gated=false; super.resume().then(resolve); };
        }); }
      };
    ''')
    page.reload()
    page.locator('.av-sound-btn').click()
    page.wait_for_function('!!window.releaseAudio')
    page.wait_for_timeout(100)
    assert page.evaluate('audioStarts.length') == 0
    page.evaluate('releaseAudio()')
    page.wait_for_function('audioStarts.length === 1')


def test_storage_unavailable_keeps_controls_functional_and_zero_volume_is_silent(audio_page):
    page, _ = audio_page()
    page.add_init_script('''
      Storage.prototype.getItem = Storage.prototype.setItem = function () {
        throw new DOMException('Storage denied','SecurityError');
      };
    ''')
    page.reload()
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    expect(page.locator('.av-sound-btn')).to_have_attribute('aria-pressed', 'true')
    page.locator('.av-volume').fill('0')
    page.wait_for_function('liveVoices.size === 0')
    assert page.evaluate("AvatarAudio.play('tap','dog')") is False


def test_home_wellness_and_public_asset_delivery(app_mod, admin, client):
    with st.connect(app_mod.DB) as conn:
        uid = conn.execute("SELECT id FROM admin_user WHERE username='admin@test.local'").fetchone()[0]
        st.set_user_avatar(conn, uid, 'dog', 'Rex')
        conn.commit()
    for url in ('/', '/wellness'):
        response = admin.get(url)
        assert response.status_code == 200
        assert 'class="av-sound-btn"' in response.text
        assert 'class="av-volume"' in response.text
        assert response.text.index('/static/js/avatar-audio.js') < response.text.index('/static/js/avatars.js')
    for filename in ('manifest.json', 'dog-1.mp3', 'CREDITS.md'):
        response = client.get('/static/audio/avatars/' + filename, follow_redirects=False)
        assert response.status_code == 200
        assert response.content == (PACK / filename).read_bytes()
        if filename.endswith('.mp3'):
            assert 'audio/mpeg' in response.headers['content-type']


def test_unchanged_audio_sync_does_not_retrigger_child_list_observer(audio_page):
    page, _ = audio_page(care=True)
    result = page.evaluate("""async () => {
      const button = document.querySelector('.av-sound-btn');
      let count = 0;
      const observer = new MutationObserver(records => count += records.length);
      observer.observe(button, {childList:true, subtree:true});
      for(let i=0;i<20;i++)AvatarAudio.sync();
      await Promise.resolve();
      const unchangedOff = count;
      AvatarAudio.setOn(true);
      await Promise.resolve();
      const changed = count;
      count = 0;
      for(let i=0;i<20;i++)AvatarAudio.sync();
      await Promise.resolve();
      const unchangedOn = count;
      observer.disconnect();
      return {unchangedOff, changed, unchangedOn, icon:button.textContent, pressed:button.getAttribute('aria-pressed')};
    }""")
    assert result['unchangedOff'] == result['unchangedOn'] == 0
    assert result['changed'] == 1
    assert result['icon'] == '🔊' and result['pressed'] == 'true'


def test_cat_voice_actions_only_use_replacement_meow_recordings(audio_page):
    page, state = audio_page('cat')
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    for action in ('tap', 'voice', 'voice'):
        page.wait_for_timeout(650)
        assert page.evaluate('(action) => AvatarAudio.play(action, "cat")', action)
    requested = {Path(path).name for path in state['requests'] if path.endswith('.mp3')}
    assert requested == {'cat-real-meow.mp3', 'cat-real-meow-twice.mp3'}
    # The whole pool must come from the replacement cat recording, including
    # the first call when enabling sound. No old excerpt or extra animal layer.
    for name in requested:
        assert {layer['source'] for layer in MANIFEST['clips'][name]['layers']} == {'cat'}
    assert MANIFEST['sources']['cat']['url'] == 'https://freesound.org/people/qubodup/sounds/813113/'


def test_default_volume_is_audible_on_a_phone_speaker(audio_page):
    page, _ = audio_page()
    # The recordings are mastered quietly; the default must not add to that.
    assert page.evaluate("localStorage.getItem('css-av-volume')") is None
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    expect(page.locator('.av-volume')).to_have_value('80')


def test_output_goes_through_a_limiter_after_the_master_gain(audio_page):
    page, _ = audio_page()
    page.add_init_script('''
      window.mixerLog = [];
      const connect = AudioNode.prototype.connect;
      AudioNode.prototype.connect = function (target, ...rest) {
        const name = n => n && n.constructor ? n.constructor.name : String(n);
        if (this instanceof GainNode || this instanceof DynamicsCompressorNode)
          mixerLog.push(name(this) + '>' + name(target));
        return connect.call(this, target, ...rest);
      };
    ''')
    page.reload()
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    log = page.evaluate('mixerLog')
    assert 'GainNode>DynamicsCompressorNode' in log
    assert 'DynamicsCompressorNode>AudioDestinationNode' in log
    assert 'GainNode>AudioDestinationNode' not in log


def test_ios_audio_session_is_playback_inside_the_tap_and_released_when_muted(audio_page):
    page, _ = audio_page()
    page.add_init_script('''
      window.sessionLog = []; let current = 'auto';
      Object.defineProperty(navigator, 'audioSession', {configurable: true, value: {
        get type() { return current; },
        set type(value) { current = value; sessionLog.push(value); }
      }});
    ''')
    page.reload()
    # Nothing touches the session until sound is switched on.
    assert page.evaluate('sessionLog') == []
    # Dispatching the click synchronously proves it is set within the gesture itself,
    # before any await (iOS ignores later changes for the unlocking tap).
    assert page.evaluate("""() => { document.querySelector('.av-sound-btn').click(); return sessionLog.slice(); }""") == ['playback']
    page.wait_for_function('audioStarts.length === 1')
    page.locator('.av-sound-btn').click()
    page.wait_for_function('liveVoices.size === 0')
    assert page.evaluate('sessionLog') == ['playback', 'auto']


def test_idle_voice_never_changes_the_audio_session(audio_page):
    page, _ = audio_page()
    page.add_init_script('''
      window.sessionLog = [];
      Object.defineProperty(navigator, 'audioSession', {configurable: true, value: {
        set type(value) { sessionLog.push(value); }
      }});
    ''')
    page.reload()
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
    before = page.evaluate('sessionLog.length')
    page.wait_for_timeout(500)
    page.evaluate("AvatarAudio.play('voice','dog',true)")
    assert page.evaluate('sessionLog.length') == before


def test_audio_session_errors_never_block_playback(audio_page):
    page, _ = audio_page()
    page.add_init_script('''
      Object.defineProperty(navigator, 'audioSession', {configurable: true, value: {
        set type(value) { throw new DOMException('Not allowed', 'NotAllowedError'); }
      }});
    ''')
    page.reload()
    page.locator('.av-sound-btn').click()
    page.wait_for_function('audioStarts.length === 1')
