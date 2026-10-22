/* Office Connect progressive enhancement — tiny, no dependencies.
   Everything works without JS; this only adds comfort. */

// ── Quick-pick comment chips: shared cap/dim helper ────────────────────────
// Chip containers set data-max-chips (see rating.html / combined_form.html).
// Dims the remaining inactive chips once that many are active. Shared so both
// templates' toggleChip() and the draft-restore re-light logic below agree.
window.refreshChipCap = function (container) {
  if (!container) return;
  container.querySelectorAll('.chip').forEach(function (chip) {
    chip.setAttribute('aria-pressed', chip.classList.contains('active') ? 'true' : 'false');
  });
  var max = parseInt(container.dataset.maxChips || "0", 10);
  if (!max) return;
  var activeCount = container.querySelectorAll(".chip.active").length;
  container.classList.toggle("at-max", activeCount >= max);
};

function surveyFieldLabel(control) {
  var question = control.closest('[data-question]');
  var group = control.closest('[role=radiogroup]');
  var heading = group && document.getElementById(group.getAttribute('aria-labelledby') || '');
  var label = question ? question.dataset.question : (heading ? heading.textContent : (control.labels && control.labels[0] ? control.labels[0].textContent : control.getAttribute('aria-label') || control.name));
  var speaker = control.closest('.spk-section');
  var title = speaker && speaker.querySelector('.spk-title strong');
  return (title ? title.textContent.trim() + ' — ' : '') + label.trim();
}

