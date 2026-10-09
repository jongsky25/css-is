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

  function open(on) {
    wrap.classList.toggle('panel-open', on);
    document.body.classList.toggle('rm-sheet-open', on);
    if (on) { var t = document.getElementById('rm-title'); if (t && !t.value) t.focus({ preventScroll: true }); }
  }
  document.getElementById('rm-open').addEventListener('click', function () { open(true); });
  document.getElementById('rm-close').addEventListener('click', function () { open(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') open(false); });

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
    var f = fromEl.options[fromEl.selectedIndex], t = toEl.options[toEl.selectedIndex];
    if (!dayEl.value || !f || !t) return;
    if (fromEl.selectedIndex > toEl.selectedIndex) { summary.textContent = 'Check the times: "Until" is before "From".'; return; }
    summary.textContent = label(dayEl.value) + ' · ' + f.textContent + ' – ' + t.textContent;
    var pending = 0, bad = false;
    if (sel) for (var r = Math.min(sel.a, sel.b); r <= Math.max(sel.a, sel.b); r++) {
      var c = byRow(sel.day, r); if (c) pending = Math.max(pending, +c.dataset.pending || 0);
    }
    clash.className = 'rm-clash';
    clash.textContent = pending ? pending + ' other request' + (pending > 1 ? 's are' : ' is') +
      ' pending for these hours. The Administrative Section will decide.' : '';
  }
  function apply(day, a, b, openPanel) {
    sel = { day: day, a: a, b: b };
    var lo = Math.min(a, b), hi = Math.max(a, b);
    dayEl.value = day; fromEl.selectedIndex = lo; toEl.selectedIndex = hi;
    dayEl.dispatchEvent(new Event('input', { bubbles: true }));   // the date-picker overlay listens for this
    paint(); describe();
    if (openPanel) open(true);
  }
  function fromForm() {                           // typed by hand: mirror onto the grid when the day is shown
    var day = dayEl.value, lo = fromEl.selectedIndex, hi = toEl.selectedIndex;
    if (day && colCells(day).length && lo <= hi && rangeFree(day, lo, hi)) sel = { day: day, a: lo, b: hi };
    else sel = null;
    paint(); describe();
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
      if (moved) { moved = false; open(true); return; }
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
        if (el.getAttribute('role') === 'tab') el.setAttribute('aria-selected', el.dataset.day === day ? 'true' : 'false');
      });
    });
  });

  // Land on the form's own values (a prefilled link, or a server-side error re-render).
  if (dayEl.value) fromForm(); else describe();
  if (wrap.querySelector('.rm-panel .field-error, .flash.err') || document.querySelector('.flash.err')) open(true);
})();
