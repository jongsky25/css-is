/* Conference room board: click an hour, click another in the same day to make a range
   (or drag, or shift-click). The panel's date / From / Until stay the source of truth, so the
   form also works typed by hand. No dependencies. */
(function () {
  var wrap = document.getElementById('rm-wrap');
  if (!wrap) return;
  wrap.classList.add('js');
  var form = document.getElementById('rm-form');
  var dayEl = document.getElementById('rm-day'), fromEl = document.getElementById('rm-from'),
      toEl = document.getElementById('rm-to'), summary = document.getElementById('rm-summary'),
      clash = document.getElementById('rm-clash');
  var cells = Array.prototype.slice.call(wrap.querySelectorAll('button.rm-cell'));
  var anchor = null, dragging = false, moved = false, sel = null;   // sel = {day, a, b} row indexes

  var panel = document.getElementById('rm-panel'), openButton = document.getElementById('rm-open');
  var panelOpen = false, opener = null, releaseFocus = null;
  var sheet = matchMedia('(max-width:1199px)');
  var availability = null, checkedDay = '', checkSequence = 0, checking = false;
  var checkController = null, checkFailed = false;
  var standby = form.querySelector('input[name="standby"]');

  function syncPanel(active) {
    var modal = sheet.matches && panelOpen;
    wrap.classList.toggle('panel-open', panelOpen);
    document.body.classList.toggle('rm-sheet-open', modal);
    openButton.setAttribute('aria-expanded', modal ? 'true' : 'false');
    panel.inert = sheet.matches && !panelOpen;
    if (panel.inert) panel.setAttribute('aria-hidden', 'true');
    else panel.removeAttribute('aria-hidden');
    if (modal) {
      panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true');
      panel.setAttribute('aria-labelledby', 'rm-panel-title');
      if (!releaseFocus && window.OfficeA11y) {
        releaseFocus = OfficeA11y.open(panel, {initialFocus:active && panel.contains(active) ? active : initialControl(), returnFocus:opener,
          onDismiss:function () {open(false);}});
      }
    } else {
      panel.removeAttribute('role'); panel.removeAttribute('aria-modal'); panel.removeAttribute('aria-labelledby');
      if (releaseFocus) { releaseFocus(); releaseFocus = null; }
    }
  }
  function initialControl() {
    return document.getElementById('rm-form-error') || (!dayEl.value ? dayEl : document.getElementById('rm-title'));
  }
  function open(on, trigger) {
    if (on && !panelOpen) opener = trigger || document.activeElement;
    panelOpen = on; syncPanel();
    if (on) { initialControl().focus({preventScroll:true}); checkDay(false); }
  }
  openButton.addEventListener('click', function () { open(true, openButton); });
  document.getElementById('rm-close').addEventListener('click', function () { open(false); });
  document.getElementById('rm-check').addEventListener('click', function () { checkDay(true); });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && sheet.matches && panelOpen && !window.OfficeA11y) open(false);
  });
  window.addEventListener('resize', function () {
    var active = document.activeElement;
    if (sheet.matches && panel.contains(active)) panelOpen = true;
    syncPanel(active);
    if (!sheet.matches && panel.contains(active)) active.focus({preventScroll:true});
  });
  if (standby) standby.addEventListener('change', describe);
  syncPanel();

  function checkDay(force) {
    var day = dayEl.value;
    if (!force && checkedDay === day) return;
    var sequence = ++checkSequence;
    if (checkController) checkController.abort();
    checkedDay = day; availability = null; checkFailed = false; checking = false;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) { describe(); return; }
    checking = true; describe();
    checkController = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var options = {credentials:'same-origin'};
    if (checkController) options.signal = checkController.signal;
    fetch('/rooms/api/day?date=' + encodeURIComponent(day), options).then(function (response) {
      if (!response.ok) throw new Error('Availability unavailable');
      return response.json();
    }).then(function (data) {
      if (sequence !== checkSequence) return;
      if (data.day !== day || !Array.isArray(data.hours)) throw new Error('Unexpected availability');
      availability = data; checking = false; describe();
    }).catch(function () {
      if (sequence !== checkSequence) return;
      checking = false; checkFailed = true; describe();
    });
  }

  function colCells(day) { return cells.filter(function (c) { return c.dataset.day === day; }); }
  function byRow(day, row) { return colCells(day).filter(function (c) { return +c.dataset.row === row; })[0]; }

  function rangeFree(day, a, b) {                // every hour between a and b must be a clickable cell
    for (var r = Math.min(a, b); r <= Math.max(a, b); r++) if (!byRow(day, r)) return false;
    return true;
  }
  function paint() {
    cells.forEach(function (c) {
      var on = sel && c.dataset.day === sel.day && +c.dataset.row >= Math.min(sel.a, sel.b) && +c.dataset.row <= Math.max(sel.a, sel.b);
      c.classList.toggle('is-sel', !!on);
      c.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  function label(d) {
    var x = new Date(d + 'T00:00:00');
    return x.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  }
  function describe() {
    var lo = Math.min(fromEl.selectedIndex, toEl.selectedIndex);
    var hi = Math.max(fromEl.selectedIndex, toEl.selectedIndex);
    var first = fromEl.options[lo], last = toEl.options[hi];
    summary.textContent = dayEl.value && first && last ? label(dayEl.value) + ' · ' +
      first.textContent + ' – ' + last.textContent : 'Pick a date and hours. Sending a request does not reserve them.';
    clash.className = 'rm-clash';
    if (!dayEl.value) {clash.textContent = ''; return;}
    if (checking) {clash.textContent = 'Checking availability for this date…'; return;}
    if (checkFailed) {
      clash.textContent = 'Could not check availability. Your details are kept. Use Check availability to retry, or submit for a fresh server check.'; return;
    }
    if (!availability) {clash.textContent = 'Use Check availability to check these hours.'; return;}
    if (availability.closed) {
      clash.className = 'rm-clash bad';
      clash.textContent = 'Date unavailable for new requests: ' + availability.closed; return;
    }
    var chosen = Array.prototype.slice.call(fromEl.options, lo, hi + 1).map(function (o) {return +o.value;});
    var hours = availability.hours.filter(function (h) {return chosen.indexOf(+h.id) >= 0;});
    if (hours.length !== chosen.length) {
      clash.textContent = 'The available hours changed. Check availability again before submitting.'; return;
    }
    var taken = hours.some(function (h) {return h.state === 'booked' || h.state === 'closed';});
    var others = hours.some(function (h) {return h.state === 'requested';});
    if (standby && standby.checked) {
      clash.textContent = 'Standby only — no hours are reserved. The Administrative Section must confirm it; any room closure must be reopened first.'; return;
    }
    if (taken) {
      clash.className = 'rm-clash bad';
      clash.textContent = 'Some selected hours are booked or unavailable. Choose other hours, or select standby to ask the Administrative Section.';
      var encode = document.querySelector('.rm-encode');
      if (encode) encode.open = true;
      return;
    }
    clash.textContent = others ? 'Requests are waiting for some of these hours. You can still request; the room is not reserved until approval.' :
      'Free to request — not reserved. The Administrative Section must approve your request.';
  }
  function apply(day, a, b, openPanel) {
    sel = { day: day, a: a, b: b };
    var lo = Math.min(a, b), hi = Math.max(a, b);
    dayEl.value = day; fromEl.selectedIndex = lo; toEl.selectedIndex = hi;
    dayEl.dispatchEvent(new Event('input', { bubbles: true }));   // the date-picker overlay listens for this
    paint(); describe();
    checkDay(false);
    if (openPanel) open(true, byRow(day, a));
  }
  function fromForm() {                           // typed by hand: mirror onto the grid when the day is shown
    var day = dayEl.value, lo = fromEl.selectedIndex, hi = toEl.selectedIndex;
    if (day && colCells(day).length && lo <= hi && rangeFree(day, lo, hi)) sel = { day: day, a: lo, b: hi };
    else sel = null;
    paint(); describe(); checkDay(false);
  }
  [dayEl, fromEl, toEl].forEach(function (el) { el.addEventListener('change', fromForm); });

  cells.forEach(function (c) {
    c.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'touch') return;
      dragging = true; moved = false; anchor = +c.dataset.row;
    });
    c.addEventListener('pointerenter', function () {
      if (!dragging || !sel && anchor === null) return;
      var row = +c.dataset.row, day = c.dataset.day;
      if (day !== (sel ? sel.day : day) || row === anchor && !moved) return;
      if (rangeFree(day, anchor, row)) { moved = true; apply(day, anchor, row, false); }
    });
    c.addEventListener('click', function (e) {
      var day = c.dataset.day, row = +c.dataset.row;
      if (moved) { moved = false; open(true, c); return; }
      if (sel && sel.day === day && sel.a === sel.b && sel.a !== row && rangeFree(day, sel.a, row)) apply(day, sel.a, row, true);
      else if (e.shiftKey && sel && sel.day === day && rangeFree(day, sel.a, row)) apply(day, sel.a, row, true);
      else apply(day, row, row, true);
    });
    c.addEventListener('keydown', function (e) {  // arrow keys move between hours and days
      var d = { ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1] }[e.key];
      if (!d) return;
      var days = Array.prototype.slice.call(new Set(cells.map(function (x) { return x.dataset.day; })));
      var di = days.indexOf(c.dataset.day) + d[1], row = +c.dataset.row + d[0], next;
      if (di < 0 || di >= days.length) return;
      next = byRow(days[di], row); if (!next) return;
      e.preventDefault(); next.focus();
    });
  });
  document.addEventListener('pointerup', function () { dragging = false; });

  // Quick picks: Morning / Afternoon / Whole day set From and Until by time.
  Array.prototype.forEach.call(wrap.querySelectorAll('.rm-quick button'), function (b) {
    b.addEventListener('click', function () {
      var lo = -1, hi = -1;
      Array.prototype.forEach.call(fromEl.options, function (o, i) { if (o.dataset.time === b.dataset.from) lo = i; });
      Array.prototype.forEach.call(toEl.options, function (o, i) { if (o.dataset.time === b.dataset.to) hi = i; });
      if (lo < 0 || hi < 0) return;
      fromEl.selectedIndex = lo; toEl.selectedIndex = hi; fromForm();
    });
  });

  // Phone day strip: switch day without a reload (the links still work without JS).
  Array.prototype.forEach.call(wrap.querySelectorAll('.rm-daystrip a'), function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      var day = a.dataset.day;
      Array.prototype.forEach.call(wrap.querySelectorAll('th[data-day], td[data-day], .rm-daystrip a'), function (el) {
        if (el.closest('.rm-week2')) return;
        el.classList.toggle('is-active-day', el.dataset.day === day);
        if (el.matches('.rm-daystrip a')) {
          if (el.dataset.day === day) el.setAttribute('aria-current', 'true');
          else el.removeAttribute('aria-current');
        }
      });
    });
  });

  // Land on the form's own values (a prefilled link, or a server-side error re-render).
  if (dayEl.value) fromForm(); else describe();
  if (wrap.querySelector('.rm-panel .field-error, .rm-bump') || document.querySelector('.flash.err')) open(true);
})();

(function () {                                    // a Book-anyway prompt must not be missed
  var b = document.querySelector('.rm-bump');
  if (b) b.scrollIntoView({ block: 'center' });
})();