(function () {
  "use strict";

  /* 1. Loading state: <form data-loading="Saving…"> disables its submit
        button on submit and swaps the label so slow requests answer back. */
  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;          // inline validation blocked the submit
    var f = e.target;
    if (!f.matches("form[data-loading]")) return;
    var btn = f.querySelector("button[type=submit], button:not([type])");
    if (btn) {
      btn.dataset.label = btn.textContent;
      btn.textContent = f.dataset.loading || "Working…";
      btn.classList.add("loading");
      setTimeout(function () { btn.disabled = true; }, 0);
    }
  });

  /* 2. Confirmations: <form data-confirm="message"> or <button data-confirm>. */
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f.matches("form[data-confirm]") && !window.confirm(f.dataset.confirm)) {
      e.preventDefault();
    }
  });

  /* 3. Survey progress bar: a <div class="progress" data-progress-for="FORMID">
        fills as required radio groups in that form get answered. */
  var bars = document.querySelectorAll("[data-progress-for]");
  bars.forEach(function (bar) {
    var form = document.getElementById(bar.dataset.progressFor);
    if (!form) return;
    var fill = bar.querySelector("div");
    var note = document.querySelector("[data-progress-note]");
    function groups() {
      var names = {};
      form.querySelectorAll("input[type=radio][data-rate]").forEach(function (r) { names[r.name] = 1; });
      return Object.keys(names);
    }
    function update() {
      var gs = groups(), done = 0;
      gs.forEach(function (n) {
        if (form.querySelector('input[name="' + n + '"]:checked')) done += 1;
      });
      var pct = gs.length ? Math.round((done / gs.length) * 100) : 0;
      if (fill) fill.style.width = pct + "%";
      if (note) note.textContent = ((window.SURVEY_I18N && window.SURVEY_I18N.progress) || '{done} of {total} answered').replace('{done}',done).replace('{total}',gs.length);
    }
    form.addEventListener("change", update);
    update();
  });

  /* 4. Expand/collapse all: <button data-toggle-details="open|close"> acts on
        details elements inside the nearest [data-details-scope]. */
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-toggle-details]");
    if (!b) return;
    var scope = b.closest("[data-details-scope]") || document;
    scope.querySelectorAll("details.event").forEach(function (d) {
      d.open = b.dataset.toggleDetails === "open";
    });
  });

  /* 5. Close open nav dropdowns when clicking elsewhere. */
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.navgroup[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });

  /* 5a. Mobile menu sheet: close from the backdrop, the ✕ / any [data-mm-close]
        control, or Esc, and hand focus back to ☰. */
  (function () {
    var tg = document.querySelector("details.nav-toggle");
    if (!tg) return;
    var releaseMenu = null;
    function closeMenu() {
      if (!tg.open) return;
      tg.removeAttribute("open");
      var dp = tg.querySelector(".mm-disp");
      if (dp) dp.removeAttribute("open");
      var sm = tg.querySelector("summary");
      if (releaseMenu) { releaseMenu(); releaseMenu = null; }
      else if (sm) sm.focus();
    }
    tg.addEventListener('toggle', function () {
      if (tg.open && window.OfficeA11y) {
        releaseMenu = OfficeA11y.open(tg, { focusRoot: tg.querySelector('.mobile-menu'), allow:[tg.querySelector('.mm-backdrop')],
          initialFocus: '.mm-close', returnFocus: tg.querySelector('summary'), onDismiss: closeMenu });
      } else if (releaseMenu) { releaseMenu(); releaseMenu = null; }
    });
    window.addEventListener('resize', function () {
      if (tg.open && getComputedStyle(tg).display === 'none') closeMenu();
    });
    tg.addEventListener("click", function (e) {
      if (e.target.closest("[data-mm-close]")) closeMenu();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeMenu();
    });
  })();

  /* 5b. Nav dropdowns anchor to their trigger's left edge (.menu { left:0 }),
        which is fine near the left of the bar but runs a wide menu off the
        right edge of the screen for a group sitting further along the row —
        the later items become unreachable with no scrollbar to reveal them.
        Flip to right-anchored only when the left anchor would overflow, so
        groups that already fit are untouched. */
  document.querySelectorAll("details.navgroup").forEach(function (d) {
    d.addEventListener("toggle", function () {
      var menu = d.querySelector(".menu");
      if (!menu) return;
      if (!d.open) { menu.classList.remove("menu-flip"); return; }
      menu.classList.remove("menu-flip");
      if (menu.getBoundingClientRect().right > window.innerWidth) {
        menu.classList.add("menu-flip");
      }
    });
  });

  /* 6. Display settings popover: theme (light/dark/contrast) + text size
        (sm/md/lg). Buttons write <html data-theme>/<html data-textscale> and
        persist to localStorage; the pre-paint script in <head> applies the
        saved choice before first render. */
  function syncSettings() {
    var root = document.documentElement;
    var theme = root.getAttribute("data-theme") || "light";
    var ts = root.getAttribute("data-textscale") || "md";
    var dn = root.getAttribute("data-density") || "cozy";
    var ac = root.getAttribute("data-accent") || "blue";
    document.querySelectorAll("[data-set-theme]").forEach(function (b) {
      var on = b.getAttribute("data-set-theme") === theme;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll("[data-set-accent]").forEach(function (b) {
      var on = b.getAttribute("data-set-accent") === ac;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll("[data-set-text]").forEach(function (b) {
      var on = b.getAttribute("data-set-text") === ts;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll("[data-set-density]").forEach(function (b) {
      var on = b.getAttribute("data-set-density") === dn;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  syncSettings();
  document.addEventListener("click", function (e) {
    var th = e.target.closest("[data-set-theme]");
    if (th) {
      var v = th.getAttribute("data-set-theme");
      document.documentElement.setAttribute("data-theme", v);
      try { localStorage.setItem("theme", v); } catch (_) {}
      syncSettings();
      return;
    }
    var ac = e.target.closest("[data-set-accent]");
    if (ac) {
      var av = ac.getAttribute("data-set-accent");
      document.documentElement.setAttribute("data-accent", av);
      try { localStorage.setItem("accent", av); } catch (_) {}
      syncSettings();
      return;
    }
    var tx = e.target.closest("[data-set-text]");
    if (tx) {
      var s = tx.getAttribute("data-set-text");
      document.documentElement.setAttribute("data-textscale", s);
      try { localStorage.setItem("textscale", s); } catch (_) {}
      syncSettings();
      return;
    }
    var dn = e.target.closest("[data-set-density]");
    if (dn) {
      var dv = dn.getAttribute("data-set-density");
      document.documentElement.setAttribute("data-density", dv);
      try { localStorage.setItem("density", dv); } catch (_) {}
      syncSettings();
    }
  });

  /* 6b. Close the settings popover when clicking outside it. */
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.settings[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });

  /* 6c. Show/hide password: a <button data-pw-toggle> flips the type of the
        password <input> inside the same .pw-wrap. Reduces blind-typing errors on
        phones (and on the 8-char set/reset screens). */
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-pw-toggle]");
    if (!b) return;
    e.preventDefault();
    var wrap = b.closest(".pw-wrap") || b.parentNode;
    var inp = wrap && wrap.querySelector("input");
    if (!inp) return;
    var show = inp.type === "password";
    inp.type = show ? "text" : "password";
    b.setAttribute("aria-pressed", show ? "true" : "false");
    b.setAttribute("aria-label", show ? "Hide password" : "Show password");
    b.textContent = show ? "Hide" : "Show";
  });

  /* 7. Auto-scroll to the first invalid field after a server-side error. */
  var firstErr = document.querySelector(".field.invalid");
  if (firstErr) {
    firstErr.scrollIntoView({ block: "center" });
    var input = firstErr.querySelector("input, select, textarea");
    if (input) input.focus({ preventScroll: true });
  }

  /* 8b. In-page re-tag (Verbatims & dashboard pull-quotes). Posts the sentiment
        change over fetch so the page does NOT reload — the list stays put instead
        of scrolling away and re-sorting under the curator. The card updates in
        place and keeps a "✓ re-tagged" marker so it is clear what is already done.
        Falls back to a normal form submit if JS/fetch is unavailable. */
  var RETAG_OPTS = [["appreciate", "Appreciated"], ["mixed", "Mixed"], ["improve", "To improve"]];
  function retagRender(box, tag) {
    box.dataset.sentiment = tag;
    box.dataset.overridden = "1";
    var lab = (RETAG_OPTS.filter(function (o) { return o[0] === tag; })[0] || [tag, tag])[1];
    var rid = box.dataset.rid, item = box.dataset.item || "", back = box.dataset.back || "";
    var esc = function (s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; };
    var html = '<span class="retag-mark" title="Manually re-tagged">✓ re-tagged as ' + esc(lab) + "</span>";
    RETAG_OPTS.forEach(function (o) {
      if (o[0] === tag) return;
      html += '<form method="post" action="/dashboard/comment-tag">'
        + '<input type="hidden" name="response_id" value="' + esc(rid) + '">'
        + '<input type="hidden" name="item_id" value="' + esc(item) + '">'
        + '<input type="hidden" name="tag" value="' + o[0] + '">'
        + '<input type="hidden" name="back" value="' + esc(back) + '">'
        + '<button type="submit" data-tag="' + o[0] + '" data-label="' + o[1]
        + '" title="Re-tag this comment as “' + o[1] + '”">→ ' + o[1] + "</button></form>";
    });
    box.innerHTML = html;
    box.classList.remove("just-tagged");
    void box.offsetWidth;                       // restart the pulse if re-tagged again
    box.classList.add("just-tagged");
    var card = box.closest(".vb-card");          // recolour the Verbatims sentiment dot
    if (card) {
      var dot = card.querySelector(".vb-dot");
      if (dot) dot.className = "vb-dot " + tag;
    }
  }
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches || !form.matches(".retag form")) return;
    var box = form.closest(".retag[data-retag]");
    if (!box || !window.fetch) return;           // unenhanced control: post normally
    e.preventDefault();
    var btn = form.querySelector("button[type=submit]");
    var tag = btn && btn.dataset.tag;
    if (!tag) return;
    box.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
    fetch("/dashboard/comment-tag", {
      method: "POST",
      headers: { "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(new FormData(form)).toString()
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok) retagRender(box, d.tag);
        else box.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      })
      .catch(function () { form.submit(); });    // network hiccup: classic submit
  });

  /* 8. Sticky-stack offsets. The topnav wraps to a second row for users with
        many nav groups (admins), so its height is NOT a fixed 53px. Publish the
        real height as --topnav-h, and the bottom edge of the whole sticky
        header stack (topnav + optional scopebar) as --stuck-top, so sub-bars
        pin directly below the header instead of hiding underneath it. CSS reads
        these with sensible fallbacks, so it still works before JS runs. */
  var nav = document.querySelector(".topnav");
  if (nav) {
    var root = document.documentElement;
    var publishStick = function () {
      var h = nav.offsetHeight;
      root.style.setProperty("--topnav-h", h + "px");
      var scope = document.querySelector(".scopebar");
      root.style.setProperty("--stuck-top", (h + (scope ? scope.offsetHeight : 0)) + "px");
    };
    publishStick();
    if (window.ResizeObserver) new ResizeObserver(publishStick).observe(nav);
    window.addEventListener("resize", publishStick);
  }

  /* 9. Inline real-time validation for forms with data-validate.
        Uses existing .field.invalid + .field-error CSS from app.css.
        Text/email/tel inputs: validate on blur, re-check on input once touched.
        Selects & checkboxes: validate on change.
        Submit: block + scroll to first error if any field fails. */
  (function () {
    function fieldError(el, msg) {
      var wrap = el.closest('.field');
      if (!wrap) return;
      wrap.classList.add('invalid');
      var err = wrap.querySelector('.field-error');
      if (!err) {
        err = document.createElement('p');
        err.className = 'field-error';
        err.setAttribute('role', 'alert');
        wrap.appendChild(err);
      }
      err.textContent = msg;
    }
    function fieldClear(el) {
      var wrap = el.closest('.field');
      if (!wrap) return;
      wrap.classList.remove('invalid');
      var err = wrap.querySelector('.field-error');
      if (err) err.remove();
    }
    function isValidEmail(v) {
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());
    }
    function isValidPhone(v) {
      // PH mobile: 09XXXXXXXXX (11 digits). Strips spaces/hyphens before check.
      return /^09\d{9}$/.test(v.replace(/[\s\-]/g, ''));
    }
    function validateEl(el) {
      var val = el.value;
      var type = (el.getAttribute('type') || '').toLowerCase();
      if (type === 'checkbox') {
        if (el.required && !el.checked) { fieldError(el, 'Please check this box to continue.'); return false; }
        fieldClear(el); return true;
      }
      if (el.required && !val.trim()) {
        fieldError(el, el.tagName.toLowerCase() === 'select' ? 'Please select an option.' : 'This field is required.');
        return false;
      }
      if (type === 'email' && val && !isValidEmail(val)) {
        fieldError(el, 'Please enter a valid email address.');
        return false;
      }
      if ('phone' in el.dataset && val && !isValidPhone(val)) {
        fieldError(el, 'Enter a valid PH mobile number (09XXXXXXXXX).');
        return false;
      }
      fieldClear(el); return true;
    }

    document.querySelectorAll('form[data-validate]').forEach(function (form) {
      form.querySelectorAll('input[type=text], input[type=email], input[type=tel]').forEach(function (inp) {
        var touched = false;
        inp.addEventListener('blur', function () { touched = true; validateEl(inp); });
        inp.addEventListener('input', function () { if (touched) validateEl(inp); });
      });
      form.querySelectorAll('select').forEach(function (sel) {
        sel.addEventListener('change', function () { validateEl(sel); });
      });
      form.querySelectorAll('input[type=checkbox][required]').forEach(function (cb) {
        cb.addEventListener('change', function () { validateEl(cb); });
      });

      form.addEventListener('submit', function (e) {
        var ok = true, first = null;
        form.querySelectorAll('input[type=text], input[type=email], input[type=tel], select, input[type=checkbox]').forEach(function (el) {
          if (el.disabled) return;
          if (!validateEl(el)) { ok = false; if (!first) first = el; }
        });
        // Required radio groups: check at least one picked per group name
        var groups = {};
        form.querySelectorAll('input[type=radio][required]:not([disabled])').forEach(function (r) {
          if (!groups[r.name]) groups[r.name] = [];
          groups[r.name].push(r);
        });
        Object.keys(groups).forEach(function (name) {
          var radios = groups[name];
          if (!radios.some(function (r) { return r.checked; })) {
            ok = false;
            var wrap = radios[0].closest('.item, .field');
            if (wrap && !first) { first = radios[0]; wrap.style.outline = '2px solid var(--red)'; wrap.style.borderRadius = '8px'; }
          }
        });
        if (!ok) {
          e.preventDefault();
          if (first) {
            var target = first.closest('.field, .item') || first;
            target.scrollIntoView({ block: 'center', behavior: 'smooth' });
          }
        }
      }, true);  // capture: runs before bubble-phase handlers (e.g. double-submit guard)
    });
  })();

})();

