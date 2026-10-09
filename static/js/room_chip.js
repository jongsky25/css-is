/* The activity form's conference-room line: show the chosen day's hours, and tick "also reserve" for online
   or hybrid activities (the room hosts the session). Everything still works without this script. */
(function () {
  var box = document.getElementById('room-chip-box');
  if (!box) return;
  var chip = document.getElementById('room-chip'), stateEl = document.getElementById('room-chip-state'),
      list = document.getElementById('room-chip-hours'), dateEl = document.getElementById('event_date'),
      venue = document.getElementById('venue'), from = document.getElementById('room-from'), to = document.getElementById('room-to');
  var touched = !!box.checked, autoTicked = false, closed = false, seq = 0;

  function wants() {
    var m = document.querySelector('input[name=modality]:checked');
    return (m && (m.value === 'online' || m.value === 'hybrid')) || /conference\s*room/i.test(venue ? venue.value : '');
  }
  function apply() {                                    // the auto-tick, unless the person has decided
    if (touched) return;
    var on = wants() && !closed;
    if (on !== box.checked) { box.checked = on; autoTicked = on; }
    if (on) chip.open = true;
  }
  function render(j) {
    list.textContent = '';
    closed = !!j.closed;
    if (closed) {
      stateEl.textContent = '· not available: ' + j.closed.replace(/\.$/, '');
      box.disabled = true; if (box.checked) box.checked = false;
      return;
    }
    box.disabled = false;
    var free = 0;
    j.hours.forEach(function (h) {
      if (h.state === 'free' || h.state === 'requested') free++;
      var li = document.createElement('li'); li.className = 'st-' + h.state;
      var b = document.createElement('b'); b.textContent = h.start;
      var s = document.createElement('span');
      s.textContent = h.state === 'free' ? '✓ Free' : h.state === 'requested' ? '○ Others asked' : h.state === 'booked' ? '● Booked' : '✕ Closed';
      li.appendChild(b); li.appendChild(s); list.appendChild(li);
    });
    stateEl.textContent = '· ' + free + ' of ' + j.hours.length + ' hours open that day';
  }
  function refresh() {
    var v = dateEl ? dateEl.value : '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) { stateEl.textContent = ''; list.textContent = ''; closed = false; box.disabled = false; return; }
    var mine = ++seq;
    fetch('/rooms/api/day?date=' + encodeURIComponent(v), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && mine === seq) { render(j); apply(); } })
      .catch(function () {});
  }
  box.addEventListener('change', function () { touched = true; if (box.checked) chip.open = true; });
  Array.prototype.forEach.call(document.querySelectorAll('input[name=modality]'), function (r) { r.addEventListener('change', apply); });
  if (venue) venue.addEventListener('input', apply);
  if (dateEl) { dateEl.addEventListener('change', refresh); dateEl.addEventListener('input', refresh); }
  chip.addEventListener('toggle', function () { if (chip.open && !touched && wants() && !closed) { box.checked = true; } });
  refresh(); apply();
})();
