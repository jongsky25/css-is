/* Locally hosted companion recordings. No audio requests until sound is enabled. */
(function () {
  "use strict";
  var ROOT = "/static/audio/avatars/";
  var SOUND_KEY = "css-av-sound", VOLUME_KEY = "css-av-volume";
  function setting(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
  }
  function save(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  function volumeValue(value) {
    var n = Number(value);
    return isFinite(n) ? Math.max(0, Math.min(1, n)) : 0.35;
  }
  var enabled = setting(SOUND_KEY, "off") === "on";
  var volume = volumeValue(setting(VOLUME_KEY, "0.35"));
  var ctx = null, master = null, manifestPromise = null;
  var buffers = {}, lastChoice = {}, active = [], revision = 0, lastStart = -Infinity;

  function request(path) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 8000);
    return fetch(ROOT + path, { credentials: "same-origin", signal: controller.signal })
      .then(function (r) {
        if (!r.ok) throw new Error("Companion audio unavailable");
        return path.indexOf(".json") !== -1 ? r.json() : r.arrayBuffer();
      }).finally(function () { clearTimeout(timer); });
  }

  function stop() {
    revision++;                         // also cancels pending fetch/decode/resume
    active.forEach(function (node) { try { node.stop(); } catch (_) {} });
    active = [];
  }
  function context() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = volume;
    master.connect(ctx.destination);
    // iOS requires starting a source inside the unlocking user gesture.
    var silent = ctx.createBufferSource();
    silent.buffer = ctx.createBuffer(1, 1, 22050);
    silent.connect(master); silent.start(0);
    return ctx;
  }
  function manifest() {
    if (!manifestPromise) {
      manifestPromise = request("manifest.json?v=1")
        .catch(function (e) { manifestPromise = null; throw e; });
    }
    return manifestPromise;
  }
  function buffer(file) {
    // Only filenames from our local manifest can become requests.
    if (!/^[a-z0-9-]+\.mp3$/.test(file)) return Promise.reject(new Error("Invalid audio path"));
    if (!buffers[file]) {
      buffers[file] = request(file)
        .then(function (data) { return ctx.decodeAudioData(data); })
        .catch(function (e) { delete buffers[file]; throw e; });
    }
    return buffers[file];
  }
  function track(node) {
    active.push(node);
    node.onended = function () {
      var i = active.indexOf(node);
      if (i !== -1) active.splice(i, 1);
      node.disconnect();
    };
  }
  function badge() {
    [523, 659, 784].forEach(function (freq, i) {
      var tone = ctx.createOscillator(), gain = ctx.createGain();
      var t = ctx.currentTime + i * 0.11;
      tone.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.08, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
      tone.connect(gain); gain.connect(master);
      track(tone); tone.start(t); tone.stop(t + 0.22);
      tone.onended = function () {
        var i = active.indexOf(tone);
        if (i !== -1) active.splice(i, 1);
        tone.disconnect(); gain.disconnect();
      };
    });
  }
  function choose(files, key) {
    var choices = files.filter(function (file) { return file !== lastChoice[key]; });
    var file = (choices.length ? choices : files)[Math.floor(Math.random() * (choices.length || files.length))];
    lastChoice[key] = file;
    return file;
  }
  function play(action, kind, idle) {
    if (!enabled || !volume || document.hidden) return Promise.resolve(false);
    if (idle && (!ctx || ctx.state !== "running" || active.length)) return Promise.resolve(false);
    // Explicit taps can interrupt an idle voice; rapid taps cannot stack sounds.
    if (performance.now() - lastStart < 450) return Promise.resolve(false);
    var audio;
    try { audio = idle ? ctx : context(); } catch (_) { return Promise.resolve(false); }
    if (!audio) return Promise.resolve(false);
    stop();
    var ticket = revision;
    // resume() must be called synchronously within the gesture, before fetching.
    var ready;
    try { ready = audio.state === "running" ? Promise.resolve() : audio.resume(); }
    catch (_) { return Promise.resolve(false); }
    var data = action === "badge" ? Promise.resolve(null) : manifest().then(function (m) {
      if (ticket !== revision || !enabled || document.hidden) throw new Error("Audio cancelled");
      var species = m.species[kind];
      if (!species) throw new Error("Unknown companion");
      var files = action === "water" ? m.events.water : species[action] || species.voice;
      if (!files || !files.length) throw new Error("Missing companion audio");
      return buffer(choose(files, kind + ":" + action));
    });
    return Promise.all([ready, data]).then(function (result) {
      if (ticket !== revision || !enabled || !volume || document.hidden || audio.state !== "running") return false;
      lastStart = performance.now();
      if (action === "badge") { badge(); return true; }
      var source = audio.createBufferSource(), gain = audio.createGain();
      source.buffer = result[1];
      gain.gain.value = idle ? 0.35 : 1;
      source.connect(gain); gain.connect(master); track(source);
      source.onended = function () {
        var i = active.indexOf(source);
        if (i !== -1) active.splice(i, 1);
        source.disconnect(); gain.disconnect();
      };
      source.start();
      return true;
    }).catch(function () { return false; });       // a failed clip never blocks care
  }
  function sync() {
    document.querySelectorAll(".av-sound-btn").forEach(function (btn) {
      btn.setAttribute("aria-pressed", enabled ? "true" : "false");
      btn.textContent = enabled ? "🔊" : "🔇";
    });
    document.querySelectorAll(".av-volume").forEach(function (slider) {
      slider.value = Math.round(volume * 100);
      slider.setAttribute("aria-valuetext", Math.round(volume * 100) + " percent");
      slider.hidden = !enabled;
    });
  }
  function setOn(on) {
    enabled = !!on; save(SOUND_KEY, enabled ? "on" : "off");
    if (!enabled) stop();
    sync();
  }
  function setVolume(value) {
    volume = volumeValue(value); save(VOLUME_KEY, String(volume));
    if (master) master.gain.setValueAtTime(volume, ctx.currentTime);
    if (!volume) stop();
    sync();
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".av-sound-btn");
    if (!btn) return;
    setOn(!enabled);
    var wrap = btn.closest(".avwrap");
    if (enabled && wrap) play("tap", wrap.dataset.kind);
  });
  document.addEventListener("input", function (e) {
    if (e.target.matches(".av-volume")) setVolume(Number(e.target.value) / 100);
  });
  document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); });
  window.addEventListener("pagehide", stop);
  window.addEventListener("storage", function (e) {
    if (e.key !== SOUND_KEY && e.key !== VOLUME_KEY && e.key !== null) return;
    enabled = setting(SOUND_KEY, "off") === "on";
    volume = volumeValue(setting(VOLUME_KEY, "0.35"));
    if (master) master.gain.setValueAtTime(volume, ctx.currentTime);
    if (!enabled || !volume) stop();
    sync();
  });
  window.AvatarAudio = { play: play, stop: stop, sync: sync, setOn: setOn,
    setVolume: setVolume, isOn: function () { return enabled; } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sync);
  else sync();
})();