// ── Chart hover tooltips + period-over-period delta badges ───────────────────
(function () {
  var tip = null;

  function mkTip() {
    if (tip) return tip;
    tip = document.createElement('div');
    tip.id = 'chart-tip';
    tip.style.cssText = 'position:fixed;display:none;pointer-events:none;z-index:9999;' +
      'background:var(--ink,#1e293b);color:#fff;padding:.38rem .7rem;border-radius:8px;' +
      'font-size:.8rem;font-weight:600;line-height:1.6;white-space:nowrap;' +
      'box-shadow:0 3px 14px rgba(0,0,0,.22);';
    document.body.appendChild(tip);
    return tip;
  }

  function txt(s) { var e = document.createElement('span'); e.textContent = String(s); return e; }

  function initCharts() {
    document.querySelectorAll('.chart svg').forEach(function (svg) {
      var dots = Array.from(svg.querySelectorAll('.dot[data-tip]'));
      if (!dots.length) return;

      dots.sort(function (a, b) {
        return parseFloat(a.getAttribute('cx')) - parseFloat(b.getAttribute('cx'));
      });

      dots.forEach(function (dot, i) {
        if (i === 0) return;
        var prev = parseFloat(dots[i - 1].getAttribute('data-val'));
        var curr = parseFloat(dot.getAttribute('data-val'));
        if (!isNaN(prev) && !isNaN(curr)) {
          dot.setAttribute('data-delta', (curr - prev).toFixed(2));
        }
      });

      // End-of-series delta badge injected after the SVG (skip when no change)
      if (dots.length >= 2) {
        var last = dots[dots.length - 1];
        var d = parseFloat(last.getAttribute('data-delta') || 'NaN');
        if (!isNaN(d) && d !== 0) {
          var isPct = (last.getAttribute('data-val') || '').indexOf('%') !== -1;
          var abs = Math.abs(d);
          var sym = d > 0 ? '▲ +' : (d < 0 ? '▼ −' : '— ');
          var mag = isPct ? Math.round(abs) + '%' : abs.toFixed(1) + ' pts';
          var badge = document.createElement('div');
          badge.className = 'chart-end-delta ' + (d > 0 ? 'up' : d < 0 ? 'down' : 'flat');
          badge.textContent = sym + mag + ' vs prior period';
          svg.insertAdjacentElement('afterend', badge);
        }
      }

      dots.forEach(function (dot) {
        dot.style.cursor = 'crosshair';
        dot.addEventListener('mouseenter', function () {
          var t = mkTip();
          t.innerHTML = '';
          var lbl = txt(dot.getAttribute('data-tip') || '');
          lbl.style.fontWeight = '800';
          var val = txt(' ' + (dot.getAttribute('data-val') || ''));
          t.appendChild(lbl);
          t.appendChild(val);
          var n = dot.getAttribute('data-n');
          if (n) {
            var ne = txt(' (n=' + n + ')');
            ne.style.opacity = '.62'; ne.style.fontWeight = '500';
            t.appendChild(ne);
          }
          var dAttr = dot.getAttribute('data-delta');
          if (dAttr) {
            var dv = parseFloat(dAttr);
            if (!isNaN(dv)) {
              var isPct = (dot.getAttribute('data-val') || '').indexOf('%') !== -1;
              var abs = Math.abs(dv);
              var line = document.createElement('div');
              line.textContent = (dv > 0 ? '▲ +' : (dv < 0 ? '▼ −' : '— ')) +
                (isPct ? Math.round(abs) + '%' : abs.toFixed(1) + ' pts') + ' vs prior';
              line.style.color = dv > 0 ? '#86efac' : (dv < 0 ? '#fca5a5' : '#94a3b8');
              line.style.fontWeight = '500';
              t.appendChild(line);
            }
          }
          t.style.display = 'block';
        });
        dot.addEventListener('mousemove', function (e) {
          if (!tip) return;
          tip.style.left = (e.clientX + 16) + 'px';
          tip.style.top  = (e.clientY - 44) + 'px';
        });
        dot.addEventListener('mouseleave', function () {
          if (tip) tip.style.display = 'none';
        });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCharts);
  } else {
    initCharts();
  }
}());

// ── Survey form: save-and-resume draft ────────────────────────────────────────
// Autosaves survey answers to localStorage on every change, so nothing is lost
// when a phone rings, the tab closes, or the respondent steps away mid-form. On
// reload of the same survey a banner offers to restore. Works for BOTH survey
// forms — the multi-speaker combined form (#combinedform) and the single
// ARTA/event/RP form (#surveyform) — by serialising every named control plus the
// combined form's nameless skip toggles. Format v2.
(function () {
  var DRAFT_TTL = 7 * 24 * 60 * 60 * 1000; // discard drafts older than 7 days
  var T = window.SURVEY_I18N || {};
  // A delayed success must never erase a newer draft from another tab.
  window.clearSurveyDraft = function (key, revision) {
    if (!key || !revision) return;
    try {
      var saved = JSON.parse(localStorage.getItem(key));
      if (saved && saved.revision === revision) localStorage.removeItem(key);
    } catch (_) {}
  };
  var confirmed = document.querySelector('[data-confirmed-draft]');
  if (confirmed) window.clearSurveyDraft(confirmed.dataset.confirmedDraft, confirmed.dataset.draftRevision);
  var recovery = document.querySelector('[data-survey-recovery]');
  if (recovery) {
    try {
      var copy = JSON.parse(localStorage.getItem(recovery.dataset.surveyRecovery));
      if (copy && copy.fields && Number.isFinite(new Date(copy.savedAt).getTime()) && Date.now() - new Date(copy.savedAt).getTime() <= DRAFT_TTL) {
        var details = document.createElement('details'), summary = document.createElement('summary'), text = document.createElement('textarea');
        summary.textContent = T.saved_answers || 'Show saved answers';
        text.readOnly = true; text.rows = 8; text.style.width = '100%'; text.setAttribute('aria-label',summary.textContent);
        text.value = Object.keys(copy.fields).map(function (name) { return (copy.labels && copy.labels[name] || name) + ': ' + copy.fields[name]; }).join('\n');
        details.appendChild(summary); details.appendChild(text); recovery.appendChild(details); recovery.hidden = false;
      }
    } catch (_) {}
  }

  var form = document.getElementById("combinedform") || document.getElementById("surveyform");
  if (!form) return;

  // Stable per-survey key: the combined form's token set (action is always /seq),
  // otherwise the single form's action path (/r/<token>).
  var tokInput = form.querySelector('input[name="tokens"]');
  var keyBase = (tokInput && tokInput.value.trim())
    ? tokInput.value.split(",").map(function (t) { return t.trim(); }).filter(Boolean).sort().join(",")
    : (form.getAttribute("action") || form.id);
  var STORE_KEY = form.dataset.surveyDraftKey || "css_draft_v2_" + keyBase;
  var revisionInput = document.createElement('input');
  revisionInput.type = 'hidden'; revisionInput.name = 'draft_saved_at'; form.appendChild(revisionInput);

  // ── Collect every named control + nameless skip toggles ──
  function collect() {
    var fields = {}, skips = {}, labels = {};
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (el) {
      var name = el.name, type = (el.type || "").toLowerCase();
      if (type === "hidden") return;                       // tokens/seq/att are URL-derived
      labels[name] = surveyFieldLabel(el);
      if (type === "radio") { if (el.checked) fields[name] = el.value; }
      else if (type === "checkbox") { fields[name] = el.checked; }
      else { if (el.value !== "") fields[name] = el.value; }
    });
    // Combined form skip toggles carry no name — key them by their section token.
    form.querySelectorAll(".spk-section .skip-toggle").forEach(function (t) {
      var sec = t.closest(".spk-section");
      if (sec && sec.dataset.token) skips[sec.dataset.token] = t.checked;
    });
    return { v: 2, savedAt: new Date().toISOString(), revision: Date.now() + '-' + Math.random().toString(36).slice(2), fields: fields, skips: skips, labels:labels };
  }

  // ── Autosave on input/change (150 ms debounce) ──
  var saveTimer;
  function saveNow() {
    clearTimeout(saveTimer); saveTimer = null;
    if (!form.isConnected) return;
    var snapshot = collect();
    revisionInput.value = snapshot.revision;
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(snapshot));
      flashSaved();
    } catch (_) {
      var warning = form.querySelector('[data-draft-warning]');
      if (warning) { warning.hidden = false; warning.textContent = T.storage_failed || 'Device draft saving is unavailable. Keep this page open until submission is confirmed.'; }
    }
    return snapshot.revision;
  }
  form.saveSurveyDraft = saveNow;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 150);
  }
  form.addEventListener("input",  scheduleSave);
  form.addEventListener("change", scheduleSave);
  // Chips set the textarea value directly without firing input — catch their click.
  form.addEventListener("click", function (e) {
    if (e.target.closest(".chip")) scheduleSave();
  });

  // Keep the draft until the matching server confirmation, not merely a submit event.
  form.addEventListener('submit', function (event) { if (!event.defaultPrevented) saveNow(); });
  window.addEventListener('pagehide', function () { if (saveTimer) saveNow(); });

  // ── "Draft saved" toast (fades after ~2 s) ──
  var flashEl = null;
  function flashSaved() {
    if (!flashEl) {
      flashEl = document.createElement("div");
      flashEl.id = "draft-flash";
      flashEl.textContent = T.draft_saved || "Draft saved on this device";
      flashEl.setAttribute('role','status');
      document.body.appendChild(flashEl);
    }
    flashEl.classList.remove("draft-flash-on");
    void flashEl.offsetWidth;
    flashEl.classList.add("draft-flash-on");
  }

  // ── Load existing draft ──
  var raw;
  try { raw = localStorage.getItem(STORE_KEY); } catch (_) {}
  if (!raw) return;

  var draft;
  try { draft = JSON.parse(raw); } catch (_) { return; }

  if (!draft || !draft.fields || !draft.savedAt || !Number.isFinite(new Date(draft.savedAt).getTime()) ||
      (Date.now() - new Date(draft.savedAt).getTime()) > DRAFT_TTL) {
    try { localStorage.removeItem(STORE_KEY); } catch (_) {}
    return;
  }

  // ── Resume banner ──

  var banner = document.createElement("div");
  banner.id = "draft-banner";
  banner.innerHTML =
    '<div class="draft-inner">'
    + '<span class="draft-msg">' + (T.resume_prompt || 'An earlier draft is saved on this device. Resume only if this feedback has not already been submitted.') + '</span>'
    + '<div class="draft-acts">'
    + '<button type="button" id="draft-resume" class="btn" style="padding:.5rem 1rem;font-size:.9rem;">' + (T.resume || 'Resume draft') + '</button>'
    + '<button type="button" id="draft-discard" style="background:none;border:none;cursor:pointer;font-size:.9rem;color:var(--soft);text-decoration:underline;padding:.5rem .4rem;">' + (T.fresh || 'Start fresh') + '</button>'
    + '</div></div>';

  // Insert before the first visible element (skip the leading hidden inputs).
  var anchor = Array.from(form.children).find(function (c) {
    return !(c.tagName === "INPUT" && c.type === "hidden");
  });
  form.insertBefore(banner, anchor || null);

  document.getElementById("draft-resume").addEventListener("click", function () {
    restore(draft);
    banner.remove();
  });
  document.getElementById("draft-discard").addEventListener("click", function () {
    try { localStorage.removeItem(STORE_KEY); } catch (_) {}
    banner.remove();
  });

  // ── Restore draft into the live form ──
  function restore(d) {
    Object.keys(d.fields || {}).forEach(function (name) {
      var val = d.fields[name];
      var els = form.querySelectorAll('[name="' + (window.CSS && CSS.escape ? CSS.escape(name) : name) + '"]');
      if (!els.length) return;
      var first = els[0], type = (first.type || "").toLowerCase();
      if (type === 'hidden' || type === 'file') return;
      if (type === "radio") {
        els.forEach(function (r) {
          if (r.value === val) {
            r.checked = true;
            // Re-run the form's own per-radio handlers (note auto-expand, branch
            // banner, progress) so the restored UI matches what the user saw.
            r.dispatchEvent(new Event("change", { bubbles: true }));
          }
        });
      } else if (type === "checkbox") {
        first.checked = !!val;
        first.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        first.value = val;
      }
    });

    // Combined form: restore skip toggles AFTER filling, so the body isn't hidden
    // before its inputs are populated.
    Object.keys(d.skips || {}).forEach(function (tok) {
      var sec = form.querySelector('.spk-section[data-token="' + tok + '"]');
      var toggle = sec && sec.querySelector(".skip-toggle");
      if (toggle && !!d.skips[tok] !== toggle.checked) {
        toggle.checked = !!d.skips[tok];
        toggle.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    // Single form: reveal any hidden note box that holds restored text but wasn't
    // re-opened by a score's change handler (e.g. a note added on a mid score).
    form.querySelectorAll(".note-wrap[hidden]").forEach(function (w) {
      var inp = w.querySelector("input, textarea");
      if (inp && inp.value.trim()) {
        w.removeAttribute("hidden");
        var btn = w.parentNode && w.parentNode.querySelector(".add-note-btn");
        if (btn) btn.setAttribute("aria-expanded", "true");
      }
    });

    // Re-light chips whose word is present in their comments box.
    form.querySelectorAll(".chip[data-word]").forEach(function (chip) {
      var box = chip.closest(".field, .group, [data-conv='comments']");
      var ta  = box && box.querySelector("textarea");
      if (!ta) return;
      var parts = ta.value.split(",").map(function (s) { return s.trim(); });
      if (parts.indexOf(chip.dataset.word) !== -1) chip.classList.add("active");
    });
    // A draft saved before the chip cap existed may have more active chips
    // than the current cap allows — dim the rest to match, same as a live tap.
    form.querySelectorAll(".chips[data-max-chips]").forEach(window.refreshChipCap);
    var cc1 = form.querySelector('input[name=csm_cc1]:checked');
    if (cc1) cc1.dispatchEvent(new Event('change', {bubbles:true}));

    form.dispatchEvent(new Event("change", { bubbles: true })); // refresh progress bar
  }
}());

// ── Offline response capture + sync (PWA Phase 2) ──────────────────────────────
// Submit a survey with no connection and the full form body is saved to an on-device
// IndexedDB queue, then POSTed automatically when connectivity returns. We attach a
// per-submission id; the server logs it (submission_log) so a replay is idempotent —
// which is what makes page-flush and the service worker's Background Sync safe to
// run together. Online submits are left untouched (native POST keeps the rich thanks
// flow: next speaker, certificate, ending message).
(function () {
  if (!("indexedDB" in window)) return;

  var T = window.OFFLINE_I18N || {};
  var surveyText = window.SURVEY_I18N || {};
  var t = {
    saved_h1:  T.saved_h1  || "✓ Saved on your device",
    saved_msg: T.saved_msg || "Saved on this device, not yet confirmed by the server. Answers will be sent when connected if the survey still accepts responses.",
    waiting:   T.waiting   || "waiting to send",
    sent_one:  T.sent_one  || "Saved response sent.",
    sent_many: T.sent_many || "Saved responses sent.",
    failed:    T.failed    || "the server refused this request; the form may be closed or unavailable. Your saved answers remain on this device",
    failed_label: T.failed_label || "Couldn't send",
    discard:   T.discard   || "Discard"
  };

  var DB_NAME = "css_offline", STORE = "queue", DB_VER = 1;
  function openDB() {
    return new Promise(function (resolve, reject) {
      var r = indexedDB.open(DB_NAME, DB_VER);
      r.onupgradeneeded = function () {
        var db = r.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "id" });
      };
      r.onsuccess = function () { resolve(r.result); };
      r.onerror   = function () { reject(r.error); };
    });
  }
  function reqP(r) { return new Promise(function (res, rej) { r.onsuccess = function () { res(r.result); }; r.onerror = function () { rej(r.error); }; }); }
  function withStore(mode, fn) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tr = db.transaction(STORE, mode), out;
        Promise.resolve(fn(tr.objectStore(STORE))).then(function (v) { out = v; });
        tr.oncomplete = function () { resolve(out); };
        tr.onerror = function () { reject(tr.error); };
        tr.onabort = function () { reject(tr.error); };
      });
    });
  }
  function qPut(item) { return withStore("readwrite", function (s) { s.put(item); }); }
  function qDelete(id) { return withStore("readwrite", function (s) { s.delete(id); }); }
  function qAll() { return withStore("readonly", function (s) { return reqP(s.getAll()); }); }

  function uuid() {
    try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (e) {}
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var n = (Math.random() * 16) | 0; return (c === "x" ? n : (n & 0x3) | 0x8).toString(16);
    });
  }
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
  function labelFor() {
    var h = document.querySelector(".pub-card h1, .pub-card h2, h1");
    return (h && h.textContent.trim().slice(0, 60)) || location.pathname;
  }

  // ── Submit interception (capture phase: runs before the loading-state handler) ─
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || (form.id !== "surveyform" && form.id !== "combinedform")) return;
    if (navigator.onLine) return;                       // online → let the native POST proceed
    e.preventDefault();
    if (form.dataset.queueSaving === '1') return;
    form.dataset.queueSaving = '1';
    if (form.saveSurveyDraft) form.saveSurveyDraft();
    var sid = uuid();
    var body = new URLSearchParams(new FormData(form));  // byte-identical to a native submit
    body.set("submission_id", sid);
    var labels = {};
    Array.from(form.elements).forEach(function (control) {
      if (control.name && control.type !== 'hidden') labels[control.name] = surveyFieldLabel(control);
    });
    qPut({ id: sid, action: form.action, body: body.toString(),
           draftKey:form.dataset.surveyDraftKey, draftRevision:body.get('draft_saved_at'), labels:labels,
           label: labelFor(), savedAt: new Date().toISOString(), status: "pending" })
      .then(function () {
        showSavedPanel(form);
        refreshBadge();
        try {                                            // nudge Background Sync (Android/Chrome)
          if ("serviceWorker" in navigator && "SyncManager" in window) {
            navigator.serviceWorker.ready.then(function (reg) {
              if (reg.sync) reg.sync.register("css-flush").catch(function () {});
            });
          }
        } catch (_) {}
      })
      .catch(function () {
        delete form.dataset.queueSaving;
        form.dispatchEvent(new Event('survey-save-failed'));
      });
  }, true);

  function showSavedPanel(form) {
    var div = document.createElement("div");
    div.className = "pub-card offline-saved";
    div.innerHTML = '<h1 style="margin-top:0;color:var(--green);">' + esc(t.saved_h1) + "</h1>" +
                    '<p class="muted">' + esc(t.saved_msg) + "</p>";
    form.replaceWith(div);                               // swap just the form; layout stays intact
    var heading = div.querySelector('h1'); heading.tabIndex = -1; heading.focus();
    window.scrollTo(0, 0);
  }

  // ── Pending / failed badge ────────────────────────────────────────────────────
  var badgeEl = null;
  function badge() {
    if (badgeEl) return badgeEl;
    badgeEl = document.createElement("div");
    badgeEl.className = "offline-badge";
    badgeEl.hidden = true;
    document.body.appendChild(badgeEl);
    return badgeEl;
  }
  function refreshBadge() {
    return qAll().then(function (items) {
      var b = badge();
      var pending = items.filter(function (i) { return i.status !== "failed"; });
      var failed  = items.filter(function (i) { return i.status === "failed"; });
      if (!pending.length && !failed.length) { b.hidden = true; b.innerHTML = ""; return; }
      var html = "";
      if (pending.length) html += '<span class="ob-pending">' + pending.length + " " + esc(t.waiting) + "</span>";
      failed.forEach(function (it) {
        var reason = it.reason === 'partial' ? surveyText.queue_partial : it.reason === 'previous' ? surveyText.queue_previous : t.failed;
        html += '<span class="ob-failed">' + esc(surveyText.needs_review || t.failed_label) + ": " + esc(it.label) + " — " + esc(reason) +
                ' <button type="button" data-discard="' + esc(it.id) + '">' + esc(t.discard) + "</button></span>";
        html += '<details><summary>' + esc(surveyText.saved_answers || 'Show saved answers') + '</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">';
        new URLSearchParams(it.body).forEach(function (value, name) {
          if (['tokens','seq','att','submission_id','draft_saved_at'].indexOf(name) < 0) html += esc((it.labels && it.labels[name] || name) + ': ' + value) + '\n';
        });
        html += '</pre></details>';
      });
      b.innerHTML = html;
      b.hidden = false;
    }).catch(function () {});
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-discard]");
    if (!btn) return;
    qDelete(btn.getAttribute("data-discard")).then(refreshBadge);
  });

  // ── Flush the queue to the server ─────────────────────────────────────────────
  var flushing = false;
  function flush() {
    if (flushing || !navigator.onLine) return Promise.resolve();
    flushing = true;
    var sent = 0;
    return qAll().then(function (items) {
      var pending = items.filter(function (i) { return i.status !== "failed"; });
      return pending.reduce(function (chain, it) {
        return chain.then(function (stop) {
          if (stop) return true;
          return fetch(it.action, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded", "Accept":"application/json" },
            body: it.body
          }).then(function (res) {
            if (res.ok) return res.json().then(function (receipt) {
              if (!receipt || receipt.ok !== true || receipt.submission_id !== it.id) return true;
              var combined = new URL(it.action, location.href).pathname === '/seq';
              if (combined && !receipt.deduped && (!Number.isInteger(receipt.recorded) || receipt.recorded < 0 || !Number.isInteger(receipt.unavailable) || receipt.unavailable < 0)) return true;
              if (receipt.unavailable || receipt.recorded === 0 || (receipt.deduped && combined)) {
                it.status = 'failed'; it.reason = receipt.deduped ? 'previous' : 'partial';
                return qPut(it).then(function () { return false; });
              }
              sent++;
              if (window.clearSurveyDraft) window.clearSurveyDraft(it.draftKey, it.draftRevision);
              return qDelete(it.id).then(function () { return false; });
            });
            if (res.status >= 400 && res.status < 500) {  // permanent (window closed / bad token)
              it.status = "failed"; return qPut(it).then(function () { return false; });
            }
            return true;                                  // 5xx → stop, retry next time
          }).catch(function () { return true; });         // network error → stop
        });
      }, Promise.resolve(false));
    }).then(function () {
      flushing = false;
      refreshBadge();
      if (sent) toast(sent === 1 ? t.sent_one : t.sent_many);
    }).catch(function () { flushing = false; });
  }

  function toast(msg) {
    var el = document.createElement("div");
    el.className = "offline-toast";
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add("show"); });
    setTimeout(function () { el.classList.remove("show"); setTimeout(function () { el.remove(); }, 300); }, 3200);
  }

  window.addEventListener("online", flush);
  if ('serviceWorker' in navigator) navigator.serviceWorker.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'survey-confirmed') {
      if (window.clearSurveyDraft) window.clearSurveyDraft(event.data.key, event.data.revision);
      refreshBadge();
    }
  });
  refreshBadge().then(flush);                            // catch up any queue on every public page load
}());

