/* Optional profile preview. Persistence belongs exclusively to the profile POST. */
(function () {
  'use strict';
  var panel = document.getElementById('companion-customizer');
  if (!panel) return;
  var mode = panel.querySelector('[name="avatar_appearance_mode"]');
  var primary = panel.querySelector('[name="avatar_primary"]');
  var secondary = panel.querySelector('[name="avatar_secondary"]');
  var kinds = Array.from(document.querySelectorAll('[name="avatar_kind"]'));
  var name = document.querySelector('[name="avatar_name"]');
  var status = document.getElementById('companion-customizer-status');
  var preview = document.getElementById('companion-customizer-preview');
  var original = {mode: mode.value, primary: primary.value, secondary: secondary.value,
    kind: selectedKind(), name: name.value};
  var pending, timer, generation = 0;
  function selectedKind() { var chosen = kinds.find(function (el) { return el.checked; }); return chosen ? chosen.value : 'plant'; }
  function compatible() {
    var kind = selectedKind(), cleared = false;
    [primary, secondary].forEach(function (select) {
      Array.from(select.options).forEach(function (option) {
        var allowed = !option.value || option.dataset.species.split(' ').includes(kind);
        option.disabled = !allowed;
        option.hidden = !allowed;
        if (!allowed && option.selected) { select.value = ''; cleared = true; }
      });
    });
    panel.querySelectorAll('[data-personal-accessories]').forEach(function (el) { el.hidden = mode.value !== 'personal'; });
    return cleared;
  }
  function refresh() {
    var cleared = compatible(), version = ++generation;
    if (pending) pending.abort();
    clearTimeout(timer);
    status.textContent = cleared ? 'Incompatible accessories removed from this preview. Save to keep these changes.' : 'Preview only. Save to keep these changes.';
    timer = setTimeout(async function () {
      pending = new AbortController();
      var query = new URLSearchParams({kind: selectedKind(), stage: panel.dataset.stage,
        mode: mode.value, primary: primary.value, secondary: secondary.value});
      try {
        var response = await fetch('/me/companion-preview?' + query, {signal: pending.signal, cache: 'no-store'});
        if (version !== generation) return;
        if (!response.ok) throw new Error('preview');
        var doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        var svg = doc.querySelector('svg[data-avatar-kind]');
        if (!svg) throw new Error('preview');
        if (version === generation) preview.replaceChildren(document.importNode(svg, true));
      } catch (error) {
        if (error.name !== 'AbortError' && version === generation) status.textContent = 'Preview unavailable. Your saved companion has not changed.';
      }
    }, 120);
  }
  [mode, primary, secondary].concat(kinds).forEach(function (el) { el.addEventListener('change', refresh); });
  document.getElementById('companion-customizer-reset').addEventListener('click', function () {
    mode.value = 'seasonal'; primary.value = secondary.value = ''; refresh();
  });
  document.getElementById('companion-customizer-remove').addEventListener('click', function () {
    mode.value = 'none'; primary.value = secondary.value = ''; refresh();
  });
  document.getElementById('companion-customizer-cancel').addEventListener('click', function () {
    kinds.forEach(function (el) { el.checked = el.value === original.kind; });
    mode.value = original.mode; primary.value = original.primary; secondary.value = original.secondary; name.value = original.name;
    refresh();
    status.textContent = 'Companion changes cancelled. Saved appearance restored.';
  });
  compatible();
})();
