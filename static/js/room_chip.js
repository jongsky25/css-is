/* The conference-room line on the Add activity form and the calendar item form: show the chosen day's hours, and tick "also reserve" for online
   or hybrid activities (the room hosts the session). Everything still works without this script. */
(function () {
  var box = document.getElementById('room-chip-box');
  if (!box) return;
  var chip = document.getElementById('room-chip'), stateEl = document.getElementById('room-chip-state'),
      list = document.getElementById('room-chip-hours'), from = document.getElementById('room-from'), to = document.getElementById('room-to');
  // The form's own fields are named on the chip: the date input, the venue input, the format field (a select or radios),
  // and (calendar items only) the optional start / end time inputs the hours follow.
  var dateEl = document.getElementById(chip.dataset.date || 'event_date'),
      venue = document.getElementById(chip.dataset.venue || 'venue'),
      fmtName = chip.dataset.format || 'modality',
      startEl = chip.dataset.start ? document.getElementById(chip.dataset.start) : null,
      endEl = chip.dataset.end ? document.getElementById(chip.dataset.end) : null;
  var standbyRow = document.getElementById('room-standby-row'), standbyBox = document.getElementById('room-standby-box');
  var touched = !!box.checked, autoTicked = false, closed = false, seq = 0;

  function wants() {
    var sel = document.getElementById(fmtName), m = sel && sel.tagName === 'SELECT' ? sel : document.querySelector('input[name=' + fmtName + ']:checked');
    return (m && (m.value === 'online' || m.value === 'hybrid')) || /conference\s*room/i.test(venue ? venue.value : '');
  }
  function apply() {                                    // the auto-tick, unless the person has decided
    if (touched) return;
    var on = wants() && !closed;
    if (on !== box.checked) { box.checked = on; autoTicked = on; }
    if (on) chip.open = true;
  }
  function showStandby(on) {                            // a provisional (standby) use only makes sense when some hours are taken
    if (!standbyRow) return;
    standbyRow.hidden = !on;
    if (!on && standbyBox) standbyBox.checked = false;
  }
  function render(j) {
    list.textContent = '';
    closed = !!j.closed;
    if (closed) {
      showStandby(false);
      stateEl.textContent = 'Not available: ' + j.closed.replace(/\.$/, '');
      chip.dataset.state = 'closed';
      box.disabled = true; if (box.checked) box.checked = false;
      return;
    }
    box.disabled = false;
    var free = 0, taken = 0;
    j.hours.forEach(function (h) {
      if (h.state === 'free' || h.state === 'requested') free++; else taken++;
      var li = document.createElement('li'); li.className = 'st-' + h.state;
      var b = document.createElement('b'); b.textContent = h.start;
      var s = document.createElement('span');
      s.textContent = h.state === 'free' ? '✓ Free' : h.state === 'requested' ? '○ Others asked' : h.state === 'booked' ? '● Booked' : '✕ Closed';
      li.appendChild(b); li.appendChild(s); list.appendChild(li);
    });
    showStandby(taken > 0);
    stateEl.textContent = free + ' of ' + j.hours.length + ' hours open that day';
    chip.dataset.state = taken > 0 ? 'partial' : 'free';
  }
  function refresh() {
    var v = dateEl ? dateEl.value : '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) { stateEl.textContent = ''; delete chip.dataset.state; list.textContent = ''; closed = false; box.disabled = false; showStandby(false); return; }
    var mine = ++seq;
    fetch('/rooms/api/day?date=' + encodeURIComponent(v), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && mine === seq) { render(j); apply(); } })
      .catch(function () {});
  }
  box.addEventListener('change', function () { touched = true; if (box.checked) chip.open = true; });
  Array.prototype.forEach.call(document.querySelectorAll('input[name=' + fmtName + '], select[name=' + fmtName + ']'), function (r) { r.addEventListener('change', apply); });
  // A calendar item with times: the hours follow them (from the hour it starts, until the hour it ends).
  function pick(sel, hhmm, up) {
    if (!sel || !/^\d{2}:\d{2}$/.test(hhmm)) return;
    var best = null;
    Array.prototype.forEach.call(sel.options, function (o) {
      var t = o.getAttribute('data-time'); if (!t) return;
      if (up ? t >= hhmm && (!best || t < best.getAttribute('data-time')) : t <= hhmm && (!best || t > best.getAttribute('data-time'))) best = o;
    });
    if (best) sel.value = best.value;
  }
  function followTimes() { if (startEl && startEl.value) pick(from, startEl.value, false); if (endEl && endEl.value) pick(to, endEl.value, true); }
  if (startEl) startEl.addEventListener('change', followTimes);
  if (endEl) endEl.addEventListener('change', followTimes);
  if (venue) venue.addEventListener('input', apply);
  if (dateEl) { dateEl.addEventListener('change', refresh); dateEl.addEventListener('input', refresh); }
  chip.addEventListener('toggle', function () { if (chip.open && !touched && wants() && !closed) { box.checked = true; } });
  refresh(); apply();
})();