// ── Shared toast ───────────────────────────────────────────────────────────────
// A single brief confirmation toast, reusing the .offline-toast pill styling.
// Exposed globally so any module can call it (the offline queue keeps its own copy).
window.cssToast = window.cssToast || function (msg) {
  var el = document.createElement("div");
  el.className = "offline-toast";
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(function () { el.classList.add("show"); });
  setTimeout(function () {
    el.classList.remove("show");
    setTimeout(function () { el.remove(); }, 300);
  }, 2600);
};

// ── Saved views + share (UX #9) ────────────────────────────────────────────────
// The URL already carries the full filter state (scope bar + every pill is a query
// param), so a report view IS its URL. This adds two affordances on the scope bar:
//   • "Copy link"  — copy the current URL so it can be shared (deep-link).
//   • "Save view"  — pin the current URL under a name, recalled from "Saved views ▾".
// Saved views live in localStorage, namespaced per page (css_views_<key>) — private
// to this device, no schema. Sharing across people is done via the copied link.
(function () {
  var box = document.querySelector("[data-savedviews]");
  if (!box) return;                                        // only on scope-bar pages

  var CTX  = window.SAVED_VIEW_CTX || {};
  var KEY  = "css_views_" + (CTX.key || location.pathname);
  var CAP  = 20;
  var saveBtn   = box.querySelector("[data-sv-save]");
  var toggleBtn = box.querySelector("[data-sv-toggle]");
  var copyBtn   = box.querySelector("[data-sv-copy]");
  var menu      = box.querySelector("[data-sv-menu]");

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; }
    catch (_) { return []; }
  }
  function store(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list.slice(-CAP))); } catch (_) {}
  }
  function currentUrl() { return location.pathname + location.search; }

  // A readable default name from the active scope + lit filter pills.
  function defaultName() {
    var bits = [];
    if (CTX.scopeLabel) bits.push(CTX.scopeLabel);
    document.querySelectorAll(".seg a.on, .pills a.on").forEach(function (a) {
      var t = (a.textContent || "").trim();
      if (t) bits.push(t);
    });
    return bits.join(" · ") || (document.title || "Saved view").split("—")[0].trim();
  }

  function toast(msg) { (window.cssToast || function () {})(msg); }

  function closeMenu() {
    menu.hidden = true;
    toggleBtn.setAttribute("aria-expanded", "false");
  }

  function renderMenu() {
    var list = load();
    toggleBtn.hidden = list.length === 0;                  // nothing to recall yet
    if (list.length === 0) { closeMenu(); }
    menu.textContent = "";
    list.slice().reverse().forEach(function (v) {
      var row = document.createElement("div");
      row.className = "sv-row";
      var go = document.createElement("a");
      go.className = "sv-go"; go.href = v.url; go.textContent = v.name;
      var del = document.createElement("button");
      del.type = "button"; del.className = "sv-del"; del.textContent = "×";
      del.title = "Remove this saved view";
      del.setAttribute("aria-label", "Remove saved view " + v.name);
      del.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        store(load().filter(function (x) { return x.name !== v.name; }));
        renderMenu();
      });
      row.appendChild(go); row.appendChild(del);
      menu.appendChild(row);
    });
  }

  saveBtn.addEventListener("click", function () {
    var name = window.prompt("Name this view", defaultName());
    if (name == null) return;                              // cancelled
    name = name.trim();
    if (!name) return;
    var list = load().filter(function (x) { return x.name !== name; });  // de-dupe by name
    list.push({ name: name, url: currentUrl() });
    store(list);
    renderMenu();
    toast("View saved");
  });

  copyBtn.addEventListener("click", function () {
    var url = location.href;
    function done() { toast("Link copied"); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, fallback);
    } else { fallback(); }
    function fallback() {
      try {
        var ta = document.createElement("textarea");
        ta.value = url; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); ta.remove();
        done();
      } catch (_) { window.prompt("Copy this link", url); }
    }
  });

  toggleBtn.addEventListener("click", function () {
    var open = menu.hidden;
    menu.hidden = !open;
    if (open) { var first = menu.querySelector("a,button"); if (first) first.focus(); }
    toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
  });

  document.addEventListener("click", function (e) {
    if (!box.contains(e.target)) closeMenu();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !menu.hidden) { closeMenu(); toggleBtn.focus(); }
  });

  renderMenu();
  box.hidden = false;                                       // reveal now JS is live
}());

