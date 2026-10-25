/* Guided page tours — coach-marks driven by window.PAGE_TOUR (steps for the
   current page) + window.PAGE_KEY. Single source is tours.py on the server.

   - Auto-shows ONCE per page per device (localStorage "css_tour_<key>"), unless
     the user has opted out of all tours ("css_tour_optout"), another modal is
     open, or there are no steps whose target exists on this page.
   - Replayable: the nav "?" button ([data-tour-replay]) or ?tour=1 force-starts.
   - Spotlights each target (dim everything else via a big box-shadow), shows a
     card with Back / Next / Skip, traps focus, Esc skips. No dependencies. */
(function () {
  "use strict";
  var steps = (window.PAGE_TOUR || []).filter(function (s) { return s && s.target; });
  var pageKey = window.PAGE_KEY || "";

  // ---- per-device seen / opt-out flags (mirrors the snapshot popup pattern) ----
  function lsGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
  var SEEN_KEY = "css_tour_" + pageKey;
  var OPTOUT_KEY = "css_tour_optout";

  // ---- a tour must not land on top of another modal (snapshot popup, palette) ----
  function modalOpen() {
    var snap = document.getElementById("snapshot-bd");
    if (snap && !snap.hasAttribute("hidden")) return true;
    var cmdk = document.getElementById("cmdk");
    if (cmdk && !cmdk.hasAttribute("hidden")) return true;
    return false;
  }

  var backdrop, spot, card, idx = 0, live = null, lastFocus = null, releaseFocus = null;

  function visible(sel) {
    var el = document.querySelector(sel);
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return (r.width > 0 && r.height > 0) ? el : null;  // skip hidden/role-absent
  }

  function build() {
    backdrop = document.createElement("div");
    backdrop.className = "tour-backdrop";
    backdrop.addEventListener("click", skip);   // click-off = skip

    spot = document.createElement("div");
    spot.className = "tour-spot";

    card = document.createElement("div");
    card.className = "tour-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-labelledby", "tour-title");
    card.innerHTML =
      '<div class="tour-step" aria-hidden="true"></div>' +
      '<h2 id="tour-title" class="tour-h"></h2>' +
      '<p class="tour-body"></p>' +
      '<div class="tour-nav">' +
        '<button type="button" class="tour-skip">Skip</button>' +
        '<span class="tour-spacer"></span>' +
        '<button type="button" class="tour-back btn ghost">Back</button>' +
        '<button type="button" class="tour-next btn">Next</button>' +
      '</div>';
    card.querySelector(".tour-skip").addEventListener("click", skip);
    card.querySelector(".tour-back").addEventListener("click", function () { go(idx - 1); });
    card.querySelector(".tour-next").addEventListener("click", function () { go(idx + 1); });

    document.body.appendChild(backdrop);
    document.body.appendChild(spot);
    document.body.appendChild(card);
    if (window.OfficeA11y) releaseFocus = OfficeA11y.open(card, {allow:[backdrop,spot], onDismiss:skip, returnFocus:lastFocus});
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("keydown", onKey, true);
  }

  function teardown(markSeen) {
    if (markSeen) lsSet(SEEN_KEY, "1");
    window.removeEventListener("resize", place);
    window.removeEventListener("scroll", place, true);
    document.removeEventListener("keydown", onKey, true);
    [backdrop, spot, card].forEach(function (n) { if (n && n.parentNode) n.parentNode.removeChild(n); });
    backdrop = spot = card = live = null;
    if (releaseFocus) { releaseFocus(); releaseFocus = null; }
    else if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (_) {} }
  }

  function skip() { teardown(true); }

  function go(n) {
    if (n < 0) return;
    if (n >= live.length) { teardown(true); return; }   // finished
    idx = n;
    var step = live[idx];
    card.querySelector(".tour-step").textContent = (idx + 1) + " of " + live.length;
    card.querySelector(".tour-h").textContent = step.title || "";
    card.querySelector(".tour-body").textContent = step.body || "";
    card.querySelector(".tour-back").style.visibility = idx === 0 ? "hidden" : "visible";
    card.querySelector(".tour-next").textContent = idx === live.length - 1 ? "Done" : "Next";
    // Instant (not smooth) scroll so the target's rect is final synchronously —
    // a smooth scroll races place() against the still-moving viewport.
    step._el.scrollIntoView({ block: "center", inline: "nearest" });
    place();                                   // position against the settled rect
    requestAnimationFrame(place);              // re-measure once the card has laid out
    card.querySelector(".tour-next").focus();
  }

  function place() {
    if (!live || !card) return;
    var el = live[idx]._el;
    var r = el.getBoundingClientRect();
    var pad = 6;
    spot.style.top = (r.top - pad) + "px";
    spot.style.left = (r.left - pad) + "px";
    spot.style.width = (r.width + pad * 2) + "px";
    spot.style.height = (r.height + pad * 2) + "px";

    var vw = document.documentElement.clientWidth;
    var vh = document.documentElement.clientHeight;
    var cw = card.offsetWidth, ch = card.offsetHeight, gap = 12;
    var top = r.bottom + gap;                       // prefer below the target
    if (top + ch > vh - gap) top = r.top - ch - gap; // else above
    if (top < gap) top = Math.max(gap, (vh - ch) / 2);
    var left = Math.min(Math.max(gap, r.left), vw - cw - gap);
    card.style.top = top + "px";
    card.style.left = left + "px";
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); skip(); return; }
    if (e.key !== "Tab") return;
    // simple focus trap inside the card
    var f = card.querySelectorAll("button:not([style*='hidden'])");
    f = Array.prototype.filter.call(f, function (b) { return b.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function start() {
    if (live) return;                               // already running
    var resolved = [];
    steps.forEach(function (s) {
      var el = visible(s.target);
      if (el) resolved.push({ title: s.title, body: s.body, _el: el });
    });
    if (!resolved.length) return;                   // nothing to show for this role
    live = resolved;
    lastFocus = document.activeElement;
    build();
    go(0);
  }

  // ---- wiring -------------------------------------------------------------
  // Replay affordance (nav "?" button) always works, even after opt-out / seen.
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-tour-replay]");
    if (t) { e.preventDefault(); start(); }
  });

  var forced = /[?&]tour=1(&|$)/.test(window.location.search);
  if (!steps.length) return;
  if (forced) { start(); return; }
  if (lsGet(OPTOUT_KEY)) return;
  if (lsGet(SEEN_KEY)) return;
  if (modalOpen()) return;          // defer to a later visit; don't stack on a modal
  // small delay so the page (and any deferred enhancements) settle first
  setTimeout(function () {
    // Recheck after the delay: a search may have opened since initialization.
    var focused = document.activeElement;
    if (modalOpen() || (focused && focused.closest('form[data-search]'))) return;
    start();
  }, 600);
})();
