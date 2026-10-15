/* Travel filing: prepare the forms. Everything typed here stays in this page (and an optional draft in
   this browser); the server builds the documents from it and keeps none of it. */
(function (root) {
  'use strict';

  // Same rules as travel_rules.ride_check, so the page can warn before anything is sent. `cap` is the
  // policy limit for the rate chosen on the row (travel_rates.row_cap, worked out by the server).
  function rideCheck(mode, routeType, fare, receipt, ceil, cap) {
    fare = Number(fare) || 0;
    var flags = [];
    if (fare <= 0 || ['tnvs', 'taxi', 'public_noreceipt'].indexOf(mode) < 0) return { kind: null, flags: flags };
    var policy = cap != null;
    var known = policy || ceil.routes.indexOf(routeType) >= 0;
    function over(limit) { flags.push('Fare is ' + (fare - limit).toFixed(2).replace(/\.00$/, '') + ' above the ' + limit + ' ceiling.'); }
    if (!known) flags.push('The route is not on the approved list.');
    if (policy && fare > cap) over(cap);
    if ((mode === 'tnvs' || mode === 'taxi') && receipt === 'receipt') {
      var flat = ceil.flat[mode] || 0;
      if (!policy && flat && fare > flat) over(flat);
      return { kind: 'receipt', flags: flags };
    }
    if (fare <= (ceil.flat.cenrr || 300)) return { kind: 'cenrr', flags: flags };
    if (!policy) {
      var rcap = known ? (ceil.rer[routeType] || 0) : 0;
      if (known && rcap && fare > rcap) over(rcap);
    }
    if (fare > 1000) flags.push('No receipt for a fare of ' + fare + '.');
    return { kind: 'rer', flags: flags };
  }

  function ceilings(list) {
    var c = { flat: {}, rer: {}, routes: [] };
    list.forEach(function (x) {
      if (x[0] === 'rer') { c.rer[x[1]] = x[2]; c.routes.push(x[1]); } else if (x[1] === '*') c.flat[x[0]] = x[2];
    });
    return c;
  }

  root.TravelPrepare = { rideCheck: rideCheck, ceilings: ceilings };
  if (typeof document === 'undefined') return;

  var app = document.getElementById('prep-app'), raw = document.getElementById('prep-data');
  if (!app || !raw) return;
  var data = JSON.parse(raw.textContent), ceil = ceilings(data.ceilings), state = data, policy = data.policy;
  var BLANK = { date: '', from: '', to: '', dep: '', arr: '', mode: 'none', route_type: '', receipt: 'none', allowance: 0, per_diem: 0,
                basis: '', place: '', km: 0, day_kind: '', lodging_provided: false, meals_provided: false };
  var calc = [];                       // what the server says the policy allows, one entry per row
  var draftKey = 'travel-draft-' + data.ref;
  try {
    var d = JSON.parse(localStorage.getItem(draftKey) || 'null');
    if (d && d.rows) {
      state.rows = d.rows.map(function (x) { return Object.assign({}, BLANK, x); });
      state.texts = d.texts; state.signatories = d.signatories; state.mc114_text = d.mc114_text;
      if (d.rates) state.rates = Object.assign({}, state.rates, d.rates);
    }
  } catch (e) { /* no storage: fine */ }

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); });
    (kids || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }
  function save() { try { localStorage.setItem(draftKey, JSON.stringify({ rows: state.rows, texts: state.texts, signatories: state.signatories, mc114_text: state.mc114_text, rates: state.rates })); } catch (e) { /* ignore */ } }
  function field(label, value, onInput, opts) {
    opts = opts || {};
    var input = opts.area ? el('textarea', { rows: opts.rows || 3 }) : el('input', { type: opts.type || 'text' });
    input.value = value == null ? '' : value;
    input.addEventListener('input', function () { onInput(input.value); save(); if (opts.refresh) refresh(); });
    var wrap = el('div', opts.wide ? { 'class': 'tv-row-wide' } : {}, [el('label', { text: label }), input]);
    return wrap;
  }
  function select(label, value, options, onChange) {
    var s = el('select');
    options.forEach(function (o) { var op = el('option', { value: o[0], text: o[1] }); if (o[0] === value) op.selected = true; s.appendChild(op); });
    s.addEventListener('change', function () { onChange(s.value); save(); refresh(); });
    return el('div', {}, [el('label', { text: label }), s]);
  }

  function check(label, value, onChange) {
    var box = el('input', { type: 'checkbox' });
    box.checked = !!value;
    box.addEventListener('change', function () { onChange(box.checked); save(); refresh(); });
    return el('label', { 'class': 'tv-check' }, [box, document.createTextNode(' ' + label)]);
  }
  function peso(n) { return '\u20b1' + Number(n).toLocaleString('en-PH', { maximumFractionDigits: 2 }); }

  var rowsBox = el('div', { 'class': 'tv-rows' }), totals = el('div', { 'class': 'tv-totals' });
  var flagsBox = el('div'), msgBox = el('div', { role: 'status', 'aria-live': 'polite' }), docsList = el('ul', { 'class': 'tv-docs' });

  var uis = [];                        // per row: the lines the server's answer is painted into

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

  function drawRows() {
    rowsBox.textContent = '';
    uis = [];
    state.rows.forEach(function (r, i) {
      var routeOpts = [['', 'Other route (needs review)']].concat(data.routes);
      var basisOpts = [['', 'I type the fare myself']].concat(policy.bases.map(function (b) { return [b[0], b[1]]; }));
      var kinds = [['', 'I type the per diem myself']].concat(policy.day_kinds.map(function (k) { return [k[0], k[2]]; }));
      var kids = [
        field('Date', r.date, function (v) { r.date = v; }, { type: 'date', refresh: true }),
        field('From', r.from, function (v) { r.from = v; }),
        field('To', r.to, function (v) { r.to = v; }),
        field('Departure', r.dep, function (v) { r.dep = v; }, { type: 'time' }),
        field('Arrival', r.arr, function (v) { r.arr = v; }, { type: 'time' }),
        select('How you travelled', r.mode, data.modes, function (v) { r.mode = v; }),
        select('Route', r.route_type, routeOpts, function (v) { r.route_type = v; }),
        select('Receipt', r.receipt, [['none', 'No receipt'], ['receipt', 'I have a receipt']], function (v) { r.receipt = v; }),
        select('Fare rate', r.basis, basisOpts, function (v) { r.basis = v; r.place = ''; drawRows(); })
      ];
      var inputKind = (policy.bases.filter(function (b) { return b[0] === r.basis; })[0] || [])[2];
      if (inputKind === 'area' || inputKind === 'zone') kids.push(placePicker(r));
      if (inputKind === 'km') kids.push(field('Distance by Google Maps (km)', r.km, function (v) { r.km = v; }, { type: 'number', refresh: true }));
      var capLine = el('div', { 'class': 'tv-row-wide tv-hint' });
      kids.push(capLine);
      kids.push(field('Fare / allowance (\u20b1)', r.allowance, function (v) { r.allowance = v; }, { type: 'number', refresh: true }));
      kids.push(select('Per diem rule', r.day_kind, kinds, function (v) { r.day_kind = v; }));
      if (r.day_kind === 'full' || r.day_kind === 'departure' || ['monitor', 'monitor_late', 'liaison', 'hpdpb'].indexOf(r.day_kind) >= 0) {
        kids.push(check('Meals were provided', r.meals_provided, function (v) { r.meals_provided = v; }));
      }
      if (r.day_kind === 'full') kids.push(check('Lodging was provided', r.lodging_provided, function (v) { r.lodging_provided = v; }));
      kids.push(field('Per diem (\u20b1)', r.per_diem, function (v) { r.per_diem = v; }, { type: 'number', refresh: true }));
      var pdLine = el('div', { 'class': 'tv-row-wide tv-hint' }), noteLine = el('div', { 'class': 'tv-row-wide tv-flagline' });
      kids.push(pdLine); kids.push(noteLine);
      var box = el('div', { 'class': 'tv-row' }, kids);
      var rm = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Remove this day' });
      rm.addEventListener('click', function () { state.rows.splice(i, 1); save(); drawRows(); refresh(); });
      box.appendChild(el('div', { 'class': 'tv-row-wide' }, [rm]));
      rowsBox.appendChild(box);
      uis.push({ cap: capLine, pd: pdLine, notes: noteLine, row: r });
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
        u.cap.appendChild(use);
      }
      u.pd.textContent = '';
      if (c.per_diem != null) {
        var parts = c.day || {};
        u.pd.appendChild(document.createTextNode('Allowed for this day: ' + peso(c.per_diem) +
          (parts.lodging || parts.meals || parts.incidentals ? ' (lodging ' + peso(parts.lodging) + ', meals ' + peso(parts.meals) + ', incidentals ' + peso(parts.incidentals) + ')' : '') +
          '. ' + (parts.notes || []).join(' ') + ' '));
        var useP = el('button', { type: 'button', 'class': 'btn ghost small', text: 'Use ' + peso(c.per_diem) });
        useP.addEventListener('click', function () { u.row.per_diem = c.per_diem; save(); drawRows(); refresh(); });
        u.pd.appendChild(useP);
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
          calc = j.rows;
          var changed = false;
          state.rows.forEach(function (r, i) {
            var c = calc[i] || {};
            if (autofill(r, 'allowance', '_aa', c.cap == null ? null : c.cap)) changed = true;
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
      el('p', { 'class': 'tv-hint', text: 'Choose the destination and how the days were spent, and the amounts fill in by themselves from the policy (DO 2019-0225 and 2019-0225-A). Change any amount to what you actually spent. See the Policy rates tab for every rate.' }),
      select('Where you are going', state.rates.region, regionOpts, function (v) { state.rates.region = v; }),
      check('I receive the \u20b150 daily subsistence allowance through payroll', state.rates.receives_sa, function (v) { state.rates.receives_sa = v; }),
      check('I am a senior citizen, PWD or student (20% lower public fare)', state.rates.discounted, function (v) { state.rates.discounted = v; }),
      allDays()]);
  }

  function refresh(fromServer) {
    var total = 0, kinds = {}, lines = [];
    if (fromServer !== true) recalc();
    state.rows.forEach(function (r, i) {
      total += (Number(r.allowance) || 0) + (Number(r.per_diem) || 0);
      var c = calc[i] || {};
      var res = rideCheck(r.mode, r.route_type, r.allowance, r.receipt, ceil, c.cap == null ? null : c.cap);
      if (res.kind) kinds[res.kind] = (kinds[res.kind] || 0) + 1;
      res.flags.forEach(function (f) { lines.push('Day ' + (i + 1) + ': ' + f); });
      if (c.per_diem != null && (Number(r.per_diem) || 0) > c.per_diem) {
        lines.push('Day ' + (i + 1) + ': Per diem is ' + ((Number(r.per_diem) || 0) - c.per_diem).toFixed(2).replace(/\.00$/, '') + ' above the ' + c.per_diem + ' the policy allows for this day.');
      }
    });
    totals.textContent = 'Total: ₱' + total.toLocaleString('en-PH', { maximumFractionDigits: 2 }) +
      (kinds.cenrr ? ' · ' + kinds.cenrr + ' ride(s) go on a CENRR' : '') + (kinds.rer ? ' · ' + kinds.rer + ' RER form(s)' : '');
    flagsBox.textContent = '';
    if (lines.length) {
      flagsBox.appendChild(el('p', { 'class': 'tv-flagline bad', text: 'These will be sent to the Admin Unit to verify before you can mark the filing ready:' }));
      var ul = el('ul'); lines.forEach(function (l) { ul.appendChild(el('li', { 'class': 'tv-flagline', text: l })); }); flagsBox.appendChild(ul);
    }
  }

  function textArea(label, key) { return field(label, state.texts[key], function (v) { state.texts[key] = v; }, { area: true, wide: true }); }
  function section(title, kids) { return el('section', { 'class': 'tv-card' }, [el('h2', { text: title })].concat(kids)); }

  var addDay = el('button', { type: 'button', 'class': 'btn ghost', text: 'Add a day' });
  addDay.addEventListener('click', function () { state.rows.push(Object.assign({}, BLANK)); save(); drawRows(); refresh(); });

  var T = state.texts, S = state.signatories;
  app.appendChild(ratesPanel());
  app.appendChild(section('Itinerary of travel', [rowsBox, addDay, totals, flagsBox,
    field('Purpose (completes "To …")', T.purpose, function (v) { T.purpose = v; }, { wide: true }),
    field('Itinerary number (optional)', T.itinerary_no, function (v) { T.itinerary_no = v; })]));
  app.appendChild(section('Certificate of travel completed', [
    select('How the travel went', T.strictness, [['strict', 'Strictly as in the itinerary'], ['cut', 'Cut short'], ['extended', 'Extended'], ['other', 'Other']], function (v) { T.strictness = v; }),
    textArea('Explanation (if it did not go as planned)', 'explanation'),
    field('Refund amount (if any)', T.refund_amount, function (v) { T.refund_amount = v; }),
    field('Refund official receipt no.', T.refund_or_no, function (v) { T.refund_or_no = v; }),
    field('Refund official receipt date', T.refund_or_date, function (v) { T.refund_or_date = v; })]));
  app.appendChild(section('Post travel report', [textArea('Overview', 'overview')]
    .concat(state.texts.day_by_day.map(function (line, i) { return field('Day ' + (i + 1), line, function (v) { T.day_by_day[i] = v; }, { area: true, rows: 2, wide: true }); }))
    .concat([textArea('Key points', 'key_points'), textArea('Contributions', 'contributions'), textArea('Support needed', 'support_needed'), textArea('Recommendations', 'recommendations'), textArea('Conclusion', 'conclusion')])));
  app.appendChild(section('Job Order certification and MC 114 justification', [
    textArea('Activities you were engaged in', 'activities'), textArea('Obligations under your contract', 'obligations'),
    field('MC 114 justification text', state.mc114_text, function (v) { state.mc114_text = v; }, { area: true, rows: 6, wide: true })]));
  app.appendChild(section('Who signs', [
    field('Head of office', S.head_name, function (v) { S.head_name = v; }), field('Title', S.head_title, function (v) { S.head_title = v; }),
    field('Station', S.station, function (v) { S.station = v; }),
    field('Certifying officer', S.certifier_name, function (v) { S.certifier_name = v; }), field('Title', S.certifier_title, function (v) { S.certifier_title = v; }),
    field('Approver', S.approver_name, function (v) { S.approver_name = v; }), field('Title', S.approver_title, function (v) { S.approver_title = v; }),
    field('Reviewed by (report)', S.reviewed_by_name, function (v) { S.reviewed_by_name = v; }), field('Title', S.reviewed_by_title, function (v) { S.reviewed_by_title = v; }),
    field('Approved by (report)', S.approved_by_name, function (v) { S.approved_by_name = v; }), field('Title', S.approved_by_title, function (v) { S.approved_by_title = v; })]));

  var go = el('button', { type: 'button', 'class': 'btn', text: 'Make the forms' });
  if (app.getAttribute('data-has-relay') !== '1') go.disabled = true;
  app.appendChild(el('div', { 'class': 'tv-card' }, [go, msgBox, docsList]));

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
      go.disabled = false;
      msgBox.textContent = j.gen_state === 'done' ? 'Done. Open each form, check it, and sign where it says. Then go back to the filing page.' : 'Some forms did not finish. Press the button to try again.';
    }).catch(function () { timer = setTimeout(poll, 5000); });
  }
  go.addEventListener('click', function () {
    go.disabled = true; msgBox.textContent = 'Making the forms…';
    fetch(data.post_url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows: state.rows, rates: state.rates, texts: state.texts, signatories: state.signatories, mc114_text: state.mc114_text }) })
      .then(function (r) { return r.json(); }).then(function (j) {
        if (!j.ok) { go.disabled = false; msgBox.textContent = j.error || 'That did not work.'; return; }
        if (j.flags) msgBox.textContent = 'Making the forms… ' + j.flags + ' item(s) go to the Admin Unit to verify.';
        poll();
      }).catch(function () { go.disabled = false; msgBox.textContent = 'Could not reach the server. Try again.'; });
  });

  drawRows(); refresh(); poll();
})(typeof window !== 'undefined' ? window : globalThis);