// ── Locale-proof date fields ──────────────────────────────────────────────────
// A native <input type=date> shows its text in the OS/browser locale (dd/mm vs
// mm/dd) and there is no way to override that from the page — which read as a bug
// to encoders on US-locale desktops. We keep the native control (calendar, min/
// max, keyboard, ISO value the server already expects) but make it invisible and
// overlay a FIXED, unambiguous "22 Jun 2026" display on top. Inputs carrying a
// data-echo attribute also get a spelled-out "Sunday, 22 June 2026" line below.
// If the field is swapped to datetime-local (the "Add specific time" toggle),
// we drop the overlay and reveal the native control as-is.
(function () {
  "use strict";
  var MON   = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  var MONTH = ["January","February","March","April","May","June","July","August",
               "September","October","November","December"];
  var DOW   = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];

  function parseISO(v) {                                    // "2026-06-22" → parts | null
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || "");
    return m ? { y: +m[1], mo: +m[2], d: +m[3] } : null;
  }
  function shortFmt(v) {
    var p = parseISO(v);
    return p ? p.d + " " + MON[p.mo - 1] + " " + p.y : "";                 // 22 Jun 2026
  }
  function longFmt(v) {
    var p = parseISO(v);
    if (!p) return "";
    var dt = new Date(p.y, p.mo - 1, p.d);                 // local — no timezone shift
    return DOW[dt.getDay()] + ", " + p.d + " " + MONTH[p.mo - 1] + " " + p.y;
  }

  function enhance(input) {
    if (input.dataset.dfx) return;                         // upgrade once
    input.dataset.dfx = "1";

    var wrap = document.createElement("span");
    wrap.className = "datefix";
    // Carry the input's own width hints so flex rows (flex:1) keep their layout.
    if (input.style.flex)     { wrap.style.flex = input.style.flex;     input.style.flex = ""; }
    if (input.style.minWidth) { wrap.style.minWidth = input.style.minWidth; input.style.minWidth = ""; }

    var disp = document.createElement("span");
    disp.className = "datefix-disp";
    disp.setAttribute("aria-hidden", "true");              // native input stays the labelled control

    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(disp);
    wrap.appendChild(input);

    var echo = null;
    if (input.hasAttribute("data-echo")) {
      echo = document.createElement("div");
      echo.className = "datefix-echo";
      wrap.parentNode.insertBefore(echo, wrap.nextSibling);
    }

    var placeholder = input.getAttribute("data-placeholder") || "Pick a date";
    // A native date input splits a click into a text zone (focuses only) and a
    // narrow calendar-icon zone (actually opens the picker). Stretched invisible
    // over the display box here, that split no longer lines up with anything the
    // user can see, so a click on most of the box did nothing — reported as
    // "there are times [it's] not clickable" (Spot Feedback #83). Where
    // showPicker() exists we skip the split entirely: the real input stops
    // taking clicks and any click in the box opens the picker directly.
    var canShowPicker = !!input.showPicker;

    function sync() {
      if (input.type !== "date") {                         // swapped to datetime-local → show native
        wrap.classList.add("raw");
        input.style.pointerEvents = "";                     // reveal the real control to clicks
        if (echo) echo.textContent = "";
        return;
      }
      wrap.classList.remove("raw");
      if (canShowPicker) input.style.pointerEvents = "none";
      var s = shortFmt(input.value);
      disp.textContent = s || placeholder;
      disp.classList.toggle("empty", !s);
      if (echo) echo.textContent = longFmt(input.value);
    }

    if (canShowPicker) {
      wrap.addEventListener("click", function () {
        if (wrap.classList.contains("raw")) return;        // native control is visible here already
        input.focus();
        try { input.showPicker(); } catch (_) {}
      });
    }

    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
    // The "Add specific time" toggle flips type=date ↔ datetime-local in place;
    // watch the attribute so the overlay follows.
    if (window.MutationObserver) {
      new MutationObserver(sync).observe(input, { attributes: true, attributeFilter: ["type"] });
    }
    sync();
  }

  document.querySelectorAll("input[type=date]").forEach(enhance);
}());

