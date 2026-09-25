/* telemetry.js — passive UX-behavior capture (docs/UX_TELEMETRY_HANDOFF_PLAN.md).
 *
 * Ported from jongsky25/ofis-platform's app/components/Telemetry.tsx + lib/telemetry.ts
 * (commit 7a7e369) to a plain script for this server-rendered (Jinja, full page loads,
 * no client router) app. Loaded once from dash_layout.html, signed-in shell only.
 *
 * Batches sanitized events and ships them to POST /telemetry via sendBeacon (fetch
 * keepalive fallback). Best-effort throughout: never throws into the page, never
 * blocks navigation. Everything sensitive is masked HERE, before it leaves the
 * browser — the server re-sanitizes again on ingest (see app.py telemetry_ingest),
 * never trusting the client mask alone.
 */
(function () {
  "use strict";

  var FLUSH_MS = 10000;
  var MAX_QUEUE = 25;
  var RAGE_WINDOW_MS = 800;
  var RAGE_RADIUS_PX = 24;
  var RAGE_MIN = 3;
  var RAGE_COOLDOWN_MS = 1500;
  var MAX_TEXT = 160;
  var MAX_SELECTOR = 1000;
  var MAX_DEPTH = 6;

  // Elements that legitimately do something when clicked — a click on/inside
  // one is never "dead". NOTE: deliberately does NOT include [data-tour] — unlike
  // the OFIS reference (where a similar attribute marks individual controls),
  // this app's data-tour tags whole page REGIONS (.statbar, #stats, .mods, the
  // help menu — see templates/home.html/dash_layout.html), never just a button.
  // Including it here was tried and verified wrong: it silently swallowed dead-
  // click detection across most of the UI, since nearly every click has SOME
  // data-tour ancestor. componentOf() below still uses data-tour, correctly,
  // for its unrelated job — naming which region a click happened in.
  // [tabindex] excludes tabindex="-1" specifically — dash_layout.html's shared
  // <main id="maincontent" tabindex="-1"> skip-link target wraps EVERY page's
  // content, so a bare [tabindex] match verified-wrong the same way [data-tour]
  // did above: it silently swallowed dead-click detection app-wide (tabindex=-1
  // means "focusable via script/skip-link", never "clicking this does something"
  // — unlike tabindex="0"+, which does mean a custom interactive widget).
  var INTERACTIVE = 'a,button,input,select,textarea,label,summary,option,' +
    '[role="button"],[role="link"],[role="tab"],[role="menuitem"],[role="switch"],' +
    '[role="checkbox"],[onclick],[tabindex]:not([tabindex="-1"]),[contenteditable="true"],' +
    // a companion's surrounding area taps the companion (static/js/avatars.js)
    '[data-pet-area]';

  // Clicks that are never evidence of a broken control, so they record neither
  // a dead nor a rage click: drawing on a <canvas> (the /me signature pad, the
  // photo cropper — every stroke is a "click" on a non-interactive element, and
  // #sigCanvas topped the friction board for exactly that reason), plus anything
  // a template opts out with data-ux-ignore.
  var NON_ACTIONABLE = "canvas, [data-ux-ignore]";

  // A click whose target IS the page background (not something inside it) —
  // clicking empty space to deselect, dismiss or refocus. These arrived as
  // "html > body" / "#maincontent" dead clicks carrying the whole page's text.
  function isBackground(el) {
    return el === document.documentElement || el === document.body ||
      el.id === "maincontent" || el.tagName === "MAIN";
  }

  // The mouseup that ends a drag-to-select fires a click on whatever text was
  // under the pointer — reading/copying, not expecting an action.
  function endsTextSelection() {
    try {
      var sel = window.getSelection && window.getSelection();
      return !!(sel && !sel.isCollapsed && String(sel).trim());
    } catch (e) { return false; }
  }

  // Our own Spot Feedback picker overlay (static/js/feedback.js) — never measure
  // clicks on/inside it as friction against itself.
  var OWN_UI = "#sfBtn, .sf-backdrop, .sf-hl, .sf-toast";

  // ── sanitizers (mirror ui_telemetry.py; re-sanitized server-side too) ──────

  function sanitizeText(s, max) {
    max = max || MAX_TEXT;
    if (!s) return null;
    var clean = String(s).replace(/\s+/g, " ").trim();
    if (!clean) return null;
    clean = clean.replace(/\d{3,}/g, "###").trim();
    if (!clean) return null;
    return clean.length > max ? clean.slice(0, max) + "…" : clean;
  }

  function sanitizeSelector(s) {
    if (!s) return null;
    var clean = String(s).trim();
    if (!clean) return null;
    return clean.length > MAX_SELECTOR ? clean.slice(0, MAX_SELECTOR) : clean;
  }

  var DATE_RE = /^\d{4}-\d{2}(-\d{2})?$/;
  var HEX_TOKEN_RE = /^[0-9a-f]{6,}$/i;
  var NUMERIC_ID_RE = /^\d+$/;

  // Best-effort route mask: numeric id / hex token (the /r/<token>, /e/<token>
  // link shapes) / date segment -> a placeholder, same curly-brace convention
  // as monitoring.bucket_path. Query string and hash are dropped. Idempotent —
  // see ui_telemetry.mask_route for why that matters.
  function maskRoute(path) {
    if (!path) return "/";
    var p = String(path);
    var cut = p.search(/[?#]/);
    if (cut >= 0) p = p.slice(0, cut);
    p = p.replace(/^https?:\/\/[^/]+/i, "");
    if (p.charAt(0) !== "/") p = "/" + p;
    var masked = p.split("/").map(function (seg) {
      if (!seg) return seg;
      if (DATE_RE.test(seg)) return "{date}";
      if (HEX_TOKEN_RE.test(seg)) return "{token}";
      if (NUMERIC_ID_RE.test(seg)) return "{id}";
      return seg;
    }).join("/");
    return masked.length > 1 ? masked.replace(/\/$/, "") : masked;
  }

  // ── element context (mirror lib/dom-path.ts) ───────────────────────────────

  function cssEscape(s) {
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) { return "\\" + c; });
  }

  // Robust-ish CSS path up from `el`, preferring stable anchors (id, data-tour
  // — this app has no data-testid convention) and capped at MAX_DEPTH.
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    var parts = [];
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && depth < MAX_DEPTH) {
      if (node.id) { parts.unshift("#" + cssEscape(node.id)); break; }
      var tour = node.getAttribute && node.getAttribute("data-tour");
      if (tour) { parts.unshift('[data-tour="' + cssEscape(tour) + '"]'); break; }
      var part = node.tagName.toLowerCase();
      var parent = node.parentElement;
      if (parent) {
        var same = [];
        for (var i = 0; i < parent.children.length; i++) {
          if (parent.children[i].tagName === node.tagName) same.push(parent.children[i]);
        }
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      node = parent;
      depth++;
    }
    return parts.join(" > ");
  }

  // Nearest data-tour above `el` — the source anchor an opportunity maps back
  // to code with (this app's equivalent of OFIS's data-testid).
  function componentOf(el) {
    var node = el;
    while (node && node !== document.body) {
      var id = node.getAttribute && node.getAttribute("data-tour");
      if (id) return id.slice(0, 120);
      node = node.parentElement;
    }
    return null;
  }

  function elementText(el) {
    var label = (el.getAttribute && el.getAttribute("aria-label")) ||
      el.innerText || el.textContent || el.placeholder || "";
    return sanitizeText(label);
  }

  function isOwnUi(el) {
    return !!(el && el.closest && el.closest(OWN_UI));
  }

  // ── session (sessionStorage, not a JS var — this app does full page loads,
  // not client-side navigation, so a plain variable would fragment every
  // pageview into its own "session") ─────────────────────────────────────────

  function newSessionId() {
    try {
      if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    } catch (e) { /* fall through */ }
    return "s-" + Date.now() + "-" + Math.floor(Math.random() * 1e9);
  }

  function getSessionId() {
    try {
      var existing = sessionStorage.getItem("csiTelemetrySession");
      if (existing) return existing;
      var id = newSessionId();
      sessionStorage.setItem("csiTelemetrySession", id);
      return id;
    } catch (e) {
      return newSessionId();
    }
  }

  var sessionId = getSessionId();
  var queue = [];
  var recentClicks = [];
  var lastRageAt = 0;

  // ── queue + flush ───────────────────────────────────────────────────────────

  function flush() {
    if (queue.length === 0) return;
    var batch = queue;
    queue = [];
    try {
      var blob = new Blob([JSON.stringify({ events: batch })], { type: "application/json" });
      var ok = navigator.sendBeacon && navigator.sendBeacon("/telemetry", blob);
      if (!ok) {
        fetch("/telemetry", { method: "POST", body: blob, keepalive: true }).catch(function () {});
      }
    } catch (e) {
      // Telemetry is best-effort — never surface an error to the user.
    }
  }

  function enqueue(ev) {
    queue.push(ev);
    if (queue.length >= MAX_QUEUE) flush();
  }

  function record(eventType, opts) {
    opts = opts || {};
    var el = opts.el || null;
    enqueue({
      event_type: eventType,
      route: maskRoute(location.pathname),
      component: el ? componentOf(el) : null,
      element_selector: el ? sanitizeSelector(cssPath(el)) : null,
      element_text: el ? elementText(el) : null,
      meta: opts.meta || null,
      session_id: sessionId,
    });
  }

  setInterval(flush, FLUSH_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);

  // ── pageview — one per full page load; meta.from is the referring route
  // (same-origin only) since this app has no client-side router to track a
  // previous-route ref across navigations ────────────────────────────────────

  (function () {
    var from = null;
    if (document.referrer) {
      try {
        var refUrl = new URL(document.referrer);
        if (refUrl.origin === location.origin) from = maskRoute(refUrl.pathname);
      } catch (e) { /* malformed/opaque referrer — ignore */ }
    }
    // Viewport class only (phone / tablet / desktop) — nothing finer, no
    // user-agent, no screen size.
    var w = window.innerWidth || document.documentElement.clientWidth || 0;
    var vp = w < 640 ? "phone" : (w < 1024 ? "tablet" : "desktop");
    var meta = { vp: vp };
    if (from) meta.from = from;
    record("pageview", { meta: meta });
  })();

  // ── page_timing — how long this page took, from the browser's own
  // navigation timing, once it has finished loading ─────────────────────────

  window.addEventListener("load", function () {
    // loadEventEnd is only filled in AFTER the load handlers return.
    setTimeout(function () {
      try {
        var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
        if (!nav || !nav.loadEventEnd) return;
        record("page_timing", { meta: {
          ttfb_ms: Math.round(nav.responseStart),
          dom_ms: Math.round(nav.domContentLoadedEventEnd),
          load_ms: Math.round(nav.loadEventEnd),
        } });
      } catch (e) { /* timing is best-effort */ }
    }, 0);
  });

  // ── form_error — this page came back showing an error message (the app's
  // flash(err=…) banner): a submitted task that didn't go through. Only the
  // fact and the referring screen are recorded, never the message text. ──────

  (function () {
    function check() {
      if (!document.querySelector(".flash.err")) return;
      var from = null;
      try {
        var ref = document.referrer && new URL(document.referrer);
        if (ref && ref.origin === location.origin) from = maskRoute(ref.pathname);
      } catch (e) { /* ignore */ }
      record("form_error", { meta: from ? { from: from } : null });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check);
    else check();
  })();

  // ── dead clicks + rage clicks ────────────────────────────────────────────

  document.addEventListener("click", function (e) {
    var target = e.target;
    if (!target || target.nodeType !== 1 || isOwnUi(target)) return;
    if (isBackground(target) || (target.closest && target.closest(NON_ACTIONABLE)) ||
        endsTextSelection()) return;
    var interactive = !!(target.closest && target.closest(INTERACTIVE));

    var now = Date.now();
    recentClicks = recentClicks.filter(function (c) { return now - c.t < RAGE_WINDOW_MS; });
    recentClicks.push({ x: e.clientX, y: e.clientY, t: now });
    var near = recentClicks.filter(function (c) {
      return Math.abs(c.x - e.clientX) <= RAGE_RADIUS_PX && Math.abs(c.y - e.clientY) <= RAGE_RADIUS_PX;
    });
    if (near.length >= RAGE_MIN && now - lastRageAt > RAGE_COOLDOWN_MS) {
      lastRageAt = now;
      recentClicks = [];
      // Rapid taps on a REAL control (feeding the companion, stepping a time
      // chip) are usually play or impatience, not a dead affordance — flag
      // them so the digest weighs them like a dead click instead of ×3.
      record("rage_click", { el: target, meta: interactive ? { interactive: true } : null });
      return;
    }

    if (!interactive) record("dead_click", { el: target });
  }, true);

  // ── empty-search signal (dispatched on window as a "csi:search-empty"
  // CustomEvent by search.js, the /search fallback page, the encode/people
  // list filters and the help topic filter whenever a query returns nothing)
  // + client errors ────────────────────────────────────────────────────────

  // Every completed search, with how many results it found — so the handoff
  // can give an empty-search RATE, not just a count. No term: the empty ones
  // already carry theirs (csi:search-empty below).
  window.addEventListener("csi:search", function (e) {
    var hits = e.detail && e.detail.hits;
    record("search", { meta: { hits: typeof hits === "number" ? Math.max(0, Math.round(hits)) : 0 } });
  });
  window.addEventListener("csi:search-empty", function (e) {
    var term = e.detail && e.detail.term;
    record("search_empty", { meta: { term: sanitizeText(term, 80) } });
  });
  // Where an error happened: the script (same-origin → its masked path;
  // anything else → "external:<host>", never a third-party URL), line, column
  // and the top few stack frames as "fn /path:line:col". Without these every
  // error arrived as a bare "Error" nobody could act on. The server re-validates
  // each piece (ui_telemetry.clean_error_*).
  function scriptSource(url) {
    if (!url) return null;
    try {
      var u = new URL(url, location.href);
      if (u.origin === location.origin) return maskRoute(u.pathname);
      return u.host ? "external:" + u.host : null;
    } catch (err) { return null; }
  }

  var FRAME_URL_RE = /(https?:\/\/[^\s()]+?):(\d+):(\d+)\)?\s*$/;
  function topFrames(stack) {
    if (!stack) return null;
    var out = [];
    var lines = String(stack).split("\n");
    for (var i = 0; i < lines.length && out.length < 3; i++) {
      var line = lines[i].trim();
      var m = FRAME_URL_RE.exec(line);
      if (!m) continue;
      var src = scriptSource(m[1]);
      if (!src) continue;
      // V8: "at fn (url:l:c)" / "at url:l:c"; Firefox/Safari: "fn@url:l:c".
      var fn = (/^at\s+([^\s(]+)\s+\(/.exec(line) || /^([^@\s]+)@/.exec(line) || [])[1] || "?";
      fn = fn.replace(/[^A-Za-z0-9_$.<>\[\] -]/g, "").slice(0, 80) || "?";
      out.push(fn + " " + src + ":" + m[2] + ":" + m[3]);
    }
    return out.length ? out : null;
  }

  function errorMeta(name, message, source, line, col, stack) {
    var meta = { name: name, message: sanitizeText(message, 80) };
    var src = scriptSource(source);
    if (src) meta.source = src;
    if (line) meta.line = line;
    if (col) meta.col = col;
    var frames = topFrames(stack);
    if (frames) meta.frames = frames;
    return meta;
  }

  window.addEventListener("error", function (e) {
    // A failed <script>/<link>/<img> load fires "error" on the element, not the
    // window, and doesn't bubble — only a capture listener sees it. Only
    // scripts and stylesheets matter here: a missing one breaks the page.
    var t = e.target;
    if (t && t !== window && t.tagName) {
      var tag = t.tagName.toLowerCase();
      if (tag === "script" || (tag === "link" && /stylesheet/i.test(t.rel || ""))) {
        record("client_error", { meta: errorMeta("ResourceError", tag + " failed to load",
                                                 t.src || t.href, 0, 0, null) });
      }
      return;
    }
    record("client_error", { meta: errorMeta((e.error && e.error.name) || "Error", e.message,
                                             e.filename, e.lineno, e.colno,
                                             e.error && e.error.stack) });
  }, true);
  window.addEventListener("unhandledrejection", function (e) {
    var reason = e.reason;
    var name = (reason && reason.name) || "UnhandledRejection";
    var reasonMessage = reason && typeof reason.message === "string" ? reason.message : String(reason || "");
    record("client_error", { meta: errorMeta(name, reasonMessage, null, 0, 0,
                                             reason && reason.stack) });
  });

  // ── form abandonment — a form edited but never submitted when the page is
  // left. Only the form element and a touched-field COUNT are recorded, never
  // field names or values. Search/filter forms opt out ([data-search],
  // [role="search"], [data-telemetry-ignore]) so routine filtering doesn't
  // drown the signal; the Spot Feedback overlay is excluded like everywhere
  // else. Emitted on pagehide only (a tab switch is not abandonment), then
  // flushed explicitly — the queue's own pagehide flush (registered above)
  // has already run by the time this handler fires ────────────────────────────

  var IGNORED_FORMS = '[data-search],[role="search"],[data-telemetry-ignore]';
  var dirtyForms = typeof Map !== "undefined" ? new Map() : null;

  function formOf(target) {
    if (!target || !target.closest || isOwnUi(target)) return null;
    var form = target.closest("form");
    if (!form || (form.matches && form.matches(IGNORED_FORMS))) return null;
    return form;
  }

  function markDirty(e) {
    if (!dirtyForms) return;
    var form = formOf(e.target);
    if (!form) return;
    var fields = dirtyForms.get(form);
    if (!fields) { fields = new Set(); dirtyForms.set(form, fields); }
    fields.add(e.target);
  }

  if (dirtyForms) {
    document.addEventListener("input", markDirty, true);
    document.addEventListener("change", markDirty, true);
    document.addEventListener("submit", function (e) {
      var form = e.target;
      if (form) dirtyForms.delete(form);
      // form_submit — the other half of form_abandon, so a screen's abandon
      // RATE can be read. Same opt-outs (search/filter forms, our own UI).
      var f = formOf(form);
      if (f) record("form_submit", { el: f });
    }, true);
    window.addEventListener("pagehide", function () {
      if (dirtyForms.size === 0) return;
      dirtyForms.forEach(function (fields, form) {
        record("form_abandon", { el: form, meta: { fields: fields.size } });
      });
      dirtyForms.clear();
      flush();
    });
  }
})();
