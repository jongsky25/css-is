/* Travel filing: prepare the forms. Everything typed here stays in this page (and an optional draft in
   this browser); the server builds the documents from it and keeps none of it. */
(function (root) {
  'use strict';

  // Same rules as travel_rules.ride_check, so the page can warn before anything is sent. `cap` is the
  // policy limit for the rate chosen on the row (travel_rates.row_cap, worked out by the server).
  function rideCheck(mode, routeType, fare, receipt, ceil, cap) {
    fare = Number(fare) || 0;
    var flags = [], targets = [];     // targets[i] names the entry field flags[i] is about: fare, route or receipt
    function add(text, target) { flags.push(text); targets.push(target); }
    if (fare <= 0 || ['tnvs', 'taxi', 'public_noreceipt'].indexOf(mode) < 0) return { kind: null, flags: flags, targets: targets };
    var policy = cap != null;
    var known = policy || ceil.routes.indexOf(routeType) >= 0;
    function over(limit) { add('Fare is ' + (fare - limit).toFixed(2).replace(/\.00$/, '') + ' above the ' + limit + ' ceiling.', 'fare'); }
    if (!known) add('The route is not on the approved list.', 'route');
    if (policy && fare > cap) over(cap);
    if ((mode === 'tnvs' || mode === 'taxi') && receipt === 'receipt') {
      var flat = ceil.flat[mode] || 0;
      if (!policy && flat && fare > flat) over(flat);
      return { kind: 'receipt', flags: flags, targets: targets };
    }
    if (fare <= (ceil.flat.cenrr || 300)) return { kind: 'cenrr', flags: flags, targets: targets };
    if (!policy) {
      var rcap = known ? (ceil.rer[routeType] || 0) : 0;
      if (known && rcap && fare > rcap) over(rcap);
    }
    if (fare > 1000) add('No receipt for a fare of ' + fare + '.', 'receipt');
    return { kind: 'rer', flags: flags, targets: targets };
  }

  function ceilings(list) {
    var c = { flat: {}, rer: {}, routes: [] };
    list.forEach(function (x) {
      if (x[0] === 'rer') { c.rer[x[1]] = x[2]; c.routes.push(x[1]); } else if (x[1] === '*') c.flat[x[0]] = x[2];
    });
    return c;
  }

  // One day of the Post Travel Report written from the itinerary: the rides entered for that date and, inside the activity's
  // dates, taking part in it. `modes` maps a mode code to its label. Returns '' when there is nothing to say yet.
  function plain(label) { label = String(label); return label.length > 1 && label.charAt(1) === label.charAt(1).toUpperCase() && label.charAt(1) !== label.charAt(1).toLowerCase() ? label : label.charAt(0).toLowerCase() + label.slice(1); }
  function describeDay(rows, iso, act, modes) {
    var rides = [];
    (rows || []).forEach(function (r) {
      if (r.date !== iso || !r.mode || r.mode === 'none') return;
      var s = 'travelled' + (r.from ? ' from ' + r.from : '') + (r.to ? ' to ' + r.to : '') + ' by ' + plain((modes || {})[r.mode] || r.mode);
      var when = [];
      if (r.dep) when.push('left ' + r.dep);
      if (r.arr) when.push('arrived ' + r.arr);
      rides.push(when.length ? s + ' (' + when.join(', ') + ')' : s);
    });
    var inside = act && iso >= act.start && iso <= act.end;
    if (!inside) return rides.join('; ');
    var part = 'took part in ' + act.title + (act.venue ? ' at ' + act.venue : '');
    var first = iso === act.start, last = iso === act.end, at;
    if (first && !last) at = rides.length;                  // travel in, then the activity
    else if (last && !first) at = 0;                        // the activity, then travel home
    else if (first && last) at = Math.ceil(rides.length / 2); // out, the activity, back
    else at = 0;
    rides.splice(at, 0, part);
    return rides.join('; ');
  }

  // A liquidation's figures: what was actually spent, by kind, against the cash advance. Money is added in centavos so
  // the result never carries floating-point crumbs. `fromFiles` counts the entries drafted from an uploaded ticket or receipt.
  function liquidationFigures(rows, advance, modes) {
    var by = {}, order = [], pdCents = 0, pdDays = 0;
    function cents(v) { return Math.round((Number(v) || 0) * 100); }
    (rows || []).forEach(function (r) {
      var fare = cents(r.allowance), pd = cents(r.per_diem), key = r.mode && r.mode !== 'none' ? r.mode : 'other';
      if (fare > 0) {
        if (!by[key]) { by[key] = { label: key === 'other' ? 'Other fares' : String((modes || {})[key] || key), cents: 0, count: 0, fromFiles: 0 }; order.push(key); }
        by[key].cents += fare; by[key].count++; if (r.src) by[key].fromFiles++;
      }
      if (pd > 0) { pdCents += pd; pdDays++; }
    });
    var lines = order.map(function (k) { return by[k]; });
    if (pdCents) lines.push({ label: 'Per diem', cents: pdCents, count: pdDays, fromFiles: 0 });
    var total = lines.reduce(function (n, l) { return n + l.cents; }, 0);
    var adv = advance == null || advance === '' ? null : cents(advance);
    return { lines: lines, totalCents: total, advanceCents: adv, diffCents: adv == null ? null : adv - total };
  }

  root.TravelPrepare = { rideCheck: rideCheck, ceilings: ceilings, describeDay: describeDay, liquidationFigures: liquidationFigures };
  if (typeof document === 'undefined') return;

  var app = document.getElementById('prep-app'), raw = document.getElementById('prep-data');
  if (!app || !raw) return;
  var data = JSON.parse(raw.textContent), ceil = ceilings(data.ceilings), state = data, policy = data.policy;
  var codes = data.codes || [], isEstimate = data.kind === 'ca';
  var draftStatus = document.getElementById('draft-status');
  function needs(code) { return codes.indexOf(code) >= 0; }
  var BLANK = { date: '', from: '', to: '', dep: '', arr: '', mode: 'none', route_type: '', receipt: 'none', allowance: 0, per_diem: 0,
                basis: '', place: '', km: 0, day_kind: '', lodging_provided: false, meals_provided: false };
  var calc = [], regionDte = null;     // what the server says the policy allows, one entry per row, and the region's daily rate
  var draftKey = 'travel-draft-' + data.ref;
  // What the server drafted from the uploads (rows with `rid`/`src`, and these suggested answers). A browser draft keeps
  // what the person changed, takes up rides read from uploads made since, and lets an answer they never touched follow
  // the newest reading.
  var SUGGESTED = ['strictness', 'explanation', 'refund_amount', 'refund_or_no', 'refund_or_date'];
  var sugg = {}, gone = [], dayAuto = [];   // dayAuto: the report line the page last wrote for each day
  SUGGESTED.forEach(function (k) { sugg[k] = state.texts[k] || ''; });
  try {
    var d = JSON.parse(localStorage.getItem(draftKey) || 'null');
    if (d && Array.isArray(d.rows)) {
      var fromServer = state.rows, serverTexts = state.texts, sig = Object.assign({}, state.signatories);
      state.rows = d.rows.map(function (x) { return Object.assign({}, BLANK, x); });
      gone = Array.isArray(d.gone) ? d.gone : [];
      var have = {}, added = 0;
      state.rows.forEach(function (x) { if (x.rid) have[x.rid] = 1; });
      fromServer.forEach(function (sr) {
        if (sr.rid && !have[sr.rid] && gone.indexOf(sr.rid) < 0) { state.rows.push(Object.assign({}, BLANK, sr)); added++; }
      });
      state.texts = Object.assign({}, serverTexts, d.texts);
      if (Array.isArray(d.dauto)) dayAuto = d.dauto;
      SUGGESTED.forEach(function (k) { if (d.texts && (d.texts[k] || '') === ((d.sugg || {})[k] || '') && serverTexts[k] != null) state.texts[k] = serverTexts[k]; });
      Object.keys(d.signatories || {}).forEach(function (k) { if (d.signatories[k]) sig[k] = d.signatories[k]; });
      state.signatories = sig;
      if (typeof d.mc114_text === 'string') state.mc114_text = d.mc114_text;
      if (d.rates) state.rates = Object.assign({}, state.rates, d.rates);
      if (draftStatus) draftStatus.textContent = 'Draft restored from this browser.' + (added ? ' ' + added + ' entr' + (added === 1 ? 'y' : 'ies') + ' added from files you uploaded since.' : '');
    }
  } catch (e) {
    if (draftStatus) draftStatus.textContent = 'The saved draft could not be restored. Check your details before making forms.';
  }

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); });
    (kids || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }
  function save(quiet) {                // quiet: the page itself updated a draft line, so leave the status message alone
    try {
      localStorage.setItem(draftKey, JSON.stringify({ rows: state.rows, texts: state.texts, signatories: state.signatories, mc114_text: state.mc114_text, rates: state.rates, gone: gone, sugg: sugg, dauto: dayAuto }));
      if (draftStatus && !quiet) draftStatus.textContent = 'Draft saved in this browser only.';
    } catch (e) {
      if (draftStatus) draftStatus.textContent = 'Draft could not be saved. Keep this page open until you make the forms.';
    }
  }
  var fieldId = 0;
  function field(label, value, onInput, opts) {
    opts = opts || {};
    var input = opts.area ? el('textarea', { rows: opts.rows || 3 }) : el('input', { type: opts.type || 'text' });
    input.id = 'prep-field-' + (++fieldId);
    if (opts.type === 'number') { input.min = '0'; input.step = '0.01'; }
    if (opts.placeholder) input.setAttribute('placeholder', opts.placeholder);
    input.value = value == null ? '' : value;
    input.addEventListener('input', function () { onInput(input.value); save(); if (opts.refresh) refresh(); });
    var wrap = el('div', opts.wide ? { 'class': 'tv-row-wide' } : {}, [el('label', { text: label, 'for': input.id }), input]);
    return wrap;
  }
  function select(label, value, options, onChange) {
    var s = el('select', { id: 'prep-field-' + (++fieldId) });
    options.forEach(function (o) { var op = el('option', { value: o[0], text: o[1] }); if (o[0] === value) op.selected = true; s.appendChild(op); });
    s.addEventListener('change', function () { onChange(s.value); save(); refresh(); });
    return el('div', {}, [el('label', { text: label, 'for': s.id }), s]);
  }

  function check(label, value, onChange) {
    var box = el('input', { type: 'checkbox' });
    box.checked = !!value;
    box.addEventListener('change', function () { onChange(box.checked); save(); refresh(); });
    return el('label', { 'class': 'tv-check' }, [box, document.createTextNode(' ' + label)]);
  }
  function peso(n) { return '\u20b1' + Number(n).toLocaleString('en-PH', { maximumFractionDigits: 2 }); }

  var rowsBox = el('div', { 'class': 'tv-rows' }), totals = el('div', { 'class': 'tv-totals' }), breakBox = el('details', { 'class': 'tv-breakdown' }), liqBox = el('div', { 'class': 'tv-liq' });
  var flagsBox = el('div'), msgBox = el('div', { role: 'status', 'aria-live': 'polite' }), docsList = el('ul', { 'class': 'tv-docs' });

  var uis = [];                        // per row: the lines the server's answer is painted into
  var ownPerDiem = new WeakSet();      // rows whose per diem box the person opened to change the policy amount

  function placePicker(r) {
    var opts = policy.places[r.basis] || [], wrap = el('div', { 'class': 'tv-row-wide' });
    var find = null;
    if (r.basis === 'airport') {
      find = el('input', { type: 'search', placeholder: 'Type a place, e.g. Makati City Hall', 'aria-label': 'Find the place' });
    }
    var sel = el('select', { 'aria-label': 'Place' });
    function fill(q) {
      sel.textContent = '';
      sel.appendChild(el('option', { value: '', text: 'Choose' }));
      opts.forEach(function (o) {
        if (q && o[3].indexOf(q) < 0 && o[0] !== r.place) return;
        var op = el('option', { value: o[0], text: o[1] }); if (o[0] === r.place) op.selected = true; sel.appendChild(op);
      });
    }
    fill('');
    if (find) find.addEventListener('input', function () { fill(find.value.trim().toLowerCase()); });
    sel.addEventListener('change', function () { r.place = sel.value; save(); refresh(); });
    wrap.appendChild(el('label', { text: r.basis === 'airport' ? 'Where you live or work (Annex C area)' : 'Area' }));
    if (find) wrap.appendChild(find);
    wrap.appendChild(sel);
    return wrap;
  }

  // One reading (from the scan above) shown as a suggestion with a button.
  // Nothing is filled in until the person presses it.
  function offer(out, j, r, after) {
    var what = [j.vendor, [j.origin, j.destination].filter(Boolean).join(' to '), j.date].filter(Boolean).join(' \u00b7 ');
    out.appendChild(document.createTextNode('Found ' + peso(j.amount) + (what ? ' (' + what + ')' : '') + '. Check it against the file. ' + (j.note ? j.note + ' ' : '')));
    var use = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Use ' + peso(j.amount) });
    use.addEventListener('click', function () {
      r.allowance = j.amount; r._aa = null;
      if (!r.date && j.date) r.date = j.date;
      if (!r.from && j.origin) r.from = j.origin;
      if (!r.to && j.destination) r.to = j.destination;
      if (r.mode === 'taxi' || r.mode === 'tnvs') r.receipt = 'receipt';
      if (after) after();
      save(); drawRows(); refresh();
    });
    out.appendChild(use);
  }

  // Read the fare off a ticket, boarding pass or receipt. The file goes to the server, the AI reads it, and the answer comes
  // back as a suggestion with a button; nothing is filled in, and nothing is kept, until the person presses it.
  function scanPicker(r) {
    var out = el('div', { 'class': 'tv-hint', role: 'status', 'aria-live': 'polite' });
    var pick = el('input', { type: 'file', accept: 'image/*,application/pdf', 'aria-label': 'Read the fare from a ticket or receipt' });
    pick.addEventListener('change', function () {
      var f = pick.files && pick.files[0];
      if (!f) return;
      out.textContent = 'Reading\u2026';
      fetch(data.scan_url, { method: 'POST', credentials: 'same-origin', body: f })
        .then(function (res) {
          return res.text().then(function (t) {
            var j = null; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
            return j || { ok: false, error: res.status === 403 ? 'The server could not verify the request. Reload the page and try again, or type the amount in.'
              : res.status >= 500 ? 'The server had a problem (code ' + res.status + '). Type the amount in, or try again shortly.'
              : 'Could not read that file (code ' + res.status + '). Type the amount in.' };
          });
        }).then(function (j) {
          pick.value = '';
          out.textContent = '';
          if (!j.ok) { out.textContent = j.error || 'Could not read that file. Type the amount in.'; return; }
          if (!j.readable) { out.textContent = 'Could not find an amount on that file. Type it in.' + (j.note ? ' ' + j.note : ''); return; }
          if (j.currency !== 'PHP') { out.textContent = 'That shows ' + j.amount + ' ' + j.currency + ', not pesos. Type the peso amount you paid.'; return; }
          offer(out, j, r, null);
        }).catch(function () { pick.value = ''; out.textContent = 'No connection to the server. Check your internet, or type the amount in.'; });
    });
    return el('div', { 'class': 'tv-row-wide' }, [el('label', { text: 'Read another ticket or receipt (photo or PDF)' }), pick, out]);
  }

  // A new entry on the same date straight after entry `i`, with the day's per diem left to the first one.
  function rideButton(label, i, over) {
    var b = el('button', { type: 'button', 'class': 'btn ghost small', text: label });
    b.addEventListener('click', function () {
      state.rows.splice(i + 1, 0, Object.assign({}, BLANK, { date: state.rows[i].date }, over));
      save(); drawRows(); refresh();
    });
    return b;
  }

  var dragFrom = -1;
  // Entries are kept in the order the person sets, and the forms are made in that order.
  function moveRow(from, to) {
    if (from === to || from < 0 || to < 0 || from >= state.rows.length || to >= state.rows.length) return;
    state.rows.splice(to, 0, state.rows.splice(from, 1)[0]);
    save(); drawRows(); refresh();
  }

  function drawRows() {
    rowsBox.textContent = '';
    uis = [];
    state.rows.forEach(function (r, i) {
      var routeOpts = [['', 'Other route (needs review)']].concat(data.routes);
      var basisOpts = [['', 'I type the fare myself']].concat(policy.bases.map(function (b) { return [b[0], b[1]]; }));
      var kinds = [['', 'I type the per diem myself']].concat(policy.day_kinds.map(function (k) { return [k[0], k[2]]; }));
      var routeField = select('Route', r.route_type, routeOpts, function (v) { r.route_type = v; });
      var receiptField = select('Receipt', r.receipt, [['none', 'No receipt'], ['receipt', 'I have a receipt']], function (v) { r.receipt = v; });
      var fareField = field(isEstimate ? 'Estimated fare (\u20b1)' : 'Actual fare claimed (\u20b1)', r.allowance, function (v) { r.allowance = v; }, { type: 'number', refresh: true });
      var kids = [
        field('Date', r.date, function (v) { r.date = v; }, { type: 'date', refresh: true }),
        field('From', r.from, function (v) { r.from = v; }),
        field('To', r.to, function (v) { r.to = v; }),
        field('Departure', r.dep, function (v) { r.dep = v; }, { type: 'time' }),
        field('Arrival', r.arr, function (v) { r.arr = v; }, { type: 'time' }),
        select('How you travelled', r.mode, data.modes, function (v) { var plane = (v === 'plane') !== (r.mode === 'plane'); r.mode = v; if (plane) setTimeout(drawRows, 0); }),
        routeField,
        receiptField,
        select('Fare rate', r.basis, basisOpts, function (v) { r.basis = v; r.place = ''; drawRows(); })
      ];
      var inputKind = (policy.bases.filter(function (b) { return b[0] === r.basis; })[0] || [])[2];
      if (inputKind === 'area' || inputKind === 'zone') kids.push(placePicker(r));
      if (inputKind === 'km') kids.push(field('Distance by Google Maps (km)', r.km, function (v) { r.km = v; }, { type: 'number', refresh: true }));
      var capLine = el('div', { 'class': 'tv-row-wide tv-hint' });
      kids.push(capLine);
      kids.push(fareField);
      kids.push(scanPicker(r));
      kids.push(select('Per diem rule', r.day_kind, kinds, function (v) { r.day_kind = v; }));
      if (r.day_kind === 'full' || r.day_kind === 'departure' || ['monitor', 'monitor_late', 'liaison', 'hpdpb'].indexOf(r.day_kind) >= 0) {
        kids.push(check('Meals were provided', r.meals_provided, function (v) { r.meals_provided = v; }));
      }
      if (r.day_kind === 'full') kids.push(check('Lodging was provided', r.lodging_provided, function (v) { r.lodging_provided = v; }));
      var pdField = field('Per diem (\u20b1)', r.per_diem, function (v) { r.per_diem = v; ownPerDiem.add(r); }, { type: 'number', refresh: true });
      kids.push(pdField);
      var pdLine = el('div', { 'class': 'tv-row-wide tv-hint' }), noteLine = el('div', { 'class': 'tv-row-wide tv-flagline' });
      kids.push(pdLine); kids.push(noteLine);
      if (r.src) kids.unshift(el('div', { 'class': 'tv-row-wide tv-hint tv-drafted', text: r.src }));
      var box = el('div', { 'class': 'tv-row' }, kids);
      var rm = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Remove this entry' });
      rm.addEventListener('click', function () {
        if (r.rid && gone.indexOf(r.rid) < 0) gone.push(r.rid);            // a ride the person removed stays removed
        state.rows.splice(i, 1); save(); drawRows(); refresh();
      });
      // One entry is one ride. A day with several (plane, then TNVS to the hotel) is several entries on the same date.
      var sameDay = i > 0 && r.date && state.rows[i - 1].date === r.date;
      if (sameDay) box.insertBefore(el('div', { 'class': 'tv-row-wide tv-hint', text: 'Another ride on the same day. Claim that day\u2019s per diem on one entry only.' }), box.firstChild);
      var more = [rideButton('Add another ride on this day', i, {}), ];
      if (r.mode === 'plane') {
        more.push(rideButton('Add TNVS to the airport', i, { mode: 'tnvs', receipt: 'receipt', to: 'Airport' }));
        more.push(rideButton('Add TNVS from the airport', i, { mode: 'tnvs', receipt: 'receipt', from: 'Airport' }));
      }
      var up = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Move up', 'aria-label': 'Move entry ' + (i + 1) + ' up' });
      var down = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Move down', 'aria-label': 'Move entry ' + (i + 1) + ' down' });
      up.disabled = i === 0; down.disabled = i === state.rows.length - 1;
      up.addEventListener('click', function () { moveRow(i, i - 1); });
      down.addEventListener('click', function () { moveRow(i, i + 1); });
      var grip = el('span', { 'class': 'tv-grip', draggable: 'true', title: 'Drag to move this entry', text: '\u2807 Drag' });
      grip.addEventListener('dragstart', function (e) {
        dragFrom = i;
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', String(i)); e.dataTransfer.setDragImage(box, 20, 20); } catch (x) { /* older browsers */ }
      });
      grip.addEventListener('dragend', function () { dragFrom = -1; rowsBox.querySelectorAll('.tv-drop').forEach(function (n) { n.classList.remove('tv-drop'); }); });
      box.addEventListener('dragover', function (e) { if (dragFrom < 0) return; e.preventDefault(); box.classList.add('tv-drop'); });
      box.addEventListener('dragleave', function () { box.classList.remove('tv-drop'); });
      box.addEventListener('drop', function (e) { if (dragFrom < 0) return; e.preventDefault(); var from = dragFrom; dragFrom = -1; moveRow(from, i); });
      box.insertBefore(el('div', { 'class': 'tv-row-wide tv-row-head' }, [grip, el('strong', { text: 'Entry ' + (i + 1) })]), box.firstChild);
      box.appendChild(el('div', { 'class': 'tv-row-wide tv-row-actions' }, more.concat([up, down, rm])));
      rowsBox.appendChild(box);
      uis.push({ cap: capLine, pd: pdLine, pdField: pdField, notes: noteLine, row: r, fields: { fare: fareField, route: routeField, receipt: receiptField, per_diem: pdField } });
    });
  }

  // Paint what the server worked out: the limit for each ride and the allowance for each day, each with a
  // button that copies it into the amount box. The person can still type something lower.
  function paint() {
    uis.forEach(function (u, i) {
      var c = calc[i] || {};
      u.cap.textContent = '';
      if (c.cap != null) {
        u.cap.appendChild(document.createTextNode('Most allowed for this ride: ' + peso(c.cap) + '. ' + (c.cap_rule || '') + ' '));
        var use = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Use ' + peso(c.cap) });
        use.addEventListener('click', function () { u.row.allowance = c.cap; save(); drawRows(); refresh(); });
        if (isEstimate) { use.textContent = 'Use as estimate'; u.cap.appendChild(use); }
      }
      u.pd.textContent = '';
      // The policy already knows the per diem for a chosen rule, so the amount box stays out of the way
      // until the person asks to change it (or types the per diem themselves, or has a different amount).
      var fromPolicy = c.per_diem != null && u.row.day_kind !== '' && !ownPerDiem.has(u.row) &&
        (Number(u.row.per_diem) || 0) === c.per_diem;
      u.pdField.hidden = fromPolicy;
      if (c.per_diem != null) {
        var parts = c.day || {};
        u.pd.appendChild(document.createTextNode((fromPolicy ? 'Per diem for this day, from the policy rates: ' : 'Allowed for this day: ') + peso(c.per_diem) +
          (parts.lodging || parts.meals || parts.incidentals ? ' (lodging ' + peso(parts.lodging) + ', meals ' + peso(parts.meals) + ', incidentals ' + peso(parts.incidentals) + ')' : '') +
          '. ' + (parts.notes || []).join(' ') + ' '));
        if (fromPolicy) {
          var change = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Change amount' });
          change.addEventListener('click', function () { ownPerDiem.add(u.row); paint(); u.pdField.querySelector('input').focus(); });
          u.pd.appendChild(change);
        } else {
          var useP = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Use ' + peso(c.per_diem) });
          useP.addEventListener('click', function () { u.row.per_diem = c.per_diem; ownPerDiem.delete(u.row); save(); drawRows(); refresh(); });
          u.pd.appendChild(useP);
        }
      }
      u.notes.textContent = (c.warnings || []).join(' ');
    });
  }

  // Fill an amount box from the policy without a click. A box is filled while it is empty or still holds what
  // we put there last time, so a change of rate updates it, and a number the person typed is left alone.
  function autofill(r, field, tag, val) {
    var cur = Number(r[field]) || 0, last = r[tag];
    if (val == null) {
      if (last != null && cur === last) { r[field] = 0; r[tag] = null; return true; }
      return false;
    }
    if (cur === 0 || (last != null && cur === last)) {
      r[tag] = val;
      if (cur !== val) { r[field] = val; return true; }
    }
    return false;
  }

  var timer2 = null, calcSeq = 0;
  function recalc() {
    clearTimeout(timer2);
    timer2 = setTimeout(function () {
      var seq = ++calcSeq;
      fetch(policy.rates_url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows: state.rows, rates: state.rates }) })
        .then(function (r) { return r.json(); }).then(function (j) {
          if (seq !== calcSeq || !j.ok) return;
          calc = j.rows; regionDte = j.dte;
          var changed = false;
          state.rows.forEach(function (r, i) {
            var c = calc[i] || {};
            // A policy ceiling is not evidence of what the claimant actually paid.
            if (isEstimate && autofill(r, 'allowance', '_aa', c.cap == null ? null : c.cap)) changed = true;
            if (autofill(r, 'per_diem', '_ap', c.per_diem == null ? null : c.per_diem)) changed = true;
          });
          if (changed) { save(); drawRows(); }
          paint(); refresh(true);
        }).catch(function () { /* the limits just do not show; the form still works */ });
    }, 250);
  }

  // One choice for the whole trip instead of one per day; each day can still be changed.
  function allDays() {
    var sel = el('select', { 'aria-label': 'Set every day to' });
    sel.appendChild(el('option', { value: '', text: 'Set every day to\u2026' }));
    policy.day_kinds.forEach(function (k) { sel.appendChild(el('option', { value: k[0], text: k[2] })); });
    sel.addEventListener('change', function () {
      if (!sel.value) return;
      state.rows.forEach(function (r) { r.day_kind = sel.value; });
      save(); drawRows(); refresh();
    });
    return el('div', {}, [el('label', { text: 'Per diem rule for the whole trip' }), sel]);
  }

  function ratesPanel() {
    var regionOpts = [['', 'Choose where you are going']].concat(policy.regions.map(function (x) { return [x[0], x[1] + ' \u00b7 up to ' + peso(x[2]) + ' a day']; }));
    return el('div', { 'class': 'tv-card' }, [
      el('h3', { text: 'Policy rates' }),
      el('p', { 'class': 'tv-hint', text: isEstimate ? 'Policy rates help estimate your cash advance. Confirm each estimate before making the forms.' : 'Enter the fare you actually paid. Policy rates show the allowed limits and calculate daily allowances; they do not fill in actual fares.' }),
      select('Where you are going', state.rates.region, regionOpts, function (v) { state.rates.region = v; }),
      check('I receive the \u20b150 daily subsistence allowance through payroll', state.rates.receives_sa, function (v) { state.rates.receives_sa = v; }),
      check('I am a senior citizen, PWD or student (20% lower public fare)', state.rates.discounted, function (v) { state.rates.discounted = v; }),
      allDays()]);
  }

  // Where every peso in the Total comes from: what the person typed, and for each day the policy rule and rate behind
  // the per diem, so a manual computation can be compared line by line.
  function drawBreakdown() {
    var open = breakBox.open, rows = [], total = 0;
    breakBox.textContent = '';
    breakBox.appendChild(el('summary', { text: 'How this total is worked out' }));
    state.rows.forEach(function (r, i) {
      var c = calc[i] || {}, fare = Number(r.allowance) || 0, pd = Number(r.per_diem) || 0;
      if (!fare && !pd) return;
      total += fare + pd;
      var kind = (policy.day_kinds.filter(function (k) { return k[0] === r.day_kind; })[0] || [])[2];
      var title = 'Entry ' + (i + 1) + (r.date ? ' \u00b7 ' + r.date : '') + (r.from || r.to ? ' \u00b7 ' + (r.from || '?') + ' to ' + (r.to || '?') : '');
      var lines = [];
      if (fare) {
        lines.push([isEstimate ? 'Estimated fare' : 'Fare', fare, 'The amount you typed.' + (c.cap != null ? ' The policy allows up to ' + peso(c.cap) + '. ' + (c.cap_rule || '') : '')]);
      }
      if (pd) {
        var why;
        if (c.per_diem == null || !r.day_kind) why = 'The amount you typed. Choose a per diem rule to have the policy work it out.';
        else {
          var d = c.day || {};
          why = (kind || 'Per diem rule') + (regionDte ? ' at ' + peso(regionDte) + ' a day' : '') + ': lodging ' + peso(d.lodging || 0) + ' + meals ' + peso(d.meals || 0) +
            ' + incidentals ' + peso(d.incidentals || 0) + ' = ' + peso(c.per_diem) + '. ' + (d.notes || []).join(' ');
          if (pd !== c.per_diem) why += ' You typed ' + peso(pd) + ' instead.';
        }
        lines.push(['Per diem', pd, why]);
      }
      rows.push([title, lines]);
    });
    if (!rows.length) {
      breakBox.appendChild(el('p', { 'class': 'tv-hint', text: 'Enter a fare or choose a per diem rule on an entry and its working appears here.' }));
    } else {
      rows.forEach(function (x) {
        breakBox.appendChild(el('h4', { text: x[0] }));
        var ul = el('ul');
        x[1].forEach(function (l) { ul.appendChild(el('li', {}, [el('strong', { text: l[0] + ' ' + peso(l[1]) }), el('div', { 'class': 'tv-hint', text: l[2] })])); });
        breakBox.appendChild(ul);
      });
      breakBox.appendChild(el('p', { 'class': 'tv-breakdown-total', text: 'Total ' + peso(total) }));
      breakBox.appendChild(el('p', { 'class': 'tv-hint' }, [document.createTextNode('If your own figure differs, check the rate for where you went, whether meals or lodging were provided, and the \u20b150 subsistence allowance. '),
        el('a', { href: policy.rates_url, target: '_blank', rel: 'noopener', text: 'See every policy rate' })]));
    }
    breakBox.open = open;
  }

  // The figures to enter in FMIS for a liquidation: what was spent, by kind, against the cash advance received.
  function drawLiquidation() {
    var f = liquidationFigures(state.rows, data.advance, modeLabels);
    liqBox.textContent = '';
    liqBox.appendChild(el('h3', { text: 'Liquidation figures' }));
    if (!f.lines.length) {
      liqBox.appendChild(el('p', { 'class': 'tv-hint', text: 'Enter the fares you paid and choose a per diem rule on each entry and the figures appear here.' }));
      return;
    }
    var ul = el('ul');
    f.lines.forEach(function (l) {
      var note = l.count + (l.count === 1 ? ' entry' : ' entries') + (l.fromFiles ? ', ' + l.fromFiles + ' read from your uploaded files' : '');
      ul.appendChild(el('li', {}, [el('strong', { text: l.label + ' ' + peso(l.cents / 100) }), el('div', { 'class': 'tv-hint', text: note })]));
    });
    liqBox.appendChild(ul);
    liqBox.appendChild(el('p', { 'class': 'tv-breakdown-total', text: 'Actual expenses ' + peso(f.totalCents / 100) }));
    if (f.advanceCents == null) {
      liqBox.appendChild(el('p', { 'class': 'tv-hint', text: 'The cash advance amount is not on this filing. Add it on the filing page to see the refund or the amount over.' }));
    } else {
      var d = f.diffCents, msg;
      if (d > 0) msg = 'Cash advance received ' + peso(f.advanceCents / 100) + ' is ' + peso(d / 100) + ' more than you spent, so ' + peso(d / 100) + ' goes back to the office as a refund.';
      else if (d < 0) msg = 'You spent ' + peso(-d / 100) + ' more than the cash advance of ' + peso(f.advanceCents / 100) + '. Ask the Admin Unit how the excess is claimed.';
      else msg = 'Your expenses match the cash advance of ' + peso(f.advanceCents / 100) + ' exactly. Nothing to refund.';
      liqBox.appendChild(el('p', { 'class': d > 0 ? 'tv-flagline' : 'tv-hint', text: msg }));
    }
    liqBox.appendChild(el('p', { 'class': 'tv-hint', text: 'Fares are what you entered or what was read from your uploads, and the per diem is from the policy rate you chose. Check each against its receipt before you enter these in FMIS.' }));
  }

  // Mark the field a warning is about: red border, aria-invalid, and a message tied to it for screen readers.
  function markField(wrap, text) {
    var input = wrap && wrap.querySelector('input, select, textarea');
    if (!input) return null;
    input.setAttribute('aria-invalid', 'true');
    input.classList.add('tv-invalid');
    var note = wrap.querySelector('.tv-field-error');
    if (!note) { note = el('div', { 'class': 'tv-field-error', id: input.id + '-err' }); wrap.appendChild(note); }
    note.textContent = note.textContent ? note.textContent + ' ' + text : text;
    input.setAttribute('aria-describedby', note.id);
    return input;
  }
  function clearMarks() {
    rowsBox.querySelectorAll('.tv-invalid').forEach(function (n) { n.classList.remove('tv-invalid'); n.removeAttribute('aria-invalid'); n.removeAttribute('aria-describedby'); });
    rowsBox.querySelectorAll('.tv-field-error').forEach(function (n) { n.remove(); });
  }

  function refresh(fromServer) {
    var total = 0, kinds = {}, lines = [];       // each line: { text, short (the message on the field), marks: [[row index, field], ...] }
    if (fromServer !== true) recalc();
    state.rows.forEach(function (r, i) {
      total += (Number(r.allowance) || 0) + (Number(r.per_diem) || 0);
      var c = calc[i] || {};
      var res = rideCheck(r.mode, r.route_type, r.allowance, r.receipt, ceil, c.cap == null ? null : c.cap);
      if (res.kind) kinds[res.kind] = (kinds[res.kind] || 0) + 1;
      res.flags.forEach(function (f, k) { lines.push({ text: 'Entry ' + (i + 1) + ': ' + f, short: f, marks: [[i, res.targets[k]]] }); });
      if (c.per_diem != null && (Number(r.per_diem) || 0) > c.per_diem) {
        lines.push({ text: 'Entry ' + (i + 1) + ': Per diem is ' + ((Number(r.per_diem) || 0) - c.per_diem).toFixed(2).replace(/\.00$/, '') + ' above the ' + c.per_diem + ' the policy allows for this day.', short: 'Above the ' + c.per_diem + ' the policy allows for this day.', marks: [[i, 'per_diem']] });
      }
    });
    var perDiemOn = {};
    state.rows.forEach(function (r, i) {
      if (!r.date || !(Number(r.per_diem) > 0)) return;
      if (perDiemOn[r.date] != null) lines.push({ text: 'Entries ' + (perDiemOn[r.date] + 1) + ' and ' + (i + 1) + ' are on the same day and both claim a per diem. A day\u2019s per diem is claimed once.', short: 'Another entry on this day also claims a per diem.', marks: [[perDiemOn[r.date], 'per_diem'], [i, 'per_diem']] });
      else perDiemOn[r.date] = i;
    });
    totals.textContent = 'Total: \u20b1' + total.toLocaleString('en-PH', { maximumFractionDigits: 2 }) +
      (kinds.cenrr ? ' \u00b7 ' + kinds.cenrr + ' ride(s) go on a CENRR' : '') + (kinds.rer ? ' \u00b7 ' + kinds.rer + ' RER form(s)' : '');
    drawBreakdown();
    if (data.kind === 'liquidation') drawLiquidation();
    draftReport();
    flagsBox.textContent = '';
    clearMarks();
    if (lines.length) {
      flagsBox.appendChild(el('p', { 'class': 'tv-flagline bad', text: 'These will be sent to the Admin Unit to verify before you can mark the filing ready:' }));
      var ul = el('ul');
      lines.forEach(function (l) {
        var inputs = [];
        l.marks.forEach(function (m) {
          var u = uis[m[0]], input = u && u.fields[m[1]] && !u.fields[m[1]].hidden ? markField(u.fields[m[1]], l.short) : null;
          if (input) inputs.push(input);
        });
        var li = el('li', { 'class': 'tv-flagline' });
        if (inputs.length) {
          var go = el('button', { type: 'button', 'class': 'tv-flaglink', text: l.text, title: 'Go to the field' });
          go.addEventListener('click', function () { inputs[0].scrollIntoView({ block: 'center' }); inputs[0].focus(); });
          li.appendChild(go);
        } else li.textContent = l.text;
        ul.appendChild(li);
      });
      flagsBox.appendChild(ul);
    }
  }

  function textArea(label, key, hint) { return field(label, state.texts[key], function (v) { state.texts[key] = v; }, { area: true, wide: true, placeholder: hint }); }
  function section(title, kids) { return el('section', { 'class': 'tv-card' }, [el('h2', { text: title })].concat(kids)); }

  var addDay = el('button', { type: 'button', 'class': 'btn ghost', text: 'Add itinerary entry' });
  addDay.addEventListener('click', function () { state.rows.push(Object.assign({}, BLANK)); save(); drawRows(); refresh(); });

  var sortDays = el('button', { type: 'button', 'class': 'btn ghost', text: 'Sort by date' });
  sortDays.addEventListener('click', function () {
    var keyed = state.rows.map(function (r, i) { return { r: r, i: i }; });
    keyed.sort(function (a, b) {                       // earliest first; entries with no date go last; the same day keeps its order
      if (a.r.date === b.r.date) return a.i - b.i;
      if (!a.r.date) return 1;
      if (!b.r.date) return -1;
      return a.r.date < b.r.date ? -1 : 1;
    });
    state.rows = keyed.map(function (k) { return k.r; });
    save(); drawRows(); refresh();
  });

  var T = state.texts, S = state.signatories;
  app.appendChild(ratesPanel());
  app.appendChild(section('Itinerary of travel', [rowsBox, el('div', { 'class': 'tv-row-actions' }, [addDay, sortDays]), el('p', { 'class': 'tv-hint', text: 'To change the order, drag an entry by its handle, use Move up and Move down, or press Sort by date.' }), totals, breakBox].concat(data.kind === 'liquidation' ? [liqBox] : []).concat([flagsBox,
    field('Purpose (completes "To …")', T.purpose, function (v) { T.purpose = v; }, { wide: true }),
    field('Itinerary number (optional)', T.itinerary_no, function (v) { T.itinerary_no = v; })])));
  if (needs('appendix_b')) {
    var explanation = textArea('Explanation (if it did not go as planned)', 'explanation');
    explanation.hidden = T.strictness === 'strict';
    var completed = [select('How the travel went', T.strictness,
      [['strict', 'Strictly as in the itinerary'], ['cut', 'Cut short'], ['extended', 'Extended'], ['other', 'Other']],
      function (v) { T.strictness = v; explanation.hidden = v === 'strict'; }), explanation];
    if (data.kind === 'liquidation' && data.answers.refund) {
      completed = completed.concat([
        field('Refund amount (₱)', T.refund_amount, function (v) { T.refund_amount = v; }, { type: 'number' }),
        field('Refund official receipt no.', T.refund_or_no, function (v) { T.refund_or_no = v; }),
        field('Refund official receipt date', T.refund_or_date, function (v) { T.refund_or_date = v; }, { type: 'date' })]);
    }
    app.appendChild(section('Certificate of travel completed', completed));
  }
  var dayInputs = [], modeLabels = {};
  (data.modes || []).forEach(function (m) { modeLabels[m[0]] = m[1]; });
  if (needs('travel_report')) {
    var dayFields = state.texts.day_by_day.map(function (line, i) {
      var f = field('Day ' + (i + 1) + (data.days && data.days[i] ? ' \u00b7 ' + data.days[i].label : ''), line, function (v) { T.day_by_day[i] = v; }, { area: true, rows: 2, wide: true });
      dayInputs[i] = f.querySelector('textarea');
      return f;
    });
    app.appendChild(section('Post travel report', [textArea('Overview', 'overview'),
      el('p', { 'class': 'tv-hint', text: 'Each day below is written from your itinerary and follows it until you edit that day yourself.' })]
      .concat(dayFields)
      .concat([textArea('Key points', 'key_points', 'The main things you learned or decided. Only you can write this.'),
               textArea('Contributions', 'contributions', 'What you contributed to the activity.'),
               textArea('Support needed', 'support_needed', 'Anything the office needs to provide as a follow-up.'),
               textArea('Recommendations', 'recommendations', 'What you recommend, based on what you saw.'),
               textArea('Conclusion', 'conclusion', 'A short closing statement.')])));
  }
  // Keep each day's line in step with the itinerary, but never overwrite a line the person has written or changed.
  function draftReport() {
    if (!dayInputs.length || !data.days) return;
    var changed = false;
    data.days.forEach(function (d, i) {
      if (!dayInputs[i]) return;
      var cur = T.day_by_day[i] || '', body = describeDay(state.rows, d.iso, data.activity, modeLabels);
      var auto = body ? d.label + ': ' + body.charAt(0).toUpperCase() + body.slice(1) + '.' : d.label + ': ';
      if ((cur === dayAuto[i] || cur.trim() === '' || cur.trim() === d.label + ':') && cur !== auto) {
        T.day_by_day[i] = auto; dayInputs[i].value = auto; dayAuto[i] = auto; changed = true;
      }
    });
    if (changed) save(true);
  }
  if (needs('jo_cert')) {
    app.appendChild(section('Job Order certification', [textArea('Activities you were engaged in', 'activities'), textArea('Obligations under your contract', 'obligations')]));
  }
  if (needs('mc114_justification') || (needs('appendix_b') && data.mc114_format === 'appendix_b')) {
    app.appendChild(section('MC 114 justification', [field('MC 114 justification text', state.mc114_text, function (v) { state.mc114_text = v; }, { area: true, rows: 6, wide: true })]));
  }
  var signerFields = [], signerSummary = [];
  function signer(label, name, title) {
    signerSummary.push(label + ': ' + (S[name] || 'Not yet set'));
    signerFields.push(field(label, S[name], function (v) { S[name] = v; }));
    if (title) signerFields.push(field(label + ' title', S[title], function (v) { S[title] = v; }));
  }
  if (needs('appendix_b')) {
    signer('Head of office', 'head_name', 'head_title');
    signerFields.push(field('Station', S.station, function (v) { S.station = v; }));
  }
  if (needs('appendix_a')) signer('Certifying officer', 'certifier_name', 'certifier_title');
  if (needs('appendix_a') || needs('appendix_b')) signer('Approver', 'approver_name', 'approver_title');
  if (needs('travel_report')) {
    signer('Reviewed by (report)', 'reviewed_by_name', 'reviewed_by_title');
    signer('Approved by (report)', 'approved_by_name', 'approved_by_title');
  }
  if (needs('jo_cert')) signer('JO certifying signatory', 'signatory_name', 'signatory_title');
  // CENRR may become necessary as rides are entered.
  if (!isEstimate) signer('Noted by (CENRR)', 'noted_by_name', 'noted_by_title');
  var signers = el('details', { 'class': 'tv-card' }, [el('summary', { text: 'Review or change signatories' }),
    el('p', { 'class': 'tv-hint', text: signerSummary.join(' · ') })].concat(signerFields));
  if (signerSummary.some(function (s) { return s.indexOf('Not yet set') >= 0; })) signers.open = true;
  app.appendChild(signers);

  var go = el('button', { type: 'button', 'class': 'btn', text: 'Make the forms' });
  if (app.getAttribute('data-has-relay') !== '1') go.disabled = true;
  app.appendChild(el('div', { 'class': 'tv-card' }, [go, el('p', { 'class': 'tv-hint', text: 'Each form is saved as a Google Doc or Sheet in your Drive. You can open it from the list below and edit any part of it. Rides that need a CENRR or an RER get one sheet each.' }), msgBox, docsList,
    el('a', { href: data.filing_url, 'class': 'btn ghost', text: 'Continue to checklist' })]));

  var timer = null;
  function drawDocs(items) {
    docsList.textContent = '';
    items.forEach(function (it) {
      var li = el('li', { 'class': it.state }, [document.createTextNode(it.label + ' ')]);
      if (it.url) li.appendChild(el('a', { href: it.url, target: '_blank', rel: 'noopener', text: 'Open' }));
      if (it.state === 'failed') li.appendChild(document.createTextNode(' ' + (it.error || 'Failed')));
      if (it.state === 'pending') li.appendChild(document.createTextNode(' making…'));
      docsList.appendChild(li);
    });
  }
  function poll() {
    fetch(data.status_url, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.ok) { msgBox.textContent = j.error || 'Could not check progress.'; return; }
      drawDocs(j.items);
      if (j.gen_state === 'running') { timer = setTimeout(poll, 2500); return; }
      go.disabled = app.getAttribute('data-has-relay') !== '1';
      msgBox.textContent = j.gen_state === 'idle' ? '' : j.gen_state === 'done' ? 'Done. Open each form, check it, and sign where it says. Every form is a Google Doc or Sheet that you can open and edit, so change anything that is wrong before you sign. Then go back to the filing page.' : 'Some forms did not finish. Each one says why below. Press the button to try again. If it still fails, tell the Admin Unit and give them this reference: ' + data.ref + '.';
    }).catch(function () { timer = setTimeout(poll, 5000); });
  }
  go.addEventListener('click', function () {
    go.disabled = true; msgBox.textContent = 'Making the forms…';
    // Keep hidden answers in the browser draft, but never put stale refund or
    // deviation details onto a form when they no longer apply to this claim.
    var texts = Object.assign({}, state.texts);
    if (texts.strictness === 'strict') texts.explanation = '';
    if (data.kind !== 'liquidation' || !data.answers.refund) {
      texts.refund_amount = ''; texts.refund_or_no = ''; texts.refund_or_date = '';
    }
    fetch(data.post_url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows: state.rows, rates: state.rates, texts: texts, signatories: state.signatories, mc114_text: state.mc114_text }) })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: 'The server could not make the forms (code ' + r.status + '). Reload the page and try again.' }; }); }).then(function (j) {
        if (!j.ok) { go.disabled = false; msgBox.textContent = j.error || 'That did not work.'; return; }
        if (j.flags) msgBox.textContent = 'Making the forms… ' + j.flags + ' item(s) go to the Admin Unit to verify.';
        poll();
      }).catch(function () { go.disabled = false; msgBox.textContent = 'No connection to the server. Check your internet and try again.'; });
  });

  drawRows(); refresh(); poll();
})(typeof window !== 'undefined' ? window : globalThis);