/* Searchable combobox — progressive enhancement for long <select> lists.
   Opt in with <select data-combobox>. The native select stays the real form
   control (no-JS fallback + the label target); we overlay a button + a popup
   with a type-to-filter search box and a scrollable, width-capped option list.
   Picking an option writes it back to the select and fires `change`, so any
   existing onchange="this.form.submit()" keeps working untouched. */
(function () {
  "use strict";

  var idSeq = 0;

  function enhanceCombobox(select) {
    if (select.dataset.cbx) return;                        // upgrade once
    if (!select.options.length) return;
    select.dataset.cbx = "1";
    var uid = "cbx" + (++idSeq);

    var placeholder = select.getAttribute("data-combobox-placeholder") || "Search…";

    var wrap = document.createElement("div");
    wrap.className = "combobox";

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "combobox-trigger";
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    // The native <select> keeps the <label for=…>; mirror it onto the button.
    var lbl = select.id ? document.querySelector('label[for="' + select.id + '"]') : null;
    if (lbl) btn.setAttribute("aria-label", lbl.textContent.trim());

    var face = document.createElement("span");
    face.className = "combobox-label";

    var caret = document.createElement("span");
    caret.className = "combobox-caret";
    caret.setAttribute("aria-hidden", "true");
    caret.textContent = "▾";

    var panel = document.createElement("div");
    panel.className = "combobox-panel";
    panel.hidden = true;

    var search = document.createElement("input");
    search.type = "text";
    search.className = "combobox-search";
    search.setAttribute("placeholder", placeholder);
    search.setAttribute("aria-label", placeholder);
    search.autocomplete = "off";

    var list = document.createElement("ul");
    list.className = "combobox-list";
    list.id = uid + "-list";
    list.setAttribute("role", "listbox");

    var empty = document.createElement("li");
    empty.className = "combobox-empty";
    empty.textContent = "No matches";
    empty.hidden = true;

    btn.appendChild(face);
    btn.appendChild(caret);
    panel.appendChild(search);
    panel.appendChild(list);
    panel.appendChild(empty);
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(btn);
    wrap.appendChild(panel);
    wrap.appendChild(select);                              // keep in DOM, visually hidden

    // Build one row per option, carrying its index back to the native select.
    var rows = [];
    Array.prototype.forEach.call(select.options, function (opt, i) {
      var li = document.createElement("li");
      li.className = "combobox-opt";
      li.setAttribute("role", "option");
      li.id = uid + "-o" + i;
      li.textContent = opt.textContent;
      li.title = opt.textContent;                          // hover shows full title
      li.dataset.i = i;
      li.dataset.hay = opt.textContent.toLowerCase();
      list.appendChild(li);
      rows.push(li);
    });

    var active = -1;                                       // keyboard-highlighted row

    function syncTrigger() {
      var o = select.options[select.selectedIndex];
      face.textContent = o ? o.textContent : "";
    }

    function visibleRows() { return rows.filter(function (r) { return !r.hidden; }); }

    function setActive(li) {
      rows.forEach(function (r) { r.classList.remove("active"); });
      active = li ? rows.indexOf(li) : -1;
      if (li) {
        li.classList.add("active");
        search.setAttribute("aria-activedescendant", li.id);
        var top = li.offsetTop, bot = top + li.offsetHeight;
        if (top < list.scrollTop) list.scrollTop = top;
        else if (bot > list.scrollTop + list.clientHeight) list.scrollTop = bot - list.clientHeight;
      } else {
        search.removeAttribute("aria-activedescendant");
      }
    }

    function filter() {
      var q = search.value.trim().toLowerCase();
      var any = false;
      rows.forEach(function (r) {
        var hit = !q || r.dataset.hay.indexOf(q) !== -1;
        r.hidden = !hit;
        r.setAttribute("aria-selected", String(+r.dataset.i === select.selectedIndex));
        if (hit) any = true;
      });
      empty.hidden = any;
      // Keep the highlight on something visible.
      var vis = visibleRows();
      if (!vis.length) { setActive(null); return; }
      if (active === -1 || rows[active].hidden) {
        var sel = vis.filter(function (r) { return +r.dataset.i === select.selectedIndex; })[0];
        setActive(sel || vis[0]);
      }
    }

    function open() {
      if (!panel.hidden) return;
      panel.hidden = false;
      btn.setAttribute("aria-expanded", "true");
      wrap.classList.add("open");
      search.value = "";
      filter();
      search.focus();
    }
    function close() {
      if (panel.hidden) return;
      panel.hidden = true;
      btn.setAttribute("aria-expanded", "false");
      wrap.classList.remove("open");
    }
    function choose(li) {
      if (!li) return;
      select.selectedIndex = +li.dataset.i;
      syncTrigger();
      close();
      btn.focus();
      select.dispatchEvent(new Event("change", { bubbles: true }));  // → existing auto-submit
    }

    btn.addEventListener("click", function () { panel.hidden ? open() : close(); });
    search.addEventListener("input", filter);
    list.addEventListener("click", function (e) {
      var li = e.target.closest(".combobox-opt");
      if (li) choose(li);
    });
    list.addEventListener("mousemove", function (e) {
      var li = e.target.closest(".combobox-opt");
      if (li && !li.classList.contains("active")) setActive(li);
    });

    search.addEventListener("keydown", function (e) {
      var vis = visibleRows();
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!vis.length) return;
        var cur = rows[active] && !rows[active].hidden ? vis.indexOf(rows[active]) : -1;
        var next = e.key === "ArrowDown"
          ? Math.min(cur + 1, vis.length - 1)
          : Math.max(cur - 1, 0);
        setActive(vis[next < 0 ? 0 : next]);
      } else if (e.key === "Enter") {
        e.preventDefault();
        choose(rows[active] && !rows[active].hidden ? rows[active] : vis[0]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        close();
        btn.focus();
      }
    });

    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) close();
    });

    syncTrigger();
  }

  document.querySelectorAll("select[data-combobox]").forEach(enhanceCombobox);
}());
